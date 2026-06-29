"""
Capture every transcript string Chrome SR produces.
Patches recognition.onresult to console.log the transcript text directly
so CDP can see it as a plain string (not [Object]).
Reports: what Chrome SR actually hears and whether it matches yes/no patterns.
"""

import json, threading, time, sys, io
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
            on_open=lambda ws: self._ready.set(),
            on_error=lambda ws, e: print(f"WS error: {e}"))
        threading.Thread(target=self._ws.run_forever, daemon=True).start()
        if not self._ready.wait(10): raise TimeoutError("CDP timeout")

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
            self._logs.append(" ".join(parts))
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

    def exec(self, js, await_promise=False, timeout=15):
        r = self.call("Runtime.evaluate", {
            "expression": js, "awaitPromise": await_promise, "returnByValue": True
        }, timeout)
        res = r.get("result", {}).get("result", {})
        if res.get("subtype") == "error": raise RuntimeError(res.get("description"))
        return res.get("value")

    def flush(self):
        logs, self._logs = self._logs[:], []; return logs

    def panel(self):
        raw = self.exec("JSON.stringify((() => { var s=document.querySelectorAll('.font-mono span'); var r={}; s.forEach(function(n){var l=n.querySelector('.text-green-600'); if(l)r[l.textContent]=n.textContent.replace(l.textContent,'').trim()}); return r; })())")
        return json.loads(raw) if raw else {}


# Inject a transcript-logging wrapper BEFORE page scripts run.
# This patches SR.prototype.start so each instance also gets onresult patched
# to emit a plain string log for every transcript received.
SR_WRAP = """
(function() {
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return;
  var origStart = SR.prototype.start;
  SR.prototype.start = function() {
    window.__currentSR = this;
    window.__srCount   = (window.__srCount||0)+1;
    var _origOnresult  = null;
    var self = this;

    // Proxy onresult to also emit plain-string logs
    Object.defineProperty(this, 'onresult', {
      get: function() { return _origOnresult; },
      set: function(fn) {
        _origOnresult = function(event) {
          for (var i = event.resultIndex; i < event.results.length; i++) {
            var res   = event.results[i];
            var text  = (res[0] && res[0].transcript ? res[0].transcript : '').trim();
            var isFin = res.isFinal || false;
            var conf  = res[0] ? (res[0].confidence||0).toFixed(3) : '0';
            // Plain string — CDP can capture this fully
            console.log('[SR-TRANSCRIPT] #' + window.__srCount +
              ' isFinal=' + isFin +
              ' confidence=' + conf +
              ' transcript="' + text + '"');
          }
          fn && fn(event);
        };
      },
      configurable: true
    });

    console.log('[SR-WRAP] start() #' + window.__srCount);
    return origStart.call(this);
  };
  console.log('[SR-WRAP] intercepted');
})();
"""

# Connect
with urlopen(f"{CDP_URL}/json") as r:
    tabs = json.loads(r.read())
tab = next((t for t in tabs if "5173" in t.get("url", "")), None)
if not tab:
    print("ERROR: app tab not found"); sys.exit(1)

cdp = CDP(tab["webSocketDebuggerUrl"])
cdp.call("Runtime.enable")
cdp.call("Page.enable")
print(f"[CDP] {tab['url']}")

cdp.call("Page.addScriptToEvaluateOnNewDocument", {"source": SR_WRAP})
cdp.call("Page.reload", {"ignoreCache": True})
print("[CDP] Reloaded with transcript interceptor")
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

cdp.flush()

# ── 30-second transcript capture window ──────────────────────────────────────
DIVIDER = "═" * 64
print(f"""
{DIVIDER}
  TRANSCRIPT CAPTURE — 30 seconds
  Speak YES clearly into your microphone when you see this prompt.
  Every word Chrome SR hears will be logged.
{DIVIDER}
""")

transcripts_seen = []  # list of (isFinal, text)
timeline = []
t0 = time.time()

for tick in range(60):   # 60 × 0.5s = 30s
    time.sleep(0.5)
    elapsed = time.time() - t0
    for l in cdp.flush():
        tag = ""
        if "[SR-TRANSCRIPT]" in l:
            tag = "TRANSCRIPT"
        elif "[NRS" in l and "[MIC]" in l:
            tag = "MIC"
        elif "[VOICE" in l:
            tag = "VOICE"
        if tag:
            timeline.append((elapsed, tag, l))
            sys.stdout.write(f"\n  t={elapsed:5.1f}s  [{tag}] {l}")
            sys.stdout.flush()

            if "[SR-TRANSCRIPT]" in l:
                # Parse isFinal and transcript from the log line
                try:
                    is_final_str = "isFinal=true" in l
                    # extract transcript="..."
                    import re
                    m = re.search(r'transcript="([^"]*)"', l)
                    text = m.group(1) if m else ""
                    transcripts_seen.append((is_final_str, text))
                except Exception:
                    pass

