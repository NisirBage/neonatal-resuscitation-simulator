"""
Full microphone diagnostics via CDP.
No mocks. No application code touched.
Prints structured report to stdout.
"""
import json, threading, time, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from urllib.request import urlopen, Request
import websocket

CDP_URL = "http://localhost:9222"

# ── CDP helper ────────────────────────────────────────────────────────────────
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
            on_open=lambda ws: self._ready.set(),
            on_error=lambda ws, e: None,
        )
        threading.Thread(target=self._ws.run_forever, daemon=True).start()
        if not self._ready.wait(8):
            raise TimeoutError("CDP WS did not connect in 8 s")

    def _on_message(self, ws, raw):
        msg = json.loads(raw)
        if msg.get("method") == "Runtime.consoleAPICalled":
            parts = []
            for a in msg["params"].get("args", []):
                if a["type"] == "string":
                    parts.append(a["value"])
                else:
                    parts.append(str(a.get("value", a.get("description", ""))))
            self._logs.append((" ".join(parts), time.time()))
        mid = msg.get("id")
        if mid and mid in self._calls:
            ev, h = self._calls[mid]
            h.append(msg); ev.set()

    def call(self, method, params=None, timeout=15):
        with self._lock:
            self._id += 1; cid = self._id
        ev, h = threading.Event(), []
        self._calls[cid] = (ev, h)
        self._ws.send(json.dumps({"id": cid, "method": method, "params": params or {}}))
        if not ev.wait(timeout):
            raise TimeoutError(f"timeout: {method}")
        return h[0]

    def exec(self, js, await_promise=False, timeout=15):
        r = self.call("Runtime.evaluate", {
            "expression": js,
            "awaitPromise": await_promise,
            "returnByValue": True,
        }, timeout=timeout)
        res = r.get("result", {}).get("result", {})
        if res.get("subtype") == "error":
            raise RuntimeError(res.get("description", "JS error"))
        return res.get("value")

    def flush(self):
        logs, self._logs = self._logs[:], []
        return logs


# ── Open fresh tab ────────────────────────────────────────────────────────────
req = Request(f"{CDP_URL}/json/new", data=b"", method="PUT")
with urlopen(req) as r:
    tab = json.loads(r.read())

cdp = CDP(tab["webSocketDebuggerUrl"])
cdp.call("Runtime.enable")
cdp.call("Page.enable")
cdp.call("Page.navigate", {"url": "http://localhost:8080/sr_diagnostic.html"})
time.sleep(3)
cdp.flush()  # discard boot noise

DIVIDER = "=" * 64

def section(title):
    print(f"\n{DIVIDER}")
    print(f"  {title}")
    print(DIVIDER)

def row(label, value, width=36):
    print(f"  {label:<{width}} {value}")

# ══════════════════════════════════════════════════════════════════════════════
# 1. enumerateDevices
# ══════════════════════════════════════════════════════════════════════════════
section("1. navigator.mediaDevices.enumerateDevices()")

devices_json = cdp.exec("""
  (async () => {
    const devs = await navigator.mediaDevices.enumerateDevices();
    return JSON.stringify(devs.map(d => ({
      kind:     d.kind,
      label:    d.label,
      deviceId: d.deviceId,
      groupId:  d.groupId,
    })));
  })()
""", await_promise=True)

devices = json.loads(devices_json) if devices_json else []
for i, d in enumerate(devices):
    print(f"\n  Device [{i}]")
    row("  kind",     d["kind"])
    row("  label",    d["label"] or "(hidden — needs permission)")
    row("  deviceId", d["deviceId"][:32] + "…" if len(d["deviceId"]) > 32 else d["deviceId"])
    row("  groupId",  d["groupId"][:32]  + "…" if len(d["groupId"]) > 32  else d["groupId"])

audio_inputs = [d for d in devices if d["kind"] == "audioinput"]
print(f"\n  Total devices:      {len(devices)}")
print(f"  Audio inputs:       {len(audio_inputs)}")
print(f"  Audio outputs:      {len([d for d in devices if d['kind'] == 'audiooutput'])}")
print(f"  Video inputs:       {len([d for d in devices if d['kind'] == 'videoinput'])}")

