#!/usr/bin/env python3
"""
全新极简精准 AI 研报流水线 (Concise & Accurate AI Pipeline)
专注于：Andrej Karpathy, Dave Ebbelaar, Jeff Su, Tina Huang, Google Cloud Tech, Matt Wolfe, AI Explained
原则：准确、简洁、高信噪比、100% 忠于视频原貌、绝不强塞无关代码。
"""

from __future__ import annotations
import os
import sys
import re
import json
import time
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List
import requests
from google import genai

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from summarizer.utils import sanitize_filename
from summarizer.channel_catalog import AI_CHANNELS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(PROJECT_ROOT / "ai_generation.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("AIPipeline")

OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


BATCH_SIZE = 3  # 单次合并处理 3 个视频

MODEL_POOL = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest",
]


def load_gemini_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        env_file = PROJECT_ROOT / ".env"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        api_key = line.strip().split("=", 1)[1].strip("\"'")
    if not api_key:
        raise ValueError("未找到 GEMINI_API_KEY，请在 .env 中配置！")
    return genai.Client(api_key=api_key)


def extract_channel_videos_fast(channel_url: str, limit: int = 30) -> List[Dict[str, Any]]:
    """使用 yt-dlp flat-playlist 准确拉取频道全部前 N 个视频"""
    cmd = [
        str(PROJECT_ROOT / ".venv" / "bin" / "yt-dlp"),
        "--flat-playlist",
        "-j",
        channel_url,
        "--playlist-end",
        str(limit)
    ]
    entries = []
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        seen_ids = set()
        for line in res.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line.strip())
                vid = data.get("id") or data.get("url")
                title = data.get("title", f"Video {vid}")
                if vid and vid not in seen_ids:
                    seen_ids.add(vid)
                    entries.append({
                        "id": vid,
                        "title": title,
                        "url": f"https://www.youtube.com/watch?v={vid}"
                    })
            except Exception:
                pass
    except Exception as e:
        logger.error(f"解析频道视频失败 ({channel_url}): {e}")
    return entries


def get_real_publish_date(video_id: str) -> str:
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        m = re.search(r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})"', resp.text)
        if m:
            return m.group(1)
        m2 = re.search(r'itemprop="datePublished"\s+content="(\d{4}-\d{2}-\d{2})"', resp.text)
        if m2:
            return m2.group(1)
    except Exception as e:
        logger.debug(f"获取日期失败 ({video_id}): {e}")
    return time.strftime("%Y-%m-%d")


