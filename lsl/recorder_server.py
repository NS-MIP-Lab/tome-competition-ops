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

# RCSへの接続失敗と、コマンド処理待ちのタイムアウトを分けて扱う。
# stopはXDFのflush/closeに時間がかかることがあるため長めに待つ。
LABRECORDER_CONNECT_TIMEOUT = 3.0
LABRECORDER_COMMAND_TIMEOUT = 10.0
LABRECORDER_STOP_TIMEOUT = 60.0

XDF_CREATE_TIMEOUT = 10.0
XDF_FINALIZE_TIMEOUT = 30.0
XDF_STABLE_SECONDS = 1.0

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

class LabRecorderConnectionError(RuntimeError):
    """LabRecorderのRCSへ接続・送信できなかった。"""


class LabRecorderResponseTimeout(RuntimeError):
    """コマンド送信後、LabRecorderからOKが返る前にタイムアウトした。"""


def _recv_exact(sock, size):
    data = b""

    while len(data) < size:
        chunk = sock.recv(
            size - len(data)
        )

        if not chunk:
            raise RuntimeError(
                "LabRecorderから応答が返る前に接続が切れました"
            )

        data += chunk

    return data


def send_labrecorder(
    *commands,
    response_timeout=LABRECORDER_COMMAND_TIMEOUT,
):
    """
    LabRecorder RCSへコマンドを送り、
    各コマンドに対する "OK" 応答まで待つ。

    接続できない場合と、
    LabRecorder内部の処理に時間がかかっている場合を区別する。
    """
    try:
        sock = socket.create_connection(
            (
                LABRECORDER_HOST,
                LABRECORDER_RCS_PORT,
            ),
            timeout=LABRECORDER_CONNECT_TIMEOUT,
        )

    except OSError as e:
        raise LabRecorderConnectionError(
            "LabRecorderのRCSに接続できません。"
            "LabRecorderを起動し、EnableRCSがONで、"
            f"ポート{LABRECORDER_RCS_PORT}になっているか確認してください。"
        ) from e

    with sock:
        sock.settimeout(
            response_timeout
        )

        for command in commands:
            try:
                sock.sendall(
                    (
                        command
                        + "\n"
                    ).encode(
                        "utf-8"
                    )
                )

            except OSError as e:
                raise LabRecorderConnectionError(
                    "LabRecorderへRCSコマンドを送信できませんでした: "
                    + command
                ) from e

            try:
                response = _recv_exact(
                    sock,
                    2,
                )

            except (socket.timeout, TimeoutError) as e:
                raise LabRecorderResponseTimeout(
                    "LabRecorderのRCSコマンド処理がタイムアウトしました: "
                    + command
                ) from e

            if response != b"OK":
                raise RuntimeError(
                    "LabRecorderから予期しない応答を受け取りました: "
                    + repr(response)
                )


def wait_for_xdf_created(
    path,
    timeout=XDF_CREATE_TIMEOUT,
):
    deadline = (
        time.monotonic()
        + timeout
    )

    while time.monotonic() < deadline:
        if path.is_file():
            return True

        time.sleep(
            0.05
        )

    return path.is_file()