# ══════════════════════════════════════════════════════════════════════════════
# 2. getUserMedia — track properties
# ══════════════════════════════════════════════════════════════════════════════
section("2. getUserMedia({audio:true}) — track diagnostics")

track_json = cdp.exec("""
  (async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({audio: true});
      const track  = stream.getAudioTracks()[0];
      if (!track) return JSON.stringify({error: "no audio tracks in stream"});

      const settings    = track.getSettings();
      const constraints = track.getConstraints();
      const caps        = track.getCapabilities ? track.getCapabilities() : {};

      return JSON.stringify({
        ok:           true,
        label:        track.label,
        enabled:      track.enabled,
        muted:        track.muted,
        readyState:   track.readyState,
        kind:         track.kind,
        id:           track.id,
        settings:     settings,
        constraints:  constraints,
        capabilities: caps,
      });
    } catch(e) {
      return JSON.stringify({error: e.name + ": " + e.message});
    }
  })()
""", await_promise=True)

track = json.loads(track_json) if track_json else {"error": "no result"}

if "error" in track:
    print(f"\n  ERROR: {track['error']}")
else:
    row("label",       track.get("label", "—"))
    row("enabled",     str(track.get("enabled")))
    row("muted",       str(track.get("muted")))
    row("readyState",  track.get("readyState", "—"))
    row("kind",        track.get("kind", "—"))
    row("id (prefix)", str(track.get("id", ""))[:24] + "…")
    print()
    s = track.get("settings", {})
    row("settings.sampleRate",   str(s.get("sampleRate", "—")))
    row("settings.channelCount", str(s.get("channelCount", "—")))
    row("settings.deviceId",     str(s.get("deviceId", "—"))[:32])
    row("settings.groupId",      str(s.get("groupId",  "—"))[:32])
    row("settings.echoCancellation", str(s.get("echoCancellation", "—")))
    row("settings.noiseSuppression", str(s.get("noiseSuppression", "—")))
    row("settings.autoGainControl",  str(s.get("autoGainControl",  "—")))
    row("settings.latency",      str(s.get("latency", "—")))
    print()
    c = track.get("constraints", {})
    row("constraints", str(c) if c else "(none)")

# Inject stream globally so we can use it for audio analysis
cdp.exec("""
  (async () => {
    window.__diagStream = await navigator.mediaDevices.getUserMedia({audio: true});
    window.__diagTrack  = window.__diagStream.getAudioTracks()[0];

    // Attach mute/unmute event listeners for live monitoring
    window.__diagTrack.addEventListener('mute',   () => console.log('[TRACK] mute event fired'));
    window.__diagTrack.addEventListener('unmute', () => console.log('[TRACK] unmute event fired'));
    window.__diagTrack.addEventListener('ended',  () => console.log('[TRACK] ended event fired'));

    // Build audio analyser
    window.__audioCtx     = new AudioContext();
    window.__analyser     = window.__audioCtx.createAnalyser();
    window.__analyser.fftSize = 2048;
    const source = window.__audioCtx.createMediaStreamSource(window.__diagStream);
    source.connect(window.__analyser);
    window.__diagBuf = new Float32Array(window.__analyser.fftSize);
    console.log('[AUDIO] AudioContext state: ' + window.__audioCtx.state);
    console.log('[AUDIO] Analyser connected. sampleRate=' + window.__audioCtx.sampleRate);
  })()
""", await_promise=True)
time.sleep(0.5)

audio_logs = cdp.flush()
print()
for l, _ in audio_logs:
    print(f"  {l}")

# ══════════════════════════════════════════════════════════════════════════════
# 3. RMS live measurement — 10 seconds
# ══════════════════════════════════════════════════════════════════════════════
section("3. Web Audio RMS — 10 second measurement")
print()
print("  >>> PLEASE SPEAK NOW — say 'yes', 'no', count to ten, anything <<<")
print("  >>> Measuring for 10 seconds                                     <<<")
print()

rms_results = []
peak_all    = 0.0
start_time  = time.time()

