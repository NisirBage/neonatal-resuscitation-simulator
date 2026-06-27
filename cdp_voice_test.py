"""
CDP-based voice pipeline verification.

Connects to Chrome's remote debugging port, injects a mock SpeechRecognition
that simulates the Chrome isFinal-omission bug, and drives the full NRS voice
pipeline.  All [VOICE] and [NRS] console messages are captured and reported.

Usage:
    python cdp_voice_test.py
"""
import json, threading, time, sys, io
# Force UTF-8 stdout so arrow/box chars don't crash on cp1252 terminals
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from urllib.request import urlopen
import websocket   # pip install websocket-client

CDP_URL  = "http://localhost:9222"
BASE_API = "http://127.0.0.1:8000"

# ── CDP helpers ───────────────────────────────────────────────────────────────

class CDP:
    def __init__(self, ws_url: str):
        self._id      = 0
        self._lock    = threading.Lock()
        self._calls   = {}          # id -> Event + result
        self._logs    = []
        self._ready   = threading.Event()
        self._ws      = websocket.WebSocketApp(
            ws_url,
            on_message=self._on_message,
            on_open=self._on_open,
            on_error=lambda ws, e: print(f"[CDP WS error] {e}"),
        )
        t = threading.Thread(target=self._ws.run_forever, daemon=True)
        t.start()
        if not self._ready.wait(timeout=8):
            raise TimeoutError("CDP WebSocket did not connect within 8s")

    def _on_open(self, ws):
        self._ready.set()

    def _on_message(self, ws, raw):
        msg = json.loads(raw)
        # console event
        if msg.get("method") == "Runtime.consoleAPICalled":
            args  = msg["params"].get("args", [])
            parts = []
            for a in args:
                if a["type"] == "string":
                    parts.append(a["value"])
                elif a["type"] == "object":
                    parts.append(json.dumps(a.get("value") or a.get("preview", {}).get("description", "...")))
                else:
                    parts.append(str(a.get("value", "")))
            self._logs.append(" ".join(parts))
        # call response
        mid = msg.get("id")
        if mid and mid in self._calls:
            ev, holder = self._calls[mid]
            holder.append(msg)
            ev.set()

    def call(self, method, params=None, timeout=10):
        with self._lock:
            self._id += 1
            cid = self._id
        ev     = threading.Event()
        holder = []
        self._calls[cid] = (ev, holder)
        self._ws.send(json.dumps({"id": cid, "method": method,
                                  "params": params or {}}))
        if not ev.wait(timeout):
            raise TimeoutError(f"CDP call timed out: {method}")
        return holder[0]

    def exec(self, js, await_promise=False):
        r = self.call("Runtime.evaluate", {
            "expression":    js,
            "awaitPromise":  await_promise,
            "returnByValue": True,
        })
        res = r.get("result", {}).get("result", {})
        if res.get("subtype") == "error":
            raise RuntimeError(f"JS error: {res.get('description')}")
        return res.get("value")

    def flush_logs(self):
        logs, self._logs = self._logs[:], []
        return logs


# ── Find the app tab ──────────────────────────────────────────────────────────

with urlopen(f"{CDP_URL}/json") as r:
    tabs = json.loads(r.read())

app_tab = next(
    (t for t in tabs if "localhost:5173" in t.get("url", "")),
    None
)
if not app_tab:
    print("ERROR: localhost:5173 tab not found in Chrome. Is the app running?")
    sys.exit(1)

ws_url = app_tab["webSocketDebuggerUrl"]
print(f"[CDP] Connected to tab: {app_tab['title']} ({app_tab['url']})")

cdp = CDP(ws_url)
cdp.call("Runtime.enable")
cdp.call("Console.enable")

# ── Enable dev panel ──────────────────────────────────────────────────────────

# ── Inject mock SpeechRecognition BEFORE page scripts run ────────────────────
# Must use Page.addScriptToEvaluateOnNewDocument so the mock is in place
# when React mounts and useMemo captures window.SpeechRecognition.
#
# Strategy: override window.SpeechRecognition and window.webkitSpeechRecognition
# with a mock class.  Because the React app has already mounted, we must also
# directly trigger the voice pipeline by invoking the already-constructed
# recognitionRef instances.  Instead, we inject the mock so that the NEXT
# launchRecognition() call (triggered by startContinuous) gets our mock.
#
# The mock simulates the Chrome isFinal-omission bug:
#   1. Calls onstart / onaudiostart / onsoundstart / onspeechstart
#   2. Fires onresult with isFinal=false (interim "yes")
#   3. Fires onend WITHOUT isFinal=true
#
# Our interim fallback in useSpeechRecognition.ts should detect this and
# invoke the callback with "yes" anyway.

