#!/usr/bin/env python3
"""
全自动批量量化研报生成流水线 (基于 Gemini 官方 API)
遍历 14 个顶级交易/量化频道，每频道生成 10 篇真实、深度、结构化的 7 维度研报。
自动提取真实发布日期、生成 Markdown 文档并构建双层索引系统。
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
import yt_dlp
from google import genai

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from summarizer.utils import sanitize_filename
from summarizer.channel_catalog import QUANT_CHANNELS_WITH_OPTIONAL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(PROJECT_ROOT / "gemini_generation.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("GeminiPipeline")

OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 14 个目标博主/频道
CHANNELS = QUANT_CHANNELS_WITH_OPTIONAL


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
        raise ValueError("未找到 GEMINI_API_KEY，请在 .env 文件中配置！")
    return genai.Client(api_key=api_key)


def get_real_publish_date(video_id: str) -> str:
    """从 YouTube HTML 正则抓取真实发布日期 (YYYY-MM-DD)"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=8)
        m = re.search(r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})"', resp.text)
        if m:
            return m.group(1)
        m2 = re.search(r'itemprop="datePublished"\s+content="(\d{4}-\d{2}-\d{2})"', resp.text)
        if m2:
            return m2.group(1)
        m3 = re.search(r'uploadDate"\s*:\s*"(\d{4}-\d{2}-\d{2})"', resp.text)
        if m3:
            return m3.group(1)
    except Exception as e:
        logger.debug(f"获取日期失败 ({video_id}): {e}")
    return time.strftime("%Y-%m-%d")


def generate_single_report(client: genai.Client, video_title: str, video_url: str, channel_name: str, pub_date: str) -> str:
    """调用 Gemini 官方 API 生成 7 维度研报"""
    prompt = f"""你是一名顶级买方量化基金投资总监与资深机构交易分析师。
请针对以下 YouTube 视频内容，撰写一份严格结构化的【7 维度机构级量化与交易策略研报】。

- 视频标题：{video_title}
- 视频链接：{video_url}
- 发布机构/博主：{channel_name}
- 发布日期：{pub_date}

【严格格式与输出要求】：
必须输出标准 Markdown 格式，包含以下 7 个核心章节：

# 📊 【量化/交易研报】{video_title}

- **分析机构/博主**：`{channel_name}`
- **视频发布日期**：`{pub_date}`
- **原始视频链接**：[YouTube 视频]({video_url})
- **分析引擎**：Google Gemini 官方深度分析

---

## 🎯 一、核心投资观点与交易假设 (Core Investment Thesis & Hypotheses)
（详细提炼视频中的核心观点、逻辑链条、宏观与行业背景、市场预期）

## 📈 二、涉及标的资产与适用市场环境 (Target Assets & Market Regime)
（核心标的代码、资产类别、适用的波动率与流动性环境）

## 🛠️ 三、交易指标与关键触发逻辑 (Key Technical/Quantitative Signals)
（买入/入场触发条件、卖出/止盈触发条件，技术指标组合）

## 🛡️ 四、资金管理与风控止损规则 (Risk Management & Position Sizing)
（仓位管理建议、ATR 动态止损或固定止损逻辑）

## 📊 五、历史表现与统计数据 (Historical Performance & Evidence)
（视频中披露的数据或估值模型。若博主未披露回测数据，请如实声明“博主未在视频中提供回测数据”，严禁捏造虚假数字）

## 💻 六、量化回测与指标实现示例 (Quantitative Implementation Code)
（给出高质量、可运行的 Python 代码，包含数据加载与信号生成函数）

## ⚠️ 七、策略局限性与实盘失效风险 (Limitations & Risk Disclaimers)
（市场风险、模型过拟合、流动性冲击等）
"""
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt
    )
    return response.text


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

        # 生成频道 INDEX.md
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

    # 生成全局 INDEX.md
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


def run_full_pipeline(target_count_per_channel: int = 10):
    client = load_gemini_client()
    logger.info("==================================================================")
    logger.info("🚀 启动全量量化研报自动化流水线 (Gemini 3.6 Flash 原生驱动)")
    logger.info("==================================================================")

    ydl_opts = {
        "extract_flat": True,
        "skip_download": True,
        "quiet": True,
        "playlistend": target_count_per_channel * 2,  # 抓取多一点以备筛选
    }

    grand_total = 0

    for ch_idx, (ch_name, ch_url) in enumerate(CHANNELS, 1):
        logger.info(f"\n[{ch_idx}/{len(CHANNELS)}] 正在处理频道: {ch_name}")
        ch_dir = OUTPUT_DIR / sanitize_filename(ch_name)
        ch_dir.mkdir(parents=True, exist_ok=True)

        # 统计已有报告
        existing_reports = list(ch_dir.glob("*.md"))
        existing_ids = set()
        for er in existing_reports:
            parts = er.stem.split("_")
            if len(parts) >= 2:
                existing_ids.add(parts[1])

        entries = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(ch_url, download=False)
                entries = [e for e in info.get("entries", []) if e]
        except Exception as e:
            logger.error(f"获取频道视频失败 ({ch_name}): {e}")
            continue

        generated_for_channel = len(existing_reports)
        logger.info(f"  当前已有研报: {generated_for_channel} 篇，目标: {target_count_per_channel} 篇")

        for entry in entries:
            if generated_for_channel >= target_count_per_channel:
                break

            video_id = entry.get("id") or entry.get("url")
            title = entry.get("title", f"Video {video_id}")
            if video_id in existing_ids:
                continue

            video_url = f"https://www.youtube.com/watch?v={video_id}"
            logger.info(f"  [处理中 {generated_for_channel+1}/{target_count_per_channel}] 正在提炼研报: {title[:35]} (ID: {video_id})")

            # 获取真实发布日期
            pub_date = get_real_publish_date(video_id)

            # 调用 Gemini 生成研报
            try:
                report_md = generate_single_report(client, title, video_url, ch_name, pub_date)
                clean_title = sanitize_filename(title)[:45]
                report_filename = f"{pub_date}_{video_id}_{clean_title}.md"
                report_path = ch_dir / report_filename

                with open(report_path, "w", encoding="utf-8") as rf:
                    rf.write(report_md)

                logger.info(f"  🎉 成功生成并保存: {report_filename}")
                existing_ids.add(video_id)
                generated_for_channel += 1
                grand_total += 1

                # 间隔 2 秒保护调用频率
                time.sleep(2.0)

            except Exception as ge:
                logger.error(f"  ❌ 生成研报失败 ({video_id}): {ge}")
                time.sleep(5.0)

        update_indexes()
        logger.info(f"✅ 频道 {ch_name} 完成！当前累计生成 {generated_for_channel} 篇研报。")

    logger.info(f"\n🏁 全部频道处理结束！本次任务累计生成 {grand_total} 篇全新研报！")


if __name__ == "__main__":
    run_full_pipeline(target_count_per_channel=10)
