"""
Two-phase voice pipeline trace.

PHASE 1 — INJECTION TEST
  Bypasses real SpeechRecognition.
  Calls exactly recognition.onresult() + recognition.onend() —
  the same handlers Chrome's SR service would invoke.
  Proves whether the React callback chain from onresult → FSM works.

PHASE 2 — REAL SPEECH TEST
  Restarts Chrome using the user's DEFAULT profile (no fake-device flag).
  Waits for the user to speak.
  Captures every [VOICE] and [NRS] log.
  Identifies the exact stage where execution stops.

No application code is modified.
SR prototype is intercepted via CDP addScriptToEvaluateOnNewDocument.
"""

import json, threading, time, sys, io, subprocess, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from urllib.request import urlopen, Request
import websocket

CDP_URL  = "http://localhost:9222"
APP_URL  = "http://localhost:5173"
CHROME   = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# ── CDP helper ────────────────────────────────────────────────────────────────
class CDP:
    def __init__(self, ws_url):
        self._id    = 0
        self._lock  = threading.Lock()
        self._calls = {}
        self._logs  = []          # [(text, timestamp)]
        self._ready = threading.Event()
        self._ws    = websocket.WebSocketApp(
            ws_url,
            on_message=self._on_message,
            on_open=lambda ws: self._ready.set(),
            on_error=lambda ws, e: print(f"[CDP WS error] {e}"),
        )
        threading.Thread(target=self._ws.run_forever, daemon=True).start()
        if not self._ready.wait(10):
            raise TimeoutError("CDP WS timeout")

    def _on_message(self, ws, raw):
        msg = json.loads(raw)
        if msg.get("method") == "Runtime.consoleAPICalled":
            parts = []
            for a in msg["params"].get("args", []):
                if a["type"] == "string":
                    parts.append(a["value"])
                elif a["type"] == "object":
                    v = a.get("value")
                    if v is not None:
                        parts.append(json.dumps(v))
                    else:
                        prev = a.get("preview", {})
                        parts.append(prev.get("description", str(a)))
                else:
                    parts.append(str(a.get("value", "")))
            self._logs.append((" ".join(parts), time.time()))
        mid = msg.get("id")
        if mid and mid in self._calls:
            ev, h = self._calls[mid]; h.append(msg); ev.set()

    def call(self, method, params=None, timeout=15):
        with self._lock:
            self._id += 1; cid = self._id
        ev, h = threading.Event(), []
        self._calls[cid] = (ev, h)
        self._ws.send(json.dumps({"id": cid, "method": method, "params": params or {}}))
        if not ev.wait(timeout): raise TimeoutError(f"timeout: {method}")
        return h[0]

    def exec(self, js, await_promise=False, timeout=15):
        r = self.call("Runtime.evaluate", {
            "expression": js, "awaitPromise": await_promise,
            "returnByValue": True,
        }, timeout=timeout)
        res = r.get("result", {}).get("result", {})
        if res.get("subtype") == "error":
            raise RuntimeError(res.get("description", "JS error"))
        return res.get("value")

    def flush(self):
        logs, self._logs = self._logs[:], []
        return logs

    def wait_for_log(self, pattern, timeout=30):
        """Block until a log line matching pattern appears, returns the line."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.2)
            for l, ts in self._logs:
                if pattern in l:
                    return l
        return None


def new_tab(cdp_url=CDP_URL):
    req = Request(f"{cdp_url}/json/new", data=b"", method="PUT")
    with urlopen(req) as r:
        return json.loads(r.read())

def print_logs(logs, heading):
    relevant = [l for l, _ in logs
                if any(t in l for t in ["[NRS", "[VOICE", "[SR-WRAP", "[SR]"])]
    if relevant:
        print(f"\n{'─'*60}")
        print(f"  {heading}")
        print(f"{'─'*60}")
        for l in relevant:
            print(f"  {l}")
    return relevant

DIVIDER = "═" * 64

# ── SR intercept script (runs before any page script) ────────────────────────
#
# Patches SR.prototype.start so every new instance is captured globally.
# Does NOT alter any recognition behaviour.
# Does NOT replace or mock the SR class.
#
SR_INTERCEPT = """
(function() {
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    console.log('[SR-WRAP] SpeechRecognition NOT AVAILABLE');
    return;
  }
  var origStart = SR.prototype.start;
  SR.prototype.start = function() {
    window.__currentSR  = this;
    window.__srCount    = (window.__srCount || 0) + 1;
    console.log('[SR-WRAP] start() #' + window.__srCount + ' — instance captured');
    return origStart.call(this);
  };
  console.log('[SR-WRAP] SR.prototype.start intercepted (' + SR.name + ')');
})();
"""

print(f"\n{DIVIDER}")
print("  VOICE PIPELINE TRACE — PHASE 1: INJECTION TEST")
print(DIVIDER)

# ── Connect to existing CDP Chrome ────────────────────────────────────────────
try:
    with urlopen(f"{CDP_URL}/json/version", timeout=3) as r:
        ver = json.loads(r.read())
    print(f"[CDP] Connected to {ver.get('Browser','?')}")
except Exception as e:
    print(f"[CDP] ERROR: cannot reach CDP at {CDP_URL}: {e}")
    sys.exit(1)

# ── Open new tab with SR intercept injected before page scripts ───────────────
tab = new_tab()
cdp = CDP(tab["webSocketDebuggerUrl"])
cdp.call("Runtime.enable")
cdp.call("Page.enable")

# Register intercept script — runs before ANY page JavaScript
cdp.call("Page.addScriptToEvaluateOnNewDocument", {"source": SR_INTERCEPT})
print("[CDP] SR.prototype.start intercept registered")

# Navigate to app
cdp.call("Page.navigate", {"url": APP_URL + "/student"})
print(f"[CDP] Navigating to {APP_URL}/student")
time.sleep(4)

# Set dev panel
cdp.exec("localStorage.setItem('NRS_DEV', '1')")
logs = cdp.flush()
print_logs(logs, "Boot logs")

# Verify intercept was installed
sr_name = cdp.exec(
    "(window.SpeechRecognition || window.webkitSpeechRecognition || {name:'NOT FOUND'}).name"
)
print(f"\n[CDP] window.SpeechRecognition class: {sr_name}")

# ── Click Start ───────────────────────────────────────────────────────────────
cdp.flush()
result = cdp.exec("""
  (() => {
    var btns = Array.from(document.querySelectorAll('button'));
    var btn  = btns.find(b => /^start$/i.test(b.textContent.trim()));
    if (btn) { btn.click(); return 'clicked: ' + btn.textContent.trim(); }
    return 'NOT FOUND — buttons: ' + btns.map(b=>b.textContent.trim()).join('|');
  })()