MOCK_SR_JS = r"""
(function() {
  var _instances = [];
  var _logs = [];

  function MockRecognition() {
    this.continuous       = false;
    this.interimResults   = false;
    this.lang             = "en-US";
    this.maxAlternatives  = 1;
    this.onstart          = null;
    this.onaudiostart     = null;
    this.onsoundstart     = null;
    this.onspeechstart    = null;
    this.onend            = null;
    this.onerror          = null;
    this.onresult         = null;
    this._started         = false;
    this._aborted         = false;
    _instances.push(this);
  }

  MockRecognition.prototype.start = function() {
    if (this._started) throw new Error("Already started");
    this._started = true;
    this._aborted = false;
    var self = this;
    _logs.push("[MOCK-SR] start() called");
    console.log("[MOCK-SR] start() called — will simulate interim-only result in 800ms");
    setTimeout(function() {
      if (self._aborted) return;
      self.onstart && self.onstart();
      setTimeout(function() {
        if (self._aborted) return;
        self.onaudiostart && self.onaudiostart();
        setTimeout(function() {
          if (self._aborted) return;
          self.onsoundstart && self.onsoundstart();
          setTimeout(function() {
            if (self._aborted) return;
            self.onspeechstart && self.onspeechstart();
            // Simulate interim result "yes" (isFinal=false)
            setTimeout(function() {
              if (self._aborted) return;
              if (self.onresult) {
                var evt = {
                  resultIndex: 0,
                  results: {
                    0: { 0: { transcript: window._mockSRTranscript || "yes", confidence: 0.91 }, isFinal: false, length: 1 },
                    length: 1
                  }
                };
                _logs.push("[MOCK-SR] onresult(isFinal=false, transcript=" + (window._mockSRTranscript || "yes") + ")");
                console.log("[MOCK-SR] firing onresult isFinal=false transcript=" + (window._mockSRTranscript || "yes"));
                self.onresult(evt);
              }
              // Fire onend WITHOUT isFinal=true — simulates the Chrome bug
              setTimeout(function() {
                if (self._aborted) return;
                _logs.push("[MOCK-SR] onend (no isFinal=true sent — Chrome bug simulation)");
                console.log("[MOCK-SR] firing onend — no isFinal=true was sent");
                self.onend && self.onend();
              }, 100);
            }, 200);
          }, 100);
        }, 100);
      }, 100);
    }, 300);
  };

  MockRecognition.prototype.stop = function() {
    this._started = false;
    var self = this;
    setTimeout(function() { self.onend && self.onend(); }, 50);
  };

  MockRecognition.prototype.abort = function() {
    this._aborted = true;
    this._started = false;
  };

  window.SpeechRecognition        = MockRecognition;
  window.webkitSpeechRecognition  = MockRecognition;
  window._mockSRInstances = _instances;
  window._mockSRLogs      = _logs;
  window._mockSRTranscript = "yes";   // default spoken word

  console.log("[MOCK-SR] SpeechRecognition replaced with mock (Chrome isFinal-bug simulator)");
})();
"""

# Register the mock to run before every page script
cdp.call("Page.enable")
cdp.call("Page.addScriptToEvaluateOnNewDocument", {"source": MOCK_SR_JS})
print("[CDP] Mock registered via addScriptToEvaluateOnNewDocument")

# Hard reload so React mounts with the mock constructor already in place
cdp.call("Page.reload", {"ignoreCache": True})
print("[CDP] Page reloading...")
time.sleep(4)   # wait for React to fully mount

# Now also set localStorage (must be done after page load)
cdp.exec("localStorage.setItem('NRS_DEV', '1')")
print("[CDP] NRS_DEV=1 set in localStorage")

# Verify the mock is in place
mock_name = cdp.exec("window.SpeechRecognition?.name || window.webkitSpeechRecognition?.name || 'NOT FOUND'")
print(f"[CDP] window.SpeechRecognition.name = {mock_name}")

cdp.flush_logs()  # clear boot noise

# ── Session is started by the React app when Start button is clicked ──────────
# (no separate REST call needed)

# ── Helper: capture logs ──────────────────────────────────────────────────────

def grab_logs(label, wait=1.5):
    time.sleep(wait)
    logs = cdp.flush_logs()
    relevant = [l for l in logs if any(tag in l for tag in ["[VOICE", "[NRS", "[MOCK-SR", "VOICE", "NRS"])]
    if relevant:
        print(f"\n=== Console logs during: {label} ===")
        for l in relevant:
            print(f"  {l}")
    else:
        print(f"  (no [VOICE]/[NRS] logs during: {label})")
    return relevant

# ── Test 1: Simulate "yes" via mock SpeechRecognition ────────────────────────
# The app's React UI calls startContinuous() which calls launchRecognition().
# Since we replaced window.SpeechRecognition/webkitSpeechRecognition, the next
# launchRecognition() call will get our mock.
#
# We trigger startContinuous() by clicking the Start button in the UI,
# or by directly calling the handler.  The simplest approach is to use CDP
# to invoke the React state setter directly.
#
# However, React internals are not easily accessible.  Instead, let's
# simulate what the app does: wait for TTS to call startContinuous, then
# watch the logs.