def generate_concise_reports(client: genai.Client, video_batch: List[Dict[str, Any]], channel_name: str) -> Dict[str, str]:
    """生成简洁、精准、高信噪比的总结报告"""
    prompt_items = []
    for idx, v in enumerate(video_batch, 1):
        prompt_items.append(f"""### 视频 #{idx}
- 视频ID：{v['video_id']}
- 视频标题：{v['title']}
- 视频链接：{v['url']}
- 发布日期：{v['pub_date']}
- 作者/频道：{channel_name}
""")

    prompt = f"""你是一名顶级技术分析师与高质量内容总结专家。
请针对以下 {len(video_batch)} 个 YouTube 视频，分别撰写一份【准确、简洁、高信噪比的内容总结报告】。

{"".join(prompt_items)}

【严格准则】：
1. **准确与忠实**：100% 基于视频实际讲解的内容进行总结，绝不主观捏造，严禁编造不相关的代码或虚假回测。
2. **简洁直击要害**：去除一切客套与冗余废话，语言精炼，突出重点。
3. **因片制宜**：若视频主要讲工具操作，重点总结操作流程与配置；若讲算法原理，重点总结逻辑架构；若讲观点趋势，重点总结论点论据。

请按顺序输出这 {len(video_batch)} 份总结。每份总结之间使用固定的分割线 `===REPORT_SPLIT:{video_batch[0]['video_id']}===` 隔开。

总结模板格式：
===REPORT_SPLIT:VIDEO_ID_HERE===
# 🎬 视频真实标题

- **创作者**：`{channel_name}` | **发布日期**：`YYYY-MM-DD` | **原视频链接**：[YouTube 视频](URL)

---

### 📌 一句话核心主旨 (TL;DR)
（用 1~2 句话极简概括：视频核心讲了什么？解决了什么问题或传达了什么核心观点？）

### 🔍 核心要点精炼拆解 (Key Takeaways)
（分 3~5 个重点模块，用高度凝练的要点清单，清晰拆解视频中讲解的核心原理、工具对比、技术细节或论点链条）

### 💡 实操建议与落地启示 (Actionable Insights)
（提炼博主给出的最实用、最具实操价值的建议、操作步骤、配置推荐或决策思路）

### ⚠️ 局限性与注意事项 (Caveats & Limitations)
（博主提及的潜在局限性、适用边界或避坑提醒。若无特殊限制可简要注明）
"""

    raw_text = None
    last_err = None
    for model_name in MODEL_POOL:
        try:
            logger.info(f"    🤖 正在调用模型 [{model_name}] 生成简洁精准研报...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            raw_text = response.text
            break
        except Exception as me:
            last_err = me
            logger.warning(f"    ⚠️ 模型 [{model_name}] 暂不可用，尝试切换下一个可用模型...")
            time.sleep(2.0)

    if not raw_text:
        raise last_err or RuntimeError("所有可用模型均被限制")

    results = {}
    parts = re.split(r'===REPORT_SPLIT:([a-zA-Z0-9_-]+)===', raw_text)
    if len(parts) >= 3:
        for i in range(1, len(parts), 2):
            vid = parts[i].strip()
            content = parts[i+1].strip()
            results[vid] = content
    else:
        for v in video_batch:
            vid = v["video_id"]
            results[vid] = raw_text

    return results


def update_indexes():
    """更新所有频道 INDEX.md 与全局 INDEX.md"""
    global_index_path = OUTPUT_DIR / "INDEX.md"
    channels_summary = []
    total_reports = 0

    subdirs = sorted([d for d in OUTPUT_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")])

    for ch_dir in subdirs:
        reports = sorted(list(ch_dir.glob("*.md")), reverse=True)
        reports = [r for r in reports if r.name != "INDEX.md"]
        if not reports:
            continue

        ch_name = ch_dir.name.replace("_", " ")
        ch_index_path = ch_dir / "INDEX.md"
        ch_lines = [
            f"# 📚 {ch_name} - 精简研报索引",
            f"\n> 累计提炼精准报告：`{len(reports)}` 篇\n",
            "| 发布日期 | 视频标题 | 报告文档 |",
            "| :--- | :--- | :--- |",
        ]
        for r in reports:
            parts = r.stem.split("_", 2)
            date_str = parts[0] if len(parts) > 0 else "-"
            title_str = parts[2] if len(parts) > 2 else r.stem
            ch_lines.append(f"| `{date_str}` | {title_str} | [{r.name}](./{r.name}) |")

        with open(ch_index_path, "w", encoding="utf-8") as cif:
            cif.write("\n".join(ch_lines) + "\n")

        channels_summary.append((ch_name, len(reports), ch_dir.name))
        total_reports += len(reports)

    g_lines = [
        "# 🌐 YouTube 顶级 AI 技术与策略精炼知识库",
        f"\n> 收录频道总数：`{len(channels_summary)}` 个 | 累计精炼报告：`{total_reports}` 篇\n",
        "## 📁 各创作者研报导航",
        "| 创作者 / 频道 | 报告数量 | 报告目录 |",
        "| :--- | :---: | :--- |",
    ]
    for c_name, c_cnt, c_dir in channels_summary:
        g_lines.append(f"| **{c_name}** | `{c_cnt}` 篇 | [查看报告列表](./{c_dir}/INDEX.md) |")

    with open(global_index_path, "w", encoding="utf-8") as gif:
        gif.write("\n".join(g_lines) + "\n")
    logger.info("📑 全局与频道索引 INDEX.md 更新完成！")


def run_clean_ai_pipeline(max_videos_per_channel: int = 30):
    client = load_gemini_client()
    logger.info("==================================================================")
    logger.info(f"🚀 启动全新【极简精准】AI 视频研报流水线 (批次大小: {BATCH_SIZE})")
    logger.info("==================================================================")

    grand_total = 0

    for ch_idx, (ch_name, ch_url) in enumerate(AI_CHANNELS, 1):
        logger.info(f"\n[{ch_idx}/{len(AI_CHANNELS)}] 正在扫描频道: {ch_name}")
        ch_dir = OUTPUT_DIR / sanitize_filename(ch_name)
        ch_dir.mkdir(parents=True, exist_ok=True)

        existing_reports = list(ch_dir.glob("*.md"))
        existing_ids = set()
        for er in existing_reports:
            parts = er.stem.split("_")
            if len(parts) >= 2:
                existing_ids.add(parts[1])

        entries = extract_channel_videos_fast(ch_url, max_videos_per_channel)

        pending_videos = []
        for entry in entries:
            vid = entry.get("id")
            title = entry.get("title", f"Video {vid}")
            if vid in existing_ids:
                continue
            
            pub_date = get_real_publish_date(vid)
            pending_videos.append({
                "video_id": vid,
                "title": title,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "pub_date": pub_date
            })

        logger.info(f"  🔍 频道已有: {len(existing_reports)} 篇，待处理视频: {len(pending_videos)} 个")

        for b_start in range(0, len(pending_videos), BATCH_SIZE):
            batch = pending_videos[b_start : b_start + BATCH_SIZE]
            batch_titles = " | ".join([f"[{v['video_id']}] {v['title'][:20]}" for v in batch])
            logger.info(f"  📦 正在提炼批次 ({b_start+1}-{b_start+len(batch)}/{len(pending_videos)}): {batch_titles}")

            for retry in range(10):
                try:
                    reports_map = generate_concise_reports(client, batch, ch_name)
                    for v in batch:
                        vid = v["video_id"]
                        report_content = reports_map.get(vid)
                        if not report_content:
                            continue
                        
                        clean_title = sanitize_filename(v["title"])[:45]
                        report_filename = f"{v['pub_date']}_{vid}_{clean_title}.md"
                        report_path = ch_dir / report_filename
                        with open(report_path, "w", encoding="utf-8") as rf:
                            rf.write(report_content)
                        
                        logger.info(f"    🎉 成功生成精准报告: {report_filename}")
                        existing_ids.add(vid)
                        grand_total += 1
                    
                    time.sleep(12.0)
                    break
                except Exception as be:
                    be_str = str(be)
                    if "RESOURCE_EXHAUSTED" in be_str or "429" in be_str:
                        delay_match = re.search(r'retryDelay[\'"]\s*:\s*[\'"]?(\d+)', be_str)
                        wait_seconds = int(delay_match.group(1)) + 5 if delay_match else 45
                        logger.warning(f"  ⏳ 触发短时频控，自动休眠 {wait_seconds} 秒后恢复 (重试 {retry+1}/10)...")
                        time.sleep(wait_seconds)
                    else:
                        logger.error(f"  ❌ 批次生成异常: {be}")
                        time.sleep(5.0)
                        break

            update_indexes()

        logger.info(f"✅ 频道 {ch_name} 处理完毕！")

    logger.info(f"\n🏁 全部频道处理完毕！累计生成 {grand_total} 篇全新极简精准研报！")


if __name__ == "__main__":
    run_clean_ai_pipeline(max_videos_per_channel=30)