print(f"\n\n[CDP] Capture complete. Events: {len(timeline)}")

p = cdp.panel()
print(f"[DevPanel] {p}")

# ── Analysis ──────────────────────────────────────────────────────────────────
print(f"\n{DIVIDER}")
print("  ALL TRANSCRIPTS CHROME SR PRODUCED")
print(DIVIDER)

if not transcripts_seen:
    print("  NONE — SR fired no onresult events (silent environment or no speech detected)")
else:
    # Group by unique texts
    from collections import Counter
    counts = Counter(text for _, text in transcripts_seen)
    print(f"  Total onresult events: {len(transcripts_seen)}")
    print(f"  Unique transcripts:")
    for text, count in counts.most_common():
        import re
        t = text.strip().lower()
        matches_yes = bool(re.search(r'\b(yes|yeah|yep|yup|correct|affirmative)\b', t))
        matches_no  = bool(re.search(r'\b(no|nope|negative|nah)\b', t))
        would_match = "YES" if matches_yes else ("NO" if matches_no else "NO MATCH")
        print(f"    {count:3d}×  {repr(text):30s}  → normaliseToYesNo: {would_match}")

    final_transcripts = [(f, t) for f, t in transcripts_seen if f]
    interim_only      = [(f, t) for f, t in transcripts_seen if not f]
    print(f"\n  isFinal=true events:  {len(final_transcripts)}")
    print(f"  isFinal=false events: {len(interim_only)}")
    if final_transcripts:
        for _, t in final_transcripts:
            print(f"    FINAL: {repr(t)}")

print(f"\n{DIVIDER}")
print("  DIAGNOSIS")
print(DIVIDER)

all_texts = [t for _, t in transcripts_seen]

import re
yes_texts = [t for t in all_texts if re.search(r'\b(yes|yeah|yep|yup|correct|affirmative)\b', t.lower())]
no_texts  = [t for t in all_texts if re.search(r'\b(no|nope|negative|nah)\b', t.lower())]

# Check what the FSM and MIC logs show
mic_lines  = [l for _, tag, l in timeline if tag == "MIC"]
voice_lines= [l for _, tag, l in timeline if tag == "VOICE"]

print(f"""
  SR results produced:     {len(all_texts)}
  Matched yes patterns:    {len(yes_texts)}  {yes_texts[:3]}
  Matched no patterns:     {len(no_texts)}   {no_texts[:3]}
  FSM after test:          {p.get("FSM","?")}
  HTTP status:             {p.get("HTTP","?")}
""")

if not all_texts:
    print("  ROOT CAUSE: Chrome SR never fired onresult.")
    print("  Mic may be capturing silence. Check ambient noise or mic gain.")
elif yes_texts or no_texts:
    print("  Chrome SR DID produce matching transcripts.")
    print("  FSM should have advanced. Check [MIC] normalised log.")
    for l in mic_lines:
        print(f"  {l}")
else:
    # Real words were produced but none matched
    sample = list(counts.most_common(5))
    print("  Chrome SR produced transcripts but NONE matched yes/no patterns.")
    print(f"  Sample transcripts: {sample}")
    print()
    print("  CONCLUSION:")
    print(f"  File:  frontend/src/pages/StudentDashboard.tsx")
    print(f"  Line:  ~116")
    print(f"  Issue: normaliseToYesNo() regex does not match what Chrome SR")
    print(f"         produces for this user's speech.")
    print()
    print("  The user's speech (possibly non-native English accent or word choice)")
    print("  is transcribed by Chrome SR as words outside the yes/no regex set.")
    print()
    print("  MINIMAL FIX: expand normaliseToYesNo() to include the actual words")
    print("  Chrome produced (shown above in 'Unique transcripts' table).")
    print()
    print("  normaliseToYesNo is at StudentDashboard.tsx lines 115-119:")
    print('    /\\b(yes|yeah|yep|yup|correct|affirmative)\\b/ → "yes"')
    print('    /\\b(no|nope|negative|nah)\\b/                 → "no"')