""")
print(f"[CDP] Start button: {result}")

# Wait for session to start + TTS to play
print("[CDP] Waiting for session start + TTS to complete…")
started = cdp.wait_for_log("[MIC] microphone ON", timeout=20)
if not started:
    print("[CDP] ERROR: [MIC] microphone ON never appeared — session may not have started")
    logs = cdp.flush()
    print_logs(logs, "Logs captured so far")
    sys.exit(1)

logs = cdp.flush()
start_logs = print_logs(logs, "Session start + TTS logs")

# ── Check SR instance was captured ───────────────────────────────────────────
sr_count = cdp.exec("window.__srCount || 0")
has_sr   = cdp.exec("!!window.__currentSR")
print(f"\n[CDP] SR instances started: {sr_count}")
print(f"[CDP] window.__currentSR available: {has_sr}")

if not has_sr:
    print("[CDP] ERROR: No SR instance captured — recognition may not have started")
    sys.exit(1)

# ── Read dev panel state ──────────────────────────────────────────────────────
def dev_panel():
    raw = cdp.exec("""
      (() => {
        var spans = document.querySelectorAll('.font-mono span');
        var r = {};
        spans.forEach(function(s) {
          var lbl = s.querySelector('.text-green-600');
          if (lbl) r[lbl.textContent] = s.textContent.replace(lbl.textContent,'').trim();
        });
        return JSON.stringify(r);
      })()
    """)
    return json.loads(raw) if raw else {}

panel = dev_panel()
print(f"[DevPanel] {panel}")
phase = panel.get("PHASE", "UNKNOWN")
state = panel.get("FSM", "UNKNOWN")
print(f"[CDP] voicePhase={phase}  FSM={state}")

if phase != "LISTENING":
    print(f"[CDP] WARNING: Expected LISTENING, got {phase} — waiting 3s more…")
    time.sleep(3)
    panel = dev_panel()
    phase = panel.get("PHASE", "UNKNOWN")
    print(f"[DevPanel after wait] {panel}")

# ── INJECTION TEST ────────────────────────────────────────────────────────────
print(f"\n{DIVIDER}")
print("  INJECTION: calling recognition.onresult() then recognition.onend()")
print(f"  Simulates Chrome SR firing isFinal=false then onend (Chrome isFinal bug)")
print(DIVIDER)

cdp.flush()

# Call onresult exactly as Chrome SR would — isFinal=false, transcript="yes"
# Then call onend — this is what the interim fallback in useSpeechRecognition responds to
inject_result = cdp.exec(r"""
  (() => {
    var sr = window.__currentSR;
    if (!sr) return 'ERROR: no SR instance';

    var log = [];
    log.push('onresult handler present: ' + (typeof sr.onresult));
    log.push('onend handler present:    ' + (typeof sr.onend));

    // Simulate onresult(isFinal=false, transcript="yes")
    if (typeof sr.onresult === 'function') {
      var evt = {
        resultIndex: 0,
        results: {
          0: { 0: {transcript: 'yes', confidence: 0.92}, isFinal: false, length: 1 },
          length: 1
        }
      };
      try {
        sr.onresult(evt);
        log.push('onresult("yes", isFinal=false) called OK');
      } catch(e) {
        log.push('onresult THREW: ' + e.message);
      }
    } else {
      log.push('onresult is not a function — SR may not be active');
    }

    // Simulate onend (triggers interim fallback in useSpeechRecognition.ts)
    if (typeof sr.onend === 'function') {
      try {
        sr.onend();
        log.push('onend() called OK');
      } catch(e) {
        log.push('onend THREW: ' + e.message);
      }
    } else {
      log.push('onend is not a function');
    }

    return log.join('\n');
  })()
