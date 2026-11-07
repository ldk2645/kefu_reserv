"""Run: python -m kbs_collector.main [--browser chrome|edge] [--demo]."""
import argparse
import re
import sys

from .policy import DATA


def main():
    parser = argparse.ArgumentParser(description="小鲸 KBS 有头、人工登录、本地待审核试采集（最多 5 产品）")
    parser.add_argument("--browser",choices=["edge","chrome"],default="chrome",help="默认 chrome；同一浏览器复用自己的持久登录目录")
    parser.add_argument("--driver",help="已安装的官方 msedgedriver/chromedriver 路径；省略时使用 Selenium Manager")
    parser.add_argument("--demo",action="store_true",help="使用明确标记为虚构的本地 HTML；不访问真实知识库")
    parser.add_argument('--collection',help='打开 data/kbs_import 下指定采集目录，例如 pilot_four_categories')
    args = parser.parse_args()
    if args.collection and (args.demo or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',args.collection)):
        parser.error('--collection 仅接受本地目录名称，且不能与 --demo 同用')
    from PySide6.QtCore import QLockFile
    from PySide6.QtWidgets import QApplication, QMessageBox
    from .storage import Storage
    from .ui import CollectorWindow
    app = QApplication(sys.argv[:1])
    directory = DATA / "demo" if args.demo else DATA / args.collection if args.collection else DATA
    directory.mkdir(parents=True,exist_ok=True)
    lock = QLockFile(str(DATA/"collector.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None,"小鲸采集器","已有采集窗口运行，请切换至该窗口。")
        return 1
    server = None
    try:
        store = Storage(directory)
        store.recover()
        url = None
        if args.demo:
            from .demo import start_demo
            server,url = start_demo()
        window = CollectorWindow(store,args.browser,args.driver,url,args.demo)
        window.show()
        return app.exec()
    except Exception:
        QMessageBox.critical(None,"启动失败","请检查依赖安装和本地 data/kbs_import 目录权限；未输出原始错误或资料。")
        return 1
    finally:
        if server:
            server.shutdown()
            server.server_close()
        lock.unlock()


if __name__ == "__main__":
    raise SystemExit(main())
