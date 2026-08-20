"""
Muse MU-02 -> LSL

Research-minimal stream set:
  - Muse / EEG : TP9, AF7, AF8, TP10
  - Muse / ACC : X, Y, Z

Right AUX and GYRO are intentionally not relayed.

Important:
- Muse-LSLのBleak backendでは、BLE notificationを処理するため
  backends.sleep() でasyncioイベントループを動かす必要がある。
- time_func=local_clock とすることで、Muse由来のtimestampを
  LSL clock上に載せる。
"""

from muselsl import backends, list_muses
from muselsl.muse import Muse
from pylsl import (
    StreamInfo,
    StreamOutlet,
    cf_float32,
    local_clock,
)


# ============================================================
# Configuration
# ============================================================

EEG_CHANNELS = (
    "TP9",
    "AF7",
    "AF8",
    "TP10",
)

ACC_CHANNELS = (
    "X",
    "Y",
    "Z",
)

EEG_SAMPLING_RATE = 256.0
ACC_SAMPLING_RATE = 52.0

MUSE_TIMEOUT_SEC = 10.0


# ============================================================
# LSL outlets
# ============================================================

eeg_outlet = None
acc_outlet = None


# ============================================================
# Runtime state
# ============================================================

last_eeg_timestamp = None
last_acc_timestamp = None

eeg_sample_count = 0
acc_sample_count = 0


# ============================================================
# LSL metadata
# ============================================================

def add_channels_metadata(
    info,
    labels,
    unit,
):
    """
    LSL StreamInfoにchannel metadataを追加する。
    """

    channels = (
        info.desc()
        .append_child("channels")
    )

    for label in labels:
        channel = channels.append_child(
            "channel"
        )

        channel.append_child_value(
            "label",
            label,
        )

        channel.append_child_value(
            "unit",
            unit,
        )


def make_outlets(
    address,
):
    """
    EEG / ACC用のLSL outletを作成する。
    """

    global eeg_outlet
    global acc_outlet

    # --------------------------------------------------------
    # EEG
    # --------------------------------------------------------

    eeg_info = StreamInfo(
        name="Muse",
        type="EEG",
        channel_count=4,
        nominal_srate=EEG_SAMPLING_RATE,
        channel_format=cf_float32,
        source_id=f"Muse_{address}_EEG4",
    )

    eeg_info.desc().append_child_value(
        "device",
        "Muse MU-02",
    )

    eeg_info.desc().append_child_value(
        "transport",
        "Bluetooth LE",
    )

    eeg_info.desc().append_child_value(
        "model",
        "MU-02",
    )

    add_channels_metadata(
        eeg_info,
        EEG_CHANNELS,
        "microvolts",
    )

    # --------------------------------------------------------
    # ACC
    # --------------------------------------------------------

    acc_info = StreamInfo(
        name="Muse",
        type="ACC",
        channel_count=3,
        nominal_srate=ACC_SAMPLING_RATE,
        channel_format=cf_float32,
        source_id=f"Muse_{address}_ACC",
    )

    acc_info.desc().append_child_value(
        "device",
        "Muse MU-02",
    )

    acc_info.desc().append_child_value(
        "transport",
        "Bluetooth LE",
    )

    acc_info.desc().append_child_value(
        "model",
        "MU-02",
    )

    add_channels_metadata(
        acc_info,
        ACC_CHANNELS,
        "g",
    )

    # --------------------------------------------------------
    # Create outlets
    # --------------------------------------------------------

    eeg_outlet = StreamOutlet(
        eeg_info
    )

    acc_outlet = StreamOutlet(
        acc_info
    )


# ============================================================
# Muse callbacks
# ============================================================

def on_eeg(
    data,
    timestamps,
):
    """
    Muse EEG callback.

    muselslからは基本的に

        data.shape = (5, N)

    として、

        0: TP9
        1: AF7
        2: AF8
        3: TP10
        4: Right AUX

    が入る。

    今回はRight AUXを除外し、
    最初の4chだけLSLへ流す。
    """

    global last_eeg_timestamp
    global eeg_sample_count

    if eeg_outlet is None:
        return

    for i, timestamp in enumerate(
        timestamps
    ):
        sample = [
            float(data[0, i]),
            float(data[1, i]),
            float(data[2, i]),
            float(data[3, i]),
        ]

        eeg_outlet.push_sample(
            sample,
            timestamp=float(timestamp),
        )

        last_eeg_timestamp = float(
            timestamp
        )

        eeg_sample_count += 1


def on_acc(
    data,
    timestamps,
):
    """
    Muse accelerometer callback.

    muselslからは

        data.shape = (3, N)

    として、

        X
        Y
        Z

    が入る。
    """

    global last_acc_timestamp
    global acc_sample_count

    if acc_outlet is None:
        return

    for i, timestamp in enumerate(
        timestamps
    ):
        sample = [
            float(data[0, i]),
            float(data[1, i]),
            float(data[2, i]),
        ]

        acc_outlet.push_sample(
            sample,
            timestamp=float(timestamp),
        )

        last_acc_timestamp = float(
            timestamp
        )

        acc_sample_count += 1


