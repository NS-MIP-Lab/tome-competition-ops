"""
Muse MU-02 -> LSL
Research-minimal stream set:
  - Muse / EEG : TP9, AF7, AF8, TP10 only
  - Muse / ACC : X, Y, Z

Right AUX and GYRO are intentionally not relayed.

The Muse device uses pylsl.local_clock() as its time function so the generated
sample timestamps live directly on the LSL clock.
"""

import time

from muselsl import list_muses
from muselsl.muse import Muse
from pylsl import StreamInfo, StreamOutlet, cf_float32, local_clock


EEG_CHANNELS = ("TP9", "AF7", "AF8", "TP10")
ACC_CHANNELS = ("X", "Y", "Z")

eeg_outlet = None
acc_outlet = None


def add_channels_metadata(info, labels, unit):
    channels = info.desc().append_child("channels")
    for label in labels:
        ch = channels.append_child("channel")
        ch.append_child_value("label", label)
        ch.append_child_value("unit", unit)


def make_outlets(address):
    global eeg_outlet, acc_outlet

    eeg_info = StreamInfo(
        name="Muse",
        type="EEG",
        channel_count=4,
        nominal_srate=256.0,
        channel_format=cf_float32,
        source_id=f"Muse_{address}_EEG4",
    )
    eeg_info.desc().append_child_value("device", "Muse MU-02")
    eeg_info.desc().append_child_value("transport", "Bluetooth LE")
    add_channels_metadata(eeg_info, EEG_CHANNELS, "microvolts")

    acc_info = StreamInfo(
        name="Muse",
        type="ACC",
        channel_count=3,
        nominal_srate=52.0,
        channel_format=cf_float32,
        source_id=f"Muse_{address}_ACC",
    )
    acc_info.desc().append_child_value("device", "Muse MU-02")
    acc_info.desc().append_child_value("transport", "Bluetooth LE")
    add_channels_metadata(acc_info, ACC_CHANNELS, "g")

    eeg_outlet = StreamOutlet(eeg_info)
    acc_outlet = StreamOutlet(acc_info)


def on_eeg(data, timestamps):
    if eeg_outlet is None:
        return

    for i, timestamp in enumerate(timestamps):
        eeg_outlet.push_sample(
            [float(data[ch, i]) for ch in range(4)],
            timestamp=float(timestamp),
        )


def on_acc(data, timestamps):
    if acc_outlet is None:
        return

    for i, timestamp in enumerate(timestamps):
        acc_outlet.push_sample(
            [float(data[ch, i]) for ch in range(3)],
            timestamp=float(timestamp),
        )


def main():
    print("Muse を検索中...")
    muses = list_muses()

    if not muses:
        raise RuntimeError("Muse が見つかりません")

    muse_info = muses[0]
    address = muse_info["address"]
    name = muse_info.get("name", "Muse")

    print(f"接続先: {name} ({address})")

    muse = Muse(
        address=address,
        name=name,
        callback_eeg=on_eeg,
        callback_acc=on_acc,
        time_func=local_clock,
    )

    connected = muse.connect(retries=1)
    if not connected:
        raise RuntimeError("Muse への接続に失敗しました")

    make_outlets(address)

    print("LSL配信: Muse / EEG (4ch), Muse / ACC (3ch)")
    print("Ctrl+C で終了")

    try:
        muse.start()

        while True:
            time.sleep(1)

            if local_clock() - muse.last_timestamp > 10:
                raise RuntimeError(
                    "Museから10秒以上データを受信していません"
                )

    except KeyboardInterrupt:
        print("\n終了")

    finally:
        try:
            muse.stop()
        except Exception:
            pass

        try:
            muse.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()