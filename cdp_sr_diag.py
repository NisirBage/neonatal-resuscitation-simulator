"""
Native SpeechRecognition diagnostics via CDP.
No mocks.  Uses real Chrome SR + real microphone.
"""
import json, threading, time, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from urllib.request import urlopen, Request
import websocket

CDP_URL  = "http://localhost:9222"
PAGE_URL = "http://localhost:8080/sr_diagnostic.html"

# ── CDP class (same as before) ────────────────────────────────────────────────
class CDP:
    def __init__(self, ws_url):
        self._id    = 0
        self._lock  = threading.Lock()
        self._calls = {}
        self._logs  = []
        self._ready = threading.Event()
        self._ws    = websocket.WebSocketApp(
            ws_url,
            on_message=self._on_message,
            on_open=self._on_open,
            on_error=lambda ws, e: print(f"[CDP WS error] {e}"),
        )
        threading.Thread(target=self._ws.run_forever, daemon=True).start()
        if not self._ready.wait(8):
            raise TimeoutError("CDP WS did not connect")

    def _on_open(self, ws):   self._ready.set()

    def _on_message(self, ws, raw):
        msg = json.loads(raw)
        if msg.get("method") == "Runtime.consoleAPICalled":
            args  = msg["params"].get("args", [])
            parts = []
            for a in args:
                if a["type"] == "string":
                    parts.append(a["value"])
                elif a["type"] == "object":
                    parts.append(json.dumps(a.get("value") or
                                            a.get("preview", {}).get("description", "...")))
                else:
                    parts.append(str(a.get("value", "")))
            self._logs.append(" ".join(parts))
        mid = msg.get("id")
        if mid and mid in self._calls:
            ev, h = self._calls[mid]
            h.append(msg)
            ev.set()

    def call(self, method, params=None, timeout=15):
        with self._lock:
            self._id += 1; cid = self._id
        ev, h = threading.Event(), []
        self._calls[cid] = (ev, h)
        self._ws.send(json.dumps({"id": cid, "method": method,
                                  "params": params or {}}))
        if not ev.wait(timeout):
            raise TimeoutError(f"CDP call timed out: {method}")
        return h[0]

    def exec(self, js, await_promise=False):
        r = self.call("Runtime.evaluate", {
            "expression": js, "awaitPromise": await_promise,
            "returnByValue": True,
        })
        res = r.get("result", {}).get("result", {})
        if res.get("subtype") == "error":
            raise RuntimeError(f"JS error: {res.get('description')}")
        return res.get("value")

    def flush(self):
        logs, self._logs = self._logs[:], []
        return logs


# ── Open diagnostic page ──────────────────────────────────────────────────────
# Create a new tab via CDP /json/new (PUT)
req = Request(f"{CDP_URL}/json/new", data=b"", method="PUT")
with urlopen(req) as r:
    new_tab = json.loads(r.read())

tab_ws  = new_tab["webSocketDebuggerUrl"]
tab_id  = new_tab["id"]
print(f"[CDP] New tab created: id={tab_id[:8]}")

cdp = CDP(tab_ws)
cdp.call("Runtime.enable")
cdp.call("Console.enable")
cdp.call("Page.enable")

# Navigate
nav = cdp.call("Page.navigate", {"url": PAGE_URL})
print(f"[CDP] Navigated → {PAGE_URL}")
time.sleep(3)   # wait for page + async init checks

# Drain boot logs
boot = cdp.flush()
print("\n=== Boot diagnostics ===")
for l in boot:
    if "[SR-DIAG" in l:
        print(f"  {l}")

# ── Run mic monitor ───────────────────────────────────────────────────────────
print("\n[CDP] Clicking 'Start Mic Monitor'…")
cdp.exec("document.getElementById('btnMic').click()")
time.sleep(2)

mic_logs = cdp.flush()
print("\n=== getUserMedia + Track diagnostics ===")
for l in mic_logs:
    if "[SR-DIAG" in l:
        print(f"  {l}")

# Read RMS (is microphone feeding audio?)
rms_sample = []
print("\n[CDP] Sampling RMS for 4 seconds (speak or be silent)…")
for i in range(8):
    time.sleep(0.5)
    v = cdp.exec("parseFloat(document.getElementById('rms').textContent) || 0")
    if v is not None and isinstance(v, (int, float)):
        rms_sample.append(v)
        sys.stdout.write(f"\r  RMS sample {i+1}/8: {v:.5f}  peak={max(rms_sample):.5f}   ")
        sys.stdout.flush()
print()

