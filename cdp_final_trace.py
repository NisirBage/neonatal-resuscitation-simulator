"""
Final definitive trace.
Extracts CDP preview.properties so every [VOICE] onresult line shows
the actual transcript/isFinal/confidence values.
Clean run — no interceptors that modify SR behavior.
"""

import json, threading, time, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from urllib.request import urlopen
import websocket

CDP_URL = "http://localhost:9222"

def parse_arg(a):
    """Extract readable value from a CDP Runtime arg, including preview.properties."""
    t = a.get("type", "")
    if t == "string":
        return a["value"]
    if t in ("number", "boolean"):
        return str(a.get("value", ""))
    if t == "undefined":
        return "undefined"
    if t == "object":
        v = a.get("value")
        if v is not None:
            return json.dumps(v)
        preview = a.get("preview", {})
        props = preview.get("properties", [])
        if props:
            d = {p["name"]: p.get("value", "?") for p in props}
            return str(d)
        return preview.get("description", "...")
    return str(a.get("value", a.get("description", f"[{t}]")))

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
            parts = [parse_arg(a) for a in msg["params"].get("args", [])]
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


# Connect
with urlopen(f"{CDP_URL}/json") as r:
    tabs = json.loads(r.read())
tab = next((t for t in tabs if "5173" in t.get("url", "")), None)
if not tab: print("ERROR: app tab not found"); sys.exit(1)

cdp = CDP(tab["webSocketDebuggerUrl"])
cdp.call("Runtime.enable")
cdp.call("Page.enable")
print(f"[CDP] {tab['url']}")

# Clean reload — NO interceptors
cdp.call("Page.reload", {"ignoreCache": True})
print("[CDP] Clean reload")
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
        print(f"\n[CDP] LISTENING  FSM={p.get('FSM')}  SID={p.get('SID')}\n")
        break

cdp.flush()

# Inject visible banner IN CHROME
cdp.exec(r"""
  (function() {
    var d = document.createElement('div');
    d.id = '__trace_banner';
    d.style.cssText = 'position:fixed;top:0;left:0;right:0;background:#c00;color:#fff;font-size:40px;font-weight:bold;text-align:center;padding:20px;z-index:99999;font-family:monospace';
    d.textContent = '>>> SAY "YES" INTO YOUR MICROPHONE <<<';
    document.body.appendChild(d);
  })()
""")

print("="*64)
print(" RED BANNER IS NOW VISIBLE IN CHROME.")
print(" >>> LOOK AT CHROME AND SAY 'YES' CLEARLY <<<")
print(" Capturing every event for 30 seconds with full detail.")
print("="*64 + "\n")

timeline = []
t0 = time.time()

for tick in range(60):   # 30s
    time.sleep(0.5)
    elapsed = time.time() - t0
    for l, ts in cdp.flush():
        if any(x in l for x in ["[VOICE", "[NRS", "[SR"]):
            timeline.append((elapsed, l))
            print(f"  t={elapsed:5.1f}s  {l}")

cdp.exec("var b=document.getElementById('__trace_banner'); if(b) b.remove();")

p = cdp.panel()
print(f"\n[DevPanel] {p}")

# ── Full analysis ─────────────────────────────────────────────────────────────
DIVIDER = "═"*64

onresult_lines   = [(e, l) for e, l in timeline if "onresult" in l and "[VOICE" in l]
onsoundstart     = [(e, l) for e, l in timeline if "onsoundstart" in l]
onspeechstart    = [(e, l) for e, l in timeline if "onspeechstart" in l]
onend_lines      = [(e, l) for e, l in timeline if "onend" in l and "[VOICE" in l]
fallback_lines   = [(e, l) for e, l in timeline if "INTERIM FALLBACK" in l]
recognised_lines = [(e, l) for e, l in timeline if "[MIC] recognised" in l]
normalised_lines = [(e, l) for e, l in timeline if "[MIC] normalised" in l]
submitting_lines = [(e, l) for e, l in timeline if "[FSM] submitting" in l]
fsm_lines        = [(e, l) for e, l in timeline if "[FSM] transitioned" in l]
nospeech_lines   = [(e, l) for e, l in timeline if "no-speech" in l]

