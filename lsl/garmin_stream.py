import json
from openant.easy.node import Node
from openant.easy.channel import Channel
from pylsl import StreamInfo, StreamOutlet, cf_string, local_clock


NETWORK_KEY = [
    0xB9, 0xA5, 0x21, 0xFB,
    0xBD, 0x72, 0xC3, 0x45,
]

NETWORK_NUMBER = 0
DEVICE_NUMBER = 0
DEVICE_TYPE = 120
TRANSMISSION_TYPE = 0
MESSAGE_PERIOD = 8070
RF_FREQUENCY = 57

LSL_NAME = "GarminVenu3S"
LSL_TYPE = "HeartRateRR"
LSL_SOURCE_ID = "GarminVenu3S_ANT"

last_count = None
last_event_time = None


def make_lsl_outlet():
    info = StreamInfo(
        LSL_NAME,
        LSL_TYPE,
        1,
        0,
        cf_string,
        LSL_SOURCE_ID,
    )

    desc = info.desc()
    desc.append_child_value("device", "Garmin Venu 3S")
    desc.append_child_value("transport", "ANT+ Heart Rate Broadcast")
    desc.append_child_value("device_type", str(DEVICE_TYPE))
    desc.append_child_value("rr_unit", "ms")
    desc.append_child_value("event_time_unit", "1/1024 s")

    return StreamOutlet(info)


outlet = make_lsl_outlet()


def on_data(data):
    global last_count, last_event_time

    event_time = data[4] | (data[5] << 8)
    beat_count = data[6]
    hr_bpm = data[7]

    if beat_count == last_count:
        return

    rr_ms = None
    count_diff = None
    missed_beats = 0

    if last_count is not None:
        count_diff = (beat_count - last_count) & 0xFF

        if count_diff == 1:
            tick_diff = (event_time - last_event_time) & 0xFFFF
            rr_ms = tick_diff * 1000.0 / 1024.0
        elif count_diff > 1:
            missed_beats = count_diff - 1

    payload = {
        "hr_bpm": int(hr_bpm),
        "rr_ms": round(rr_ms, 3) if rr_ms is not None else None,
        "beat_count": int(beat_count),
        "beat_count_diff": int(count_diff) if count_diff is not None else None,
        "missed_beats": int(missed_beats),
        "event_time_ticks": int(event_time),
        "event_time_s": round(event_time / 1024.0, 6),
        "raw": [int(x) for x in data],
    }

    lsl_timestamp = local_clock()
    outlet.push_sample(
        [json.dumps(payload, separators=(",", ":"))],
        timestamp=lsl_timestamp,
    )

    if rr_ms is None:
        if missed_beats > 0:
            print(
                f"HR={hr_bpm} bpm "
                f"RR=missing "
                f"count={beat_count} "
                f"missed={missed_beats}"
            )
        else:
            print(
                f"HR={hr_bpm} bpm "
                f"RR=initial "
                f"count={beat_count}"
            )
    else:
        print(
            f"HR={hr_bpm} bpm "
            f"RR={rr_ms:.1f} ms "
            f"count={beat_count}"
        )

    last_count = beat_count
    last_event_time = event_time


def main():
    node = None

    try:
        print("Garmin Venu 3S ANT+ -> LSL")
        print(f"LSL stream: {LSL_NAME} / {LSL_TYPE}")
        print("ANT USBを初期化中...")

        node = Node()

        print("ANT+ network keyを設定中...")
        node.set_network_key(
            NETWORK_NUMBER,
            NETWORK_KEY,
        )

        channel = node.new_channel(
            Channel.Type.BIDIRECTIONAL_RECEIVE,
            network_number=NETWORK_NUMBER,
        )

        channel.on_broadcast_data = on_data
        channel.on_burst_data = on_data

        channel.set_period(MESSAGE_PERIOD)
        channel.set_search_timeout(12)
        channel.set_rf_freq(RF_FREQUENCY)
        channel.set_id(
            DEVICE_NUMBER,
            DEVICE_TYPE,
            TRANSMISSION_TYPE,
        )

        print("Venu 3SのANT+ Heart Rateを検索中...")
        channel.open()

        print("受信開始。LabRecorderで GarminVenu3S を確認してください。")
        print("Ctrl+C で終了")

        node.start()

    except KeyboardInterrupt:
        print("\n終了")

    except Exception as e:
        print(f"\nANT error: {type(e).__name__}: {e}")
        print(
            "ANT USBを挿し直し、Garmin ExpressなどANT USBを使う"
            "アプリを終了してから再実行してください。"
        )

    finally:
        if node is not None:
            try:
                print("ANT USBを終了中...")
                node.stop()
            except Exception as e:
                print(f"終了処理エラー: {e}")


if __name__ == "__main__":
    main()