rms_nonzero = [v for v in rms_sample if v > 0.0005]
print(f"\n  Samples with RMS > 0.0005: {len(rms_nonzero)}/{len(rms_sample)}")
if rms_nonzero:
    print(f"  Max RMS observed: {max(rms_sample):.5f}  → microphone IS feeding audio")
    mic_status = "CONFIRMED — microphone feeding audio"
else:
    print(f"  Max RMS: {max(rms_sample) if rms_sample else 0:.5f}  → no audio from microphone (silent environment or no mic)")
    mic_status = "SILENT — no audio above threshold (silent room / no mic activity)"

# ── Run standalone SpeechRecognition ─────────────────────────────────────────
print("\n[CDP] Starting native SpeechRecognition…")
cdp.exec("document.getElementById('btnSR').click()")

print("[CDP] SR started — waiting 12 seconds for onresult / onerror / onend…")
print("      *** If you can see Chrome, please speak 'yes' or 'no' into your microphone NOW ***")

all_sr_logs = []
for i in range(12):
    time.sleep(1)
    new_logs = cdp.flush()
    sr_logs  = [l for l in new_logs if "[SR-DIAG" in l]
    for l in sr_logs:
        all_sr_logs.append(l)
        print(f"  t+{i+1:02d}s  {l}")

# ── Read final page state ─────────────────────────────────────────────────────
print("\n[CDP] Reading page log panel…")
page_log = cdp.exec("""
  Array.from(document.querySelectorAll('#log div'))
       .map(d => d.textContent)
       .join('\\n')
""")
print("\n=== Full page log ===")
print(page_log)

# ── Read device/track info from DOM ──────────────────────────────────────────
context_html = cdp.exec("document.getElementById('contextInfo').innerText")
print(f"\n=== Track diagnostics (DOM) ===\n{context_html}")

perm_html = cdp.exec("document.getElementById('permInfo').innerText")
print(f"\n=== Permission state (DOM) ===\n{perm_html}")

device_html = cdp.exec("document.getElementById('deviceInfo').innerText")
print(f"\n=== Device list (DOM) ===\n{device_html}")

browser_html = cdp.exec("document.getElementById('browserInfo').innerText")
print(f"\n=== Browser info (DOM) ===\n{browser_html}")

# ── Analysis ──────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("NATIVE SPEECH RECOGNITION ANALYSIS")
print("="*60)

has_onresult   = any("onresult" in l for l in all_sr_logs)
has_final      = any("FINAL DELIVERED" in l for l in all_sr_logs)
has_interim    = any("INTERIM ONLY" in l for l in all_sr_logs)
has_onerror    = any("onerror" in l for l in all_sr_logs)
has_nospeech   = any("no-speech" in l for l in all_sr_logs)
has_notallowed = any("not-allowed" in l for l in all_sr_logs)
has_onend      = any("onend" in l for l in all_sr_logs)

print(f"\n  Microphone audio:      {mic_status}")
print(f"  onresult fired:        {'YES' if has_onresult else 'NO'}")
print(f"    isFinal=true:        {'YES' if has_final   else 'NO'}")
print(f"    interim only:        {'YES' if has_interim else 'NO'}")
print(f"  onerror fired:         {'YES' if has_onerror else 'NO'}")
print(f"    no-speech:           {'YES' if has_nospeech else 'NO'}")
print(f"    not-allowed:         {'YES' if has_notallowed else 'NO'}")
print(f"  onend fired:           {'YES' if has_onend else 'NO'}")

print()
if has_final:
    transcript_lines = [l for l in all_sr_logs if "FINAL DELIVERED" in l]
    print("RESULT: isFinal=true WAS delivered — Chrome SR works correctly in this environment.")
    print("        The isFinal omission bug does NOT affect this machine.")
    for l in transcript_lines:
        print(f"        {l}")
elif has_interim and not has_final:
    print("RESULT: Only interim results — Chrome did NOT send isFinal=true.")
    print("        This CONFIRMS the isFinal omission bug on this machine.")
    print("        The interim fallback in useSpeechRecognition.ts is REQUIRED and CORRECT.")
elif has_nospeech:
    print("RESULT: no-speech error — SR started but no voice was detected.")
    print("        This means SpeechRecognition IS functional but no speech was provided.")
    print("        Microphone is accessible; user must speak to produce transcripts.")
elif has_notallowed:
    print("RESULT: PERMISSION DENIED — microphone not allowed.")
    print("        FIX: allow microphone in Chrome site settings for localhost.")
elif not has_onresult and not has_onerror:
    print("RESULT: No events fired — SpeechRecognition may not have started,")
    print("        or Chrome SR service is unavailable (needs internet / Google API).")
else:
    print("RESULT: Partial — see logs above for details.")
