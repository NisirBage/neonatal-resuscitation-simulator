"""
Definitive transcript test.
Injects a visible "SAY YES NOW" banner into the Chrome window.
Uses ONLY the NRS app's own logging (no broken interceptors).
Captures every [VOICE] and [NRS] log including the exact transcript string.
"""

import json, threading, time, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from urllib.request import urlopen
import websocket

CDP_URL = "http://localhost:9222"

class CDP:
    def __init__(self, ws_url):
        self._id = 0; self._lock = threading.Lock()
        self._calls = {}; self._logs = []; self._ready = threading.Event()
        self._ws = websocket.WebSocketApp(ws_url,
            on_message=self._on_message,
            on_open=lambda ws: self._ready.set())
        threading.Thread(target=self._ws.run_forever, daemon=True).start()
        if not self._ready.wait(10): raise TimeoutError()

    def _on_message(self, ws, raw):
        msg = json.loads(raw)
        if msg.get("method") == "Runtime.consoleAPICalled":
            parts = []
            for a in msg["params"].get("args", []):
                if a["type"] == "string": parts.append(a["value"])
                elif a["type"] == "object":
                    v = a.get("value")
                    parts.append(json.dumps(v) if v is not None
                                 else a.get("preview", {}).get("description", "..."))
                else: parts.append(str(a.get("value", "")))
            self._logs.append((" ".join(parts), time.time()))
        mid = msg.get("id")
        if mid and mid in self._calls:
            ev, h = self._calls[mid]; h.append(msg); ev.set()

    def call(self, method, params=None, timeout=15):
        with self._lock: self._id += 1; cid = self._id
        ev, h = threading.Event(), []
        self._calls[cid] = (ev, h)
        self._ws.send(json.dumps({"id": cid, "method": method, "params": params or {}}))
        if not ev.wait(timeout): raise TimeoutError(method)
        return h[0]

    def exec(self, js, timeout=15):
        r = self.call("Runtime.evaluate", {"expression": js, "returnByValue": True}, timeout)
        res = r.get("result", {}).get("result", {})
        if res.get("subtype") == "error": raise RuntimeError(res.get("description"))
        return res.get("value")

    def flush(self):
        logs, self._logs = self._logs[:], []; return logs

    def panel(self):
        raw = self.exec("JSON.stringify((() => { var s=document.querySelectorAll('.font-mono span'); var r={}; s.forEach(function(n){var l=n.querySelector('.text-green-600'); if(l)r[l.textContent]=n.textContent.replace(l.textContent,'').trim()}); return r; })())")
        return json.loads(raw) if raw else {}

# ── Connect ───────────────────────────────────────────────────────────────────
with urlopen(f"{CDP_URL}/json") as r:
    tabs = json.loads(r.read())
tab = next((t for t in tabs if "5173" in t.get("url", "")), None)
if not tab:
    print("ERROR: app tab not found"); sys.exit(1)

cdp = CDP(tab["webSocketDebuggerUrl"])
cdp.call("Runtime.enable")
cdp.call("Page.enable")
print(f"[CDP] {tab['url']}")

# ── Reload cleanly — NO interceptor that modifies onresult ───────────────────
cdp.call("Page.reload", {"ignoreCache": True})
print("[CDP] Clean reload (no interceptor)")
time.sleep(4)
cdp.exec("localStorage.setItem('NRS_DEV','1')")
cdp.flush()

# Start session
r = cdp.exec("(() => { var b=Array.from(document.querySelectorAll('button')).find(b=>/^start$/i.test(b.textContent.trim())); if(b){b.click();return 'clicked';} return 'NOT FOUND'; })()")
print(f"[CDP] Start: {r}")

# Wait for LISTENING
for _ in range(40):
    time.sleep(0.5)
    p = cdp.panel()
    if p.get("PHASE") == "LISTENING":
        print(f"[CDP] LISTENING  FSM={p.get('FSM')}  SID={p.get('SID')}")
        break
else:
    print("[CDP] WARNING: did not reach LISTENING")

