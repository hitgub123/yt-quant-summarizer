from playwright.sync_api import sync_playwright
import json
import shutil
import sys

chrome_path = shutil.which("chromium") or "/snap/bin/chromium"

with open("youtube_cookies.txt", "r") as f:
    text = f.read().strip()
    if text.endswith("."):
        text = text[:-1].strip()
    raw_cookies = json.loads(text)

playwright_cookies = []
for c in raw_cookies:
    pc = {
        "name": c["name"],
        "value": c["value"],
        "domain": c["domain"],
        "path": c.get("path", "/"),
        "secure": c.get("secure", False),
        "httpOnly": c.get("httpOnly", False),
    }
    if c.get("sameSite") in ["Strict", "Lax", "None"]:
        pc["sameSite"] = c["sameSite"]
    playwright_cookies.append(pc)

with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=chrome_path,
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 800}
    )
    context.add_cookies(playwright_cookies)
    page = context.new_page()
    
    url = "https://www.youtube.com/watch?v=hoi59k5zh1A"
    print(f"🚀 正在访问视频: {url}", flush=True)
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)
    
    print("📜 点击展开简介...", flush=True)
    page.evaluate("""() => {
        const expandBtn = document.querySelector("#expand") || document.querySelector("tp-yt-paper-button#expand") || document.querySelector("#description-inline-expander");
        if (expandBtn) expandBtn.click();
    }""")
    page.wait_for_timeout(2000)
    
    print("📜 点击 Show transcript 按钮...", flush=True)
    res = page.evaluate("""() => {
        const buttons = Array.from(document.querySelectorAll("button, ytd-button-renderer"));
        for (const b of buttons) {
            const t = (b.innerText || "").toLowerCase();
            if (t.includes("transcript") || t.includes("文字记录") || t.includes("字幕")) {
                b.click();
                return "Clicked: " + t;
            }
        }
        return "Not found";
    }""")
    print(f"点击状态: {res}", flush=True)
    
    # 等待字幕面板加载出来
    print("⏳ 等待字幕面板渲染...", flush=True)
    try:
        page.wait_for_selector("ytd-transcript-segment-renderer", timeout=12000)
    except Exception as e:
        print(f"等待选择器超时: {e}", flush=True)
    
    page.wait_for_timeout(2000)
    
    segments_data = page.evaluate("""() => {
        const segs = Array.from(document.querySelectorAll("ytd-transcript-segment-renderer"));
        if (segs.length === 0) {
            // 兜底尝试查找包含时间戳的节点
            const allItems = Array.from(document.querySelectorAll("yt-formatted-string, div"));
            const candidateTexts = allItems
                .filter(el => el.innerText && /^[0-9]{1,2}:[0-9]{2}/.test(el.innerText.trim()))
                .map(el => ({ time: el.innerText.split("\\n")[0], text: el.innerText.split("\\n").slice(1).join(" ") }));
            if (candidateTexts.length > 0) return candidateTexts;
        }
        return segs.map(s => {
            const timeEl = s.querySelector(".segment-timestamp, .ytd-transcript-segment-renderer");
            const textEl = s.querySelector(".segment-text, yt-formatted-string");
            return {
                time: timeEl ? timeEl.innerText.trim() : "",
                text: textEl ? textEl.innerText.trim() : s.innerText.trim()
            };
        });
    }""")
    
    print(f"🎉 成功从真实网页 DOM 提取到 {len(segments_data)} 条带时间戳的字幕记录！", flush=True)
    for s in segments_data[:10]:
        print(f"  [{s.get('time')}] {s.get('text')}", flush=True)
        
    browser.close()
