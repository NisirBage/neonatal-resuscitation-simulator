import json, threading, time, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from urllib.request import urlopen
import websocket

CDP_URL = "http://localhost:9222"

class CDP:
    def __init__(self, ws_url):
        self._id=0; self._lock=threading.Lock(); self._calls={}; self._logs=[]; self._ready=threading.Event()
        self._ws=websocket.WebSocketApp(ws_url,on_message=self._on_msg,on_open=lambda ws:self._ready.set())
        threading.Thread(target=self._ws.run_forever,daemon=True).start()
        if not self._ready.wait(10): raise TimeoutError()
    def _on_msg(self,ws,raw):
        msg=json.loads(raw)
        if msg.get("method")=="Runtime.consoleAPICalled":
            parts=[]
            for a in msg["params"].get("args",[]):
                if a["type"]=="string": parts.append(a["value"])
                elif a["type"]=="object":
                    props=a.get("preview",{}).get("properties",[])
                    if props: parts.append(str({p["name"]:p.get("value","?") for p in props}))
                    else: parts.append(a.get("preview",{}).get("description","..."))
                else: parts.append(str(a.get("value","")))
            self._logs.append((" ".join(parts),time.monotonic()))
        mid=msg.get("id")
        if mid and mid in self._calls: ev,h=self._calls[mid]; h.append(msg); ev.set()
    def call(self,method,params=None,timeout=15):
        with self._lock: self._id+=1; cid=self._id
        ev,h=threading.Event(),[]
        self._calls[cid]=(ev,h)
        self._ws.send(json.dumps({"id":cid,"method":method,"params":params or {}}))
        if not ev.wait(timeout): raise TimeoutError(method)
        return h[0]
    def exec(self,js,timeout=10):
        r=self.call("Runtime.evaluate",{"expression":js,"returnByValue":True},timeout)
        return r.get("result",{}).get("result",{}).get("value")
    def flush(self):
        logs,self._logs=self._logs[:],[]; return logs
    def panel(self):
        raw=self.exec("JSON.stringify((() => { var s=document.querySelectorAll('.font-mono span'); var r={}; s.forEach(function(n){var l=n.querySelector('.text-green-600'); if(l)r[l.textContent]=n.textContent.replace(l.textContent,'').trim()}); return r; })()")
        return json.loads(raw) if raw else {}

SR_INTERCEPT = """
(function(){
  var SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR)return;
  var orig=SR.prototype.start;
  SR.prototype.start=function(){window.__currentSR=this;window.__srCount=(window.__srCount||0)+1;return orig.call(this);};
})();
"""

with urlopen(f"{CDP_URL}/json") as r: tabs=json.loads(r.read())
tab=next((t for t in tabs if "5173" in t.get("url","")),None)
cdp=CDP(tab["webSocketDebuggerUrl"])
cdp.call("Runtime.enable"); cdp.call("Page.enable")
cdp.call("Page.addScriptToEvaluateOnNewDocument",{"source":SR_INTERCEPT})
cdp.call("Page.reload",{"ignoreCache":True}); time.sleep(4)
cdp.exec("localStorage.setItem('NRS_DEV','1')")
cdp.flush()

cdp.exec("(()=>{var b=Array.from(document.querySelectorAll('button')).find(b=>/^start$/i.test(b.textContent.trim()));if(b)b.click();})()")

def wait_listening(timeout=15):
    for _ in range(timeout*2):
        time.sleep(0.5)
        if cdp.panel().get("PHASE")=="LISTENING": return True
    return False

def inject(word):
    return cdp.exec(f"""
      (function(){{
        var sr=window.__currentSR;
        if(!sr||typeof sr.onresult!=='function') return 'NO_SR';
        sr.onresult({{resultIndex:0,results:{{0:{{0:{{transcript:{json.dumps(word)},confidence:.95}},isFinal:true,length:1}},length:1}}}});
        return 'OK';
      }})()
    """)

steps=[("yes","yes"),("yes","yes"),("yes","yes")]  # baby_born->chest->crying->routine_care
for resp,_ in steps:
    wait_listening(15); cdp.flush(); inject(resp); time.sleep(1.5)

p=cdp.panel()
print(f"[Reached] FSM={p.get('FSM')} PHASE={p.get('PHASE')} HTTP={p.get('HTTP')}")

time.sleep(1)
cdp.flush()  # purge sticky logs

sr_count_before=cdp.exec("window.__srCount||0")
print(f"[Pre-inject] HTTP={cdp.panel().get('HTTP')} SR starts so far={sr_count_before}")

inject("yes")
time.sleep(2)

sr_count_after=cdp.exec("window.__srCount||0")
new_logs=cdp.flush()
submitting=[l for l,_ in new_logs if "[FSM] submitting" in l]
normalised=[l for l,_ in new_logs if "[MIC] normalised" in l]
recognised=[l for l,_ in new_logs if "[MIC] recognised" in l]
p2=cdp.panel()

print(f"[Post-inject] FSM={p2.get('FSM')} HTTP={p2.get('HTTP')} SR-starts={sr_count_after}")
print(f"[New logs] recognised={len(recognised)} normalised={len(normalised)} submitting={len(submitting)}")
for l,_ in new_logs:
    if any(x in l for x in ["[MIC]","[FSM]","VOICE","NRS"]): print(f"  {l}")

if submitting:
    print("\n  *** BUG CONFIRMED: submitStudentInput called in terminal state ***")
else:
    print("\n  PASS: No HTTP submission in terminal state (HTTP=200 was sticky from navigation)")
