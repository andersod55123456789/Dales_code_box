import threading
import webbrowser

from trainlog import create_app

HOST, PORT = "127.0.0.1", 5000


def main():
    app = create_app()
    threading.Timer(1.25, lambda: webbrowser.open(f"http://{HOST}:{PORT}/")).start()
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
