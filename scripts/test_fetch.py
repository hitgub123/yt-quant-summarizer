from summarizer.subtitle_fetcher import SubtitleFetcher

fetcher = SubtitleFetcher()
test_targets = [
    ("ARK Invest TSLA", "hoi59k5zh1A"),
    ("EverythingMoney", "U395oTkpXsE"),
    ("MrBoKong", "t8GzqXu2_6Q"),
]

for name, vid in test_targets:
    print(f"Testing {name} ({vid})...")
    res = fetcher.fetch_transcript(vid)
    if res:
        print(f"  ✅ 成功获取 {name} 真实字幕！语种: {res.get('language')}, 长度: {len(res.get('full_text', ''))} 字符")
        print(f"  来源: {res.get('source')}")
        print(f"  预览: {res.get('full_text', '')[:120]}...\n")
    else:
        print(f"  ❌ {name} 获取失败\n")