# ── Inject a big visible banner in Chrome telling the user to speak ───────────
BANNER_JS = r"""
(function() {
  var d = document.createElement('div');
  d.id = '__say_yes_banner';
  d.style.cssText = [
    'position:fixed', 'top:0', 'left:0', 'right:0',
    'background:#ff3333', 'color:#fff',
    'font-size:48px', 'font-weight:bold',
    'text-align:center', 'padding:24px',
    'z-index:99999', 'font-family:monospace',
    'letter-spacing:4px', 'box-shadow:0 4px 20px rgba(0,0,0,0.8)'
  ].join(';');
  d.textContent = '>>> SAY "YES" INTO YOUR MICROPHONE NOW <<<';
  document.body.appendChild(d);
})();
"""
cdp.exec(BANNER_JS)
print("\n>>> RED BANNER INJECTED IN CHROME WINDOW <<<")
print(">>> LOOK AT CHROME AND SAY 'YES' CLEARLY <<<")
print(">>> Capturing for 20 seconds... <<<\n")

cdp.flush()
timeline = []
t0 = time.time()

for tick in range(40):   # 40 × 0.5s = 20s
    time.sleep(0.5)
    elapsed = time.time() - t0
    for l, ts in cdp.flush():
        if any(x in l for x in ["[VOICE", "[NRS", "[SR"]):
            timeline.append((elapsed, l))
            print(f"  t={elapsed:5.1f}s  {l}")

# Remove banner
cdp.exec("var b=document.getElementById('__say_yes_banner'); if(b) b.remove();")

p = cdp.panel()
print(f"\n[DevPanel] {p}")
print(f"[CDP] Events captured: {len(timeline)}")

# ── Extract actual transcripts from [NRS] [MIC] recognised lines ──────────────
recognised = [re.search(r'recognised: "([^"]*)"', l) for _, l in timeline]
recognised = [m.group(1) for m in recognised if m]

onresult_count = sum(1 for _, l in timeline if "onresult" in l and "[VOICE" in l)
onsound_count  = sum(1 for _, l in timeline if "onsoundstart" in l)
fallback_count = sum(1 for _, l in timeline if "INTERIM FALLBACK" in l)
normalised     = [l for _, l in timeline if "[MIC] normalised" in l]
submitting     = [l for _, l in timeline if "[FSM] submitting" in l]

DIVIDER = "═" * 64
print(f"\n{DIVIDER}")
print("  RESULTS")
print(DIVIDER)
print(f"  onsoundstart fired:    {onsound_count}")
print(f"  onresult fired:        {onresult_count}")
print(f"  INTERIM FALLBACK:      {fallback_count}")
print(f"  Transcripts received:  {recognised}")
print(f"  normalised to yes/no:  {normalised}")
print(f"  FSM submit:            {submitting}")

print(f"\n{DIVIDER}")
print("  DIAGNOSIS")
print(DIVIDER)

if not recognised:
    print("""
  Chrome SR fired but delivered NO transcript to the voice handler.
  Cause: either onsoundstart never fired (ambient noise) or
  Chrome's SR service returned no text (speech not recognised).
  The interim fallback also did not fire.
""")
elif any(re.search(r'\b(yes|yeah|yep|yup|correct|affirmative)\b', t.lower()) for t in recognised):
    print(f"""
  MATCH FOUND — Chrome SR produced a yes-pattern transcript.
  Transcripts: {recognised}
  This should have advanced the FSM. Check [FSM] submitting logs.
""")
else:
    print(f"""
  CONFIRMED FAILURE POINT:
  File:  frontend/src/pages/StudentDashboard.tsx
  Lines: 115-119  (normaliseToYesNo)

  Chrome SR produced transcripts: {recognised}
  None matched the yes/no regex patterns.

  Current regex at line 116:
    /\\b(yes|yeah|yep|yup|correct|affirmative)\\b/

  MINIMAL FIX — add the words Chrome SR actually produces:
    Add each word from {recognised} to the relevant pattern.
""")

print(f"""
  FINAL TRACE:
  SpeechRecognition onresult          {'✓' if onresult_count else '✗'}  ({onresult_count} events)
  Interim fallback / final delivered  {'✓' if fallback_count else '✗'}
  [MIC] recognised callback entered   {'✓' if recognised else '✗'}  transcripts={recognised}
  normaliseToYesNo returned match     {'✓' if normalised else '✗'}
  submitStudentInput called           {'✓' if submitting else '✗'}
  FSM transitioned                    {'✓' if p.get('HTTP')=='200' else '✗'}
""")