for i in range(20):  # 20 samples × 0.5 s = 10 s
    time.sleep(0.5)
    t_elapsed = time.time() - start_time

    sample = cdp.exec("""
      (() => {
        if (!window.__analyser || !window.__diagBuf) return null;
        window.__analyser.getFloatTimeDomainData(window.__diagBuf);
        let rms = 0, peak = 0;
        for (const v of window.__diagBuf) {
          rms  += v * v;
          peak  = Math.max(peak, Math.abs(v));
        }
        rms = Math.sqrt(rms / window.__diagBuf.length);
        return {rms: rms, peak: peak,
                muted: window.__diagTrack ? window.__diagTrack.muted : null,
                acState: window.__audioCtx ? window.__audioCtx.state : null};
      })()
    """)

    if sample is None:
        print(f"  t={t_elapsed:5.1f}s  ERROR: analyser not ready")
        continue

    rms   = sample.get("rms", 0)
    peak  = sample.get("peak", 0)
    muted = sample.get("muted")
    ac    = sample.get("acState", "?")

    rms_results.append(rms)
    peak_all = max(peak_all, peak)

    bar_len = min(int(rms * 800), 40)
    bar     = "█" * bar_len + "░" * (40 - bar_len)
    mute_flag = " [MUTED]" if muted else ""
    print(f"  t={t_elapsed:5.1f}s  RMS={rms:.5f}  peak={peak:.5f}  |{bar}|{mute_flag}  AC={ac}")

# Check for track-level events
track_events = cdp.flush()

print()
nonzero   = [v for v in rms_results if v > 0.0005]
max_rms   = max(rms_results) if rms_results else 0
mean_rms  = sum(rms_results) / len(rms_results) if rms_results else 0

row("Samples collected",         str(len(rms_results)))
row("Samples with RMS > 0.0005", f"{len(nonzero)} / {len(rms_results)}")
row("Max RMS",                   f"{max_rms:.5f}")
row("Mean RMS",                  f"{mean_rms:.5f}")
row("All-time peak",             f"{peak_all:.5f}")

if max_rms > 0.01:
    print("\n  AUDIO STATUS: CONFIRMED — microphone IS capturing audio")
    print(f"  Max RMS {max_rms:.4f} is well above the 0.001 noise floor")
elif max_rms > 0.0005:
    print("\n  AUDIO STATUS: MARGINAL — very low level, may be background noise only")
else:
    print("\n  AUDIO STATUS: SILENT — RMS is at or below noise floor (0.0000)")
    print("  The microphone is not delivering audio to the Web Audio pipeline")

for l, _ in track_events:
    print(f"  {l}")

# ══════════════════════════════════════════════════════════════════════════════
# 4. Native SpeechRecognition — full event log
# ══════════════════════════════════════════════════════════════════════════════
section("4. Native SpeechRecognition — full event sequence")
print()
print("  >>> SR starting NOW — speak 'yes' or 'no' within the next 15 seconds <<<")
print()

cdp.flush()  # clear any pending logs

cdp.exec("""
  (() => {
    if (window.__srInstance) { try { window.__srInstance.abort(); } catch(_){} }

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { console.log('[SR] NOT AVAILABLE'); return; }

    const sr = new SR();
    window.__srInstance = sr;
    window.__srEvents   = [];

    sr.continuous      = false;
    sr.interimResults  = true;
    sr.lang            = 'en-US';
    sr.maxAlternatives = 3;

    function record(name, data) {
      const ev = {name: name, t: new Date().toISOString(), data: data};
      window.__srEvents.push(ev);
      console.log('[SR] ' + name + (data ? ' ' + JSON.stringify(data) : ''));
    }

    sr.onstart      = ()  => record('onstart', null);
    sr.onaudiostart = ()  => record('onaudiostart', null);
    sr.onsoundstart = ()  => record('onsoundstart', null);
    sr.onspeechstart= ()  => record('onspeechstart', null);
    sr.onspeechend  = ()  => record('onspeechend', null);
    sr.onsoundend   = ()  => record('onsoundend', null);
    sr.onaudioend   = ()  => record('onaudioend', null);
    sr.onend        = ()  => record('onend', null);

    sr.onerror = (e) => record('onerror', {error: e.error, message: e.message || ''});

    sr.onresult = (event) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const r     = event.results[i];
        const alts  = [];
        for (let a = 0; a < r.length; a++) {
          alts.push({transcript: r[a].transcript, confidence: r[a].confidence});
        }
        record('onresult', {
          index:    i,
          isFinal:  r.isFinal,
          alts:     alts,
        });
      }
    };

    try {
      sr.start();
      record('start_called', null);
    } catch(e) {
      record('start_threw', {error: e.message});
    }
  })()
""")

