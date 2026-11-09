import os
from itertools import islice, product
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QListWidget, QMessageBox, QMenu,
    QLabel, QLineEdit, QPlainTextEdit, QRadioButton, QButtonGroup,
    QCheckBox, QComboBox, QFileDialog, QSystemTrayIcon
)
from utils.file_io import save_text
from core.config import ConfigManager
from datetime import datetime

try:
    from pypinyin import lazy_pinyin, pinyin, Style
    _HAS_PINYIN = True
except ImportError:
    _HAS_PINYIN = False


def _to_pinyin(text: str) -> str:
    """中文转全拼（无空格无音调），如 '字符替换' → 'zifutihuan'"""
    return ''.join(lazy_pinyin(text, style=Style.NORMAL))


def _to_pinyin_initials(text: str) -> str:
    """中文转拼音首字母，如 '字符替换' → 'zfth'"""
    return ''.join(lazy_pinyin(text, style=Style.FIRST_LETTER))


def _to_pinyin_variants(text: str, style, limit: int = 4096) -> set[str]:
    """Return pinyin spellings for all polyphonic readings of ``text``.

    The limit prevents an unusually long name with many polyphonic characters
    from making the search path expensive.
    """
    readings = pinyin(text, style=style, heteronym=True)
    variants = {
        ''.join(parts)
        for parts in islice(product(*(item or [""] for item in readings)), limit)
    }
    return variants


def _match_plugin(name: str, query: str) -> bool:
    """Match by Chinese name, full pinyin, initials, and polyphonic pinyin."""
    if query in name:
        return True
    if _HAS_PINYIN:
        if any(query in variant for variant in _to_pinyin_variants(name, Style.NORMAL)):
            return True
        if len(query) >= 2 and any(
            query in variant
            for variant in _to_pinyin_variants(name, Style.FIRST_LETTER)
        ):
            return True
    return False


def _plugin_sort_key(name: str) -> tuple[str, str]:
    """Return a stable dictionary-order key for plugin names.

    Chinese names are ordered by their pinyin spelling when pypinyin is
    available; the original name remains a tie-breaker.
    """
    if _HAS_PINYIN:
        variants = _to_pinyin_variants(name, Style.NORMAL)
        if variants:
            return min(variants), name
    return name.lower(), name


def _plugin_match_sort_key(name: str, query: str) -> tuple[int, int, str, str]:
    """Rank matches by precision, then sort them alphabetically.

    A query at the beginning of the plugin name wins over a query occurring in
    the middle; the same rule is then applied to full pinyin and initials.
    """
    name_lower = name.lower()
    alpha_key = _plugin_sort_key(name)

    if name_lower.startswith(query):
        return (0, 0, *alpha_key)
    direct_index = name_lower.find(query)
    if direct_index >= 0:
        return (1, direct_index, *alpha_key)

    if _HAS_PINYIN:
        full_variants = _to_pinyin_variants(name, Style.NORMAL)
        if any(value.startswith(query) for value in full_variants):
            return (2, 0, *alpha_key)
        full_positions = [value.find(query) for value in full_variants]
        full_positions = [position for position in full_positions if position >= 0]
        if full_positions:
            return (3, min(full_positions), *alpha_key)

        initial_variants = _to_pinyin_variants(name, Style.FIRST_LETTER)
        if any(value.startswith(query) for value in initial_variants):
            return (4, 0, *alpha_key)
        initial_positions = [value.find(query) for value in initial_variants]
        initial_positions = [position for position in initial_positions if position >= 0]
        if initial_positions:
            return (5, min(initial_positions), *alpha_key)

    return (6, 0, *alpha_key)


