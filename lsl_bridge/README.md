# 詳細設計書作成課題 → LSL マーカーブリッジ

課題ページの操作を LSL のマーカーとして流し、脳波・心拍・視線と同期できるようにします。

```
Muse   -> LSL -------------------+
Pupil  -> LSL -------------------+--> LabRecorder --> experiment.xdf
Venu3S -> BLE -> garmin_hr_lsl.py+
課題ページ -> bridge.py -> LSL ---+
```

ブラウザは liblsl を直接呼べません。そのため課題ページは WebSocket でこのプログラムにイベントを送り、Python 側が `pylsl` でマーカーを流します。

## 何をするか

1. 課題ページ（`../index.html`）を `http://127.0.0.1:8000` で配信する
2. `ws://127.0.0.1:8001` で課題ページからイベントを受け取る
3. 受け取るたびに `DesignTask_Markers` へマーカーを1件流し、その LSL 時刻をページへ返す
4. 同じ内容を `logs/markers_YYYYMMDD_HHMMSS.csv` にも保存する（LSL が落ちたときの保険）

## 導入（macOS）

```bash
cd lsl_bridge
chmod +x install_macos.sh
./install_macos.sh
source .venv/bin/activate
```

`brew install labstreaminglayer/tap/lsl` で liblsl を入れ、venv に `pylsl` と `websockets` を入れます。既存の `garmin_mac_lsl` と同じ手順です。

## 使い方

```bash
python bridge.py --open
```

`--open` を付けると起動後にブラウザで課題ページが開きます。付けない場合は自分で `http://127.0.0.1:8000/index.html` を開いてください。

終了は Ctrl+C。

| オプション | 意味 |
|---|---|
| `--no-lsl` | pylsl を使わず、受信と CSV 記録だけ行う（動作確認用） |
| `--http-port` | 配信ポート（既定 8000） |
| `--ws-port` | 受信ポート（既定 8001） |
| `--open` | 起動後にブラウザを開く |

## 実験当日の順番

1. Muse・Pupil・Garmin の各ストリームを立ち上げる
2. `python bridge.py --open` でこのブリッジを起動する
3. LabRecorder を開き、`DesignTask_Markers` を含む全ストリームを選んで録画を開始する
4. 被験者に課題を実施してもらう
5. 課題が終わったら LabRecorder を停止する

**課題ページは必ず `http://127.0.0.1:8000` から開いてください。** ファイルをダブルクリックして開くと LSL 連携は無効になり、マーカーが記録されません。ページの「はじめに」画面に接続状態が緑で表示されていることを確認してから開始してください。未接続のままでは開始できないようにしてあります。

同期せずに練習する場合は、URL に `&lsl=0` を付けるか、`index.html` をダブルクリックで開いてください。

## マーカーの形式

1チャンネルの文字列ストリームです。中身は JSON です。

```json
{"seq":1,"event":"start","problem":"p5","mode":"learning","subject":"S01","t":"2026-08-10T10:00:00+09:00"}
```

| event | いつ |
|---|---|
| `start` | 「開始する」を押した瞬間。**ここが t = 0**。ソースコードの表示と同時 |
| `step_enter` / `step_leave` | 各設問の表示・離脱 |
| `hint` | ヒント要請ボタン（学習用のみ） |
| `quiz_open` / `quiz_submit` | 理解度テストの表示・回答 |
| `finish` | 「回答を終える」 |

`seq` は 1 から始まる連番です。**欠番があればマーカーの取りこぼしがあった**ということなので、解析前に確認してください。

課題ページが書き出す JSON にも、送った全マーカーと LSL 時刻が `LSLマーカー` として入ります。XDF 側と通番で突き合わせられます。

## 確認方法

ストリームが見えているか:

```bash
python - <<'PY'
from pylsl import StreamInlet, resolve_byprop
s = resolve_byprop("name", "DesignTask_Markers", timeout=3.0)
print("見つかりました" if s else "見つかりません")
if s:
    inlet = StreamInlet(s[0])
    while True:
        sample, t = inlet.pull_sample()
        print(f"{t:.6f} {sample[0]}")
PY
```

`garmin_mac_lsl/check_lsl.py` と同じ要領です。

## LabRecorder の自動制御について

`bridge.py` の `LABRECORDER_ENABLED` を `True` にすると、`start` で録画開始、`finish` で停止を LabRecorder へ送ります（TCP 22345）。**既定では無効です。**

無効のままにしてあるのは、録画を先に回しておくほうが安全なためです。Muse は装着の安定待ち、Pupil は較正が要り、ベースライン区間も必要になります。ボタンで録画を開始すると、それらを取り逃します。有効にする場合は LabRecorder 側でリモート制御を有効にし、コマンド書式がお使いのバージョンに合っているか確認してください。

## 遅延について

ブラウザ → localhost の WebSocket → `pylsl` で数ミリ秒程度です。設問単位・ヒント単位の事象関連分析には十分ですが、ミリ秒未満の精度が必要な場合はハードウェアトリガを検討してください。

なお `Garmin_HR` の LSL 時刻は BLE 通知の受信時刻であり、心拍の発生時刻ではありません（`garmin_mac_lsl/README.md` の注意書きを参照）。
