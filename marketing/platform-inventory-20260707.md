# crv 各平台宣傳盤點 — 2026-07-07

資料來源：Threads/IG Graph API、HN Algolia API、dev.to API、Reddit JSON（經瀏覽器讀取）、GitHub API。全部為當日實測讀回，非印象。

**GitHub 現況**：1,213 stars / 73 forks / 0 open issues（2026-07-07 查）

---

## 1. Threads @kanisleo328 — 主戰場，成效最好

### 貼文一：主宣傳文（2026-07-04 01:03 UTC）
- https://www.threads.com/@kanisleo328/post/DaWg_q5DSFV
- 內容：三天前丟上 GitHub → 登 HN 首頁、破 500 星；工具解決「AI 看不懂影片」
- 數據：606 likes / 104 replies / 32,588 views / 64 reposts
- 留言處理狀況：104 則已幾乎全回，**只剩 2 則未回**：
  1. isabella_0710c（第二則留言，substantive）：「這問題其實比你想的更深層——多模態模型還是在看圖說故事，很難理解時間軸上的因果邏輯。你工具的核心價值不只是截圖去重，而是幫 AI 重建了『這段畫面為什麼存在』的敘事結構…」（此人第一則已回；這則是追加深談，帳號帶推廣性質「編夢者」）
  2. yuyuqueen16888：借樓推「百秒學AI」課程的廣告留言 → 可不回或無視

### 貼文二：Product Hunt 拉票文（2026-07-05 09:09 UTC）
- https://www.threads.com/@kanisleo328/post/DaZ9gsSj7Da
- 內容：星星 415→828、今天上 PH 求支持
- 數據：317 likes / 10 replies / 22,954 views / 22 reposts
- 未回留言 **1 則**：makuro.8「很厲害恭喜你」（純恭喜，低優先）

### 貼文三：首發預告文（2026-06-30 11:02 UTC）
- https://www.threads.com/@kanisleo328/post/DaNSdeqgQFd
- 數據：13 likes / 5 replies / 1,050 views
- 留言全處理完（僅 1 則外部留言，已回）

Threads 小結：第一輪兩波（工具文＋PH 拉票文）合計約 5.5 萬 views、900+ likes，留言維護做得很乾淨。

---

## 2. IG @kanisleo328 — 觸發字留言機制，已自動回完

### crv 貼文（2026-07-03 12:01 UTC，輪播）
- https://www.instagram.com/p/DaVHoW5CC21/
- 內容：AI 沒看懂影片 → crv 開源上 PyPI；CTA「分享+留言『影片』傳連結」
- 數據：139 likes / 417 comments（含子回覆）；頂層留言 210 則
- 留言處理：210 則頂層留言中 **207 則已由 kanisleo328 回覆**（絕大多數是「影片」「連結」觸發字），僅 3 則未回，且全是 emoji／觸發字類，無實質問題未答
- 結論：IG 這篇不欠留言債，但 139 likes 配 417 comments 表示觸發字漏斗有效、讚數普通

（7/4 另有一篇「7 步驟做網站」輪播 68 likes / 9 comments，非 crv 主題，不列入）

---

## 3. Hacker News — Show HN 上過首頁，欠最多留言債

