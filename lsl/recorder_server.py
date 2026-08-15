import json
import re
import socket
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pylsl import resolve_byprop

HOST = "127.0.0.1"
PORT = 8000

LABRECORDER_HOST = "127.0.0.1"
LABRECORDER_RCS_PORT = 22345
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"

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


def safe_component(value, label):
    value = value.strip()
    if not value or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError(f"{label}は半角英数字・_・-だけで入力してください")
    return value


def start_recording(subject_id, problem_id):
    global recording, current_file

    if recording:
        return {
            "status": "already recording",
            "file": str(current_file),
            "missing_devices": get_missing_devices(),
        }

    subject_id = safe_component(subject_id, "被験者ID")
    problem_id = safe_component(problem_id, "問題ID")
    missing = get_missing_devices()

    output_dir = RESULTS_DIR / problem_id
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{subject_id}_{timestamp}.xdf"
    current_file = output_dir / filename

    root = str(output_dir.resolve()) + "/"

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
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        request = urlparse(self.path)
        action = request.path.strip("/")
        query = parse_qs(request.query)

        try:
            with lock:
                if action == "start":
                    result = start_recording(
                        query.get("subject_id", [""])[0],
                        query.get("problem_id", [""])[0],
                    )
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