# ============================================================
# Main
# ============================================================

def main():
    print(
        "Muse を検索中..."
    )

    # --------------------------------------------------------
    # Scan
    # --------------------------------------------------------

    muses = list_muses()

    if not muses:
        raise RuntimeError(
            "Muse が見つかりません"
        )

    # 最初に見つかったMuseを使用
    muse_info = muses[0]

    address = muse_info[
        "address"
    ]

    name = muse_info.get(
        "name",
        "Muse",
    )

    print(
        f"接続先: {name} ({address})"
    )

    # --------------------------------------------------------
    # Muse object
    # --------------------------------------------------------
    #
    # callback_eegを指定
    #   -> EEG有効
    #
    # callback_accを指定
    #   -> ACC有効
    #
    # callback_gyro=None
    #   -> GYRO無効
    #
    # callback_ppg=None
    #   -> PPG無効
    #
    # callback_telemetry=None
    #   -> telemetry無効
    #

    muse = Muse(
        address=address,
        name=name,
        callback_eeg=on_eeg,
        callback_acc=on_acc,
        time_func=local_clock,
    )

    # --------------------------------------------------------
    # Connect
    # --------------------------------------------------------

    connected = muse.connect(
        retries=1
    )

    if not connected:
        raise RuntimeError(
            "Muse への接続に失敗しました"
        )

    # BLE接続・GATT購読が成功してから
    # LSL outletを公開する。
    make_outlets(
        address
    )

    print(
        "LSL配信準備完了:"
    )

    print(
        "  Muse / EEG : "
        "TP9, AF7, AF8, TP10"
    )

    print(
        "  Muse / ACC : "
        "X, Y, Z"
    )

    print(
        "Ctrl+C で終了"
    )

    # --------------------------------------------------------
    # Start streaming
    # --------------------------------------------------------

    try:
        muse.start()

        print(
            "Muse streaming started."
        )

        # BLE callbackが最初に届くまでの基準時刻
        startup_time = local_clock()

        last_status_print = startup_time

        while True:
            # =================================================
            # IMPORTANT
            # =================================================
            #
            # time.sleep() は使わない。
            #
            # muselslのBleak backendが使っている
            # asyncio event loopを動かすために、
            # backends.sleep() を使う。
            #
            # ここでEEG / ACC notification callbackが処理される。
            #

            backends.sleep(
                1
            )

            now = local_clock()

            # ------------------------------------------------
            # Startup timeout
            # ------------------------------------------------

            if last_eeg_timestamp is None:
                if (
                    now
                    - startup_time
                    > MUSE_TIMEOUT_SEC
                ):
                    raise RuntimeError(
                        "MuseからEEGデータを"
                        f"{MUSE_TIMEOUT_SEC:.0f}秒以上"
                        "受信していません"
                    )

            # ------------------------------------------------
            # EEG timeout
            # ------------------------------------------------

            elif (
                now
                - last_eeg_timestamp
                > MUSE_TIMEOUT_SEC
            ):
                raise RuntimeError(
                    "MuseのEEGデータが"
                    f"{MUSE_TIMEOUT_SEC:.0f}秒以上"
                    "停止しています"
                )

            # ------------------------------------------------
            # ACC timeout
            # ------------------------------------------------

            if last_acc_timestamp is not None:
                if (
                    now
                    - last_acc_timestamp
                    > MUSE_TIMEOUT_SEC
                ):
                    raise RuntimeError(
                        "MuseのACCデータが"
                        f"{MUSE_TIMEOUT_SEC:.0f}秒以上"
                        "停止しています"
                    )

            # ------------------------------------------------
            # Status
            # ------------------------------------------------
            #
            # 10秒ごとに受信sample数を表示する。
            #

            if (
                now
                - last_status_print
                >= 10.0
            ):
                print(
                    "受信中:"
                    f" EEG={eeg_sample_count}"
                    f" samples,"
                    f" ACC={acc_sample_count}"
                    f" samples"
                )

                last_status_print = now

    # --------------------------------------------------------
    # Ctrl+C
    # --------------------------------------------------------

    except KeyboardInterrupt:
        print(
            "\n終了します..."
        )

    # --------------------------------------------------------
    # Cleanup
    # --------------------------------------------------------

    finally:
        try:
            muse.stop()

        except Exception as e:
            print(
                "Muse stop warning:",
                e,
            )

        try:
            muse.disconnect()

        except Exception as e:
            print(
                "Muse disconnect warning:",
                e,
            )

        print(
            "Muse切断完了"
        )


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    main()