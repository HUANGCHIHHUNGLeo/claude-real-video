# crv 第二輪文案＋留言回覆稿 — 2026-07-07（待 Leo 審）

## A. HN 回覆稿（帳號 cortexosmain，英文）

### A1. mh-（PyPI GitHub 連結 404）
> Thanks for flagging this — just checked and the links on PyPI resolve fine now (the repo went public a few hours after the first PyPI release, so you likely hit that window). Let me know if you still see a 404 anywhere.

### A2. bonoboTP（隱私質疑：幀還是送 Anthropic）
> Fair point, and you're right — I should be more precise. The extraction, scene detection, dedup and transcript all run locally; nothing is uploaded by crv itself. But the selected frames go to whatever LLM you point them at, so if that's Claude's API, those frames do leave your machine. "Local" here means the processing pipeline, not the inference. I've been tightening the README wording on this.

### A3. fred123123（快速捲動畫面怎麼處理）
> Fast scrolling is actually the easy case — every scroll step trips the scene-change detector, and the sliding-window dedup then collapses near-identical frames so you keep the distinct screens without 40 copies of the same list. The threshold is tunable with --scene if it over- or under-fires. The hard case was the opposite (slow morphs that never spike any single frame), which is what --adaptive in 0.5.3 addresses.

### A4. fzysingularity / nickvec / kraflio（token 成本，回在 fzysingularity 底下）
> Cost depends entirely on how many frames survive dedup. Ballpark from my own use: a 1-minute screen recording ends up as ~20-30 keyframes, and with --grid those pack into 3-4 contact sheets, so you're looking at a few thousand image tokens per minute rather than tens of thousands. And agreed on model choice — crv is model-agnostic (it just produces frames + manifest), so pointing the output at Gemini or a local VLM works fine if that's cheaper for your volume.

### A5. octember（keyframes ≠ video，motion 推不出來）
> Agreed, keyframes are a lossy view and things like easing curves or object permanence across cuts won't survive. The claim isn't "full video understanding" — it's that for most practical asks (what happens in this tutorial, what changed in this demo, what does this UI flow do) scene-aware frames + transcript get an LLM 90% of the way at a fraction of the cost. For motion-critical content you can crank the sampling, and 0.5.3's --adaptive helps with gradual changes, but genuine temporal reasoning needs a video-native model.

### A6. garciasn / torhorway（Claude 明明收影片檔）
> Worth clarifying: the Claude consumer apps accept video uploads, but the API and Claude Code don't — and that's where agents and pipelines live. crv exists for that gap: it turns a video into something any text+image model can consume, regardless of vendor.

### A7. ProofHouse（想貢獻）
> Would love that — issues are open and the codebase is small enough to read in one sitting. The areas I'd most welcome help on right now are additional transcript backends and smarter grid packing.

### A8. Lerc（多幀分辨動作方向）
> Frames are ordered and timestamped in the manifest, so models generally get direction right when the motion spans multiple keyframes. Single-keyframe motion (a fast gesture inside one scene) is where it fails — that information just isn't in the sample. --adaptive narrows that window but doesn't close it.

## B. Threads 第二輪（破千星里程碑文，@kanisleo328）

一週前我把 crv 丟上 GitHub 的時候，想說有個幾十顆星就很開心了。
今天它破 1200 顆星了。

這一週發生的事：上了 Hacker News 首頁、被幾十個工程師拷問（隱私、成本、keyframe 到底算不算看影片，每一題都被問爆）、收到第一批真用戶的 issue——有人拿它看慢動作教學影片抓不到幀，我加了 --adaptive；有人想先預覽 AI 會看到什麼，我加了 --viewer。

最有感的一件事：開源專案的成長不是來自你多會宣傳，是來自有人真的用了、卡住了、回來跟你說。每一個 issue 都比一百個讚值錢。

工具是免費的，GitHub 搜 claude-real-video 或 pip install claude-real-video 就有。你拿它看過最特別的影片是什麼？我看到有人拿去分析 DOS 遊戲的 sprite。

## C. Reddit 重發（r/SideProject，帳號 Various_Story8026）

標題：My open-source tool for letting LLMs "watch" videos hit 1.2k GitHub stars in a week — here's what it does

內文：
LLMs can't watch videos — they read subtitles at best. I built claude-real-video (crv): point it at a URL or local file, it extracts only the frames that matter (scene-change detection + sliding-window dedup, no ML models to download), builds a manifest with timestamps + transcript, and any LLM — Claude, Gemini, local VLMs — can then actually reason about the video.

A 58-second clip at 1 fps would be 58 frames; crv keeps the 26 that differ and can pack them into 3 contact sheets, so it's cheap enough to use in agent pipelines.

Front page of HN last week, 1.2k stars, and the first real-user issues already shaped two releases (--adaptive for slow-changing scenes, --viewer for previewing what the model sees).

pip install claude-real-video / GitHub: HUANGCHIHHUNGLeo/claude-real-video — feedback very welcome.

## D. Threads 留言回覆（isabella_0710c 深談追問）

你講到重點了，去重只是省 token 的手段，真正有價值的是把「這幾幀為什麼被留下來」的脈絡一起交給模型——時間戳、場景切換點、對應的逐字稿段落，這些合起來才是敘事結構。模型拿到的不是一疊圖，是一條有因果的時間軸。多模態模型的時間推理天花板還在，但至少餵進去的東西先有骨架。

## E. 其他平台判斷

- IG：不欠留言債。第二輪建議做「crv 一週破千星幕後」輪播（素材=HN 拷問＋issue 驅動迭代的故事），文案骨架同 B 改編，Leo 點頭我再進 ig-carousel 產製。
- dev.to：0 迴響，建議先擱置，不值得再投一篇。
- LinkedIn：需人工看第一輪狀態，待查。
- X：Leo 已自發，不動。
