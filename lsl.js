/* =====================================================================
   LSL マーカーの送出

   ブラウザは LSL を直接扱えないため、lsl_bridge/bridge.py に
   WebSocket でイベントを送り、Python 側でマーカーを流してもらう。

   LSL モードになる条件
     - bridge.py が配信する http://127.0.0.1:8000 から開いたとき
     - または URL に ?lsl=1 を付けたとき
   file:// でダブルクリックして開いた場合は無効なので、
   練習や動作確認はこれまでどおり行える（?lsl=0 で明示的に切ることも可）。

   ブリッジが返した LSL 時刻は各イベントに記録され、書き出しに含まれる。
   XDF と突き合わせるときに時刻の対応を推測せずに済む。
   ===================================================================== */
const LSL = (() => {

  const WS_URL = "ws://127.0.0.1:8001";
  const RETRY_MS = 2000;

  const flag = new URLSearchParams(location.search).get("lsl");
  const enabled = flag === "1" || (flag !== "0" && location.protocol.startsWith("http"));

  let ws = null;
  let connected = false;
  let seq = 0;
  let retryTimer = null;

  const listeners = [];               // 接続状態が変わったときに呼ぶ
  const stamps = [];                  // 送ったマーカーと LSL 時刻
  const pending = new Map();          // 通番 -> 応答待ち

  // 課題側から渡してもらう情報（被験者IDなど）
  let context = () => ({});

  function notify(){
    listeners.forEach(fn => { try { fn(connected); } catch (e) { console.error(e); } });
  }

  function connect(){
    if (!enabled || ws) return;
    try {
      ws = new WebSocket(WS_URL);
    } catch (e) {
      scheduleRetry();
      return;
    }

    ws.addEventListener("open", () => {
      connected = true;
      console.info("[LSL] ブリッジに接続しました");
      notify();
    });

    ws.addEventListener("message", ev => {
      let res = null;
      try { res = JSON.parse(ev.data); } catch (e) { return; }
      if (res && res.seq != null && pending.has(res.seq)){
        const rec = pending.get(res.seq);
        rec.lsl時刻 = (res.lsl_time == null) ? "" : res.lsl_time;
        pending.delete(res.seq);
      }
    });

    ws.addEventListener("close", () => {
      if (connected) console.warn("[LSL] ブリッジとの接続が切れました");
      ws = null;
      connected = false;
      notify();
      scheduleRetry();
    });

    ws.addEventListener("error", () => { /* close で処理する */ });
  }

  function scheduleRetry(){
    if (!enabled || retryTimer) return;
    retryTimer = setTimeout(() => { retryTimer = null; connect(); }, RETRY_MS);
  }

  /* ---- 公開する関数 ---- */

  // 送るイベントに毎回添える情報を課題側から供給してもらう
  function setContext(fn){ context = fn; }

  // マーカーを1件送る。detail は任意の追加情報
  function mark(event, detail){
    if (!enabled) return null;

    const payload = Object.assign(
      { seq: ++seq, event, t: (typeof nowStamp === "function" ? nowStamp() : "") },
      context(),
      detail || {}
    );

    const record = { 通番: payload.seq, イベント: event, 時刻: payload.t, lsl時刻: "" };
    stamps.push(record);
    pending.set(payload.seq, record);

    if (connected && ws && ws.readyState === WebSocket.OPEN){
      ws.send(JSON.stringify(payload));
    } else {
      // 送れなかったことを記録に残す。黙って落とさない
      record.lsl時刻 = "未送信";
      pending.delete(payload.seq);
      console.warn("[LSL] 未接続のため送れませんでした:", event);
    }
    return record;
  }

  function onStatus(fn){
    listeners.push(fn);
    fn(connected);
  }

  connect();

  return {
    get enabled(){ return enabled; },
    get connected(){ return connected; },
    get markers(){ return stamps; },
    setContext,
    mark,
    onStatus
  };
})();
