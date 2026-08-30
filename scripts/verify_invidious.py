#!/usr/bin/env python3
"""
验证方案 2: 使用 Invidious / Piped 开源公共节点获取真实 YouTube 字幕
"""

import requests
import json
import time

# 测试用的典型视频 ID
TEST_VIDEOS = [
    ("ARK Invest (TSLA)", "hoi59k5zh1A"),
    ("EverythingMoney", "U395oTkpXsE"),
    ("MrBoKong (波空)", "t8GzqXu2_6Q"),
    ("Andrei Jikh", "Uw84lTiD5C8"),
]

# 常用高健康度 Invidious 实例列表
INVIDIOUS_INSTANCES = [
    "https://inv.tux.pizza",
    "https://invidious.nerdvpn.de",
    "https://yewtu.be",
    "https://invidious.private.coffee",
    "https://invidious.projectsegfau.lt",
    "https://iv.ggtyler.dev",
    "https://invidious.jing.rocks",
]

def test_invidious_instances():
    print("=" * 80)
    print("🚀 开始验证方案 2: Invidious 开源公共字幕解析节点")
    print("=" * 80)

    # 1. 寻找可用的健康实例
    healthy_instances = []
    print("\n🔍 正在测试公共实例连接状态...")
    for inst in INVIDIOUS_INSTANCES:
        try:
            r = requests.get(f"{inst}/api/v1/stats", timeout=4)
            if r.status_code == 200:
                print(f"  ✅ 节点可用: {inst}")
                healthy_instances.append(inst)
            else:
                print(f"  ⚠️ 节点状态码 {r.status_code}: {inst}")
        except Exception as e:
            print(f"  ❌ 节点超时/不可达: {inst} ({e})")

    if not healthy_instances:
        print("\n❌ 未找到可用的 Invidious 公共节点，尝试动态拉取官方实例列表...")
        try:
            r = requests.get("https://api.invidious.io/instances.json?sort_by=health", timeout=5)
            data = r.json()
            for item in data:
                uri = item[1].get("uri")
                if uri and item[1].get("type") == "https":
                    healthy_instances.append(uri)
                    if len(healthy_instances) >= 5:
                        break
        except Exception as ex:
            print(f"获取官方实例列表失败: {ex}")

    print(f"\n🎉 筛选出 {len(healthy_instances)} 个可用公共解析节点: {healthy_instances}")

    # 2. 对测试视频提取字幕
    print("\n" + "=" * 80)
    print("🎯 开始通过公共节点拉取视频字幕...")
    print("=" * 80)

    results = []
    for title, vid in TEST_VIDEOS:
        print(f"\n📺 测试视频: {title} (ID: {vid})")
        success = False
        sample_transcript = ""

        for inst in healthy_instances:
            try:
                # 方式 A: 获取视频信息
                api_url = f"{inst}/api/v1/videos/{vid}?fields=captions"
                resp = requests.get(api_url, timeout=6)
                if resp.status_code != 200:
                    continue

                data = resp.json()
                captions = data.get("captions", [])
                if not captions:
                    print(f"  [{inst}] 视频无可用字幕轨")
                    continue

                print(f"  [{inst}] 发现 {len(captions)} 个字幕轨: {[c.get('languageCode') for c in captions]}")

                # 选取中英文字幕
                target_cap = None
                for c in captions:
                    code = c.get("languageCode", "")
                    if code.startswith("zh") or code == "en":
                        target_cap = c
                        break
                if not target_cap:
                    target_cap = captions[0]

                cap_url = inst + target_cap.get("url")
                cap_resp = requests.get(cap_url, timeout=6)
                if cap_resp.status_code == 200 and len(cap_resp.text) > 50:
                    sample_transcript = cap_resp.text[:200].replace("\n", " ")
                    print(f"  🎉 成功从 [{inst}] 拉取到完整字幕！语种: {target_cap.get('languageCode')} (长度: {len(cap_resp.text)} 字符)")
                    print(f"  📝 内容预览: {sample_transcript}...")
                    success = True
                    break
            except Exception as e:
                print(f"  ⚠️ [{inst}] 请求异常: {e}")
                continue

        results.append((title, vid, "✅ 验证通过 (秒级提取)" if success else "❌ 提取失败", sample_transcript[:60]))

    print("\n" + "=" * 85)
    print(f"{'视频名称':<25} | {'视频 ID':<12} | {'方案 2 可行性':<15} | {'字幕内容预览'}")
    print("=" * 85)
    for r in results:
        print(f"{r[0]:<25} | {r[1]:<12} | {r[2]:<15} | {r[3]}")
    print("=" * 85)

if __name__ == "__main__":
    test_invidious_instances()