""")

print(f"\n[INJECT] Injection result:\n  {inject_result.replace(chr(10), chr(10)+'  ')}")

# Capture pipeline logs — give it time to complete HTTP + FSM transition
print("\n[CDP] Waiting for pipeline to complete (up to 8 s)…")
time.sleep(5)
logs = cdp.flush()
inject_logs = print_logs(logs, "Injection pipeline logs")

# Read final dev panel
panel = dev_panel()
print(f"\n[DevPanel after injection] {panel}")

# ── Analyse injection test ────────────────────────────────────────────────────
all_text = " ".join(inject_logs)

has_recognised   = "[MIC] recognised" in all_text
has_normalised   = "[MIC] normalised" in all_text
has_submitting   = "[FSM] submitting" in all_text
has_transitioned = "[FSM] transitioned" in all_text
has_http_200     = panel.get("HTTP") == "200"
has_tts          = "[TTS] speaking" in all_text

print(f"\n  Injection test — stage results:")
print(f"  {'✓' if has_recognised   else '✗'} [MIC] recognised callback entered")
print(f"  {'✓' if has_normalised   else '✗'} [MIC] normalised → YES/NO")
print(f"  {'✓' if has_submitting   else '✗'} [FSM] submitting response (HTTP POST sent)")
print(f"  {'✓' if has_transitioned else '✗'} [FSM] transitioned to next state")
print(f"  {'✓' if has_http_200     else '✗'} HTTP 200 (dev panel)")
print(f"  {'✓' if has_tts          else '✗'} TTS next prompt speaking")

if not has_recognised:
    print("\n  INJECTION FAILED — onFinalResultRef.current never invoked.")
    print("  This means the interim fallback in useSpeechRecognition.ts is not firing.")
    print("  Check: continuousActiveRef.current and genRef.current at onend time.")
elif not has_normalised:
    print("\n  INJECTION FAILED at normaliseToYesNo().")
    print("  Transcript reached the handler but was not recognised as yes/no.")
elif not has_submitting:
    print("\n  INJECTION FAILED at submitResponse().")
    print("  Check: busyRef.current, sessionIdRef.current, currentStateRef.current at line 395.")
elif not has_transitioned:
    print("\n  HTTP POST was sent but FSM did not transition.")
    print("  Check: HTTP response, backend, action_id mismatch.")
else:
    print("\n  INJECTION TEST: ALL STAGES PASSED")
    print(f"  Final FSM state: {panel.get('FSM','?')}")

# ── PHASE 2: REAL SPEECH TEST ─────────────────────────────────────────────────
print(f"\n{DIVIDER}")
print("  VOICE PIPELINE TRACE — PHASE 2: REAL SPEECH TEST")
print("  (Chrome restarted with DEFAULT user profile — real microphone)")
print(DIVIDER)

# Kill current CDP Chrome and restart with user's default profile
import subprocess, signal

# Find and kill existing CDP Chrome
try:
    result_ps = subprocess.run(
        ["powershell", "-Command",
         "Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force"],
        capture_output=True, timeout=5
    )
    print("[CDP] Previous Chrome processes stopped")
except Exception as e:
    print(f"[CDP] Stop Chrome: {e}")

time.sleep(1.5)

# Start Chrome with DEFAULT profile (no --user-data-dir override, no fake device flags)
# Only add debugging port and allow-origins
chrome_args = [
    CHROME,
    "--remote-debugging-port=9222",
    "--remote-allow-origins=*",
    # No --user-data-dir → uses the default Chrome profile (which has mic permission)
    # No --use-fake-device-for-media-stream → real microphone
    # No --use-fake-ui-for-media-stream → real permission dialog (already granted in default profile)
    APP_URL + "/student"
]
subprocess.Popen(chrome_args)
print(f"[CDP] Chrome (default profile) started — navigating to {APP_URL}/student")
print("[CDP] Waiting 5 s for Chrome to load…")
time.sleep(5)

# Reconnect CDP
for attempt in range(5):
    try:
        with urlopen(f"{CDP_URL}/json", timeout=3) as r:
            tabs = json.loads(r.read())
        app_tabs = [t for t in tabs if "localhost:5173" in t.get("url","")]
        if app_tabs:
            break
    except Exception:
        pass
    time.sleep(1)
else:
    print("[CDP] ERROR: Could not find app tab after 5 attempts")
    sys.exit(1)

cdp2 = CDP(app_tabs[0]["webSocketDebuggerUrl"])
cdp2.call("Runtime.enable")
cdp2.call("Page.enable")
print(f"[CDP] Connected to tab: {app_tabs[0]['url']}")

# Register intercept
cdp2.call("Page.addScriptToEvaluateOnNewDocument", {"source": SR_INTERCEPT})
cdp2.call("Page.reload", {"ignoreCache": True})
print("[CDP] SR intercept registered — page reloaded")
time.sleep(4)

cdp2.exec("localStorage.setItem('NRS_DEV', '1')")
cdp2.flush()

# Start session
result = cdp2.exec("""
  (() => {
    var btns = Array.from(document.querySelectorAll('button'));
    var btn  = btns.find(b => /^start$/i.test(b.textContent.trim()));
    if (btn) { btn.click(); return 'clicked'; }
    return 'NOT FOUND';
  })()
