#!/usr/bin/env python3
"""詳細設計書作成課題 -> LSL マーカーブリッジ

ブラウザは liblsl を直接呼べないため、この仲介プログラムが次の3つを行う。

  1. 課題ページ（index.html など）を http://127.0.0.1:8000 で配信する
  2. ws://127.0.0.1:8001 で課題ページからイベントを受け取る
  3. 受け取ったイベントを LSL のマーカーとして流す

マーカーは1チャンネルの文字列ストリームで、中身は JSON。

  {"seq":1,"event":"start","problem":"p5","mode":"learning","subject":"S01"}

LabRecorder には "DesignTask_Markers" という名前で現れる。被験者が座る前から
一覧に出ているので、収録対象に含め忘れることがない。

使い方:
    python bridge.py                # 通常（LSL あり）
    python bridge.py --no-lsl       # pylsl 無しで動作確認だけする
    python bridge.py --open         # 起動後にブラウザを開く

イベントは LSL とは別に CSV にも保存する。LSL 側が落ちても操作履歴が残る。
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import functools
import http.server
import json
import socket
import threading
from pathlib import Path

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------

STREAM_NAME = "DesignTask_Markers"
STREAM_TYPE = "Markers"
SOURCE_ID = "design_task_markers"

DEFAULT_HTTP_PORT = 8000
DEFAULT_WS_PORT = 8001

# 課題ページのある場所（このファイルの1つ上）
SITE_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = Path(__file__).resolve().parent / "logs"

# LabRecorder のリモート制御。担当者の方針が決まるまでは無効のままにする。
# 有効にすると start イベントで録画開始、finish で停止する。
LABRECORDER_ENABLED = False
LABRECORDER_HOST = "127.0.0.1"
LABRECORDER_PORT = 22345


# ---------------------------------------------------------------------------
# LSL 出力
# ---------------------------------------------------------------------------

class MarkerStream:
    """LSL のマーカーストリーム。--no-lsl のときは何もしない。"""

    def __init__(self, enabled: bool = True) -> None:
        self.outlet = None
        self.local_clock = None
        if not enabled:
            print("[LSL] 無効（--no-lsl）。マーカーは CSV にだけ記録します。")
            return

        try:
            from pylsl import StreamInfo, StreamOutlet, local_clock
        except ImportError:
            raise SystemExit(
                "pylsl が見つかりません。\n"
                "  macOS: brew install labstreaminglayer/tap/lsl\n"
                "         pip install -r requirements.txt\n"
                "LSL 無しで動作確認だけしたい場合は --no-lsl を付けてください。"
            )

        info = StreamInfo(STREAM_NAME, STREAM_TYPE, 1, 0.0, "string", SOURCE_ID)
        desc = info.desc()
        desc.append_child_value("task", "詳細設計書作成課題")
        desc.append_child_value("format", "json")
        self.outlet = StreamOutlet(info)
        self.local_clock = local_clock
        print(f"[LSL] ストリーム '{STREAM_NAME}' を開始しました。")

    def push(self, payload: dict) -> float | None:
        """マーカーを1件流し、その LSL 時刻を返す。"""
        text = json.dumps(payload, ensure_ascii=False)
        if self.outlet is None:
            return None
        stamp = self.local_clock()
        self.outlet.push_sample([text], timestamp=stamp)
        return stamp


# ---------------------------------------------------------------------------
# CSV 記録
# ---------------------------------------------------------------------------

class EventLog:
    """受け取ったイベントを CSV に追記する（LSL が落ちたときの保険）。"""

    FIELDS = ["受信時刻", "LSL時刻", "通番", "イベント", "問題", "条件", "被験者ID", "詳細"]

    def __init__(self) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        name = dt.datetime.now().strftime("markers_%Y%m%d_%H%M%S.csv")
        self.path = LOG_DIR / name
        with self.path.open("w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerow(self.FIELDS)
        print(f"[CSV] {self.path}")

    def write(self, payload: dict, lsl_time: float | None) -> None:
        known = {"seq", "event", "problem", "mode", "subject"}
        detail = {k: v for k, v in payload.items() if k not in known}
        row = [
            dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            f"{lsl_time:.6f}" if lsl_time is not None else "",
            payload.get("seq", ""),
            payload.get("event", ""),
            payload.get("problem", ""),
            payload.get("mode", ""),
            payload.get("subject", ""),
            json.dumps(detail, ensure_ascii=False) if detail else "",
        ]
        with self.path.open("a", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerow(row)


# ---------------------------------------------------------------------------
# LabRecorder のリモート制御（既定では無効）
# ---------------------------------------------------------------------------

def labrecorder(*commands: str) -> None:
    if not LABRECORDER_ENABLED:
        return
    try:
        with socket.create_connection((LABRECORDER_HOST, LABRECORDER_PORT), timeout=2) as s:
            for cmd in commands:
                s.sendall((cmd + "\n").encode("utf-8"))
        print(f"[LabRecorder] {' / '.join(commands)}")
    except OSError as e:
        # 実験を止めないよう、失敗しても続行する
        print(f"[LabRecorder] 送信できませんでした: {e}")


def handle_recording(payload: dict) -> None:
    event = payload.get("event")
    if event == "start":
        subject = payload.get("subject") or "unknown"
        task = f"{payload.get('problem', '')}-{payload.get('mode', '')}"
        labrecorder(
            f"filename {{template:sub-%p_task-%b_run-%n.xdf}} {{p:{subject}}} {{b:{task}}}",
            "select all",
            "start",
        )
    elif event == "finish":
        labrecorder("stop")


# ---------------------------------------------------------------------------
# WebSocket サーバ
# ---------------------------------------------------------------------------

async def serve_websocket(port: int, markers: MarkerStream, log: EventLog) -> None:
    try:
        # websockets 13 以降の新しい API を優先する（旧 API は将来削除される）
        from websockets.asyncio.server import serve
    except ImportError:
        try:
            from websockets import serve
        except ImportError:
            raise SystemExit(
                "websockets が見つかりません。\n"
                "  pip install -r requirements.txt"
            )

    async def handler(ws):
        peer = getattr(ws, "remote_address", None)
        print(f"[WS] 課題ページが接続しました {peer}")
        try:
            async for raw in ws:
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    print(f"[WS] JSON として読めません: {raw!r}")
                    continue

                # 接続確認だけの ping には即返す
                if payload.get("event") == "ping":
                    await ws.send(json.dumps({"ok": True, "event": "pong"}))
                    continue

                lsl_time = markers.push(payload)
                log.write(payload, lsl_time)
                handle_recording(payload)

                seq = payload.get("seq")
                event = payload.get("event")
                stamp = f"{lsl_time:.3f}" if lsl_time is not None else "-"
                print(f"[MARK] #{seq} {event}  lsl={stamp}")

                await ws.send(json.dumps({
                    "ok": True,
                    "seq": seq,
                    "lsl_time": lsl_time,
                }))
        except Exception as e:      # 切断は正常系として扱う
            print(f"[WS] 切断 ({type(e).__name__})")
        finally:
            print("[WS] 課題ページが切断しました")

    async with serve(handler, "127.0.0.1", port):
        print(f"[WS] ws://127.0.0.1:{port} で待機中")
        await asyncio.Future()      # 終了するまで待つ


# ---------------------------------------------------------------------------
# 静的配信
# ---------------------------------------------------------------------------

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """アクセスログを出さない（マーカーのログを埋もれさせないため）。"""

    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        # 実施中に古いページが表示されないようにする
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def serve_http(port: int) -> None:
    handler = functools.partial(QuietHandler, directory=str(SITE_ROOT))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"[HTTP] http://127.0.0.1:{port}/index.html を配信中（{SITE_ROOT}）")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()


# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="詳細設計書作成課題 -> LSL マーカーブリッジ")
    parser.add_argument("--no-lsl", action="store_true", help="pylsl を使わず動作確認だけする")
    parser.add_argument("--http-port", type=int, default=DEFAULT_HTTP_PORT)
    parser.add_argument("--ws-port", type=int, default=DEFAULT_WS_PORT)
    parser.add_argument("--open", action="store_true", help="起動後にブラウザで開く")
    args = parser.parse_args()

    if not (SITE_ROOT / "index.html").exists():
        raise SystemExit(f"index.html が見つかりません: {SITE_ROOT}")

    markers = MarkerStream(enabled=not args.no_lsl)
    log = EventLog()
    serve_http(args.http_port)

    if args.open:
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{args.http_port}/index.html")

    print()
    print("準備ができました。ブラウザで次を開いてください:")
    print(f"    http://127.0.0.1:{args.http_port}/index.html")
    print("終了するには Ctrl+C。")
    print()

    try:
        asyncio.run(serve_websocket(args.ws_port, markers, log))
    except KeyboardInterrupt:
        print("\n終了しました。")


if __name__ == "__main__":
    main()