print("\n[TEST] Waiting for React to boot and TTS to start speaking...")
time.sleep(3)
grab_logs("initial boot")

# Check dev panel state
dev_panel = cdp.exec("""
  (() => {
    var spans = document.querySelectorAll('.font-mono span');
    var result = {};
    spans.forEach(function(s) {
      var label = s.querySelector('.text-green-600');
      if (label) result[label.textContent] = s.textContent.replace(label.textContent, '').trim();
    });
    return JSON.stringify(result);
  })()
""")
print(f"\n[DevPanel] {dev_panel}")

# ── Trigger startContinuous manually via CDP ──────────────────────────────────
# The StudentDashboard calls startContinuous when voicePhase becomes 'listening'.
# We can trigger this by dispatching a custom event or by finding the React fiber.
# Easiest: find the "Start Simulation" button and click it.

start_btn = cdp.exec("""
  (() => {
    var btns = Array.from(document.querySelectorAll('button'));
    var btn = btns.find(b => b.textContent.toLowerCase().includes('start'));
    if (btn) { btn.click(); return 'clicked: ' + btn.textContent.trim(); }
    return 'button not found; buttons=' + btns.map(b=>b.textContent.trim()).join('|');
  })()
""")
print(f"\n[CDP] Start button: {start_btn}")
time.sleep(4)
grab_logs("after Start click + TTS")

# ── Allow mock recognition to fire ───────────────────────────────────────────
print("\n[TEST] Waiting for mock SpeechRecognition to simulate 'yes' utterance...")
time.sleep(3)
logs_step1 = grab_logs("step1: yes → confirm_birth")

# Check dev panel again
dev_panel = cdp.exec("""
  (() => {
    var spans = document.querySelectorAll('.font-mono span');
    var result = {};
    spans.forEach(function(s) {
      var label = s.querySelector('.text-green-600');
      if (label) result[label.textContent] = s.textContent.replace(label.textContent, '').trim();
    });
    return JSON.stringify(result);
  })()
""")
print(f"\n[DevPanel after step1] {dev_panel}")

# Check mock SR log
mock_logs = cdp.exec("JSON.stringify(window._mockSRLogs || [])")
print(f"\n[MockSR internal log] {mock_logs}")

# ── Steps 2 onward: change transcript word and watch ─────────────────────────
step_words = ["yes", "yes", "no", "yeah", "nope", "yes", "yes", "yes"]
step_labels = [
    "placed_on_chest",
    "is_baby_crying → no",
    "is_apneic",
    "hr_above_100 → no",
    "start_ventilation",
    "hr_increasing",
    "final",
]

for i, (word, label) in enumerate(zip(step_words[1:], step_labels), start=2):
    cdp.exec(f"window._mockSRTranscript = '{word}'")
    print(f"\n[TEST] Step {i}: speaking '{word}' ({label})")
    time.sleep(3)
    grab_logs(f"step{i}: {label}")
    dev_panel = cdp.exec("""
      (() => {
        var spans = document.querySelectorAll('.font-mono span');
        var result = {};
        spans.forEach(function(s) {
          var label = s.querySelector('.text-green-600');
          if (label) result[label.textContent] = s.textContent.replace(label.textContent, '').trim();
        });
        return JSON.stringify(result);
      })()
    """)
    print(f"  [DevPanel] {dev_panel}")

# ── Final report ──────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("VOICE PIPELINE VERIFICATION COMPLETE")
print("="*60)

# Check dev panel one more time
final_panel = cdp.exec("""
  (() => {
    var spans = document.querySelectorAll('.font-mono span');
    var result = {};
    spans.forEach(function(s) {
      var label = s.querySelector('.text-green-600');
      if (label) result[label.textContent] = s.textContent.replace(label.textContent, '').trim();
    });
    return JSON.stringify(result);
  })()
""")
print(f"\nFinal dev panel state: {final_panel}")

all_logs = cdp.flush_logs()
voice_logs  = [l for l in all_logs if "[VOICE" in l]
interim_hits = [l for l in voice_logs if "INTERIM FALLBACK" in l]
final_hits   = [l for l in voice_logs if "FINAL transcript" in l]

print(f"\nVoice logs captured: {len(voice_logs)}")
print(f"  isFinal=true hits:    {len(final_hits)}")
print(f"  INTERIM FALLBACK hits: {len(interim_hits)}")

if interim_hits:
    print("\n[CONFIRMED] Interim fallback fired — Chrome isFinal bug workaround is working")
    for l in interim_hits:
        print(f"  {l}")
elif final_hits:
    print("\n[CONFIRMED] isFinal=true was delivered normally (Chrome sent final result)")
    for l in final_hits:
        print(f"  {l}")
else:
    print("\n[INCONCLUSIVE] No final/fallback hits captured. Check logs above for details.")
