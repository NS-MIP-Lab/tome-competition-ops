import json
import re
import socket
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pylsl import (
    StreamInfo,
    StreamOutlet,
    cf_string,
    local_clock,
    resolve_streams,
)


HOST = "127.0.0.1"
PORT = 8000

LABRECORDER_HOST = "127.0.0.1"
LABRECORDER_RCS_PORT = 22345

# JSON / CSV / XDF をすべてここへまとめる
TASK_DATA_DIR = Path(__file__).resolve().parent.parent / "task_data"


lock = threading.Lock()

recording = False
current_file = None
current_subject_id = None
current_problem_id = None
current_mode = None
task_started = False


# ============================================================
# ExperimentMarkers
# ============================================================

marker_info = StreamInfo(
    name="ExperimentMarkers",
    type="Markers",
    channel_count=1,
    nominal_srate=0.0,
    channel_format=cf_string,
    source_id="ExperimentMarkers_RecorderServer",
)

marker_info.desc().append_child_value(
    "purpose",
    "experiment event labels",
)
marker_info.desc().append_child_value(
    "source",
    "recorder_server.py",
)

marker_outlet = StreamOutlet(marker_info)


def push_marker(value):
    timestamp = local_clock()

    marker_outlet.push_sample(
        [str(value)],
        timestamp=timestamp,
    )

    print(f"MARKER {timestamp:.6f} {value}")

    return timestamp


# ============================================================
# LabRecorder Remote Control
# ============================================================

def send_labrecorder(*commands):
    try:
        with socket.create_connection(
            (LABRECORDER_HOST, LABRECORDER_RCS_PORT),
            timeout=3,
        ) as sock:
            for command in commands:
                sock.sendall(
                    (command + "\n").encode("utf-8")
                )

    except OSError as e:
        raise RuntimeError(
            "LabRecorderに接続できません。"
            "LabRecorderを起動してEnableRCSをONにしてください。"
        ) from e


# ============================================================
# LSL stream check
# ============================================================

def get_visible_streams():
    streams = resolve_streams(wait_time=1.0)

    visible = set()

    for stream in streams:
        try:
            visible.add(
                (
                    stream.name(),
                    stream.type(),
                )
            )
        except Exception:
            continue

    return visible


def get_missing_devices():
    visible = get_visible_streams()
    missing = []

    # Muse
    muse_eeg_ok = ("Muse", "EEG") in visible
    muse_acc_ok = ("Muse", "ACC") in visible

    if not (muse_eeg_ok and muse_acc_ok):
        missing.append("Muse")

    # Garmin
    garmin_ok = any(
        name == "GarminVenu3S"
        for name, _stream_type in visible
    )

    if not garmin_ok:
        missing.append("Garmin Venu 3S")

    # Pupil
    required_pupil_names = {
        "PupilGaze",
        "PupilPupillometry",
        "PupilFixations",
        "PupilSurface",
    }

    visible_names = {
        name
        for name, _stream_type in visible
    }

    if not required_pupil_names.issubset(
        visible_names
    ):
        missing.append("Pupil Labs Core")

    return missing


# ============================================================
# Validation
# ============================================================

def safe_component(value, label):
    value = value.strip()

    if not value or not re.fullmatch(
        r"[A-Za-z0-9_-]+",
        value,
    ):
        raise ValueError(
            f"{label}は半角英数字・_・-だけで入力してください"
        )

    return value


def safe_filename(value):
    value = value.strip()

    if not value or not re.fullmatch(
        r"[A-Za-z0-9._-]+",
        value,
    ):
        raise ValueError(
            f"ファイル名に使えない文字が含まれています: {value!r}"
        )

    if value.startswith(".") or ".." in value:
        raise ValueError(
            f"ファイル名として受け付けられません: {value!r}"
        )

    return value


# ============================================================
# XDF recording
# ============================================================