class MainWindow(QWidget):
    def __init__(self, dispatcher, config_manager=None):
        super().__init__()

        self.dispatcher = dispatcher
        self.config = config_manager or ConfigManager()

        self.setWindowTitle("StreamKnife V1.6 by 帅成马")

        # ---- 系统托盘 ----
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(QIcon("assets/app.ico"))
        self.tray.setToolTip("StreamKnife")

        tray_menu = QMenu()
        tray_menu.addAction("显示窗口", self._restore_from_tray)
        tray_menu.addSeparator()
        tray_menu.addAction("退出", self._quit_from_tray)
        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        # ===== 参数框 =====
        self.param_box = QVBoxLayout()
        self.param_widget = QWidget()
        self.param_widget.setLayout(self.param_box)

        # ===== 输入输出 =====
        self.input_box = QTextEdit()
        self.output_box = QTextEdit()

        # ===== 分类 + 插件 =====
        self.category_list = QListWidget()
        self.plugin_list = QListWidget()

        # ===== 搜索框 =====
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜索插件...")

        # ===== 按钮 =====
        self.run_btn = QPushButton("执行")
        self.save_btn = QPushButton("快速保存")
        self.save_as_btn = QPushButton("另存为...")
        self.import_btn = QPushButton("导入文件")
        self.copy_btn = QPushButton("一键复制")


        # ===== 布局 =====
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.category_list)
        top_layout.addWidget(self.plugin_list)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("搜索"))
        layout.addWidget(self.search_box)
        layout.addLayout(top_layout)
        layout.addWidget(QLabel("参数配置"))
        layout.addWidget(self.param_widget)

        input_header = QHBoxLayout()
        self.input_label = QLabel("输入")
        input_header.addWidget(self.input_label)
        input_header.addStretch()
        input_header.addWidget(self.import_btn)
        layout.addLayout(input_header)
        layout.addWidget(self.input_box)
        layout.addWidget(self.run_btn)

        output_header = QHBoxLayout()
        output_header.addWidget(QLabel("输出"))
        output_header.addStretch()
        output_header.addWidget(self.copy_btn)
        layout.addLayout(output_header)
        layout.addWidget(self.output_box)

        self.status_label = QLabel("右键可编辑配置 / 重置关闭行为")
        self.status_label.setStyleSheet("color: gray;")
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.status_label.setContextMenuPolicy(Qt.CustomContextMenu)
        self.status_label.customContextMenuRequested.connect(self._on_status_context_menu)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.save_as_btn)
        layout.addLayout(btn_layout)
        layout.addWidget(self.status_label)


        self.setLayout(layout)

        # ===== 绑定 =====
        self.run_btn.clicked.connect(self.run)
        self.save_btn.clicked.connect(self.save)
        self.save_as_btn.clicked.connect(self.save_as)
        self.import_btn.clicked.connect(self.import_file)
        self.copy_btn.clicked.connect(self.copy_result)
        self.search_box.textChanged.connect(self.filter_plugins)

    # 注入数据
    def set_functions(self, functions):
        self.functions = functions
        self.func_map = {}

        self.category_list.clear()
        self.plugin_list.clear()

        categories = set()

        for key, meta in functions.items():
            categories.add(meta["category"])

        for c in sorted(categories):
            self.category_list.addItem(c)

        self.category_list.itemClicked.connect(self.load_plugins)

        self.all_plugins = functions

    # 加载某分类插件
    def load_plugins(self, item):
        category = item.text()

        self.plugin_list.clear()
        self.func_map = {}

        # 恢复输入框显示
        self.input_label.setVisible(True)
        self.input_box.setVisible(True)

        for key, meta in self.all_plugins.items():
            if meta["category"] == category:
                self._add_plugin(key, meta)

    # 添加插件
    def _add_plugin(self, key, meta):
        self.func_map[meta["name"]] = key

        item = self.plugin_list.addItem(meta["name"])
        self.plugin_list.item(self.plugin_list.count() - 1).setToolTip(meta["desc"])

        # 点击插件时生成参数UI
        self.plugin_list.itemClicked.connect(self.render_params)

    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)

            if item.widget():
                item.widget().deleteLater()

            elif item.layout():
                self.clear_layout(item.layout())

    def render_params(self, item):
        name = item.text()
        key = self.func_map[name]
        meta = self.all_plugins[key]

        self.clear_layout(self.param_box)
        self.param_values = {}
        self.param_containers = {}

        for p in meta.get("meta", {}).get("params", []):
            container = QWidget()
            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            self.param_box.addWidget(container)
            self.param_containers[p["name"]] = container

            label = QLabel(p["label"])
            container_layout.addWidget(label)

            # ===== radio =====
            if p["type"] == "radio":
                group = QButtonGroup(self)
                hbox = QHBoxLayout()

                for opt in p["options"]:
                    rb = QRadioButton(opt)
                    hbox.addWidget(rb)
                    group.addButton(rb)

                    if opt == p.get("default", p["options"][0]):
                        rb.setChecked(True)

                container_layout.addLayout(hbox)
                self.param_values[p["name"]] = group
                group.buttonClicked.connect(self.update_param_visibility)

            # ===== input =====
            elif p["type"] == "input":
                if p.get("multiline"):
                    line = QPlainTextEdit()
                    line.setPlaceholderText(p.get("placeholder", ""))
                    line.setFixedHeight(60)
                else:
                    line = QLineEdit()
                    line.setPlaceholderText(p.get("placeholder", ""))
                container_layout.addWidget(line)
                self.param_values[p["name"]] = line

            # ===== select =====
            elif p["type"] == "select":
                combo = QComboBox()
                options = p.get("options", [])

                if callable(options):
                    try:
                        options = options()
                    except Exception:
                        options = []

                for option in options:
                    if isinstance(option, (tuple, list)) and len(option) == 2:
                        combo.addItem(str(option[0]), option[1])
                    else:
                        combo.addItem(str(option))

                default = p.get("default")

                if default is not None:
                    index = combo.findData(default)

                    if index < 0:
                        index = combo.findText(str(default))

                    if index >= 0:
                        combo.setCurrentIndex(index)

                container_layout.addWidget(combo)
                self.param_values[p["name"]] = combo

            # ===== checkbox =====
            elif p["type"] == "checkbox":
                cb = QCheckBox(p["label"])
                cb.setChecked(p.get("default", False))
                container_layout.addWidget(cb)
                self.param_values[p["name"]] = cb

        self.current_params = meta.get("meta", {}).get("params", [])
        self.update_param_visibility()

        # 插件标记 hide_input 时隐藏输入框
        hide = meta.get("meta", {}).get("hide_input", False)
        self.input_label.setVisible(not hide)
        self.input_box.setVisible(not hide)

    def update_param_visibility(self):
        for p in getattr(self, "current_params", []):
            condition = p.get("visible_when")
            visible = True

            if condition:
                controller = self.param_values.get(condition["param"])
                expected = condition.get("equals")

                if isinstance(controller, QButtonGroup):
                    checked = controller.checkedButton()
                    visible = checked is not None and checked.text() == expected
                elif isinstance(controller, QCheckBox):
                    visible = controller.isChecked() == expected
                elif isinstance(controller, QLineEdit):
                    visible = controller.text() == expected

            self.param_containers[p["name"]].setVisible(visible)


    # 搜索过滤
    def filter_plugins(self, text):
        self.plugin_list.clear()
        self.func_map = {}

        # 恢复输入框显示
        self.input_label.setVisible(True)
        self.input_box.setVisible(True)

        query = text.strip().lower().replace(" ", "")
        if not query:
            return

        matches = [
            (key, meta)
            for key, meta in self.all_plugins.items()
            if _match_plugin(meta["name"].lower(), query)
        ]
        for key, meta in sorted(
            matches,
            key=lambda item: _plugin_match_sort_key(item[1]["name"], query),
        ):
            self._add_plugin(key, meta)

    # 执行
    def run(self):
        data = self.input_box.toPlainText()

        selected = [i.text() for i in self.plugin_list.selectedItems()]
        keys = [self.func_map[name] for name in selected]

        config = {}

        for key in keys:
            meta = self.all_plugins[key]

            for p in meta.get("meta", {}).get("params", []):
                widget = self.param_values.get(p["name"])

                if not widget:
                    continue

                # radio
                if p["type"] == "radio":
                    for btn in widget.buttons():
                        if btn.isChecked():
                            config[p["name"]] = btn.text()

                # input
                elif p["type"] == "input":
                    if isinstance(widget, QPlainTextEdit):
                        config[p["name"]] = widget.toPlainText()
                    else:
                        config[p["name"]] = widget.text()

                # select
                elif p["type"] == "select":
                    value = widget.currentData()
                    config[p["name"]] = value if value is not None else widget.currentText()

                # checkbox
                elif p["type"] == "checkbox":
                    config[p["name"]] = widget.isChecked()

        result = self.dispatcher.run(keys[0], data, config)
        self.output_box.setPlainText(result)

    # 一键复制
    def copy_result(self):
        content = self.output_box.toPlainText()
        if not content:
            return
        QApplication.clipboard().setText(content)
        self.status_label.setStyleSheet("color: green;")
        self.status_label.setText("已复制到剪贴板")

    # 导入文件
    def import_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "导入文件",
            "",
            "文本文件 (*.txt);;所有文件 (*.*)"
        )

        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.input_box.setPlainText(content)
            self.status_label.setText(f"已导入：{os.path.normpath(file_path)}")
        except Exception as e:
            self.status_label.setText(f"导入失败：{e}")

    # 快速保存
    def save(self):
        import sys
        content = self.output_box.toPlainText()
        if not content:
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"result_{timestamp}.txt"

        custom_path = self.config.get("save_path", "")
        if custom_path:
            base = custom_path
        elif getattr(sys, 'frozen', False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.abspath(".")

        file_path = os.path.normpath(os.path.join(base, filename))

        save_text(file_path, content)
        self.status_label.setStyleSheet("color: green;")
        self.status_label.setText(f"已保存至：{file_path}")

    # 另存为（弹窗选择路径/格式/文件名）
    def save_as(self):
        content = self.output_box.toPlainText()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"result_{timestamp}.txt"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "另存为",
            default_name,
            "文本文件 (*.txt);;"
            "HTML文件 (*.html);;"
            "CSV文件 (*.csv);;"
            "JSON文件 (*.json);;"
            "日志文件 (*.log);;"
            "所有文件 (*.*)"
        )

        if not file_path:
            return

        file_path = os.path.normpath(file_path)
        save_text(file_path, content)
        self.status_label.setStyleSheet("color: green;")
        self.status_label.setText(f"已保存至：{file_path}")

    # ---- 关闭行为 ----

    def _save_close_preference(self, action):
        self.config.set("close_action", action)
        self.config.save()

    def _reset_close_preference(self):
        self.config.reset("close_action")
        self.config.save()
        self.status_label.setText("已重置关闭行为，下次关闭时将再次询问")
        self.status_label.setStyleSheet("color: green;")

    def _on_status_context_menu(self, pos):
        menu = QMenu(self)
        edit_action = menu.addAction("编辑配置文件")
        edit_action.triggered.connect(self._open_config_file)
        menu.addSeparator()
        reset_action = menu.addAction("重置关闭行为")
        reset_action.triggered.connect(self._reset_close_preference)
        menu.exec(self.status_label.mapToGlobal(pos))

    def _open_config_file(self):
        """用系统默认编辑器打开配置文件"""
        import sys
        path = self.config.filepath
        if not os.path.exists(path):
            self.config.save()
        if sys.platform == "win32":
            os.startfile(path)
        else:
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def closeEvent(self, event):
        pref = self.config.get("close_action")

        # 已有记忆 → 直接执行
        if pref == "quit":
            self.tray.hide()
            event.accept()
            return
        if pref == "minimize":
            self.hide()
            self.tray.showMessage("StreamKnife", "已最小化到任务栏，双击图标恢复", QSystemTrayIcon.Information, 2000)
            event.ignore()
            return

        # 无记忆 → 弹窗询问
        msg = QMessageBox(self)
        msg.setWindowTitle("关闭")
        msg.setText("确定退出软件？")
        msg.setIcon(QMessageBox.Question)

        btn_quit = msg.addButton("退出", QMessageBox.YesRole)
        btn_minimize = msg.addButton("最小化", QMessageBox.NoRole)
        btn_cancel = msg.addButton("取消", QMessageBox.RejectRole)

        cb = QCheckBox("记住我的选择")
        msg.setCheckBox(cb)

        msg.exec()

        clicked = msg.clickedButton()

        if clicked == btn_cancel:
            event.ignore()
            return

        if clicked == btn_minimize:
            if cb.isChecked():
                self._save_close_preference("minimize")
            self.hide()
            self.tray.showMessage("StreamKnife", "已最小化到任务栏，双击图标恢复", QSystemTrayIcon.Information, 2000)
            event.ignore()
            return

        if clicked == btn_quit:
            if cb.isChecked():
                self._save_close_preference("quit")
            self.tray.hide()
            event.accept()
            return

        event.ignore()

    def _restore_from_tray(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _quit_from_tray(self):
        self.tray.hide()
        QApplication.quit()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._restore_from_tray()
