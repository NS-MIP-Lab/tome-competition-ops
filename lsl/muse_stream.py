from muselsl import list_muses, stream

def main():
    print("Muse を検索中...")
    muses = list_muses()
    if not muses:
        raise RuntimeError("Muse が見つかりません")

    muse = muses[0]
    print(f"接続: {muse.get('name', 'Muse')}")
    print("LSL配信開始: EEG / ACC / GYRO")
    print("Ctrl+C で終了")

    stream(
        muse["address"],
        acc_enabled=True,
        gyro_enabled=True,
    )

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n終了しました")