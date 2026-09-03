#!/usr/bin/env python3
"""
真实高精度视频研报流水线 (Authentic & Concise Video Summarizer)
设计核心：
1. 100% 真实数据来源：优先读取本地已缓存的字幕 (full_text) 与完整 metadata；
   若未缓存则通过 SubtitleFetcher / yt-dlp 抓取真实字幕与章节简介。
2. 绝对杜绝假标题与虚构内容：严格使用官方元数据与视频逐字稿作为 LLM 输入。
3. 风格严格遵循用户要求：精准、简洁、高信噪比，绝不强塞无关代码。
4. 单视频独立隔离处理：逐篇生成并落盘，绝不合并请求，杜绝串台错乱。
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
from typing import Dict, Any, List, Optional
import requests
from google import genai

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from summarizer.utils import sanitize_filename
from summarizer.subtitle_fetcher import SubtitleFetcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(PROJECT_ROOT / "authentic_generation.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("AuthenticPipeline")

OUTPUT_DIR = PROJECT_ROOT / "output"
TRANSCRIPTS_DIR = OUTPUT_DIR / ".transcripts"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

# 用户指定的重点 AI 频道列表
AI_CHANNELS = [
    ("Andrej Karpathy", "https://www.youtube.com/@AndrejKarpathy/videos"),
    ("Dave Ebbelaar", "https://www.youtube.com/@daveebbelaar/videos"),
    ("Jeff Su", "https://www.youtube.com/@JeffSu/videos"),
    ("Tina Huang", "https://www.youtube.com/@TinaHuang1/videos"),
    ("Google Cloud Tech", "https://www.youtube.com/@googlecloudtech/videos"),
    ("Matt Wolfe (mreflow)", "https://www.youtube.com/@mreflow/videos"),
    ("AI Explained", "https://www.youtube.com/@aiexplained-official/videos"),
]

# 官方当前支持的最佳模型池 (优先可用性)
MODEL_POOL = [
    "gemini-3.5-flash",
    "gemini-3.6-flash",
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


def get_channel_videos(channel_url: str, limit: int = 25) -> List[Dict[str, Any]]:
    """使用官方 yt-dlp flat-playlist 准确拉取频道视频列表（杜绝网页正则匹配）"""
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
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
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
                    # 格式化 upload_date
                    up_date = str(data.get("upload_date") or "")
                    if len(up_date) == 8:
                        pub_date = f"{up_date[:4]}-{up_date[4:6]}-{up_date[6:]}"
                    else:
                        pub_date = time.strftime("%Y-%m-%d")

                    entries.append({
                        "video_id": vid,
                        "title": title,
                        "pub_date": pub_date,
                        "url": f"https://www.youtube.com/watch?v={vid}"
                    })
            except Exception:
                pass
    except Exception as e:
        logger.error(f"提取频道视频失败 ({channel_url}): {e}")
    return entries


def get_video_content(video_id: str, channel_name: str) -> Dict[str, Any]:
    """
    获取视频真实内容：
    1. 优先读取 output/.transcripts/{channel_dir}/{video_id}.json 缓存；
    2. 若未缓存，通过 SubtitleFetcher 尝试抓取真实字幕并写入缓存；
    3. 若无法抓取字幕，通过 yt-dlp 拉取完整 Description (含章节时间戳 Chapters)。
    """
    ch_slug = sanitize_filename(channel_name)
    cached_file = TRANSCRIPTS_DIR / ch_slug / f"{video_id}.json"
    
    # 检查本地缓存
    if cached_file.exists():
        try:
            with open(cached_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                meta = data.get("metadata", {})
                trans = data.get("transcript", {})
                full_text = trans.get("full_text", "")
                if full_text:
                    logger.info(f"    📖 成功读取本地真实字幕缓存 ({len(full_text)} 字符)")
                    return {
                        "title": meta.get("title", ""),
                        "pub_date": meta.get("upload_date", ""),
                        "description": meta.get("description", ""),
                        "full_text": full_text,
                        "has_transcript": True
                    }
        except Exception as e:
            logger.debug(f"读取缓存异常 ({cached_file}): {e}")

    # 尝试抓取真实字幕
    fetcher = SubtitleFetcher()
    t_data = fetcher.fetch_transcript(video_id)
    full_text = t_data.get("full_text", "") if t_data else ""
    
    # 抓取 metadata 与 description
    cmd = [
        str(PROJECT_ROOT / ".venv" / "bin" / "yt-dlp"),
        "-j",
        f"https://www.youtube.com/watch?v={video_id}"
    ]
    meta = {}
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.stdout.strip():
            meta = json.loads(res.stdout.strip())
    except Exception as e:
        logger.debug(f"yt-dlp 获取详情异常 ({video_id}): {e}")

    title = meta.get("title", "")
    up_date = str(meta.get("upload_date") or "")
    pub_date = f"{up_date[:4]}-{up_date[4:6]}-{up_date[6:]}" if len(up_date) == 8 else time.strftime("%Y-%m-%d")
    description = meta.get("description", "")

    # 保存缓存
    if full_text:
        cached_dir = TRANSCRIPTS_DIR / ch_slug
        cached_dir.mkdir(parents=True, exist_ok=True)
        with open(cached_file, "w", encoding="utf-8") as cf:
            json.dump({
                "metadata": {
                    "video_id": video_id,
                    "title": title,
                    "channel": channel_name,
                    "upload_date": pub_date,
                    "description": description,
                    "url": f"https://www.youtube.com/watch?v={video_id}"
                },
                "transcript": {
                    "video_id": video_id,
                    "full_text": full_text
                }
            }, cf, ensure_ascii=False, indent=2)
        logger.info(f"    💾 新增字幕缓存: {cached_file.name} ({len(full_text)} 字符)")

    return {
        "title": title,
        "pub_date": pub_date,
        "description": description,
        "full_text": full_text,
        "has_transcript": bool(full_text)
    }


def generate_single_report(client: genai.Client, video_info: Dict[str, Any], channel_name: str) -> str:
    """基于真实内容生成单篇极简、精准、高信噪比研报"""
    vid = video_info["video_id"]
    title = video_info["title"]
    pub_date = video_info["pub_date"]
    url = video_info["url"]
    full_text = video_info.get("full_text", "")
    description = video_info.get("description", "")

    # 构造实际内容上下文（优先字幕，截取关键部分或全文）
    if full_text:
        # 如果文本超长，截取前 35000 字符（涵盖 1 小时以上长篇对话的全部核心）
        content_block = f"""【视频真实字幕逐字稿节选】：
{full_text[:35000]}
"""
    else:
        content_block = f"""【视频官方大纲与详细简介】：
{description[:8000]}
"""

    prompt = f"""你是一名顶级技术分析师与高质量内容总结专家。
