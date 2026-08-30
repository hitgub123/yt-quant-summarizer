"""
Batch Pipeline: Fetch and summarize 10 investment videos for 14 YouTube Creators.
Zero external API key required when run in Antigravity mode.
"""
from __future__ import annotations
import os
import sys
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from summarizer.core import QuantSummarizer
from summarizer.models import VideoMetadata, TranscriptResult, ProcessingStatus, VideoRecord
from summarizer.classifier import is_investment_related
from summarizer.utils import sanitize_filename

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("batch_pipeline")

CHANNELS = [
    {"name": "AlgorithmTradingIn", "url": "https://www.youtube.com/@AlgorithmTradingIn"},
    {"name": "AndreiJikh", "url": "https://www.youtube.com/@AndreiJikh"},
    {"name": "ARKInvest2015", "url": "https://www.youtube.com/@ARKInvest2015"},
    {"name": "MrBoKong", "url": "https://www.youtube.com/@MrBoKong"},
    {"name": "DataTraders", "url": "https://www.youtube.com/@DataTraders"},
    {"name": "EverythingMoney", "url": "https://www.youtube.com/@EverythingMoney"},
    {"name": "ramitsethi", "url": "https://www.youtube.com/@ramitsethi"},
    {"name": "JosephCarlsonShow", "url": "https://www.youtube.com/@JosephCarlsonShow"},
    {"name": "Live.Traders", "url": "https://www.youtube.com/@Live.Traders"},
    {"name": "tradingwithrayner", "url": "https://www.youtube.com/@tradingwithrayner"},
    {"name": "TheStockMarket", "url": "https://www.youtube.com/@TheStockMarket"},
    {"name": "TraderTVLive", "url": "https://www.youtube.com/@TraderTVLive"},
    {"name": "YueChen-x8n9s", "url": "https://www.youtube.com/@YueChen-x8n9s"},
    {"name": "MeiTouJun", "url": "https://www.youtube.com/@MeiTouJun"},
]

TARGET_VIDEOS_PER_CHANNEL = 10


def run_batch_fetch(pipeline: QuantSummarizer):
    """Fetch transcripts for all 14 channels until each has 10 ready tasks."""
    print("=" * 70)
    print("🚀 启动 14 个频道的批量视频元数据与文稿抓取流水线")
    print("=" * 70)

    summary_stats = {}

    for idx, ch_info in enumerate(CHANNELS, 1):
        ch_name = ch_info["name"]
        ch_url = ch_info["url"]
        print(f"\n[{idx}/{len(CHANNELS)}] 正在处理频道: {ch_name} ({ch_url})")

        try:
            # Check existing completed reports in DB
            completed_in_db = [
                r for r in pipeline.storage.get_channel_records(ch_name)
                if r.status == ProcessingStatus.COMPLETED
            ]
            
            # Check pre-fetched task files
            task_dir = pipeline.output_dir / ".transcripts" / sanitize_filename(ch_name)
            existing_task_files = list(task_dir.glob("*.json")) if task_dir.exists() else []

            print(f"  📊 本地已有已完成研报: {len(completed_in_db)} 篇 | 待提炼任务: {len(existing_task_files)} 篇")

            needed = TARGET_VIDEOS_PER_CHANNEL - (len(completed_in_db) + len(existing_task_files))
            if needed <= 0:
                print(f"  ✨ 该频道已有足额任务或研报（目标: {TARGET_VIDEOS_PER_CHANNEL}），跳过扫描。")
                summary_stats[ch_name] = len(completed_in_db) + len(existing_task_files)
                continue

            # Scan raw candidate videos (up to 30 candidates to filter members-only and non-quant)
            raw_videos = pipeline.ingester.get_channel_videos(ch_url, limit=35)
            print(f"  🔍 扫描到候选视频: {len(raw_videos)} 个")

            valid_count = len(completed_in_db) + len(existing_task_files)
            
            for v in raw_videos:
                if valid_count >= TARGET_VIDEOS_PER_CHANNEL:
                    break

                if pipeline.storage.is_processed(v.video_id):
                    continue

                task_file = task_dir / f"{v.video_id}.json"
                if task_file.exists():
                    continue

                # Filter investment relevance
                is_rel, reason = is_investment_related(v.title, v.description, v.tags)
                if not is_rel:
                    logger.debug(f"跳过非投资视频: {v.title}")
                    continue

                # Attempt transcript extraction
                try:
                    meta, transcript, t_file = pipeline.fetch_video(v.video_id)
                    if transcript and transcript.full_text.strip():
                        valid_count += 1
                        print(f"  ✓ [{valid_count}/{TARGET_VIDEOS_PER_CHANNEL}] 成功抓取: {v.title[:32]}... ({v.duration_formatted})")
                except Exception as e:
                    logger.warning(f"  ⚠️ 无法抓取视频 [{v.video_id}] {v.title[:20]}: {e}")

            summary_stats[ch_name] = valid_count
            print(f"  ✅ 频道 {ch_name} 抓取完成，当前可用任务数: {valid_count}")

        except Exception as e:
            logger.error(f"  ❌ 抓取频道 {ch_name} 时发生异常: {e}")
            summary_stats[ch_name] = 0

    print("\n" + "=" * 70)
    print("📊 14 个频道文稿预抓取统计结果:")
    for ch, count in summary_stats.items():
        print(f"  - {ch:<22}: {count}/{TARGET_VIDEOS_PER_CHANNEL} 篇可用")
    print("=" * 70)


if __name__ == "__main__":
    pipeline = QuantSummarizer()
    run_batch_fetch(pipeline)
