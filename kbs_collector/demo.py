from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*args):
        pass


def start_demo():
    directory = Path(__file__).resolve().parent.parent/"samples"/"kbs_demo"
    server = ThreadingHTTPServer(("127.0.0.1",0),partial(QuietHandler,directory=str(directory)))
    Thread(target=server.serve_forever,daemon=True).start()
    return server,"http://127.0.0.1:"+str(server.server_port)+"/index.html"
