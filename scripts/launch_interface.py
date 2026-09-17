"""One foreground server, with browser opening and safe reuse of its loopback port."""

import argparse
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOST = '127.0.0.1'


def probe_workspace(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url + 'api/health', timeout=0.4) as response:
            body = json.loads(response.read(4096))
        if isinstance(body, dict) and body.get('application') == 'Roleplay' and body.get('status') == 'ok':
            return 'ready'
        return 'foreign'
    except (urllib.error.HTTPError, ValueError):
        return 'foreign'
    except (urllib.error.URLError, OSError):
        return 'waiting'


def open_interface(url):
    try:
        if webbrowser.open(url):
            return
    except OSError:
        pass
    print(f'Open {url} in your browser.', flush=True)


def reuse_workspace(url, no_browser):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = probe_workspace(url)
        if state == 'ready':
            print(f'The interface is already running at {url} Reusing it; no second server was started.', flush=True)
            if not no_browser:
                open_interface(url)
            return 0
        if state == 'foreign':
            break
        time.sleep(0.1)
    print(f'Cannot start: {url} is occupied or its service is not ready. No process was stopped. '
          'Close the existing service or inspect its terminal, then retry.', flush=True)
    return 1


def reserve_port(port):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == 'nt':
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind((HOST, port))
        return listener
    except OSError:
        listener.close()
        return None


def open_when_ready(server, stopped, url):
    while not stopped.wait(0.1):
        if server.started:
            open_interface(url)
            return


def serve(listener, url, port, no_browser):
    import uvicorn

    config = uvicorn.Config('server.main:create_app', factory=True, host=HOST, port=port,
                            access_log=False, timeout_graceful_shutdown=10)
    server = uvicorn.Server(config)
    stopped = threading.Event()
    if not no_browser:
        threading.Thread(target=open_when_ready, args=(server, stopped, url), daemon=True).start()
    print(f"Prospero's Study: {url}\nKeep this terminal open. Press Ctrl+C to stop the app.", flush=True)
    try:
        server.run(sockets=[listener])
        return 0 if server.started else 1
    except KeyboardInterrupt:
        return 0
    finally:
        stopped.set()
        listener.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Choose a port between 1024 and 65535.')
    os.chdir(ROOT)
    if not (ROOT / 'dist' / 'index.html').is_file():
        print('The interface is not built. Run install.bat first.', flush=True)
        return 1
    url = f'http://{HOST}:{args.port}/'
    listener = reserve_port(args.port)
    if listener is None:
        return reuse_workspace(url, args.no_browser)
    with listener:
        return serve(listener, url, args.port, args.no_browser)


if __name__ == '__main__':
    raise SystemExit(main())