### Show HN（2026-07-02 19:10 UTC，帳號 cortexosmain）
- https://news.ycombinator.com/item?id=48766005
- 標題：Claude-real-video － any LLM can watch a video
- 數據：**166 points**，60+ 則留言
- 已回：置頂自介（48766006）、rename 討論串（48779663，已做 pip install llm-real-video 別名）、NotebookLM 討論（48793176）
- **未被 cortexosmain 回覆的重點留言（依重要度排序）**：
  1. **mh-（bug 回報）**：「PyPI 頁上的 GitHub 連結 404」— 這是 bug，該先修再回
  2. **bonoboTP（隱私質疑，高熱度）**：「『影片留在你機器上』不對——抽出的幀還是會送去 Anthropic」（fny 幫答了半句，OP 沒正面回）
  3. **fred123123（直接問 OP）**：影片快速捲動（scrolling）畫面怎麼處理？
  4. **nickvec / kraflio / fzysingularity**：每秒影片吃多少 token？成本多貴？（fzysingularity 還說「用 Claude 看影片貴到可怕，用 Gemini 或本地 VLM 更省」，帶自家 vlm-run 連結）
  5. **octember**：keyframes 不等於影片，motion/object permanence 推不出來（技術性批評，值得正面回）
  6. **garciasn / torhorway**：聲稱 Claude 其實收影片檔（事實混淆，可澄清 Claude Code 與 API 差異）
  7. **ProofHouse**：說自己有類似工具、願意研究後貢獻（潛在 contributor，值得招呼）
  8. **gvkhna**：做過類似的，motion design 動畫細節 LLM 推不出來
  9. **BeetleB / AmazingEveryDay**：改名建議（已部分處理：llm-real-video 別名）
  10. **Lerc**：模型從多幀分辨動作方向的能力如何？
  11. 其他未回：ElijahLynn（電池充電量測用例）、noufalibrahim（DOS 遊戲 sprite 重製）、dingody（實測 2fps 夠用）、high_byte（ffmpeg scene detection 不穩）、Frost1x、wesleywt、virajk_31、nxtfari（讚美）、cpnwaugha（總結型）等
- 註：thread 已 4-5 天，HN 熱度已過；補回以「有人日後搜到」的價值為主，優先回 bug（mh-）與隱私質疑（bonoboTP）

---

## 4. dev.to — 已發但零迴響

- https://dev.to/huangchihhungleo/your-llm-isnt-watching-the-video-its-reading-subtitles-2jjl
- 發佈：2026-07-03 21:57 UTC（article id 4063259）
- 數據：**0 reactions / 0 comments**
- 未回留言：無（沒有留言）
- 判斷：第一輪沒起量，dev.to 靠 tag 與系列文累積，單篇冷啟動正常

---

## 5. Reddit — 第一輪被 AutoModerator 移除，等於沒發成

- r/LocalLLaMA：https://reddit.com/r/LocalLLaMA/comments/1ulrmae/i_built_a_tool_that_lets_any_llm_actually_watch_a/
- 帳號：Various_Story8026（2026-07-02 19:13 UTC 發）
- 標題：I built a tool that lets any LLM actually "watch" a video — scene-aware frame extraction + sliding-window dedup, runs 100% locally
- 數據：score 1 / 留言 1（只有 AutoModerator）
- **狀態：貼文已被移除**——AutoModerator 訊息：帳號 karma 不足，r/LocalLLaMA 反 spam 自動移除
- 未回留言：無（沒人看到）
- 判斷：Reddit 第一輪實質失敗。要嘛先養 karma（在別的 sub 正常留言互動），要嘛換 karma 門檻較低的 sub（r/SideProject、r/ClaudeAI 等），或聯絡 mod 申請放行
- 其他 sub 是否有發過：本次未查到其他貼文，帳號其餘活動未確認（標註：不確定）

---

## 6. LinkedIn — 需人工看

- API 讀不到。Leo 的個人頁：https://www.linkedin.com/in/leo-huang-444486363/
- 標註：需人工打開 recent activity 確認第一輪是否已發、迴響如何

---

## 7. X（Twitter）— Leo 已發第一輪

- Leo 自述已親自發過第一輪，本次不查、不重複發

---

## 附：Product Hunt（順帶記錄，非本次任務範圍）

- https://www.producthunt.com/products/claude-real-video — 7/5 已上架、Threads 有拉票文；launch day 數據未在本次盤點內查證

---

## 未回留言總表

| 平台 | 未回數 | 內容 |
|------|-------|------|
| Threads | 3 | isabella_0710c 深談（可回）、yuyuqueen16888 廣告（可略）、makuro.8 恭喜（可略） |
| IG | 3 | 全是觸發字/emoji，無實質問題 |
| HN | ~20 頂層未回 | 重點 6-8 則：mh- 404 bug、bonoboTP 隱私、fred123123 scrolling、token 成本 3 問、octember 技術批評、ProofHouse 潛在貢獻者 |
| dev.to | 0 | 無留言 |
| Reddit | 0 | 貼文被移除 |

實質該回：約 8-10 則（幾乎全在 HN）。