def wait_for_xdf_finalized(
    path,
    timeout=XDF_FINALIZE_TIMEOUT,
    stable_seconds=XDF_STABLE_SECONDS,
):
    """
    XDFが存在し、0 byteではなく、
    一定時間サイズが変化しないことを確認する。

    stopの直後だけでなく、RCSのstop応答がタイムアウトした場合にも使う。
    """
    interval = 0.20
    stable_required = max(
        1,
        int(
            stable_seconds
            / interval
        ),
    )

    deadline = (
        time.monotonic()
        + timeout
    )

    previous_size = None
    stable_count = 0

    while time.monotonic() < deadline:
        try:
            size = path.stat().st_size

        except FileNotFoundError:
            size = 0

        if size > 0:
            if size == previous_size:
                stable_count += 1

                if stable_count >= stable_required:
                    return True

            else:
                stable_count = 0

            previous_size = size

        else:
            stable_count = 0
            previous_size = size

        time.sleep(
            interval
        )

    try:
        return (
            path.is_file()
            and path.stat().st_size > 0
        )

    except FileNotFoundError:
        return False


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

    output_file = (
        output_dir
        / filename
    )

    root = (
        str(
            output_dir.resolve()
        )
        + "/"
    )

    # LabRecorderはRCSで受け取ったtemplate文字列を小文字化する。
    # problem_id / subject_id の大文字小文字を保持するため、
    # それらはtemplateへ直接埋めず %b / %p として渡す。
    template = (
        f"design_%b_{mode}_"
        f"%p_{timestamp}.xdf"
    )

    filename_command = (
        f"filename "
        f"{{root:{root}}} "
        f"{{template:{template}}} "
        f"{{participant:{subject_id}}} "
        f"{{task:{problem_id}}}"
    )

    # 先にLabRecorder自身のstream一覧を更新し、
    # その後すべて選択してから記録を始める。
    #
    # 各コマンドは send_labrecorder() 内で
    # LabRecorderからの "OK" まで待つ。
    try:
        send_labrecorder(
            "update",
            "select all",
            filename_command,
            "start",
            response_timeout=LABRECORDER_COMMAND_TIMEOUT,
        )

        # startのOKだけでなく、実ファイルが作られたことも確認する。
        if not wait_for_xdf_created(
            output_file
        ):
            try:
                send_labrecorder(
                    "stop"
                )
            except Exception:
                pass

            raise RuntimeError(
                "LabRecorderはstartに応答しましたが、"
                "XDFファイルが作成されませんでした: "
                + str(output_file)
            )

    except Exception:
        # start失敗時はPython側をrecording状態にしない。
        raise

    current_file = output_file
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

        # markerがLabRecorder側へ届く時間を確保する。
        time.sleep(
            0.10
        )

    stop_timed_out = False

    try:
        # stopRecording() ではXDFのflush/closeが走るため、
        # update/start等より長く待つ。
        send_labrecorder(
            "stop",
            response_timeout=LABRECORDER_STOP_TIMEOUT,
        )

    except LabRecorderResponseTimeout as e:
        # stopコマンド自体は送信済み。
        # LabRecorderがXDFを閉じるのに時間がかかった可能性が高いので、
        # 「RCSが無効」とは扱わず、実ファイルを確認する。
        stop_timed_out = True

        print(
            "WARNING:",
            str(e),
        )
        print(
            "WARNING: stopの応答はタイムアウトしました。"
            "XDFの保存状態を確認します。"
        )

    # stopを送信した時点で、新しいsupport等を受け付けない。
    recording = False
    task_started = False

    # XDFが実際に存在し、書き込みが落ち着いたことを確認する。
    finalized = wait_for_xdf_finalized(
        saved_file
    )

    if not finalized and stop_timed_out:
        # 1回目のstopが処理済みなら、この2回目は即OKになる。
        # まだ処理中だった場合にも、手動で「終了」を押し直す代わりになる。
        print(
            "WARNING: XDFの確定を確認できないため、"
            "LabRecorderへstopを1回だけ再送します。"
        )

        try:
            send_labrecorder(
                "stop",
                response_timeout=LABRECORDER_COMMAND_TIMEOUT,
            )

        except LabRecorderResponseTimeout:
            print(
                "WARNING: stop再送の応答もタイムアウトしました。"
            )

        except LabRecorderConnectionError:
            # すでに停止・終了しているケースもあるので、
            # 最終判断は下のXDF実ファイル確認で行う。
            print(
                "WARNING: stop再送時にRCSへ接続できませんでした。"
            )

        finalized = wait_for_xdf_finalized(
            saved_file
        )

    if not finalized:
        raise RuntimeError(
            "LabRecorderへstopは送信しましたが、"
            "XDFファイルの保存完了を確認できませんでした: "
            + str(saved_file)
        )

    file_size = (
        saved_file.stat().st_size
    )

    current_file = None
    current_subject_id = None
    current_problem_id = None
    current_mode = None

    return {
        "status": "saved",
        "file": str(saved_file),
        "size_bytes": file_size,
        "stop_response_timed_out": stop_timed_out,
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
                        "file_exists": (
                            current_file.is_file()
                            if current_file
                            else False
                        ),
                        "file_size_bytes": (
                            current_file.stat().st_size
                            if current_file
                            and current_file.is_file()
                            else 0
                        ),
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