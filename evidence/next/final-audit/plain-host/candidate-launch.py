"""Local-only launcher; standard library, no installation or network service."""
import functools
import http.server
import socket
import threading
import urllib.request
import webbrowser
from pathlib import Path

PORT = 18770
URL = f'http://127.0.0.1:{PORT}/'


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/__label_box_identity__':
            payload = b'label-box-rebuild-v1'
            self.send_response(200)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            super().do_GET()


class LocalServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main():
    folder = Path(__file__).resolve().parent
    handler = functools.partial(Handler, directory=str(folder))
    try:
        server = LocalServer(('127.0.0.1', PORT), handler)
    except OSError:
        try:
            with urllib.request.urlopen(URL + '__label_box_identity__', timeout=2) as reply:
                if reply.read(64) == b'label-box-rebuild-v1':
                    webbrowser.open(URL)
                    print('新版已经打开。请使用之前打开的服务窗口来关闭它。')
                    return
        except (OSError, ValueError):
            pass
        print('打开失败：本机18770端口正被其他程序占用。请关闭占用程序后重试。')
        raise SystemExit(1)
    print('标签收纳盒已启动。浏览器会自动打开。')
    print('物品保存在当前浏览器；下次仍请双击同一个启动文件。')
    print('使用完后关闭这个窗口即可停止服务。')
    print(URL, flush=True)
    threading.Timer(0.5, lambda: webbrowser.open(URL)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