print(f"\n{DIVIDER}")
print("  EVENT COUNTS")
print(DIVIDER)
print(f"  onsoundstart:        {len(onsoundstart)}")
print(f"  onspeechstart:       {len(onspeechstart)}")
print(f"  onresult:            {len(onresult_lines)}")
print(f"  INTERIM FALLBACK:    {len(fallback_lines)}")
print(f"  [MIC] recognised:    {len(recognised_lines)}")
print(f"  [MIC] normalised:    {len(normalised_lines)}")
print(f"  [FSM] submitting:    {len(submitting_lines)}")
print(f"  [FSM] transitioned:  {len(fsm_lines)}")
print(f"  no-speech errors:    {len(nospeech_lines)}")

# Extract transcripts from onresult lines (now with full preview data)
transcripts = []
for _, l in onresult_lines:
    m = re.search(r"'transcript':\s*'([^']*)'", l)
    if not m: m = re.search(r'"transcript":\s*"([^"]*)"', l)
    if m: transcripts.append(m.group(1))

# Also from [MIC] recognised lines
recognised_words = []
for _, l in recognised_lines:
    m = re.search(r'recognised: "([^"]*)"', l)
    if m: recognised_words.append(m.group(1))

print(f"\n  Transcripts from onresult: {transcripts}")
print(f"  Words reached handler:     {recognised_words}")

print(f"\n{DIVIDER}")
print("  ROOT CAUSE IDENTIFICATION")
print(DIVIDER)

if len(onresult_lines) == 0 and len(onsoundstart) > 0:
    print(f"""
  FAILURE POINT:
  File: frontend/src/hooks/useSpeechRecognition.ts
  Line: 296  (inside onend handler)

  Statement: lastInterim &&

  Execution trace:
    recognition.start() → onstart → onaudiostart
    ← sound detected → onsoundstart → onspeechstart
    ← Chrome SR processes audio → (no transcript returned)
    ← onend fires
    → onend handler checks: lastInterim &&  ← FAILS (lastInterim = "")
    → fallback does NOT fire
    → onFinalResultRef.current is never called
    → voiceHandlerRef.current is never called
    → normaliseToYesNo() is never called
    → submitStudentInput() is never called
    → FSM does not advance

  Why it fails:
    Chrome's SR service detects speech-like audio (onspeechstart fires)
    but returns no transcript (onresult never fires).
    This happens when the utterance is too brief, audio quality is poor,
    or the SR service cannot produce a confident recognition.
    lastInterim remains "" so the interim fallback at line 296 is skipped.

  Minimal fix:
    Add a retry-speak path when onspeechstart fired but onresult did not.
    Track whether onspeechstart occurred in a local variable inside
    launchRecognition(), similar to how lastInterim is tracked.
    In onend, if onspeechStarted && !finalDelivered && !lastInterim,
    speak a retry prompt to tell the user their speech was heard
    but not transcribed.

    OR: change recognition.lang from "en-US" to "" (empty string) to let
    Chrome use the browser's default language — may improve recognition.
""")

elif len(recognised_lines) > 0 and len(normalised_lines) == 0:
    print(f"""
  FAILURE POINT:
  File: frontend/src/pages/StudentDashboard.tsx
  Line: 115-116  (normaliseToYesNo)

  Statement: if (/\\b(yes|yeah|yep|yup|correct|affirmative)\\b/.test(t)) return "yes";

  Chrome SR produced transcripts: {recognised_words}
  None matched the yes/no regex pattern.

  Minimal fix: add the actual words Chrome produced to the regex.
""")

elif len(normalised_lines) > 0 and len(submitting_lines) == 0:
    print(f"""
  FAILURE POINT:
  File: frontend/src/pages/StudentDashboard.tsx
  Line: 395  (voice handler guard)

  Statement: if (!state || !sid || busyRef.current) return;

  normaliseToYesNo returned a match but submitStudentInput was not called.
  Check: busyRef.current (BUSY={p.get('BUSY','?')}) state/sid values.
""")

elif len(submitting_lines) > 0 and len(fsm_lines) == 0:
    print(f"""
  FAILURE POINT: HTTP layer or FSM backend.
  submitStudentInput was called but FSM did not transition.
  HTTP status: {p.get('HTTP','?')}
""")

elif len(fsm_lines) > 0:
    print(f"""
  ALL STAGES PASSED — FSM transitioned.
  Final state: {p.get('FSM','?')}
  The voice pipeline is working correctly.
""")

else:
    print(f"""
  Could not determine failure point from this run.
  Full timeline has {len(timeline)} events.
  onresult={len(onresult_lines)} recognised={len(recognised_lines)}
  no-speech={len(nospeech_lines)}
""")