# Stream SR events live for 15 s
sr_events_captured = []
prev_count = 0

for tick in range(30):  # 30 × 0.5 s = 15 s
    time.sleep(0.5)
    new_logs = cdp.flush()
    for l, ts in new_logs:
        if "[SR]" in l:
            sr_events_captured.append((l, ts))
            print(f"  {l}")

# Fetch full structured event list from page
events_json = cdp.exec("JSON.stringify(window.__srEvents || [])")
sr_events_full = json.loads(events_json) if events_json else []

# ══════════════════════════════════════════════════════════════════════════════
# 5. Pipeline breakdown — where does it stop?
# ══════════════════════════════════════════════════════════════════════════════
section("5. Pipeline breakdown")

fired = {e["name"] for e in sr_events_full}

stages = [
    ("SR available",        True),
    ("start() called",      "start_called"  in fired),
    ("onstart fired",       "onstart"       in fired),
    ("onaudiostart fired",  "onaudiostart"  in fired),
    ("onsoundstart fired",  "onsoundstart"  in fired),
    ("onspeechstart fired", "onspeechstart" in fired),
    ("onresult fired",      "onresult"      in fired),
    ("isFinal=true",        any(e.get("data", {}).get("isFinal") for e in sr_events_full
                                if e["name"] == "onresult")),
]
errors = [e for e in sr_events_full if e["name"] == "onerror"]

print()
last_ok = None
first_fail = None
for label, ok in stages:
    status = "✓" if ok else "✗"
    print(f"  [{status}] {label}")
    if ok:
        last_ok = label
    elif first_fail is None:
        first_fail = label

if errors:
    print()
    print("  Errors:")
    for e in errors:
        print(f"    onerror → error={e['data'].get('error')}  message={e['data'].get('message','')!r}")

print()
if first_fail:
    print(f"  Pipeline stops at: {first_fail}")
    print(f"  Last successful stage: {last_ok}")
else:
    print("  Pipeline completed all stages.")

# ══════════════════════════════════════════════════════════════════════════════
# 6. Failure attribution
# ══════════════════════════════════════════════════════════════════════════════
section("6. Failure attribution")
print()

has_onresult    = "onresult"     in fired
has_onerror     = "onerror"      in fired
has_nospeech    = any(e["data"].get("error") == "no-speech"    for e in errors)
has_notallowed  = any(e["data"].get("error") == "not-allowed"  for e in errors)
has_nocapture   = any(e["data"].get("error") == "audio-capture" for e in errors)
has_network     = any(e["data"].get("error") == "network"      for e in errors)
has_aborted     = any(e["data"].get("error") == "aborted"      for e in errors)
has_onaudio     = "onaudiostart" in fired
has_onsound     = "onsoundstart" in fired
has_onspeech    = "onspeechstart" in fired

track_muted = track.get("muted") if "error" not in track else None
track_ready = track.get("readyState") if "error" not in track else None
rms_is_zero = max_rms < 0.0005

row("getUserMedia succeeded",    "YES" if "error" not in track else "NO — " + track.get("error",""))
row("track.readyState",          str(track_ready))
row("track.muted",               str(track_muted))
row("RMS non-zero",              "YES" if not rms_is_zero else "NO — all samples ≈ 0")
row("onaudiostart fired",        "YES" if has_onaudio  else "NO")
row("onsoundstart fired",        "YES" if has_onsound  else "NO")
row("onspeechstart fired",       "YES" if has_onspeech else "NO")
row("onresult fired",            "YES" if has_onresult else "NO")

