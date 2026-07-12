"""--viewer: write viewer.html into the output folder — a single local file
showing the video, the kept keyframes as a browsable grid, and the transcript.
No network, no dependencies. (The Pro version adds a clickable synced
perception/shot timeline on top of this.)"""
from __future__ import annotations

import glob
import html
import os


def write_viewer(out_dir: str, video_path: str | None) -> str:
    frames = sorted(glob.glob(os.path.join(out_dir, "frames", "*.jpg")))
    transcript = ""
    tpath = os.path.join(out_dir, "transcript.txt")
    if os.path.exists(tpath):
        # explicit utf-8: the transcript/HTML carry CJK and would crash on
        # Windows' default cp1252 codec
        with open(tpath, encoding="utf-8") as f:
            transcript = f.read().strip()

    video_tag = ""
    if video_path and os.path.exists(video_path):
        rel = os.path.relpath(video_path, out_dir)
        if not rel.startswith(".."):
            video_tag = f'<video src="{html.escape(rel)}" controls playsinline></video>'

    cells = "".join(
        f'<a href="frames/{os.path.basename(f)}" target="_blank">'
        f'<img src="frames/{os.path.basename(f)}" loading="lazy">'
        f'<span>{os.path.basename(f)}</span></a>'
        for f in frames
    )

    page = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>crv viewer</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box }}
  body {{ background:#0d0b07; color:#e8dfcf; font-family:Menlo,Consolas,monospace; padding:0 0 40px }}
  header {{ display:flex; justify-content:space-between; padding:14px 24px; border-bottom:1px solid #2a2418; margin-bottom:18px }}
  header .b {{ color:#f0b429; font-weight:700 }}
  header .r {{ color:#8a7a5f; font-size:12px }}
  main {{ max-width:1500px; margin:0 auto; padding:0 24px; display:grid; grid-template-columns:1.1fr 1fr; gap:20px }}
  video {{ width:100%; max-height:70vh; object-fit:contain; border-radius:12px; border:1px solid #3a3323; background:#000 }}
  h2 {{ font-size:12px; color:#8a7a5f; letter-spacing:.1em; margin:16px 0 10px }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:8px }}
  .grid a {{ position:relative; display:block; border:1px solid #2a2418; border-radius:8px; overflow:hidden }}
  .grid img {{ width:100%; display:block }}
  .grid span {{ position:absolute; left:0; bottom:0; right:0; font-size:10px; color:#c9bda3; background:rgba(13,11,7,.75); padding:2px 6px }}
  .tr {{ font-size:13px; line-height:1.7; color:#c9bda3; white-space:pre-wrap; border:1px solid #2a2418; border-radius:12px; padding:16px; background:#14110b; max-height:80vh; overflow:auto }}
  #lb {{ position:fixed; inset:0; display:none; background:rgba(13,11,7,.93); z-index:50;
        align-items:center; justify-content:center; flex-direction:column; gap:10px }}
  #lb.open {{ display:flex }}
  #lb img {{ max-width:92vw; max-height:84vh; border-radius:10px; border:1px solid #3a3323 }}
  #lb .cap {{ color:#c9bda3; font-size:12px }}
  #lb .hint {{ color:#8a7a5f; font-size:11px }}
  #lb .x {{ position:absolute; top:14px; right:22px; color:#c9bda3; font-size:26px; cursor:pointer }}
  #lb .nav {{ position:absolute; top:50%; transform:translateY(-50%); font-size:34px; color:#c9bda3;
             cursor:pointer; padding:20px; user-select:none }}
  #lb .prev {{ left:6px }} #lb .next {{ right:6px }}
  .lang a {{ color:#8a7a5f; cursor:pointer; margin-right:6px }}
  .lang a.on {{ color:#e8b64c }}
</style></head><body>
<header><div class="b">crv viewer</div><div class="r"><span class="lang"><a data-lang="zh_tw">繁中</a> <a data-lang="zh_cn">简中</a> <a data-lang="en">EN</a></span> <span data-i="local">runs 100% locally</span> · {len(frames)} keyframes · <a href="https://leoaido.com/crv-pro/" target="_blank" rel="noopener" style="color:inherit;opacity:.65">Pro</a></div></header>
<main>
  <div>
    {video_tag}
    <h2 data-i="kf">KEYFRAMES — what the model will see</h2>
    <div class="grid">{cells}</div>
  </div>
  <div>
    <h2 data-i="tr">TRANSCRIPT</h2>
    <div class="tr">{html.escape(transcript) or "(no transcript)"}</div>
  </div>
</main>
<div id="lb">
  <div class="x" onclick="lbClose()">&times;</div>
  <div class="nav prev" onclick="lbStep(-1)">&#8249;</div>
  <img id="lb-img" alt="">
  <div class="cap" id="lb-cap"></div>
  <div class="hint">&larr; &rarr; browse &middot; ESC close &middot; click outside to close</div>
  <div class="nav next" onclick="lbStep(1)">&#8250;</div>
</div>
<script>
(function () {{
  var links = Array.prototype.slice.call(document.querySelectorAll(".grid a"));
  var idx = -1, lb = document.getElementById("lb"),
      im = document.getElementById("lb-img"), cap = document.getElementById("lb-cap");
  function show(i) {{
    idx = (i + links.length) % links.length;
    im.src = links[idx].getAttribute("href");
    cap.textContent = links[idx].querySelector("span").textContent + "  (" + (idx + 1) + "/" + links.length + ")";
    lb.classList.add("open");
  }}
  window.lbClose = function () {{ lb.classList.remove("open"); }};
  window.lbStep = function (d) {{ show(idx + d); }};
  links.forEach(function (a, i) {{
    a.addEventListener("click", function (e) {{ e.preventDefault(); show(i); }});
  }});
  lb.addEventListener("click", function (e) {{ if (e.target === lb) lbClose(); }});
  document.addEventListener("keydown", function (e) {{
    if (!lb.classList.contains("open")) return;
    if (e.key === "Escape") lbClose();
    else if (e.key === "ArrowLeft") lbStep(-1);
    else if (e.key === "ArrowRight") lbStep(1);
  }});
}})();
(function () {{
  var D = {{
    zh_tw: {{ local:"全程本機執行", kf:"關鍵幀——模型看到的畫面", tr:"逐字稿", none:"（沒有逐字稿）" }},
    zh_cn: {{ local:"全程本机运行", kf:"关键帧——模型看到的画面", tr:"逐字稿", none:"（没有逐字稿）" }},
    en:    {{ local:"runs 100% locally", kf:"KEYFRAMES — what the model will see", tr:"TRANSCRIPT", none:"(no transcript)" }}
  }};
  function set(l) {{
    localStorage.setItem("crv_lang", l);
    document.querySelectorAll("[data-i]").forEach(function (el) {{ el.textContent = D[l][el.dataset.i]; }});
    document.querySelectorAll(".lang a").forEach(function (a) {{ a.classList.toggle("on", a.dataset.lang === l); }});
    var tr = document.querySelector(".tr");
    if (tr) {{
      var t = tr.textContent.trim();
      if (t === "(no transcript)" || t === "（沒有逐字稿）" || t === "（没有逐字稿）") tr.textContent = D[l].none;
    }}
  }}
  document.querySelectorAll(".lang a").forEach(function (a) {{
    a.addEventListener("click", function () {{ set(a.dataset.lang); }});
  }});
  set(localStorage.getItem("crv_lang") || "zh_tw");
}})();
</script>
</body></html>
"""
    out = os.path.join(out_dir, "viewer.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    return out
