import os
import sys
from itertools import islice, product
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QColor
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QListWidget, QListWidgetItem, QMessageBox, QMenu,
    QLabel, QLineEdit, QPlainTextEdit, QRadioButton, QButtonGroup,
    QCheckBox, QComboBox, QFileDialog, QSystemTrayIcon, QAbstractItemView,
    QDialog, QInputDialog, QProgressBar
)
from utils.file_io import save_text
from core.config import ConfigManager
from core.recipe_store import RecipeStore
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


class PluginWorker(QThread):
    """在后台线程按顺序执行一个插件或整条配方，避免阻塞界面。"""

    progress = Signal(int, int, str)          # 当前步数, 总步数, 插件名
    succeeded = Signal(str)                   # 最终输出
    failed = Signal(int, str, str, str)       # 步数, 插件名, 错误信息, 已完成输出

    def __init__(self, dispatcher, steps, data, parent=None):
        super().__init__(parent)
        self._dispatcher = dispatcher
        self._steps = steps                    # [(key, name, config), ...]
        self._data = data

    def run(self):
        result = self._data
        total = len(self._steps)

        for index, (key, name, config) in enumerate(self._steps, start=1):
            self.progress.emit(index, total, name)

            try:
                result = self._dispatcher.run(key, result, config)
            except Exception as exc:
                self.failed.emit(
                    index,
                    name,
                    f"{type(exc).__name__}: {exc}",
                    "" if result is None else str(result),
                )
                return

            if result is None:
                result = ""

        self.succeeded.emit(str(result))


class RecipeLibraryDialog(QDialog):
    """配方库管理窗口：保存当前配方、加载或删除已保存的配方。"""

    def __init__(self, store, save_current=None, parent=None):
        super().__init__(parent)

        self.store = store
        self.save_current = save_current
        self.selected_name = None

        self.setWindowTitle("配方库")
        self.resize(480, 360)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("已保存的配方（双击加载）："))

        self.recipe_list = QListWidget(self)
        layout.addWidget(self.recipe_list)

        top_buttons = QHBoxLayout()
        self.save_btn = QPushButton("保存当前配方...")
        self.open_file_btn = QPushButton("打开配置文件")
        top_buttons.addWidget(self.save_btn)
        top_buttons.addWidget(self.open_file_btn)
        top_buttons.addStretch()
        layout.addLayout(top_buttons)

        bottom_buttons = QHBoxLayout()
        self.load_btn = QPushButton("加载到当前配方")
        self.delete_btn = QPushButton("删除")
        close_btn = QPushButton("关闭")
        bottom_buttons.addStretch()
        bottom_buttons.addWidget(self.load_btn)
        bottom_buttons.addWidget(self.delete_btn)
        bottom_buttons.addWidget(close_btn)
        layout.addLayout(bottom_buttons)

        self.save_btn.clicked.connect(self._save_current)
        self.open_file_btn.clicked.connect(self._open_file)
        self.load_btn.clicked.connect(self._accept_selected)
        self.delete_btn.clicked.connect(self._delete_selected)
        close_btn.clicked.connect(self.reject)
        self.recipe_list.itemDoubleClicked.connect(
            lambda _item: self._accept_selected()
        )

        self._reload()

    def _reload(self):
        self.recipe_list.clear()

        for recipe in self.store.list_recipes():
            items = recipe.get("items", [])
            enabled = sum(1 for item in items if item.get("enabled", True))

            text = f"{recipe['name']}（{len(items)} 步"
            if enabled != len(items):
                text += f"，禁用 {len(items) - enabled}"
            text += "）"

            list_item = QListWidgetItem(text)
            list_item.setData(Qt.UserRole, recipe["name"])

            names = [item.get("name") or item.get("key", "") for item in items]
            tooltip = "保存时间：{}".format(recipe.get("saved_at", "未知"))
            if names:
                tooltip += "\n执行顺序：" + " → ".join(names)
            list_item.setToolTip(tooltip)
            self.recipe_list.addItem(list_item)

        has_recipes = self.recipe_list.count() > 0
        self.load_btn.setEnabled(has_recipes)
        self.delete_btn.setEnabled(has_recipes)

    def _selected_name(self):
        item = self.recipe_list.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    def _accept_selected(self):
        name = self._selected_name()
        if name is None:
            return
        self.selected_name = name
        self.accept()

    def _delete_selected(self):
        name = self._selected_name()
        if name is None:
            return

        reply = QMessageBox.question(
            self,
            "删除配方",
            f"确定删除配方“{name}”？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.store.delete_recipe(name)
        self._reload()

    def _save_current(self):
        if self.save_current is not None and self.save_current(self):
            self.store.reload()
            self._reload()

    def _open_file(self):
        open_local_file(self.store)


def open_local_file(store):
    """用系统默认编辑器打开配方配置文件。"""
    store.ensure_file()
    path = store.filepath

    if sys.platform == "win32":
        os.startfile(path)
    else:
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))


