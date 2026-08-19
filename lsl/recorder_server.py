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

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"

# 課題ページが書き出す回答ファイルの保存先。
# 被験者ごとに分ける。
TASK_DATA_DIR = Path(__file__).resolve().parent.parent / "task_data"


lock = threading.Lock()
recording = False
current_file = None


# ----------------------------------------------------------------------
# ExperimentMarkers
# ----------------------------------------------------------------------
#
# recorder_server 自身が marker LSL stream を持つ。
# これにより experiment_markers.py を別プロセスで起動する必要はない。
#
# 記録するイベント:
#   task_start
#   task_end
#   support_request
#
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
    """実験イベントをLSLへ流し、そのLSL timestampを返す。"""
    timestamp = local_clock()
    marker_outlet.push_sample(
        [str(value)],
        timestamp=timestamp,
    )
    print(f"MARKER {timestamp:.6f} {value}")
    return timestamp


# ----------------------------------------------------------------------
# LabRecorder Remote Control Server
# ----------------------------------------------------------------------

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


# ----------------------------------------------------------------------
# LSL stream presence check
# ----------------------------------------------------------------------

def get_visible_streams():
    """
    現在見えているLSL streamを1回だけ探索して、
    {(name, type), ...} として返す。

    resolve_bypropを各stream名ごとに呼ぶより、
    start時の待ち時間を短くするため1回の探索にまとめる。
    """
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
            # 1つの壊れた/消失したstreamのために
            # 全体のmissing判定を失敗させない。
            continue

    return visible


def get_missing_devices():
    """
    研究用の最小LSL構成を確認する。

    Muse:
      Muse / EEG
      Muse / ACC

    Garmin:
      GarminVenu3S / HeartRateRR

    Pupil:
      PupilGaze
      PupilPupillometry
      PupilFixations
      PupilSurface

    ExperimentMarkersはこのserver自身が生成するため、
    missing device判定の対象にしない。
    """
    visible = get_visible_streams()
    missing = []

    # MuseはnameだけでなくEEGとACCの両方を見る。
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

    # 研究用Pupil Relayの4 stream
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

    if not required_pupil_names.issubset(visible_names):
        missing.append("Pupil Labs Core")

    return missing


# ----------------------------------------------------------------------
# Recording
# ----------------------------------------------------------------------

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


def start_recording(subject_id, problem_id):
    global recording, current_file

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

    # センサーが足りなくても記録自体は開始する。
    missing = get_missing_devices()

    output_dir = RESULTS_DIR / problem_id
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    filename = (
        f"{subject_id}_{timestamp}.xdf"
    )

    current_file = output_dir / filename

    root = str(
        output_dir.resolve()
    ) + "/"

    # LabRecorderを先に記録状態へする。
    send_labrecorder(
        f"filename {{root:{root}}} {{template:{filename}}}",
        "start",
    )

    recording = True

    # task_startはLabRecorder startの後に送る。
    # LabRecorder側のinletへ到達するためのsample自体の時刻は
    # push_marker内のlocal_clock()。
    marker_timestamp = push_marker(
        "task_start"
    )

    return {
        "status": "recording",
        "file": str(current_file),
        "missing_devices": missing,
        "marker": "task_start",
        "marker_lsl_timestamp": marker_timestamp,
    }


def end_recording():
    global recording, current_file

    if not recording:
        raise RuntimeError(
            "記録中ではありません"
        )

    saved_file = current_file

    # stopより先にtask_endをLSLへ入れる。
    marker_timestamp = push_marker(
        "task_end"
    )

    # LabRecorderのLSL inletがmarkerを取り込む時間を少しだけ確保。
    # marker自身のtimestampはsleep前に確定している。
    time.sleep(0.05)

    send_labrecorder("stop")

    recording = False
    current_file = None

    return {
        "status": "saved",
        "file": str(saved_file),
        "marker": "task_end",
        "marker_lsl_timestamp": marker_timestamp,
    }


def support_request():
    """
    被験者の支援要求を教師ラベルとしてLSLへ記録する。
    XDF記録外のsupport_requestを作らないため、記録中だけ許可する。
    """
    if not recording:
        raise RuntimeError(
            "記録中ではないためsupport_requestを記録できません"
        )

    timestamp = push_marker(
        "support_request"
    )

    return {
        "status": "marked",
        "marker": "support_request",
        "marker_lsl_timestamp": timestamp,
    }


# ----------------------------------------------------------------------
# Task data
# ----------------------------------------------------------------------

def safe_filename(value):
    """
    課題ページから受け取ったファイル名を検証する。

    ブラウザから届いた文字列でファイルを書くため、
    パス区切りや .. を含むものは弾き、
    task_data の外に出られないようにする。
    """
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


def save_task_data(subject_id, files):
    """
    課題ページの書き出しを
    task_data/<被験者ID>/ に保存する。
    """
    subject_id = safe_component(
        subject_id,
        "被験者ID",
    )

    if not isinstance(files, list) or not files:
        raise ValueError(
            "保存するファイルがありません"
        )

    prepared = []

    for item in files:
        name = safe_filename(
            str(item.get("name", ""))
        )

        content = item.get("content")

        if not isinstance(content, str):
            raise ValueError(
                f"{name} の中身が文字列ではありません"
            )

        prepared.append(
            (name, content)
        )

    output_dir = (
        TASK_DATA_DIR / subject_id
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # 上書きは行わない。
    # 1つでも既にあれば、何も書かずに知らせる。
    existing = [
        name
        for name, _content in prepared
        if (output_dir / name).exists()
    ]

    if existing:
        raise ValueError(
            "すでに同じ名前のファイルがあります: "
            + "、".join(existing)
        )

    saved = []

    for name, content in prepared:
        path = output_dir / name

        # 解決後のパスが保存先の中に収まっているか、
        # 書く直前にもう一度確かめる。
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

        saved.append(name)

    return {
        "status": "saved",
        "dir": str(output_dir),
        "files": saved,
    }


# ----------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(
            data,
            ensure_ascii=False,
        ).encode("utf-8")

        self.send_response(status)

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
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)

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
        request = urlparse(self.path)
        action = request.path.strip("/")
        query = parse_qs(request.query)

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
                    )

                elif action == "end":
                    result = end_recording()

                elif action == "support":
                    result = support_request()

                elif action == "status":
                    result = {
                        "recording": recording,
                        "file": (
                            str(current_file)
                            if current_file
                            else None
                        ),
                        "missing_devices": (
                            get_missing_devices()
                        ),
                    }

                else:
                    self.send_json(
                        404,
                        {
                            "error": (
                                "use /start, /end, "
                                "/support or /status"
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
                {"error": str(e)},
            )

        except RuntimeError as e:
            self.send_json(
                409,
                {"error": str(e)},
            )

        except Exception as e:
            self.send_json(
                500,
                {"error": str(e)},
            )

    def do_POST(self):
        action = (
            urlparse(self.path)
            .path
            .strip("/")
        )

        if action != "save":
            self.send_json(
                404,
                {"error": "use /save"},
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
                self.rfile.read(length)
                .decode("utf-8")
            )

            with lock:
                result = save_task_data(
                    payload.get(
                        "subject_id",
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
                {"error": str(e)},
            )

        except Exception as e:
            self.send_json(
                500,
                {"error": str(e)},
            )

    def log_message(self, format, *args):
        # HTTPアクセスログを抑え、
        # 実験イベントのログを見やすくする。
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(
        (HOST, PORT),
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
        "  /start?subject_id=...&problem_id=..."
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