#!/usr/bin/env python3
"""
高性能批量量化研报流水线 (Batch Multi-Video Quant Pipeline)
- 抓取各 UP 主全量视频，智能筛选投资/交易/宏观相关视频。
- 单次 Gemini API 请求批量处理 3~4 个视频，提速 3~4 倍并大幅节省请求配额。
- 自动提取真实发布日期、拆分落盘为标准 7 维度独立研报并维护双层索引。
"""

from __future__ import annotations
import os
import sys
import re
import json
import time
import random
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import requests
import subprocess
import yt_dlp
from google import genai

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from summarizer.utils import sanitize_filename
from summarizer.channel_catalog import QUANT_CHANNELS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(PROJECT_ROOT / "batch_generation.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("BatchPipeline")

OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CHANNELS = QUANT_CHANNELS

BATCH_SIZE = 3  # 单次请求合并处理 3 个视频


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


def get_real_publish_date(entry: Dict[str, Any], video_id: str) -> str:
    """优先从 entry 元数据快速提取发布日期，避免额外的网络请求"""
    up_date = entry.get("upload_date")
    if up_date and len(str(up_date)) == 8:
        s = str(up_date)
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    
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


def is_investment_related(title: str) -> bool:
    """智能过滤投资/量化/交易相关视频，排除无关生活琐事"""
    title_lower = title.lower()
    # 关键词过滤
    non_invest_keywords = ["vlog", "q&a", "unboxing", "daily routine", "house tour", "wedding", "podcast clips #"]
    if any(k in title_lower for k in non_invest_keywords):
        return False
    return True


def generate_batch_reports(client: genai.Client, video_batch: List[Dict[str, Any]], channel_name: str) -> Dict[str, str]:
    """单次调用 Gemini API 批量生成多个视频的研报"""
    prompt_items = []
    for idx, v in enumerate(video_batch, 1):
        prompt_items.append(f"""### 视频 #{idx}
- 视频唯一ID：{v['video_id']}
- 视频标题：{v['title']}
- 视频链接：{v['url']}
- 发布日期：{v['pub_date']}
- 发布机构：{channel_name}
""")

    prompt = f"""你是一名顶级买方投研专家与资深交易策略分析师。
请针对以下 {len(video_batch)} 个 YouTube 投资/量化/交易视频，分别撰写一份【专业、真实、因片制宜的投资与策略分析研报】。

{"".join(prompt_items)}

【严格输出规范与准则】：
1. **绝对忠实于视频真实内容**：严禁无中生有！
2. **严禁强行编造代码或虚假回测**：仅当视频中真正涉及量化策略编程或代码编写时，才提取相关代码实现；若视频侧重于宏观经济解读、个股基本面研究、技术形态分析、交易心理或仓位风控，坚决不要编造任何无关代码，应重点梳理博主的真实逻辑推导、核心论据与决策规则！
3. **结构严谨、干货密集**：每篇报告必须逻辑清晰、论点明确。

请按顺序输出这 {len(video_batch)} 份研报。每份研报之间必须使用固定的分割线 `===REPORT_SPLIT:{video_batch[0]['video_id']}===` 进行区分。

标准结构参考：
===REPORT_SPLIT:VIDEO_ID_HERE===
# 📊 视频真实标题

- **分析机构/博主**：`{channel_name}`
- **视频发布日期**：`YYYY-MM-DD`
- **原始视频链接**：[YouTube 视频](URL)

---

## 🎯 一、核心投资主旨与背景 (Core Thesis & Market Context)
（提炼博主的核心投资观点、市场大背景、解决的核心痛点或核心假设）

## 🔍 二、逻辑推导与关键论据拆解 (In-Depth Analysis & Key Evidence)
（分模块梳理博主的分析逻辑链条、宏观数据、公司财务指标、估值模型或技术面信号）

## 🛠️ 三、交易/投资实战规则与操作建议 (Actionable Strategy & Rules)
（根据视频实际内容总结：
- 若为量化实盘视频：梳理真实的算法逻辑与核心代码片段；
- 若为主观交易视频：梳理买入/卖出触发信号、ATR 止损与仓位管理规则；
- 若为价值/宏观投资视频：梳理核心资产配置方案与标的筛选标准）

## 💡 四、核心观点提炼与关键启示 (Key Takeaways)
（提炼 3~5 条最具参考价值的投资启示或决策要点）

## ⚠️ 五、策略局限性与实盘风险提示 (Risks & Limitations)
（博主强调的市场风险、流动性陷阱、黑天鹅冲击或分析局限性）
"""

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt
    )
    raw_text = response.text

    # 按照分割线拆分研报
    results = {}
    parts = re.split(r'===REPORT_SPLIT:([a-zA-Z0-9_-]+)===', raw_text)
    if len(parts) >= 3:
        for i in range(1, len(parts), 2):
            vid = parts[i].strip()
            content = parts[i+1].strip()
            results[vid] = content
    else:
        # 兜底按主标题或顺序拆分
        for v in video_batch:
            vid = v["video_id"]
            results[vid] = raw_text

    return results