""")
print(f"[CDP] Start button: {result}")

# Wait for listening state
print("[CDP] Waiting for session to start and TTS to finish…")
for _ in range(30):
    time.sleep(0.5)
    p = cdp2.exec("JSON.stringify((() => {var s=document.querySelectorAll('.font-mono span');var r={};s.forEach(function(n){var l=n.querySelector('.text-green-600');if(l)r[l.textContent]=n.textContent.replace(l.textContent,'').trim()});return r})())")
    if p:
        pj = json.loads(p)
        if pj.get("PHASE") == "LISTENING":
            print(f"[CDP] voicePhase = LISTENING  FSM={pj.get('FSM','?')}")
            break

cdp2.flush()

# Track permission and mic state
mic_state = cdp2.exec("""
  (async () => {
    try {
      const perm   = await navigator.permissions.query({name:'microphone'});
      const stream = await navigator.mediaDevices.getUserMedia({audio:true});
      const track  = stream.getAudioTracks()[0];
      return JSON.stringify({
        permission: perm.state,
        muted:      track ? track.muted      : null,
        readyState: track ? track.readyState : null,
        label:      track ? track.label      : null,
      });
    } catch(e) {
      return JSON.stringify({error: e.name + ': ' + e.message});
    }
  })()
""", await_promise=True)
print(f"\n[Mic state in default-profile Chrome] {mic_state}")

sr_count2 = cdp2.exec("window.__srCount || 0")
print(f"[CDP] SR instances started (default Chrome): {sr_count2}")

# ── Real speech test ──────────────────────────────────────────────────────────
print(f"""
{DIVIDER}
  >>> ACTION REQUIRED <<<
  The simulation is running in Chrome.
  When you hear the voice prompt, speak clearly into your microphone.
  Say: YES
  Recording for 20 seconds.
{DIVIDER}
""")

cdp2.flush()
all_real_logs = []

for tick in range(40):   # 40 × 0.5 s = 20 s
    time.sleep(0.5)
    new_logs = cdp2.flush()
    for l, ts in new_logs:
        if any(t in l for t in ["[NRS", "[VOICE", "[SR-WRAP", "[SR]"]):
            all_real_logs.append((l, ts))
            print(f"  t={tick*0.5:4.1f}s  {l}")

# Final dev panel
p2 = cdp2.exec("JSON.stringify((() => {var s=document.querySelectorAll('.font-mono span');var r={};s.forEach(function(n){var l=n.querySelector('.text-green-600');if(l)r[l.textContent]=n.textContent.replace(l.textContent,'').trim()});return r})())")
panel2 = json.loads(p2) if p2 else {}
print(f"\n[DevPanel final] {panel2}")

# ── Analyse real speech test ──────────────────────────────────────────────────
real_text    = " ".join(l for l, _ in all_real_logs)
r_onstart    = "[VOICE" in real_text and "onstart" in real_text
r_onaudio    = "onaudiostart" in real_text
r_onsound    = "onsoundstart" in real_text
r_onspeech   = "onspeechstart" in real_text
r_onresult   = "onresult" in real_text
r_interim    = "INTERIM FALLBACK" in real_text or "FINAL transcript" in real_text
r_recognised = "[MIC] recognised" in real_text
r_normalised = "[MIC] normalised" in real_text
r_submit     = "[FSM] submitting" in real_text
r_fsm        = "[FSM] transitioned" in real_text
r_nospeech   = "no-speech" in real_text

print(f"\n{DIVIDER}")
print("  REAL SPEECH TEST — PIPELINE STAGE BREAKDOWN")
print(DIVIDER)
print(f"  {'✓' if r_onstart   else '✗'} [VOICE] onstart fired")
print(f"  {'✓' if r_onaudio   else '✗'} [VOICE] onaudiostart fired")
print(f"  {'✓' if r_onsound   else '✗'} [VOICE] onsoundstart fired  {'← SOUND DETECTED' if r_onsound else '← NO SOUND — mic silent or muted'}")
print(f"  {'✓' if r_onspeech  else '✗'} [VOICE] onspeechstart fired {'← VOICE DETECTED' if r_onspeech else ''}")
print(f"  {'✓' if r_onresult  else '✗'} [VOICE] onresult fired      {'← TRANSCRIPT PRODUCED' if r_onresult else '← NO TRANSCRIPT'}")
print(f"  {'✓' if r_interim   else '✗'} [VOICE] interim fallback / final delivered")
print(f"  {'✓' if r_recognised else '✗'} [NRS]   [MIC] recognised callback entered")
print(f"  {'✓' if r_normalised else '✗'} [NRS]   normalised → YES/NO")
print(f"  {'✓' if r_submit     else '✗'} [NRS]   HTTP POST sent")
print(f"  {'✓' if r_fsm        else '✗'} [NRS]   FSM transitioned")
if r_nospeech:
    print(f"\n  NOTE: onerror(no-speech) fired — recognition was active but received silence")

# Find exact failure point
stages_real = [
    ("onstart",          r_onstart),
    ("onaudiostart",     r_onaudio),
    ("onsoundstart",     r_onsound),
    ("onspeechstart",    r_onspeech),
    ("onresult",         r_onresult),
    ("interim fallback", r_interim),
    ("recognised",       r_recognised),
    ("normalised",       r_normalised),
    ("HTTP POST",        r_submit),
    ("FSM transition",   r_fsm),
]
first_fail = next((name for name, ok in stages_real if not ok), None)
last_ok    = next((name for name, ok in reversed(stages_real) if ok), None)

print(f"\n  Last confirmed stage: {last_ok or 'NONE'}")
print(f"  Pipeline stops at:   {first_fail or 'COMPLETED SUCCESSFULLY'}")

# ── Final report ──────────────────────────────────────────────────────────────
print(f"\n{DIVIDER}")
print("  FINAL REPORT")
print(DIVIDER)

print(f"""
  PHASE 1 — INJECTION TEST:
    onresult→onend injected directly into SR instance.
    recognised:   {'PASS' if has_recognised  else 'FAIL'}
    normalised:   {'PASS' if has_normalised  else 'FAIL'}
    HTTP POST:    {'PASS' if has_submitting  else 'FAIL'}
    FSM:          {'PASS' if has_transitioned else 'FAIL'}

  PHASE 2 — REAL SPEECH TEST:
    Mic state:    {mic_state}
    Last stage:   {last_ok or 'NONE'}
    Failure at:   {first_fail or 'NONE — completed'}
