"""crv web — local web UI: paste a video URL (YouTube, Instagram, ...) or a file
path, run the analysis, open the result viewer. Stdlib only, runs 100% locally.
UI ships in Traditional Chinese, Simplified Chinese and English (toggle, persisted)."""
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

JOBS: dict = {}  # id -> {state, log, out_dir, err}

PAGE = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>crv Web</title>
<style>
  :root { color-scheme: dark }
  * { box-sizing:border-box; margin:0; padding:0 }
  body { background:#0d0b07; color:#e8dfcf; font-family:Menlo,Consolas,monospace; min-height:100vh;
         display:flex; flex-direction:column; align-items:center; padding:48px 20px }
  .lang { position:fixed; top:16px; right:20px; display:flex; gap:6px }
  .lang button { font:inherit; font-size:12px; color:#8a7d63; background:#14110b;
         border:1px solid #2a2418; border-radius:8px; padding:4px 10px; cursor:pointer; margin:0; font-weight:normal }
  .lang button.on { color:#e8b64c; border-color:#e8b64c }
  h1 { color:#e8b64c; font-size:22px; letter-spacing:1px }
  .sub { color:#8a7d63; font-size:13px; margin-top:8px; text-align:center; max-width:720px; line-height:1.7 }
  form { width:100%; max-width:720px; margin-top:36px }
  input[type=text] { width:100%; font:inherit; font-size:15px; color:#e8dfcf; background:#14110b;
         border:1px solid #3a3323; border-radius:12px; padding:14px 16px; outline:none }
  input[type=text]:focus { border-color:#e8b64c }
  .opts { display:flex; flex-wrap:wrap; gap:10px 22px; margin-top:16px; font-size:13.5px; color:#c9bda3 }
  .opts label { cursor:pointer; display:flex; align-items:center; gap:7px }
  .opts small { color:#6d6350 }
  #go { font:inherit; font-size:14.5px; margin-top:22px; cursor:pointer; color:#0d0b07;
         background:#e8b64c; border:none; border-radius:10px; padding:12px 28px; font-weight:bold }
  #go:disabled { background:#4a4130; color:#8a7d63; cursor:default }
  #log { width:100%; max-width:720px; margin-top:26px; font-size:12.5px; line-height:1.7; color:#8a7d63;
         white-space:pre-wrap; border:1px solid #2a2418; border-radius:12px; padding:14px 16px;
         background:#14110b; min-height:80px; max-height:40vh; overflow:auto; display:none }
  #done { display:none; margin-top:18px }
  #done button { font:inherit; font-size:14.5px; cursor:pointer; color:#0d0b07; background:#7cc36a;
         border:none; border-radius:10px; padding:12px 28px; font-weight:bold }
</style></head><body>
<div class="lang">
  <button data-lang="zh_tw">繁中</button><button data-lang="zh_cn">简中</button><button data-lang="en">EN</button>
</div>
<h1 data-i="title"></h1>
<div class="sub" data-i="sub"></div>
<form id="f">
  <input type="text" id="src" data-p="ph" autofocus>
  <div class="opts">
    <label><input type="checkbox" id="adaptive"> <span data-i="adaptive"></span> <small data-i="adaptive_h"></small></label>
    <label><input type="checkbox" id="text_anchors"> <span data-i="ta"></span> <small data-i="ta_h"></small></label>
    <label><input type="checkbox" id="grid" checked> <span data-i="grid"></span> <small data-i="grid_h"></small></label>
    <label><input type="checkbox" id="transcribe" checked> <span data-i="tr"></span></label>
  </div>
  <button type="submit" id="go"></button>
</form>
<div id="log"></div>
<div id="done"><button id="openv"></button></div>
<p style="margin-top:28px;font-size:12px;opacity:.55;text-align:center">Built in public by <a href="https://x.com/LeoAidoAI" target="_blank" style="color:inherit">@LeoAidoAI</a></p>
<script>
const I18N = {
  zh_tw: { title:"crv 網頁版",
    sub:"貼上 YouTube / Instagram Reels 連結或本機影片路徑，AI 就能真的看懂這支影片。全程在你的電腦上跑，不上傳任何東西。",
    ph:"https://www.youtube.com/watch?v=...  或  /Users/you/video.mp4",
    adaptive:"慢變化內容", adaptive_h:"（教學、手寫、慢速運鏡）",
    ta:"字幕感知", ta_h:"（字卡、簡報、螢幕錄影）",
    grid:"九宮格", grid_h:"（省 token）", tr:"逐字稿",
    go:"開始分析", running:"分析中...", starting:"啟動中...",
    open:"開啟結果頁", failed:"失敗" },
  zh_cn: { title:"crv 网页版",
    sub:"粘贴 YouTube / Instagram Reels 链接或本机视频路径，AI 就能真的看懂这条视频。全程在你的电脑上跑，不上传任何东西。",
    ph:"https://www.youtube.com/watch?v=...  或  /Users/you/video.mp4",
    adaptive:"慢变化内容", adaptive_h:"（教学、手写、慢速运镜）",
    ta:"字幕感知", ta_h:"（字卡、演示文稿、屏幕录制）",
    grid:"九宫格", grid_h:"（省 token）", tr:"逐字稿",
    go:"开始分析", running:"分析中...", starting:"启动中...",
    open:"打开结果页", failed:"失败" },
  en: { title:"crv Web",
    sub:"Paste a YouTube / Instagram Reels link or a local file path — your AI gets to actually watch the video. Runs 100% on your machine, nothing is uploaded.",
    ph:"https://www.youtube.com/watch?v=...  or  /Users/you/video.mp4",
    adaptive:"Slow-changing", adaptive_h:"(tutorials, handwriting, slow pans)",
    ta:"Text anchors", ta_h:"(captions, slides, screen recordings)",
    grid:"Contact sheets", grid_h:"(saves tokens)", tr:"Transcript",
    go:"Analyze", running:"Running...", starting:"Starting...",
    open:"Open results", failed:"Failed" }
};
let L = localStorage.getItem('crv_lang') || 'zh_tw';
let T = I18N[L];
function applyLang(l){
  L=l; T=I18N[l]; localStorage.setItem('crv_lang', l);
  document.documentElement.lang = l==='en'?'en':(l==='zh_cn'?'zh-Hans':'zh-Hant');
  document.querySelectorAll('[data-i]').forEach(el=>el.textContent=T[el.dataset.i]);
  document.querySelectorAll('[data-p]').forEach(el=>el.placeholder=T[el.dataset.p]);
  document.querySelectorAll('.lang button').forEach(b=>b.classList.toggle('on', b.dataset.lang===l));
  const go=document.getElementById('go');
  go.textContent = go.disabled ? T.running : T.go;
  document.getElementById('openv').textContent = T.open;
}
document.querySelectorAll('.lang button').forEach(b=>b.addEventListener('click',()=>applyLang(b.dataset.lang)));
applyLang(L);

const f=document.getElementById('f'), log=document.getElementById('log'),
      done=document.getElementById('done'), go=document.getElementById('go');
let jid=null, timer=null;
f.addEventListener('submit', async e=>{
  e.preventDefault();
  const src=document.getElementById('src').value.trim();
  if(!src) return;
  go.disabled=true; go.textContent=T.running; done.style.display='none';
  log.style.display='block'; log.textContent=T.starting;
  const opts={adaptive:adaptive.checked, text_anchors:text_anchors.checked,
              grid:grid.checked, transcribe:transcribe.checked};
  const r=await fetch('/run',{method:'POST',headers:{'Content-Type':'application/json'},
              body:JSON.stringify({src, opts})});
  jid=(await r.json()).id;
  timer=setInterval(poll, 1200);
});
async function poll(){
  const s=await (await fetch('/status?id='+jid)).json();
  log.textContent=s.log||'...'; log.scrollTop=log.scrollHeight;
  if(s.state==='done'){ clearInterval(timer); go.disabled=false; go.textContent=T.go;
    done.style.display='block'; }
  if(s.state==='error'){ clearInterval(timer); go.disabled=false; go.textContent=T.go;
    log.textContent+='\\n\\n'+T.failed+': '+(s.err||''); }
}
document.getElementById('openv').addEventListener('click', ()=>fetch('/open?id='+jid));
</script></body></html>"""


def _run_job(jid: str, src: str, opts: dict) -> None:
    job = JOBS[jid]
    out = job["out_dir"]
    cmd = [sys.executable, "-m", "claude_real_video", src, "-o", out, "--viewer"]
    if opts.get("adaptive"):
        cmd.append("--adaptive")
    if opts.get("text_anchors"):
        cmd.append("--text-anchors")
    if opts.get("grid"):
        cmd.append("--grid")
    if not opts.get("transcribe", True):
        cmd.append("--no-transcribe")
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in p.stdout:
            job["log"] += line
        p.wait()
        job["state"] = "done" if p.returncode == 0 else "error"
        if p.returncode != 0:
            job["err"] = f"exit {p.returncode}"
    except Exception as e:  # noqa: BLE001 — whatever failed, show it in the UI
        job["state"], job["err"] = "error", str(e)


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence request logging
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/status"):
            jid = self.path.split("id=")[-1]
            j = JOBS.get(jid)
            self._json({"state": j["state"], "log": j["log"][-4000:], "err": j.get("err")}
                       if j else {"state": "error", "err": "unknown job"})
        elif self.path.startswith("/open"):
            jid = self.path.split("id=")[-1]
            j = JOBS.get(jid)
            if j:
                viewer = os.path.join(j["out_dir"], "viewer.html")
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                if shutil.which(opener) and os.path.exists(viewer):
                    subprocess.Popen([opener, viewer])
                else:
                    webbrowser.open("file://" + viewer)
            self._json({"ok": True})
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/run":
            return self.send_error(404)
        n = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(n) or b"{}")
        src = (data.get("src") or "").strip()
        if not src:
            return self._json({"error": "missing src"}, 400)
        jid = str(int(time.time() * 1000))
        out = os.path.join(os.path.expanduser("~/crv-web-out"), jid)
        JOBS[jid] = {"state": "running", "log": "", "out_dir": out}
        threading.Thread(target=_run_job, args=(jid, src, data.get("opts") or {}),
                         daemon=True).start()
        self._json({"id": jid})


def main() -> None:
    port = 8642
    if len(sys.argv) > 2 and sys.argv[1] == "--port":
        port = int(sys.argv[2])
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"crv Web: {url}  (Ctrl+C to stop)")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
