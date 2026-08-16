import json
import sys

import matplotlib.pyplot as plt
import numpy as np
import pyxdf


def stream_name(stream):
    return stream["info"]["name"][0]


def stream_type(stream):
    return stream["info"]["type"][0]


def channel_labels(stream):
    try:
        channels = stream["info"]["desc"][0]["channels"][0]["channel"]
        labels = []
        for i, ch in enumerate(channels):
            labels.append(ch.get("label", [f"ch{i}"])[0])
        return labels
    except Exception:
        return []


def relative_time(stream):
    ts = np.asarray(stream["time_stamps"], dtype=float)
    return ts - ts[0] if len(ts) else ts


def print_summary(streams):
    print("\n=== XDF streams ===")

    for i, stream in enumerate(streams):
        ts = np.asarray(stream["time_stamps"], dtype=float)
        samples = len(ts)
        duration = ts[-1] - ts[0] if samples > 1 else 0.0
        rate = (samples - 1) / duration if duration > 0 else 0.0

        print(
            f"[{i}] "
            f"name={stream_name(stream)} | "
            f"type={stream_type(stream)} | "
            f"samples={samples} | "
            f"duration={duration:.3f}s | "
            f"effective_rate={rate:.3f}Hz"
        )

        labels = channel_labels(stream)
        if labels:
            print("    channels:", ", ".join(labels))


def view_numeric(stream):
    data = np.asarray(stream["time_series"], dtype=float)
    t = relative_time(stream)

    if data.ndim == 1:
        data = data[:, None]

    labels = channel_labels(stream)
    if len(labels) != data.shape[1]:
        labels = [f"ch{i}" for i in range(data.shape[1])]

    print(f"\n=== {stream_name(stream)} ({stream_type(stream)}) ===")
    print("shape:", data.shape)

    for i, label in enumerate(labels):
        col = data[:, i]
        finite = col[np.isfinite(col)]
        if len(finite):
            print(
                f"  {label}: "
                f"min={finite.min():.4f}, "
                f"max={finite.max():.4f}, "
                f"mean={finite.mean():.4f}"
            )

    plt.figure()
    for i, label in enumerate(labels):
        plt.plot(t, data[:, i], label=label)

    plt.xlabel("Time [s]")
    plt.ylabel(stream_type(stream))
    plt.title(f"{stream_name(stream)} ({stream_type(stream)})")

    if data.shape[1] <= 12:
        plt.legend()

    plt.tight_layout()
    plt.show()


def parse_garmin(stream):
    rows = []

    for ts, sample in zip(stream["time_stamps"], stream["time_series"]):
        value = sample[0] if isinstance(sample, (list, tuple, np.ndarray)) else sample

        if isinstance(value, bytes):
            value = value.decode("utf-8")

        try:
            obj = json.loads(value)
        except Exception:
            continue

        obj["timestamp"] = float(ts)
        rows.append(obj)

    return rows


def view_garmin(stream):
    rows = parse_garmin(stream)

    if not rows:
        print("Garmin JSONを解析できませんでした。")
        return

    t0 = rows[0]["timestamp"]
    t = np.array([r["timestamp"] - t0 for r in rows], dtype=float)
    hr = np.array([r.get("hr_bpm", np.nan) for r in rows], dtype=float)
    rr_count = sum(len(r.get("rr_ms") or []) for r in rows)

    print("\n=== GarminVenu3S ===")
    print("samples:", len(rows))
    print("RR intervals:", rr_count)

    finite_hr = hr[np.isfinite(hr)]
    if len(finite_hr):
        print(
            f"HR: min={finite_hr.min():.0f}, "
            f"max={finite_hr.max():.0f}, "
            f"mean={finite_hr.mean():.2f} bpm"
        )

    print("\nfirst 5 samples:")
    for row in rows[:5]:
        print(row)

    plt.figure()
    plt.plot(t, hr)
    plt.xlabel("Time [s]")
    plt.ylabel("Heart Rate [bpm]")
    plt.title("Garmin Venu 3S - Heart Rate")
    plt.tight_layout()
    plt.show()

    rr_t = []
    rr_v = []

    for row in rows:
        for rr in row.get("rr_ms") or []:
            rr_t.append(row["timestamp"] - t0)
            rr_v.append(rr)

    if rr_v:
        plt.figure()
        plt.plot(rr_t, rr_v, marker="o")
        plt.xlabel("Time [s]")
        plt.ylabel("RR interval [ms]")
        plt.title("Garmin Venu 3S - RR Intervals")
        plt.tight_layout()
        plt.show()


def view_stream(stream):
    if stream_name(stream) == "GarminVenu3S":
        view_garmin(stream)
        return

    try:
        np.asarray(stream["time_series"], dtype=float)
    except Exception:
        print("\nRaw samples:")
        for sample in stream["time_series"][:20]:
            print(sample)
        return

    view_numeric(stream)


def main():
    if len(sys.argv) != 2:
        print("Usage:")
        print("  python view_xdf.py path/to/file.xdf")
        sys.exit(1)

    path = sys.argv[1]
    streams, _ = pyxdf.load_xdf(path)

    print(f"Loaded: {path}")
    print_summary(streams)

    while True:
        choice = input("\n表示するstream番号 (qで終了): ").strip()

        if choice.lower() == "q":
            break

        try:
            index = int(choice)
            stream = streams[index]
        except (ValueError, IndexError):
            print("有効な番号を入力してください。")
            continue

        view_stream(stream)


if __name__ == "__main__":
    main()