请基于以下 YouTube 视频的【真实逐字稿/真实大纲内容】，撰写一份【准确、简洁、高信噪比的内容总结报告】。

【视频基本信息】：
- 视频标题：{title}
- 创作者/频道：{channel_name}
- 发布日期：{pub_date}
- 原视频链接：{url}

{content_block}

【严格输出准则】：
1. **绝对忠实于视频真实内容**：严禁主观臆造！视频讲了什么就总结什么，视频没讲的坚决不提。
2. **严禁强行编造代码**：仅当视频中创作者真正展示或编写了代码时，才提取相关代码片段；若视频是工具介绍、行业趋势、认知思考或工作流，严禁编造任何无关伪代码！
3. **极简、高信噪比**：去除所有客套话与废话，语言高度凝练，突出核心干货与实战价值。

请严格按照以下 Markdown 格式输出：

# 🎬 {title}

- **创作者**：`{channel_name}` | **发布日期**：`{pub_date}` | **原视频链接**：[YouTube 视频]({url})

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

    last_err = None
    for model_name in MODEL_POOL:
        try:
            logger.info(f"    🤖 正在调用模型 [{model_name}] 生成准确研报...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            if response.text and response.text.strip():
                return response.text.strip()
        except Exception as me:
            last_err = me
            logger.warning(f"    ⚠️ 模型 [{model_name}] 调用异常: {me}，尝试切换下一个可用模型...")
            time.sleep(2.0)

    raise last_err or RuntimeError("所有可用模型均被限制")


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
            f"# 📚 {ch_name} - 精准研报索引",
            f"\n> 累计提炼真实报告：`{len(reports)}` 篇\n",
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
        "# 🌐 YouTube 顶级 AI 技术与量化策略精炼知识库 (真实数据驱动)",
        f"\n> 收录频道总数：`{len(channels_summary)}` 个 | 累计精准报告：`{total_reports}` 篇\n",
        "## 📁 各创作者研报导航",
        "| 创作者 / 频道 | 报告数量 | 报告目录 |",
        "| :--- | :---: | :--- |",
    ]
    for c_name, c_cnt, c_dir in channels_summary:
        g_lines.append(f"| **{c_name}** | `{c_cnt}` 篇 | [查看报告列表](./{c_dir}/INDEX.md) |")

    with open(global_index_path, "w", encoding="utf-8") as gif:
        gif.write("\n".join(g_lines) + "\n")
    logger.info("📑 全局与频道索引 INDEX.md 更新完成！")


