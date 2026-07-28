import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from ui.window import MainWindow
from core.dispatcher import Dispatcher
from core.registry import load_plugins, FUNCTIONS
from core.config import ConfigManager


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

    window.resize(config.get("window_width"), config.get("window_height"))
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()