class MainWindow(QWidget):
    def __init__(self, dispatcher, config_manager=None):
        super().__init__()

        self.dispatcher = dispatcher
        self.config = config_manager or ConfigManager()
        self.recipe_store = RecipeStore()

        # 窗口自适应状态：文本区的富余高度 / 上次自动调整后的窗口高度
        self._preferred_extra_height = None
        self._last_auto_height = None

        # 配方（有序执行队列）与参数编辑状态
        self.recipe = []            # 按执行顺序排列的配方项
        self._next_recipe_id = 1
        self.preview_targets = {}   # 插件列表预览：key -> 参数对象（按插件记住配置）
        self.preview_target = None  # 最近一次预览的插件
        self.active_target = None   # 当前参数区正在显示的配方项/预览

        # 后台执行状态（避免长任务阻塞界面）
        self._worker = None
        self._exec_mode = None      # "single" | "recipe"
        self._pending_success = ""  # 执行成功后显示的状态文本

        self.setWindowTitle("StreamKnife V2.0 by 帅成马")

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
        # 支持 Ctrl/Shift 多选，便于一次加入多个插件
        self.plugin_list.setSelectionMode(QAbstractItemView.ExtendedSelection)

        # ===== 配方列表 =====
        self.recipe_list = QListWidget()
        self.recipe_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.recipe_list.setToolTip("按从上到下的顺序依次执行")

        self.recipe_add_btn = QPushButton("添加所选插件")
        self.recipe_add_btn.setToolTip(
            "把插件列表中选中的插件按列表顺序加入配方（可按住 Ctrl/Shift 多选）"
        )
        self.recipe_lib_btn = QPushButton("配方库")
        self.recipe_lib_btn.setToolTip("左键打开配方库；右键打开配方配置文件")
        self.recipe_lib_btn.setContextMenuPolicy(Qt.CustomContextMenu)
        self.recipe_remove_btn = QPushButton("移除")
        self.recipe_up_btn = QPushButton("上移")
        self.recipe_down_btn = QPushButton("下移")
        self.recipe_toggle_btn = QPushButton("禁用")
        self.recipe_toggle_btn.setToolTip("临时禁用/启用当前配方项；禁用后执行配方时跳过该步")
        self.recipe_clear_btn = QPushButton("清空")

        # ===== 搜索框 =====
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜索插件...")

        # ===== 按钮 =====
        self.run_btn = QPushButton("执行当前插件")
        self.run_btn.setToolTip("执行当前预览的插件（仅限未加入配方的插件）")
        self.run_recipe_btn = QPushButton("执行配方")
        self.run_recipe_btn.setToolTip("按配方顺序执行已启用的插件")
        self.run_recipe_btn.setEnabled(False)
        self.save_btn = QPushButton("快速保存")
        self.save_as_btn = QPushButton("另存为...")
        self.import_btn = QPushButton("导入文件")
        self.copy_btn = QPushButton("一键复制")

        # ===== 后台执行进度条（任务运行期间显示）=====
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setVisible(False)

        # ===== 布局 =====
        recipe_col = QVBoxLayout()
        recipe_header = QHBoxLayout()
        recipe_header.addWidget(QLabel("配方列表（按顺序执行）"))
        recipe_header.addStretch()
        recipe_header.addWidget(self.recipe_clear_btn)
        recipe_col.addLayout(recipe_header)
        recipe_col.addWidget(self.recipe_list)

        add_row = QHBoxLayout()
        add_row.addWidget(self.recipe_add_btn)
        add_row.addWidget(self.recipe_lib_btn)
        recipe_col.addLayout(add_row)

        recipe_btns = QHBoxLayout()
        recipe_btns.addWidget(self.recipe_up_btn)
        recipe_btns.addWidget(self.recipe_down_btn)
        recipe_btns.addWidget(self.recipe_toggle_btn)
        recipe_btns.addWidget(self.recipe_remove_btn)
        recipe_col.addLayout(recipe_btns)

        top_layout = QHBoxLayout()
        top_layout.addWidget(self.category_list, 1)
        top_layout.addWidget(self.plugin_list, 2)
        top_layout.addLayout(recipe_col, 2)

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

        exec_layout = QHBoxLayout()
        exec_layout.addWidget(self.run_btn)
        exec_layout.addWidget(self.run_recipe_btn)
        layout.addLayout(exec_layout)
        layout.addWidget(self.progress_bar)

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
        self.run_btn.clicked.connect(self.run_single_plugin)
        self.run_recipe_btn.clicked.connect(self.run_recipe)
        self.save_btn.clicked.connect(self.save)
        self.save_as_btn.clicked.connect(self.save_as)
        self.import_btn.clicked.connect(self.import_file)
        self.copy_btn.clicked.connect(self.copy_result)
        self.search_box.textChanged.connect(self.filter_plugins)
        # 只连接一次，避免每添加一个插件就重复连接导致点击时多次重建参数区
        self.category_list.itemClicked.connect(self.load_plugins)
        self.plugin_list.itemClicked.connect(self.render_params)
        self.plugin_list.itemDoubleClicked.connect(
            lambda _item: self.add_selected_plugins()
        )
        self.recipe_add_btn.clicked.connect(self.add_selected_plugins)
        self.recipe_lib_btn.clicked.connect(self.open_recipe_library)
        self.recipe_lib_btn.customContextMenuRequested.connect(
            self._open_recipe_config_file
        )
        self.recipe_remove_btn.clicked.connect(self.remove_recipe_entry)
        self.recipe_up_btn.clicked.connect(lambda: self.move_recipe_entry(-1))
        self.recipe_down_btn.clicked.connect(lambda: self.move_recipe_entry(1))
        self.recipe_clear_btn.clicked.connect(self.clear_recipe)
        self.recipe_toggle_btn.clicked.connect(self.toggle_recipe_entry)
        self.recipe_list.itemClicked.connect(self._on_recipe_item_clicked)
        self.recipe_list.itemChanged.connect(self._on_recipe_item_changed)

    # 注入数据
    def set_functions(self, functions):
        self.functions = functions
        self.func_map = {}

        self.category_list.clear()
        self.plugin_list.clear()

        categories = set()

        for key, meta in functions.items():
            categories.add(meta["category"])

        # 与插件列表一致，按拼音排序分类
        for c in sorted(categories, key=_plugin_sort_key):
            self.category_list.addItem(c)

        self.all_plugins = functions

    def show_load_errors(self, errors):
        """启动时提示加载失败的插件（不影响程序继续运行）。"""
        if not errors:
            return
        detail = "；".join(f"{key}（{msg}）" for key, msg in errors.items())
        self._set_status(f"{len(errors)} 个插件加载失败：{detail}", "red")

    def show_load_warnings(self, warnings):
        """启动时提示非致命问题（如插件显示名重复）。"""
        if not warnings:
            return
        self._set_status("；".join(warnings), "orange")

    # 加载某分类插件
    def load_plugins(self, item):
        category = item.text()

        self.plugin_list.clear()
        self.func_map = {}

        # 维持当前参数对象对输入框的显示要求
        self._apply_input_visibility()

        for key, meta in self.all_plugins.items():
            if meta["category"] == category:
                self._add_plugin(key, meta)

    # 添加插件
    def _add_plugin(self, key, meta):
        self.func_map[meta["name"]] = key

        self.plugin_list.addItem(meta["name"])
        self.plugin_list.item(self.plugin_list.count() - 1).setToolTip(meta["desc"])

    # ------------------------------------------------------------------
    # 参数区：配方项与插件预览共用同一套构建逻辑
    # ------------------------------------------------------------------

    def _build_param_widget(self, target):
        """为配方项/预览创建一个参数控件容器，并把控件登记到 target。"""
        widget = QWidget()
        box = QVBoxLayout(widget)
        box.setContentsMargins(0, 0, 0, 0)

        header = QLabel()
        header.setStyleSheet("font-weight: bold;")
        box.addWidget(header)
        target["header"] = header

        for p in target["params"]:
            container = QWidget()
            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            box.addWidget(container)
            target["containers"][p["name"]] = container

            container_layout.addWidget(QLabel(p["label"]))

            # ===== radio =====
            if p["type"] == "radio":
                group = QButtonGroup(widget)
                hbox = QHBoxLayout()

                # options 支持两种写法： "显示文本" 或 ("显示文本", 值)。
                # 值为收集参数时写回 config 的内容，可用于中文显示 + 内部英文值。
                options = []
                for opt in p["options"]:
                    if isinstance(opt, (tuple, list)) and len(opt) == 2:
                        options.append((str(opt[0]), opt[1]))
                    else:
                        options.append((str(opt), opt))

                default = p.get("default", options[0][1] if options else None)
                for display, value in options:
                    rb = QRadioButton(display)
                    rb.setProperty("value", value)
                    hbox.addWidget(rb)
                    group.addButton(rb)

                    if value == default or display == default:
                        rb.setChecked(True)

                container_layout.addLayout(hbox)
                target["values"][p["name"]] = group
                # 显式忽略信号参数，让窗口跟随选项切换重新计算高度
                group.buttonClicked.connect(
                    lambda *_, t=target: self._on_radio_changed(t)
                )

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
                target["values"][p["name"]] = line

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
                target["values"][p["name"]] = combo

            # ===== checkbox =====
            elif p["type"] == "checkbox":
                cb = QCheckBox(p["label"])
                cb.setChecked(p.get("default", False))
                container_layout.addWidget(cb)
                target["values"][p["name"]] = cb

        self._update_visibility_for(target)
        self._update_header(target)
        return widget

    def _update_header(self, target):
        header = target.get("header")
        if header is None:
            return

        name = target["meta"]["name"]
        if target.get("is_preview"):
            header.setText(f"单独执行：{name}（参数独立于配方）")
            return

        index = next(
            (i for i, entry in enumerate(self.recipe) if entry is target), -1
        )
        header.setText(f"{index + 1}. {name}" if index >= 0 else name)

    def _matches_visible_condition(self, target, condition):
        """判断单个 visible_when 条件是否成立。

        兼容两种写法：{"param": "mode", "equals": "值"} 与 {"mode": "值"}
        （或 {"mode": {"equals": "值"}}）。
        """
        if "param" in condition:
            param_name = condition["param"]
            expected = condition.get("equals")
        else:
            param_name, expected = next(iter(condition.items()))
            if isinstance(expected, dict):
                expected = expected.get("equals")

        controller = target["values"].get(param_name)

        if isinstance(controller, QButtonGroup):
            checked = controller.checkedButton()
            if checked is None:
                return False
            value = checked.property("value")
            return value == expected or checked.text() == expected
        elif isinstance(controller, QCheckBox):
            return controller.isChecked() == expected
        elif isinstance(controller, QLineEdit):
            return controller.text() == expected
        elif isinstance(controller, QComboBox):
            return controller.currentText() == expected
        return True

    def _update_visibility_for(self, target):
        for p in target["params"]:
            conditions = p.get("visible_when")
            if not conditions:
                visible = True
            else:
                # 支持列表形式的多条件：列表内全部成立才显示
                if not isinstance(conditions, list):
                    conditions = [conditions]
                visible = all(
                    self._matches_visible_condition(target, condition)
                    for condition in conditions
                )

            target["containers"][p["name"]].setVisible(visible)

    def _on_radio_changed(self, target):
        self.layout().activate()
        old_height = self.height()
        old_min_height = self.minimumSizeHint().height()

        self._update_visibility_for(target)

        # 只有正在显示的参数区才影响窗口高度
        if target is self.active_target:
            self._sync_window_to_params(old_min_height, old_height)

    def _apply_input_visibility(self):
        target = self.active_target
        hide = False
        if target is not None:
            hide = target["meta"].get("meta", {}).get("hide_input", False)
        self.input_label.setVisible(not hide)
        self.input_box.setVisible(not hide)

    def _show_target(self, target, old_min_height=None, old_height=None):
        """把参数区切换为指定配方项/预览，并同步窗口高度。"""
        if target is self.active_target:
            return

        if old_min_height is None or old_height is None:
            self.layout().activate()
            old_height = self.height()
            old_min_height = self.minimumSizeHint().height()

        self.active_target = target

        for entry in self.recipe:
            entry["widget"].setVisible(entry is target)
        for preview in self.preview_targets.values():
            preview["widget"].setVisible(preview is target)

        self._apply_input_visibility()
        self._update_execution_buttons()
        self._sync_window_to_params(old_min_height, old_height)

    # ------------------------------------------------------------------
    # 配方列表操作
    # ------------------------------------------------------------------

    def _entry_by_id(self, entry_id):
        for entry in self.recipe:
            if entry["id"] == entry_id:
                return entry
        return None

    def _selected_recipe_id(self):
        item = self.recipe_list.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    def _current_recipe_entry(self):
        entry = self._entry_by_id(self._selected_recipe_id())
        if entry is not None:
            return entry

        for current in self.recipe:
            if current is self.active_target:
                return current
        return None

    def _active_recipe_index(self):
        for index, entry in enumerate(self.recipe):
            if entry is self.active_target:
                return index
        return -1

    def _format_recipe_item(self, item, entry, index):
        """按启用状态刷新配方项的文字、颜色与勾选框。"""
        suffix = "" if entry["enabled"] else "（已禁用）"
        item.setText(f"{index + 1}. {entry['meta']['name']}{suffix}")
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if entry["enabled"] else Qt.Unchecked)

        if entry["enabled"]:
            item.setForeground(self.palette().color(self.foregroundRole()))
        else:
            item.setForeground(QColor("gray"))

    def _refresh_recipe_list(self):
        self.recipe_list.blockSignals(True)
        self.recipe_list.clear()

        for index, entry in enumerate(self.recipe):
            item = QListWidgetItem()
            item.setData(Qt.UserRole, entry["id"])
            item.setToolTip(entry["meta"]["desc"])
            self._format_recipe_item(item, entry, index)
            self.recipe_list.addItem(item)
            self._update_header(entry)

        active_index = self._active_recipe_index()
        if active_index >= 0:
            self.recipe_list.setCurrentRow(active_index)

        self.recipe_list.blockSignals(False)
        self._update_execution_buttons()

    def _update_execution_buttons(self):
        """更新单插件/配方两个执行按钮的文字与可用状态。"""
        total = len(self.recipe)
        enabled = sum(1 for entry in self.recipe if entry["enabled"])

        if total and enabled == total:
            self.run_recipe_btn.setText(f"执行配方（{total} 步）")
        elif total:
            self.run_recipe_btn.setText(f"执行配方（{enabled}/{total} 步）")
        else:
            self.run_recipe_btn.setText("执行配方")

        if self._is_busy():
            self.run_recipe_btn.setEnabled(False)
        else:
            self.run_recipe_btn.setEnabled(enabled > 0)
        if enabled > 0:
            self.run_recipe_btn.setToolTip(
                "按配方顺序执行已启用的插件，使用配方中各插件自己的参数"
            )
        else:
            self.run_recipe_btn.setToolTip("配方列表为空或所有插件都已禁用")

        self.run_btn.setToolTip(
            "执行当前参数配置界面所显示的插件，参数与配方中的配置互不影响"
        )

        current = self._current_recipe_entry()
        if current is not None and not current["enabled"]:
            self.recipe_toggle_btn.setText("启用")
        else:
            self.recipe_toggle_btn.setText("禁用")

    def _append_recipe_entry(self, key):
        meta = self.all_plugins[key]
        entry = {
            "id": self._next_recipe_id,
            "key": key,
            "meta": meta,
            "params": meta.get("meta", {}).get("params", []),
            "values": {},
            "containers": {},
            "widget": None,
            "header": None,
            "enabled": True,
        }
        self._next_recipe_id += 1

        entry["widget"] = self._build_param_widget(entry)
        entry["widget"].setVisible(False)
        self.param_box.addWidget(entry["widget"])
        self.recipe.append(entry)
        return entry

    def _select_recipe_entry(self, entry_id):
        entry = self._entry_by_id(entry_id)
        if entry is None:
            return
        self._show_target(entry)
        self._refresh_recipe_list()

    def add_selected_plugins(self):
        """把插件列表中选中的插件按显示顺序加入配方。"""
        items = sorted(self.plugin_list.selectedItems(), key=self.plugin_list.row)
        if not items:
            self.status_label.setStyleSheet("color: gray;")
            self.status_label.setText("请先在插件列表中选择要加入配方的插件")
            return

        first_new = None
        added = 0

        for item in items:
            key = self.func_map.get(item.text())
            if key is None:
                continue

            entry = self._append_recipe_entry(key)
            if first_new is None:
                first_new = entry
            added += 1

        if not added:
            return

        self._refresh_recipe_list()
        self._select_recipe_entry(first_new["id"])
        self.status_label.setStyleSheet("color: gray;")
        self.status_label.setText(f"已添加 {added} 个插件到配方")

    def _on_recipe_item_clicked(self, item):
        entry = self._entry_by_id(item.data(Qt.UserRole))
        if entry is None:
            return
        self._show_target(entry)
        self._refresh_recipe_list()

    def _on_recipe_item_changed(self, item):
        """勾选/取消勾选配方项时更新临时禁用状态。"""
        entry = self._entry_by_id(item.data(Qt.UserRole))
        if entry is None:
            return

        enabled = item.checkState() == Qt.Checked
        if enabled == entry["enabled"]:
            return

        entry["enabled"] = enabled
        index = next(
            (i for i, current in enumerate(self.recipe) if current is entry), -1
        )
        if index >= 0:
            self.recipe_list.blockSignals(True)
            self._format_recipe_item(item, entry, index)
            self.recipe_list.blockSignals(False)

        self._update_execution_buttons()
        self.status_label.setStyleSheet("color: gray;")
        if enabled:
            self.status_label.setText(f"已启用：{entry['meta']['name']}")
        else:
            self.status_label.setText(
                f"已临时禁用：{entry['meta']['name']}（执行配方时跳过）"
            )

    def toggle_recipe_entry(self):
        """临时禁用/启用当前选中的配方项，不将其从配方中移除。"""
        entry = self._current_recipe_entry()
        if entry is None:
            self.status_label.setStyleSheet("color: gray;")
            self.status_label.setText("请先选择要禁用/启用的配方项")
            return

        entry["enabled"] = not entry["enabled"]
        self._refresh_recipe_list()
        self.status_label.setStyleSheet("color: gray;")
        if entry["enabled"]:
            self.status_label.setText(f"已启用：{entry['meta']['name']}")
        else:
            self.status_label.setText(
                f"已临时禁用：{entry['meta']['name']}（执行配方时跳过）"
            )

    def remove_recipe_entry(self):
        entry = self._current_recipe_entry()
        if entry is None:
            return

        self.layout().activate()
        old_height = self.height()
        old_min_height = self.minimumSizeHint().height()

        was_active = entry is self.active_target
        old_index = next(
            (i for i, current in enumerate(self.recipe) if current is entry), -1
        )
        self.recipe.remove(entry)
        entry["widget"].setVisible(False)
        self.param_box.removeWidget(entry["widget"])
        entry["widget"].deleteLater()

        if was_active:
            self.active_target = None
            if self.recipe:
                next_index = min(old_index, len(self.recipe) - 1)
                self._show_target(self.recipe[next_index], old_min_height, old_height)
            elif self.preview_target is not None:
                self._show_target(self.preview_target, old_min_height, old_height)
            else:
                self._apply_input_visibility()
                self._sync_window_to_params(old_min_height, old_height)

        self._refresh_recipe_list()
        self.status_label.setStyleSheet("color: gray;")
        self.status_label.setText(f"已从配方移除：{entry['meta']['name']}")

    def move_recipe_entry(self, delta):
        entry = self._current_recipe_entry()
        if entry is None:
            return

        old_index = next(
            (i for i, current in enumerate(self.recipe) if current is entry), -1
        )
        new_index = old_index + delta
        if old_index < 0 or not (0 <= new_index < len(self.recipe)):
            return

        self.recipe.pop(old_index)
        self.recipe.insert(new_index, entry)
        self._refresh_recipe_list()

    def clear_recipe(self):
        if not self.recipe:
            return

        self.layout().activate()
        old_height = self.height()
        old_min_height = self.minimumSizeHint().height()
        was_active = self._active_recipe_index() >= 0

        for entry in self.recipe:
            entry["widget"].setVisible(False)
            self.param_box.removeWidget(entry["widget"])
            entry["widget"].deleteLater()
        self.recipe.clear()

        if was_active:
            self.active_target = None
            if self.preview_target is not None:
                self._show_target(self.preview_target, old_min_height, old_height)
            else:
                self._apply_input_visibility()
                self._sync_window_to_params(old_min_height, old_height)

        self._refresh_recipe_list()
        self.status_label.setStyleSheet("color: gray;")
        self.status_label.setText("配方已清空")

    # ------------------------------------------------------------------
    # 配方库：保存/加载/管理已配置好的配方
    # ------------------------------------------------------------------

    def save_current_recipe(self, parent=None):
        """把当前配方（含每个插件的参数和禁用状态）保存到配方库。"""
        parent = parent or self

        if not self.recipe:
            self._set_status("当前配方为空，无法保存")
            return False

        name, ok = QInputDialog.getText(parent, "保存配方", "配方名称：")
        if not ok:
            return False

        name = name.strip()
        if not name:
            self._set_status("配方名称不能为空")
            return False

        if self.recipe_store.get(name) is not None:
            reply = QMessageBox.question(
                parent,
                "覆盖配方",
                f"配方“{name}”已存在，是否覆盖？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return False

        items = [
            {
                "key": entry["key"],
                "name": entry["meta"]["name"],
                "enabled": entry["enabled"],
                "config": self._collect_config(entry),
            }
            for entry in self.recipe
        ]

        try:
            self.recipe_store.save_recipe(name, items)
        except Exception as exc:
            self._set_status(f"保存配方失败：{exc}")
            return False

        self._set_status(f"配方已保存到配方库：{name}（{len(items)} 步）", "green")
        return True

    def open_recipe_library(self):
        """左键配方库按钮：打开配方库管理窗口。"""
        self.recipe_store.reload()
        dialog = RecipeLibraryDialog(
            self.recipe_store, save_current=self.save_current_recipe, parent=self
        )
        if dialog.exec() == QDialog.Accepted and dialog.selected_name:
            self._load_recipe(dialog.selected_name)

    def _open_recipe_config_file(self, *_pos):
        """右键配方库按钮：用系统默认编辑器打开 recipes.json。"""
        open_local_file(self.recipe_store)

    def _apply_config(self, target, config):
        """把配方库中保存的参数字典写回新建的参数控件。"""
        for p in target["params"]:
            value = config.get(p["name"])
            if value is None:
                continue

            widget = target["values"].get(p["name"])
            if widget is None:
                continue

            if p["type"] == "radio":
                for btn in widget.buttons():
                    stored = btn.property("value")
                    if stored == value or btn.text() == str(value):
                        btn.setChecked(True)
            elif p["type"] == "input":
                if isinstance(widget, QPlainTextEdit):
                    widget.setPlainText(str(value))
                else:
                    widget.setText(str(value))
            elif p["type"] == "select":
                index = widget.findData(value)
                if index < 0:
                    index = widget.findText(str(value))
                if index >= 0:
                    widget.setCurrentIndex(index)
            elif p["type"] == "checkbox":
                widget.setChecked(bool(value))

        self._update_visibility_for(target)

    def _load_recipe(self, name):
        recipe = self.recipe_store.get(name)
        if recipe is None:
            self._set_status(f"配方库中未找到配方：{name}")
            return

        if self.recipe:
            reply = QMessageBox.question(
                self,
                "加载配方",
                f"加载配方“{name}”将替换当前配方列表，是否继续？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        self.clear_recipe()

        loaded = 0
        skipped = 0

        for item in recipe.get("items", []):
            if not isinstance(item, dict):
                skipped += 1
                continue

            key = item.get("key")
            if key not in self.all_plugins:
                skipped += 1
                continue

            entry = self._append_recipe_entry(key)
            entry["enabled"] = bool(item.get("enabled", True))

            config = item.get("config", {})
            if isinstance(config, dict):
                self._apply_config(entry, config)

            loaded += 1

        self._refresh_recipe_list()
        if self.recipe:
            self._select_recipe_entry(self.recipe[0]["id"])

        message = f"已加载配方：{name}（{loaded} 步）"
        if skipped:
            message += f"，跳过 {skipped} 个不存在的插件"
        self._set_status(message, "green")

    # ------------------------------------------------------------------
    # 插件预览
    # ------------------------------------------------------------------

    def render_params(self, item):
        """点击插件列表时在参数区预览该插件。"""
        name = item.text()
        key = self.func_map.get(name)
        if key is None:
            return

        self.layout().activate()
        old_height = self.height()
        old_min_height = self.minimumSizeHint().height()

        # 每个插件保留一份独立的预览参数控件，切换插件后再回来仍保留配置
        target = self.preview_targets.get(key)
        if target is None:
            meta = self.all_plugins[key]
            target = {
                "id": None,
                "key": key,
                "meta": meta,
                "params": meta.get("meta", {}).get("params", []),
                "values": {},
                "containers": {},
                "widget": None,
                "header": None,
                "is_preview": True,
            }
            target["widget"] = self._build_param_widget(target)
            target["widget"].setVisible(False)
            self.param_box.addWidget(target["widget"])
            self.preview_targets[key] = target

        self.preview_target = target
        self._show_target(target, old_min_height, old_height)
        # 预览时取消配方高亮，避免误以为正在编辑配方项
        self.recipe_list.clearSelection()
        self.recipe_list.setCurrentItem(None)
        self._update_execution_buttons()

    def _sync_window_to_params(self, old_min_height, old_height=None):
        """参数区变化后自动调整窗口高度。

        保持文本区原有的可用高度：新窗口高度 = 新最小高度 + 原有富余高度。
        因此控件多的插件会把窗口撑高，切回控件少的插件时窗口会缩回去，
        而不是停留在上一次被撑大的高度。
        """
        if self.isMaximized() or self.isFullScreen():
            return

        if old_height is None:
            old_height = self.height()

        # 参数区增删/隐藏控件后，需逐级失效并重新激活布局，
        # 否则窗口会沿用缓存的最小高度而无法缩回
        self.param_box.invalidate()
        self.param_box.activate()
        self.layout().activate()
        new_min_height = self.minimumSizeHint().height()

        # 记录文本区需要的富余高度。若窗口仍停留在上次自动调整的高度，
        # 说明这次只是切换插件，沿用原富余高度；若用户手动改过窗口大小，
        # 则以新的富余高度为准。这样可避免屏幕高度限制把富余高度逐步压缩。
        current_extra = max(0, old_height - old_min_height)
        if (
            self._preferred_extra_height is None
            or self._last_auto_height is None
            or abs(old_height - self._last_auto_height) > 1
        ):
            self._preferred_extra_height = current_extra

        extra_height = self._preferred_extra_height
        target_height = new_min_height + extra_height

        screen = self.screen() or QApplication.primaryScreen()
        if screen:
            target_height = min(
                target_height,
                max(new_min_height, screen.availableGeometry().height() - 40),
            )

        # 不能低于当前布局的最小高度，否则控件会被裁切
        target_height = max(new_min_height, target_height)

        # 显式更新窗口最小高度，否则布局缓存的最小尺寸会阻止窗口缩回
        self.setMinimumHeight(new_min_height)

        if target_height != self.height():
            self.resize(self.width(), target_height)

        self._last_auto_height = self.height()

    # 搜索过滤
    def filter_plugins(self, text):
        self.plugin_list.clear()
        self.func_map = {}

        # 维持当前参数对象对输入框的显示要求
        self._apply_input_visibility()

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

    def _collect_config(self, target):
        """从配方项/预览的控件中收集参数。"""
        config = {}

        for p in target.get("params", []):
            widget = target["values"].get(p["name"])

            if not widget:
                continue

            # radio
            if p["type"] == "radio":
                for btn in widget.buttons():
                    if btn.isChecked():
                        value = btn.property("value")
                        config[p["name"]] = value if value is not None else btn.text()

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

        return config

    def _set_status(self, text, color="gray"):
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(text)

    # 执行单个插件（仅限未加入配方的插件）
    def run_single_plugin(self):
        target = self.active_target

        # 没有预览时，用插件列表中选中的第一个插件作为当前插件
        if target is None:
            selected = self.plugin_list.selectedItems()
            if selected:
                self.render_params(selected[0])
                target = self.active_target

        if target is None:
            self._set_status("请先在插件列表中选择要执行的插件")
            return

        # 使用当前参数界面上的配置执行（预览配置与配方配置互相独立）
        name = target["meta"]["name"]
        steps = [(target["key"], name, self._collect_config(target))]
        self._start_execution("single", steps, f"已执行：{name}")

    # 执行配方（按顺序串联已启用的插件）
    def run_recipe(self):
        entries = [entry for entry in self.recipe if entry["enabled"]]
        if not entries:
            self._set_status("配方列表中没有启用的插件")
            return

        steps = [
            (entry["key"], entry["meta"]["name"], self._collect_config(entry))
            for entry in entries
        ]

        skipped = len(self.recipe) - len(entries)
        message = f"已按配方执行 {len(entries)} 步"
        if skipped:
            message += f"（跳过 {skipped} 个已禁用插件）"

        self._start_execution("recipe", steps, message)

    # ------------------------------------------------------------------
    # 后台执行：长任务放入 QThread，界面保持响应
    # ------------------------------------------------------------------

    def _is_busy(self):
        return self._worker is not None and self._worker.isRunning()

    def _start_execution(self, mode, steps, success_message):
        """在后台线程执行一个插件或整条配方。"""
        if self._is_busy():
            self._set_status("已有任务正在执行，请稍候", "red")
            return

        self._exec_mode = mode
        self._pending_success = success_message

        self.progress_bar.setRange(0, len(steps))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("准备执行…")
        self.progress_bar.setVisible(True)
        self._set_busy(True)
        self._set_status("正在执行…")

        self._worker = PluginWorker(
            self.dispatcher, steps, self.input_box.toPlainText()
        )
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.succeeded.connect(self._on_worker_succeeded)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _set_busy(self, busy):
        for button in (self.run_btn, self.run_recipe_btn,
                       self.save_btn, self.save_as_btn):
            button.setEnabled(not busy)

        if not busy:
            # 恢复“执行配方”按钮自身的可用性状态
            self._update_execution_buttons()

    def _on_worker_progress(self, index, total, name):
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(index)
        self.progress_bar.setFormat(f"正在执行：第 {index}/{total} 步「{name}」")

        if self._exec_mode == "single":
            self._set_status(f"正在执行：{name}…")
        else:
            self._set_status(f"正在执行配方：第 {index}/{total} 步「{name}」…")

    def _on_worker_succeeded(self, result):
        self.output_box.setPlainText(result)
        self._set_status(self._pending_success, "green")

    def _on_worker_failed(self, index, name, error, partial):
        if self._exec_mode == "recipe":
            # 配方失败时保留已成功步骤的输出
            self.output_box.setPlainText(partial)
            message = f"配方第 {index} 步「{name}」执行失败：{error}"
        else:
            message = f"插件「{name}」执行失败：{error}"

        self._set_status(message, "red")

    def _on_worker_finished(self):
        worker = self._worker
        self._worker = None
        self._exec_mode = None
        self._pending_success = ""

        self.progress_bar.setVisible(False)
        self._set_busy(False)

        if worker is not None:
            worker.deleteLater()

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

        try:
            os.makedirs(base, exist_ok=True)
            save_text(file_path, content)
        except OSError as exc:
            self._set_status(f"保存失败：{exc}", "red")
            return

        self._set_status(f"已保存至：{file_path}", "green")

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

        try:
            parent = os.path.dirname(file_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            save_text(file_path, content)
        except OSError as exc:
            self._set_status(f"保存失败：{exc}", "red")
            return

        self._set_status(f"已保存至：{file_path}", "green")

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
            if self._is_busy():
                self.show()
                self._set_status("任务正在执行，请等待完成后再退出", "red")
                event.ignore()
                return
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
            if self._is_busy():
                self._set_status("任务正在执行，请等待完成后再退出", "red")
                event.ignore()
                return
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
        if self._is_busy():
            self._restore_from_tray()
            self._set_status("任务正在执行，请等待完成后再退出", "red")
            return
        self.tray.hide()
        QApplication.quit()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._restore_from_tray()