def start_recording(
    subject_id,
    problem_id,
    mode,
):
    global recording
    global current_file
    global current_subject_id
    global current_problem_id
    global current_mode
    global task_started

    if recording:
        return {
            "status": "already recording",
            "file": str(current_file),
            "missing_devices": get_missing_devices(),
        }

    subject_id = safe_component(
        subject_id,
        "被験者ID",
    )

    problem_id = safe_component(
        problem_id,
        "問題ID",
    )

    mode = safe_component(
        mode,
        "モード",
    )

    if mode not in {
        "learning",
        "test",
    }:
        raise ValueError(
            "モードは learning または test を指定してください"
        )

    missing = get_missing_devices()

    # task_data/S01/pA/
    output_dir = (
        TASK_DATA_DIR
        / subject_id
        / problem_id
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    filename = (
        f"design_{problem_id}_{mode}_"
        f"{subject_id}_{timestamp}.xdf"
    )

    current_file = (
        output_dir / filename
    )

    root = (
        str(output_dir.resolve())
        + "/"
    )

    # ここでは「XDF記録開始」だけ。
    # task_start は /task_start で別に記録する。
    send_labrecorder(
        f"filename {{root:{root}}} {{template:{filename}}}",
        "start",
    )

    recording = True
    task_started = False
    current_subject_id = subject_id
    current_problem_id = problem_id
    current_mode = mode

    return {
        "status": "recording",
        "file": str(current_file),
        "missing_devices": missing,
    }


def mark_task_start():
    global task_started

    if not recording:
        raise RuntimeError(
            "XDF記録中ではありません"
        )

    if task_started:
        return {
            "status": "already marked",
            "marker": "task_start",
        }

    push_marker(
        "task_start"
    )

    task_started = True

    return {
        "status": "marked",
        "marker": "task_start",
    }


def support():
    if not recording:
        raise RuntimeError(
            "XDF記録中ではありません"
        )

    if not task_started:
        raise RuntimeError(
            "課題開始前のためsupportを記録できません"
        )

    push_marker(
        "support"
    )

    return {
        "status": "marked",
        "marker": "support",
    }


def end_recording():
    global recording
    global current_file
    global current_subject_id
    global current_problem_id
    global current_mode
    global task_started

    if not recording:
        raise RuntimeError(
            "記録中ではありません"
        )

    saved_file = current_file

    # 課題が実際に始まっている場合だけ task_end を入れる。
    if task_started:
        push_marker(
            "task_end"
        )

        # LabRecorderがmarkerを受け取る時間を少し確保する。
        time.sleep(0.05)

    send_labrecorder(
        "stop"
    )

    recording = False
    current_file = None
    current_subject_id = None
    current_problem_id = None
    current_mode = None
    task_started = False

    return {
        "status": "saved",
        "file": str(saved_file),
    }


# ============================================================
# JSON / CSV save
# ============================================================

def save_task_data(
    subject_id,
    problem_id,
    files,
):
    subject_id = safe_component(
        subject_id,
        "被験者ID",
    )

    problem_id = safe_component(
        problem_id,
        "問題ID",
    )

    if not isinstance(
        files,
        list,
    ) or not files:
        raise ValueError(
            "保存するファイルがありません"
        )

    prepared = []

    for item in files:
        name = safe_filename(
            str(
                item.get(
                    "name",
                    "",
                )
            )
        )

        content = item.get(
            "content"
        )

        if not isinstance(
            content,
            str,
        ):
            raise ValueError(
                f"{name} の中身が文字列ではありません"
            )

        prepared.append(
            (
                name,
                content,
            )
        )

    # task_data/S01/pA/
    output_dir = (
        TASK_DATA_DIR
        / subject_id
        / problem_id
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # 上書きしない
    existing = [
        name
        for name, _content in prepared
        if (
            output_dir / name
        ).exists()
    ]

    if existing:
        raise ValueError(
            "すでに同じ名前のファイルがあります: "
            + "、".join(existing)
        )

    saved = []

    for name, content in prepared:
        path = (
            output_dir / name
        )

        if (
            output_dir.resolve()
            not in path.resolve().parents
        ):
            raise ValueError(
                f"保存先の外を指しています: {name}"
            )

        path.write_text(
            content,
            encoding="utf-8",
        )

        saved.append(
            name
        )

    return {
        "status": "saved",
        "dir": str(output_dir),
        "files": saved,
    }


# ============================================================
# HTTP
# ============================================================

class Handler(
    BaseHTTPRequestHandler
):
    def send_json(
        self,
        status,
        data,
    ):
        body = json.dumps(
            data,
            ensure_ascii=False,
        ).encode(
            "utf-8"
        )

        self.send_response(
            status
        )

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )

        self.send_header(
            "Access-Control-Allow-Origin",
            "*",
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, POST, OPTIONS",
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type",
        )

        self.send_header(
            "Content-Length",
            str(len(body)),
        )

        self.end_headers()

        self.wfile.write(
            body
        )

    def do_OPTIONS(self):
        self.send_response(
            204
        )

        self.send_header(
            "Access-Control-Allow-Origin",
            "*",
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, POST, OPTIONS",
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type",
        )

        self.end_headers()

    def do_GET(self):
        request = urlparse(
            self.path
        )

        action = (
            request.path
            .strip("/")
        )

        query = parse_qs(
            request.query
        )

        try:
            with lock:
                if action == "start":
                    result = start_recording(
                        query.get(
                            "subject_id",
                            [""],
                        )[0],
                        query.get(
                            "problem_id",
                            [""],
                        )[0],
                        query.get(
                            "mode",
                            [""],
                        )[0],
                    )

                elif action == "task_start":
                    result = mark_task_start()

                elif action == "support":
                    result = support()

                elif action == "end":
                    result = end_recording()

                elif action == "status":
                    result = {
                        "recording": recording,
                        "task_started": task_started,
                        "file": (
                            str(current_file)
                            if current_file
                            else None
                        ),
                        "subject_id": current_subject_id,
                        "problem_id": current_problem_id,
                        "mode": current_mode,
                        "missing_devices": get_missing_devices(),
                    }

                else:
                    self.send_json(
                        404,
                        {
                            "error": (
                                "use /start, /task_start, "
                                "/support, /end or /status"
                            )
                        },
                    )
                    return

            self.send_json(
                200,
                result,
            )

        except ValueError as e:
            self.send_json(
                400,
                {
                    "error": str(e)
                },
            )

        except RuntimeError as e:
            self.send_json(
                409,
                {
                    "error": str(e)
                },
            )

        except Exception as e:
            self.send_json(
                500,
                {
                    "error": str(e)
                },
            )

    def do_POST(self):
        action = (
            urlparse(
                self.path
            )
            .path
            .strip("/")
        )

        if action != "save":
            self.send_json(
                404,
                {
                    "error": "use /save"
                },
            )
            return

        try:
            length = int(
                self.headers.get(
                    "Content-Length"
                )
                or 0
            )

            payload = json.loads(
                self.rfile.read(
                    length
                ).decode(
                    "utf-8"
                )
            )

            with lock:
                result = save_task_data(
                    payload.get(
                        "subject_id",
                        "",
                    ),
                    payload.get(
                        "problem_id",
                        "",
                    ),
                    payload.get(
                        "files",
                        [],
                    ),
                )

            self.send_json(
                200,
                result,
            )

        except ValueError as e:
            self.send_json(
                400,
                {
                    "error": str(e)
                },
            )

        except Exception as e:
            self.send_json(
                500,
                {
                    "error": str(e)
                },
            )

    def log_message(
        self,
        format,
        *args,
    ):
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(
        (
            HOST,
            PORT,
        ),
        Handler,
    )

    print(
        f"Server: http://{HOST}:{PORT}"
    )

    print(
        "LSL: ExperimentMarkers"
    )

    print(
        "Endpoints:"
    )

    print(
        "  /start?subject_id=S01&problem_id=pA&mode=learning"
    )

    print(
        "  /task_start"
    )

    print(
        "  /support"
    )

    print(
        "  /end"
    )

    print(
        "  /status"
    )

    print(
        "  POST /save"
    )

    try:
        server.serve_forever()

    except KeyboardInterrupt:
        pass

    finally:
        server.server_close()