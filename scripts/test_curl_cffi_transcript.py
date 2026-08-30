from curl_cffi import requests
import re
import json

TEST_VIDEOS = [
    ("ARK Invest TSLA", "hoi59k5zh1A"),
    ("MrBoKong (波空)", "t8GzqXu2_6Q"),
    ("EverythingMoney", "U395oTkpXsE"),
]

print("🚀 开始测试通过 curl_cffi (Chrome TLS 指纹伪装) 获取 YouTube 真实字幕...\n")

for name, vid in TEST_VIDEOS:
    url = f"https://www.youtube.com/watch?v={vid}"
    print(f"🔍 请求页面: {name} ({url})...")
    
    try:
        # 1. 以真实 Chrome 124 浏览器指纹访问视频主页
        s = requests.Session(impersonate="chrome124")
        resp = s.get(url, timeout=15)
        
        # 2. 提取 ytInitialPlayerResponse 中的 captions
        m = re.search(r'ytInitialPlayerResponse\s*=\s*({.+?});', resp.text)
        if not m:
            m = re.search(r'var ytInitialPlayerResponse\s*=\s*({.+?});', resp.text)
            
        if not m:
            print("  ❌ 未在页面中找到 ytInitialPlayerResponse\n")
            continue
            
        player_json = json.loads(m.group(1))
        captions = player_json.get("captions", {}).get("playerCaptionsTracklistRenderer", {}).get("captionTracks", [])
        
        if not captions:
            print(f"  ❌ 该视频无公开字幕轨道 (captions 为空)\n")
            continue
            
        print(f"  🎯 发现 {len(captions)} 个字幕轨: {[c.get('languageCode') for c in captions]}")
        
        # 选取中英文字幕
        chosen_track = captions[0]
        for c in captions:
            code = c.get("languageCode", "")
            if code.startswith("zh") or code == "en":
                chosen_track = c
                break
                
        base_url = chosen_track.get("baseUrl")
        print(f"  📡 请求字幕数据流: {chosen_track.get('name', {}).get('simpleText')} ({chosen_track.get('languageCode')})...")
        
        # 3. 以 Chrome TLS 指纹请求 timedtext 接口 (json3 格式)
        cap_resp = s.get(base_url + "&fmt=json3", timeout=15)
        
        if cap_resp.status_code == 200 and not cap_resp.text.strip().startswith("<"):
            cap_json = cap_resp.json()
            events = cap_json.get("events", [])
            lines = []
            for ev in events:
                segs = ev.get("segs", [])
                txt = "".join([sg.get("utf8", "") for sg in segs]).replace("\n", " ").strip()
                if txt and txt not in lines:
                    lines.append(txt)
                    
            full_text = " ".join(lines)
            print(f"  🎉 成功获取到真实逐字稿！总句数: {len(lines)}, 字符数: {len(full_text)}")
            print(f"  📝 前 120 字符预览: {full_text[:120]}...\n")
        else:
            print(f"  ⚠️ 字幕响应状态码: {cap_resp.status_code}, 内容预览: {cap_resp.text[:100]}...\n")
            
    except Exception as e:
        print(f"  ❌ 异常: {e}\n")
