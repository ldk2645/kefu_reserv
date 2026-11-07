import argparse
import sys

from app.settings import load_settings
from app.repositories.db import Database


def main():
    parser = argparse.ArgumentParser(description="小鲸离线客服助手")
    parser.add_argument("--smoke", action="store_true", help="启动窗口后自动退出，仅用于启动检查")
    parser.add_argument('--first-product',action='store_true',help='打开本地首个真实商品核对、人工审核与离线验证窗口')
    args = parser.parse_args()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from app.ui.main_window import MainWindow
    application = QApplication(sys.argv[:1])
    application.setApplicationName("小鲸离线客服助手")
    settings = load_settings()
    db = Database(settings.data_dir / "copilot.sqlite3")
    window = MainWindow(settings, db)
    window.show()
    if args.first_product:
        QTimer.singleShot(100,window.open_first_product)
    if args.smoke:
        QTimer.singleShot(500, application.quit)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