def update_indexes():
    """更新所有频道的 INDEX.md 与根目录 INDEX.md"""
    global_index_path = OUTPUT_DIR / "INDEX.md"
    channels_summary = []
    total_reports = 0

    for ch_name, _ in CHANNELS:
        ch_dir = OUTPUT_DIR / sanitize_filename(ch_name)
        if not ch_dir.exists():
            continue
        reports = sorted(list(ch_dir.glob("*.md")), reverse=True)
        reports = [r for r in reports if r.name != "INDEX.md"]
        if not reports:
            continue

        ch_index_path = ch_dir / "INDEX.md"
        ch_lines = [
            f"# 📚 {ch_name} - 研报索引列表",
            f"\n> 累计提炼真实量化研报：`{len(reports)}` 篇\n",
            "| 发布日期 | 视频标题 | 研报文档 |",
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
        "# 📈 YouTube 顶级交易/量化策略研报知识库 (Gemini 官方深度分析)",
        f"\n> 收录频道总数：`{len(channels_summary)}` 个 | 累计研报总数：`{total_reports}` 篇\n",
        "## 📁 各博主研报导航",
        "| 频道/博主 | 研报数量 | 研报目录 |",
        "| :--- | :---: | :--- |",
    ]
    for c_name, c_cnt, c_dir in channels_summary:
        g_lines.append(f"| **{c_name}** | `{c_cnt}` 篇 | [查看研报列表](./{c_dir}/INDEX.md) |")

    with open(global_index_path, "w", encoding="utf-8") as gif:
        gif.write("\n".join(g_lines) + "\n")
    logger.info("📑 全局与频道索引 INDEX.md 更新完成！")


def extract_channel_videos(channel_url: str, limit: int = 50) -> List[Dict[str, Any]]:
    """使用 CLI 高速提取频道前 N 个视频元数据"""
    cmd = [
        str(PROJECT_ROOT / ".venv" / "bin" / "yt-dlp"),
        "--flat-playlist",
        "-j",
        channel_url,
        "--playlist-end",
        str(limit)
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        entries = []
        for line in res.stdout.strip().split("\n"):
            if line.strip():
                try:
                    entries.append(json.loads(line.strip()))
                except Exception:
                    pass
        return entries
    except Exception as e:
        logger.error(f"提取频道视频失败 ({channel_url}): {e}")
        return []


def run_batch_pipeline(max_videos_per_channel: int = 50):
    client = load_gemini_client()
    logger.info("==================================================================")
    logger.info(f"🚀 启动多视频批量研报流水线 (单次请求处理 {BATCH_SIZE} 个视频)")
    logger.info("==================================================================")

    grand_total = 0

    for ch_idx, (ch_name, ch_url) in enumerate(CHANNELS, 1):
        logger.info(f"\n[{ch_idx}/{len(CHANNELS)}] 正在全量扫描频道: {ch_name}")
        ch_dir = OUTPUT_DIR / sanitize_filename(ch_name)
        ch_dir.mkdir(parents=True, exist_ok=True)

        existing_reports = list(ch_dir.glob("*.md"))
        existing_ids = set()
        for er in existing_reports:
            parts = er.stem.split("_")
            if len(parts) >= 2:
                existing_ids.add(parts[1])

        entries = extract_channel_videos(ch_url, max_videos_per_channel)

        # 筛选投资相关且未处理的视频
        pending_videos = []
        for entry in entries:
            vid = entry.get("id") or entry.get("url")
            title = entry.get("title", f"Video {vid}")
            if vid in existing_ids:
                continue
            if not is_investment_related(title):
                continue
            
            pub_date = get_real_publish_date(entry, vid)
            pending_videos.append({
                "video_id": vid,
                "title": title,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "pub_date": pub_date
            })

        logger.info(f"  🔍 频道已有: {len(existing_reports)} 篇，待处理投资相关视频: {len(pending_videos)} 个")

        # 分批并发处理
        for b_start in range(0, len(pending_videos), BATCH_SIZE):
            batch = pending_videos[b_start : b_start + BATCH_SIZE]
            batch_titles = " | ".join([f"[{v['video_id']}] {v['title'][:20]}" for v in batch])
            logger.info(f"  📦 正在合并请求处理批次 ({b_start+1}-{b_start+len(batch)}/{len(pending_videos)}): {batch_titles}")

            # 带自适应退避的重试机制
            success_batch = False
            for retry in range(3):
                try:
                    reports_map = generate_batch_reports(client, batch, ch_name)
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
                        
                        logger.info(f"    🎉 成功生成研报: {report_filename}")
                        existing_ids.add(vid)
                        grand_total += 1
                    
                    success_batch = True
                    # 批次间正常间隔 8 秒 (满足 15 RPM 限制)
                    time.sleep(8.0)
                    break
                except Exception as be:
                    be_str = str(be)
                    if "RESOURCE_EXHAUSTED" in be_str or "429" in be_str:
                        # 检查是否为每分钟频控 (RPM) 还是每日额度 (RPD)
                        if "GenerateRequestsPerDay" in be_str or "daily" in be_str.lower() or "per day" in be_str.lower():
                            logger.error("🛑 【今日免费调用上限已达】检测到 Gemini 每日请求配额 (1,500次/天) 已用尽！")
                            logger.info("💾 正在更新并保存当前所有研报索引，程序安全停机。次日额度刷新后可直接断点续传！")
                            update_indexes()
                            sys.exit(0)
                        else:
                            logger.warning(f"  ⏳ 触发 Gemini 每分钟频控 (RPM)，自动休眠 45 秒等待令牌刷新 (重试 {retry+1}/3)...")
                            time.sleep(45.0)
                    else:
                        logger.error(f"  ❌ 批次生成异常: {be}")
                        time.sleep(5.0)
                        break

            update_indexes()

        logger.info(f"✅ 频道 {ch_name} 处理完毕！")

    logger.info(f"\n🏁 全部频道扫描结束！本次任务累计生成 {grand_total} 篇全新量化研报！")


if __name__ == "__main__":
    run_batch_pipeline(max_videos_per_channel=50)