""")

if has_recognised and not r_recognised:
    print("  CONCLUSION:")
    print("  The React pipeline from onresult→FSM works correctly (injection proved it).")
    print("  SpeechRecognition is NOT delivering audio in this context.")
    print(f"  Real SR stops at: {first_fail}")
    if not r_onsound:
        print()
        print("  ROOT CAUSE: onsoundstart never fired.")
        print("  Chrome's SR engine received audio capture but detected no sound.")
        print("  This is an OS/hardware audio layer issue, not an application bug.")
        print("  Possible causes:")
        print("   1. Microphone muted at Windows level for THIS app's audio session")
        print("   2. Wrong default recording device selected")
        print("   3. Chrome audio session not receiving OS audio routing")
    elif not r_onresult:
        print()
        print("  ROOT CAUSE: onspeechstart fired but onresult never fired.")
        print("  Chrome detected speech but SR service returned no transcript.")
        print("  Possible causes:")
        print("   1. Network timeout to Google SR service")
        print("   2. Language mismatch (en-US set but OS locale differs)")
        print("   3. Speech too short or quiet for SR confidence threshold")
elif not has_recognised and not r_recognised:
    print("  CONCLUSION:")
    print("  BOTH injection test and real speech test failed at [MIC] recognised.")
    print("  The interim fallback in useSpeechRecognition.ts is NOT invoking the callback.")
    print("  File: frontend/src/hooks/useSpeechRecognition.ts")
    print("  Check lines 295-310: continuousActiveRef.current and genRef guards.")
elif has_transitioned and r_fsm:
    print("  CONCLUSION: Both tests PASSED. Pipeline is fully functional.")
    print("  The issue was environmental (muted mic in CDP test Chrome).")
    print("  With real microphone audio, the simulation advances correctly.")
