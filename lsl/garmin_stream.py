import asyncio
import json

from bleak import BleakClient, BleakScanner
from pylsl import StreamInfo, StreamOutlet, cf_string, local_clock

DEVICE_NAME = "Venu 3S"
HR_MEASUREMENT = "00002a37-0000-1000-8000-00805f9b34fb"

def parse_heart_rate(data):
    b = bytes(data)
    flags = b[0]
    i = 1

    if flags & 0x01:
        hr = int.from_bytes(b[i:i + 2], "little")
        i += 2
    else:
        hr = b[i]
        i += 1

    contact_supported = bool(flags & 0x04)
    contact = bool(flags & 0x02) if contact_supported else None

    energy_kj = None
    if flags & 0x08:
        energy_kj = int.from_bytes(b[i:i + 2], "little")
        i += 2

    rr_ms = []
    if flags & 0x10:
        while i + 1 < len(b):
            rr = int.from_bytes(b[i:i + 2], "little")
            rr_ms.append(rr * 1000.0 / 1024.0)
            i += 2

    return {
        "hr_bpm": hr,
        "rr_ms": rr_ms,
        "energy_kj": energy_kj,
        "contact_supported": contact_supported,
        "contact": contact,
        "flags": flags,
        "raw_hex": b.hex(),
    }

async def main():
    print(f"{DEVICE_NAME} を検索中...")
    device = await BleakScanner.find_device_by_name(
        DEVICE_NAME,
        timeout=15,
    )
    if device is None:
        raise RuntimeError(f"{DEVICE_NAME} が見つかりません")

    info = StreamInfo(
        name="GarminVenu3S",
        type="HeartRate",
        channel_count=1,
        nominal_srate=0,
        channel_format=cf_string,
        source_id="GarminVenu3S",
    )

    channel = (
        info.desc()
        .append_child("channels")
        .append_child("channel")
    )
    channel.append_child_value(
        "label",
        "HeartRateMeasurementJSON",
    )

    outlet = StreamOutlet(info)

    print(f"接続: {device.name}")
    print("LSL配信開始: GarminVenu3S")
    print("Ctrl+C で終了")

    async with BleakClient(device) as client:
        def on_heart_rate(_, data):
            parsed = parse_heart_rate(data)

            outlet.push_sample(
                [json.dumps(parsed, separators=(",", ":"))],
                timestamp=local_clock(),
            )

            rr = parsed["rr_ms"]
            rr_text = (
                f" RR={','.join(f'{x:.1f}' for x in rr)}ms"
                if rr
                else ""
            )
            print(f"HR={parsed['hr_bpm']} bpm{rr_text}")

        await client.start_notify(
            HR_MEASUREMENT,
            on_heart_rate,
        )

        while True:
            await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n終了しました")