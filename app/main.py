import argparse
import sys

from app.settings import load_settings
from app.repositories.db import Database


def main():
    parser = argparse.ArgumentParser(description="PDD 视觉 AI 客服副驾驶")
    parser.add_argument("--smoke", action="store_true", help="启动窗口后自动退出，仅用于启动检查")
    args = parser.parse_args()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from app.ui.main_window import MainWindow
    application = QApplication(sys.argv[:1])
    application.setApplicationName("PDD 视觉 AI 客服副驾驶")
    settings = load_settings()
    db = Database(settings.data_dir / "copilot.sqlite3")
    window = MainWindow(settings, db)
    window.show()
    if args.smoke:
        QTimer.singleShot(500, application.quit)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
