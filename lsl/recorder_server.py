import json
import socket
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from pylsl import resolve_byprop

HOST = "127.0.0.1"
PORT = 8000

LABRECORDER_HOST = "127.0.0.1"
LABRECORDER_RCS_PORT = 22345
OUTPUT_DIR = Path(__file__).resolve().parent / "recordings"

lock = threading.Lock()
recording = False
current_file = None


def send_labrecorder(*commands):
    try:
        with socket.create_connection(
            (LABRECORDER_HOST, LABRECORDER_RCS_PORT),
            timeout=3,
        ) as sock:
            for command in commands:
                sock.sendall((command + "\n").encode("utf-8"))
    except OSError as e:
        raise RuntimeError(
            "LabRecorderに接続できません。"
            "LabRecorderを起動してEnableRCSをONにしてください。"
        ) from e


def get_missing_devices():
    missing = []

    if not resolve_byprop("name", "Muse", minimum=1, timeout=1):
        missing.append("Muse")

    if not resolve_byprop("name", "GarminVenu3S", minimum=1, timeout=1):
        missing.append("Garmin Venu 3S")

    pupil_streams = [
        "pupil_capture",
        "pupil_capture_pupillometry_only",
        "pupil_capture_fixations",
    ]
    if any(
        not resolve_byprop("name", name, minimum=1, timeout=1)
        for name in pupil_streams
    ):
        missing.append("Pupil Labs Core")

    return missing


def start_recording():
    global recording, current_file

    if recording:
        return {
            "status": "already recording",
            "file": str(current_file),
            "missing_devices": get_missing_devices(),
        }

    missing = get_missing_devices()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = datetime.now().strftime("%Y%m%d_%H%M%S") + ".xdf"
    current_file = OUTPUT_DIR / filename

    root = str(OUTPUT_DIR.resolve()) + "/"

    send_labrecorder(
        f"filename {{root:{root}}} {{template:{filename}}}",
        "start",
    )

    recording = True

    return {
        "status": "recording",
        "file": str(current_file),
        "missing_devices": missing,
    }


def end_recording():
    global recording, current_file

    if not recording:
        raise RuntimeError("記録中ではありません")

    saved_file = current_file
    send_labrecorder("stop")

    recording = False
    current_file = None

    return {
        "status": "saved",
        "file": str(saved_file),
    }


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        action = urlparse(self.path).path.strip("/")

        try:
            with lock:
                if action == "start":
                    result = start_recording()
                elif action == "end":
                    result = end_recording()
                else:
                    self.send_json(404, {"error": "use /start or /end"})
                    return

            self.send_json(200, result)

        except Exception as e:
            self.send_json(500, {"error": str(e)})


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Server: http://{HOST}:{PORT}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()