def run_pipeline():
    client = load_gemini_client()
    logger.info("==================================================================")
    logger.info("🚀 启动【真实数据驱动】极简精准研报流水线 (单视频严格隔离模式)")
    logger.info("==================================================================")

    total_done = 0

    for ch_idx, (ch_name, ch_url) in enumerate(AI_CHANNELS, 1):
        logger.info(f"\n[{ch_idx}/{len(AI_CHANNELS)}] 正在全量获取频道视频: {ch_name}")
        ch_dir = OUTPUT_DIR / sanitize_filename(ch_name)
        ch_dir.mkdir(parents=True, exist_ok=True)

        existing_reports = list(ch_dir.glob("*.md"))
        existing_ids = set()
        for er in existing_reports:
            parts = er.stem.split("_")
            if len(parts) >= 2:
                existing_ids.add(parts[1])

        videos = get_channel_videos(ch_url, limit=20)
        logger.info(f"  🔍 频道已有: {len(existing_reports)} 篇，待处理视频: {len(videos) - len(existing_ids)} 个")

        for v_idx, v in enumerate(videos, 1):
            vid = v["video_id"]
            if vid in existing_ids:
                continue

            logger.info(f"  🎬 [{v_idx}/{len(videos)}] 正在处理: {v['title']} (ID: {vid})")

            # 获取真实视频内容（优先本地字幕缓存）
            content_data = get_video_content(vid, ch_name)
            v_info = {
                "video_id": vid,
                "title": content_data["title"] or v["title"],
                "pub_date": content_data["pub_date"] or v["pub_date"],
                "url": v["url"],
                "full_text": content_data["full_text"],
                "description": content_data["description"]
            }

            # 单视频生成并写入磁盘
            for retry in range(5):
                try:
                    report_text = generate_single_report(client, v_info, ch_name)
                    clean_title = sanitize_filename(v_info["title"])[:45]
                    filename = f"{v_info['pub_date']}_{vid}_{clean_title}.md"
                    filepath = ch_dir / filename

                    with open(filepath, "w", encoding="utf-8") as rf:
                        rf.write(report_text)

                    logger.info(f"    🎉 成功生成精准报告: {filename}")
                    existing_ids.add(vid)
                    total_done += 1
                    
                    # 平稳间隔 8 秒满足免费频控
                    time.sleep(8.0)
                    break
                except Exception as e:
                    e_str = str(e)
                    if "429" in e_str or "RESOURCE_EXHAUSTED" in e_str:
                        delay_match = re.search(r'retryDelay[\'"]\s*:\s*[\'"]?(\d+)', e_str)
                        wait_sec = int(delay_match.group(1)) + 5 if delay_match else 35
                        logger.warning(f"    ⏳ 触发短时频控，休眠 {wait_sec} 秒后自动恢复 (重试 {retry+1}/5)...")
                        time.sleep(wait_sec)
                    else:
                        logger.error(f"    ❌ 生成异常: {e}")
                        time.sleep(5.0)
                        break

            update_indexes()

        logger.info(f"✅ 频道 {ch_name} 处理完毕！")

    logger.info(f"\n🏁 全部频道扫描结束！本次任务累计生成 {total_done} 篇全新研报！")


if __name__ == "__main__":
    run_pipeline()
