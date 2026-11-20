import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from ui.window import MainWindow
from core.dispatcher import Dispatcher
from core.registry import load_plugins, FUNCTIONS, LOAD_ERRORS, LOAD_WARNINGS
from core.config import ConfigManager


def read_window_size(config):
    """读取配置中的窗口初始大小，非法值回退默认值并限制最小值。"""

    def _value(key, default, minimum):
        try:
            value = int(config.get(key, default))
        except (TypeError, ValueError):
            return default
        return max(value, minimum)

    return _value("window_width", 800, 400), _value("window_height", 600, 300)


def main():
    app = QApplication(sys.argv)

    # 设置程序图标
    app.setWindowIcon(QIcon("assets/app.ico"))

    # 加载插件
    load_plugins()

    # 加载配置（首次运行自动生成带注释的配置文件）
    config = ConfigManager()
    config.save()

    dispatcher = Dispatcher()
    window = MainWindow(dispatcher, config_manager=config)

    window.set_functions(FUNCTIONS)
    if LOAD_ERRORS:
        window.show_load_errors(LOAD_ERRORS)
    else:
        window.show_load_warnings(LOAD_WARNINGS)

    width, height = read_window_size(config)
    window.resize(width, height)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()