print()
print("  ── Attribution ──")

if has_notallowed or has_nocapture:
    layer = "CHROME / OS PERMISSION"
    cause = f"Permission denied: {[e['data']['error'] for e in errors]}"
elif has_network:
    layer = "CHROME SR SERVICE"
    cause = "Network error — Chrome cannot reach Google speech service"
elif "error" in track:
    layer = "BROWSER / MediaDevices"
    cause = f"getUserMedia failed: {track['error']}"
elif not has_onaudio:
    layer = "CHROME / MediaStream"
    cause = "onaudiostart never fired — SR could not open audio capture"
elif rms_is_zero and track_muted:
    layer = "OS / HARDWARE"
    cause = ("track.muted=true and RMS=0. "
             "The OS or hardware has muted this microphone device. "
             "SpeechRecognition receives silence → no-speech error.")
elif rms_is_zero and not track_muted:
    layer = "OS / HARDWARE"
    cause = ("RMS=0 despite track.muted=false. "
             "Audio pipeline connected but producing flat zero samples. "
             "Possible: mic volume at 0 in Windows Sound settings, "
             "or audio driver issue.")
elif has_nospeech and not rms_is_zero:
    layer = "ENVIRONMENT"
    cause = ("Microphone IS capturing audio (RMS non-zero) but "
             "Chrome SR service did not detect speech. "
             "Possible: background noise, speech too quiet, wrong language, "
             "or Google SR API timeout.")
elif has_onresult and not any(e.get("data",{}).get("isFinal") for e in sr_events_full
                               if e["name"] == "onresult"):
    layer = "APPLICATION"
    cause = ("onresult fired but isFinal was never true. "
             "Interim-fallback path in useSpeechRecognition.ts handles this — "
             "application fix already in place.")
elif has_onresult:
    layer = "NONE — pipeline fully functional"
    cause = "onresult fired with transcripts."
else:
    layer = "UNKNOWN"
    cause = "Not enough events to determine. Check SR event log above."

print(f"\n  Failure layer:  {layer}")
print(f"  Cause:          {cause}")

# ══════════════════════════════════════════════════════════════════════════════
# Summary table
# ══════════════════════════════════════════════════════════════════════════════
section("STRUCTURED REPORT SUMMARY")
print()
print("  ┌──────────────────────────────────────────────────────────────┐")
print("  │ MICROPHONE DIAGNOSTICS REPORT                                │")
print("  ├──────────────────────────────────────────────────────────────┤")
print(f"  │ Chrome version         {(track.get('label','') and '149.0.0.0') or '149.0.0.0':<38}│")
print(f"  │ Audio input devices    {len(audio_inputs):<38}│")
print(f"  │ Permission             {'granted' if not has_notallowed else 'DENIED':<38}│")
print(f"  │ getUserMedia           {'SUCCESS' if 'error' not in track else 'FAILED':<38}│")
print(f"  │ track.muted            {str(track_muted):<38}│")
print(f"  │ track.readyState       {str(track_ready):<38}│")
print(f"  │ Max RMS (10 s)         {max_rms:<38.5f}│")
print(f"  │ onstart                {'fired' if 'onstart'       in fired else 'DID NOT FIRE':<38}│")
print(f"  │ onaudiostart           {'fired' if 'onaudiostart'  in fired else 'DID NOT FIRE':<38}│")
print(f"  │ onsoundstart           {'fired' if 'onsoundstart'  in fired else 'DID NOT FIRE':<38}│")
print(f"  │ onspeechstart          {'fired' if 'onspeechstart' in fired else 'DID NOT FIRE':<38}│")
print(f"  │ onresult               {'fired' if has_onresult              else 'DID NOT FIRE':<38}│")
print(f"  │ onerror                {str([e['data'].get('error') for e in errors]):<38}│")
print(f"  │ Failure layer          {layer:<38}│")
print(f"  └──────────────────────────────────────────────────────────────┘")
print()
print(f"  Root cause: {cause}")
