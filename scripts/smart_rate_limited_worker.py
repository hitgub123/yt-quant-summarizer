#!/usr/bin/env python3
"""
Smart Rate-Limited Quant Pipeline Worker
- 每次抓取视频字幕之间加入 3.0 ~ 5.0 秒的随机休眠。
- 一旦遇到 429 (Too Many Requests)，立即暂停任务。
- 自动进入冷却探测模式：每 10 分钟 (600秒) 测试一次 429 是否解除。
- 429 解除后，自动恢复逐个视频的真实字幕抓取。
- 严格原则：仅对 100% 成功抓取到真实字幕文本的视频进行真实提炼，绝不编造任何内容。
"""

from __future__ import annotations
import os
import sys
import json
import time
import random
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import yt_dlp

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from summarizer.core import QuantSummarizer
from summarizer.models import VideoMetadata, VideoRecord, ProcessingStatus
from summarizer.utils import sanitize_filename

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(PROJECT_ROOT / "pipeline_worker.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("SmartWorker")

CHANNELS = [
    ("Algorithm Trading", "https://www.youtube.com/@AlgorithmTradingIn/videos"),
    ("Andrei Jikh", "https://www.youtube.com/@AndreiJikh/videos"),
    ("ARK Invest", "https://www.youtube.com/@ARKInvest2015/videos"),
    ("MrBoKong", "https://www.youtube.com/@MrBoKong/videos"),
    ("DataTraders", "https://www.youtube.com/@DataTraders/videos"),
    ("EverythingMoney", "https://www.youtube.com/@EverythingMoney/videos"),
    ("Ramit Sethi", "https://www.youtube.com/@ramitsethi/videos"),
    ("Joseph Carlson", "https://www.youtube.com/@JosephCarlsonShow/videos"),
    ("Live Traders", "https://www.youtube.com/@Live.Traders/videos"),
    ("Trading with Rayner", "https://www.youtube.com/@tradingwithrayner/videos"),
    ("TraderTV Live", "https://www.youtube.com/@TraderTVLive/videos"),
    ("Yue Chen", "https://www.youtube.com/@YueChen-x8n9s/videos"),
    ("美投君", "https://www.youtube.com/@MeiTouJun/videos"),
]

PROBE_VIDEO_URL = "https://www.youtube.com/watch?v=hoi59k5zh1A"
RECHECK_INTERVAL_SECONDS = 600  # 10 分钟测试一次


def probe_is_429() -> bool:
    """轻量探测当前是否仍然处于 429 频控中"""
    logger.info("🔍 发起 429 状态探测请求...")
    ydl_opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en"],
        "quiet": True,
        "no_warnings": True,
        "outtmpl": "/tmp/probe_test.%(ext)s"
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([PROBE_VIDEO_URL])
        logger.info("🎉 探测成功！429 频控已解除，YouTube 接口恢复正常！")
        return False
    except Exception as e:
        err_msg = str(e)
        if "429" in err_msg or "Too Many Requests" in err_msg:
            logger.warning(f"❌ 探测确认：当前仍处于 429 频控限制中。({err_msg.strip()})")
            return True
        logger.info(f"ℹ️ 探测收到非 429 响应: {err_msg.strip()}")
        return False


def wait_until_unblocked():
    """当遇到 429 时进入暂停轮询模式，每 10 分钟探测一次"""
    logger.warning("🚨 触发 YouTube 429 频控，批量抓取任务已暂停！")
    attempt = 1
    while True:
        logger.info(f"⏳ 任务处于冷却休眠中... 将在 {RECHECK_INTERVAL_SECONDS // 60} 分钟后进行第 {attempt} 次探测...")
        time.sleep(RECHECK_INTERVAL_SECONDS)
        
        is_blocked = probe_is_429()
        if not is_blocked:
            logger.info("✅ 429 限制已消除，自动恢复批量抓取流水线！")
            break
        attempt += 1


def fetch_video_subtitles(video_id: str, output_dir: Path) -> Optional[Path]:
    """尝试下载指定视频的自动生成字幕或官方字幕，若遇 429 则抛出异常"""
    sub_tmpl = str(output_dir / f"{video_id}.%(ext)s")
    
    ydl_opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "zh-Hans", "zh-Hant", "zh", "hi", "ja"],
        "subtitlesformat": "vtt",
        "outtmpl": sub_tmpl,
        "quiet": True,
        "no_warnings": True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    
    # 查找下载到的字幕文件
    vtt_files = list(output_dir.glob(f"{video_id}.*.vtt"))
    if vtt_files:
        return vtt_files[0]
    return None


def parse_vtt_content(vtt_file: Path) -> str:
    """从 VTT 字幕文件中提取带时间戳的纯文本逐字稿"""
    lines = []
    with open(vtt_file, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
                continue
            if "-->" in line:
                continue
            if line not in lines:  # 简单去重
                lines.append(line)
    return " ".join(lines)


def run_pipeline():
    summarizer = QuantSummarizer()
    subs_cache_dir = summarizer.output_dir / ".raw_subtitles"
    subs_cache_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=====================================================")
    logger.info("🚀 启动智能频控量化研报流水线 (带 3~5s 随机休眠与 10min 429 探测)")
    logger.info("=====================================================")

    # 先做一次初始探测
    if probe_is_429():
        wait_until_unblocked()

    for ch_idx, (ch_name, ch_url) in enumerate(CHANNELS, 1):
        logger.info(f"\n[{ch_idx}/{len(CHANNELS)}] 正在处理频道: {ch_name} ({ch_url})")
        
        try:
            ydl_opts = {
                "extract_flat": True,
                "skip_download": True,
                "quiet": True,
                "playlistend": 10,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(ch_url, download=False)
                entries = [e for e in info.get("entries", []) if e][:10]

            for v_idx, entry in enumerate(entries, 1):
                video_id = entry.get("id") or entry.get("url")
                title = entry.get("title") or f"Video {video_id}"
                
                # 检查数据库是否已成功处理
                if summarizer.storage.is_processed(video_id):
                    rec = summarizer.storage.get_record(video_id)
                    if rec and rec.status == ProcessingStatus.COMPLETED and rec.transcript_source == "real_verified_subtitles":
                        logger.info(f"  [跳过] 已存在真实逐字稿研报: {title}")
                        continue

                logger.info(f"  [{v_idx}/10] 正在尝试抓取真实字幕: {video_id} - {title[:35]}")
                
                sub_file = None
                while True:
                    try:
                        sub_file = fetch_video_subtitles(video_id, subs_cache_dir)
                        break
                    except Exception as ex:
                        err_text = str(ex)
                        if "429" in err_text or "Too Many Requests" in err_text:
                            logger.error(f"  🚨 抓取 {video_id} 时遭遇 429 限流！立即暂停任务...")
                            wait_until_unblocked()
                            logger.info(f"  🔄 恢复重试抓取视频: {video_id}")
                        else:
                            logger.warning(f"  ⚠️ 该视频暂无可用字幕轨道: {err_text.strip()}")
                            break

                # 随机休眠 3.0 ~ 5.0 秒
                sleep_time = random.uniform(3.0, 5.0)
                logger.info(f"  ⏳ 正常间隔休眠 {sleep_time:.2f} 秒...")
                time.sleep(sleep_time)

                if not sub_file or not sub_file.exists():
                    logger.warning(f"  ⚠️ 跳过生成：未获取到真实字幕文件 ({video_id})，绝不编造虚假研报。")
                    continue

                transcript_text = parse_vtt_content(sub_file)
                if not transcript_text.strip():
                    logger.warning(f"  ⚠️ 跳过生成：字幕内容为空 ({video_id})。")
                    continue

                logger.info(f"  🎉 成功获取到真实字幕 ({len(transcript_text)} 字符)，开始提炼 100% 真实量化研报...")
                # 记录为真实逐字稿任务
                channel_task_dir = summarizer.output_dir / ".transcripts" / sanitize_filename(ch_name)
                channel_task_dir.mkdir(parents=True, exist_ok=True)
                task_file = channel_task_dir / f"{video_id}.json"
                
                task_data = {
                    "metadata": {
                        "video_id": video_id,
                        "title": title,
                        "channel": ch_name,
                        "channel_url": ch_url,
                        "url": f"https://www.youtube.com/watch?v={video_id}",
                    },
                    "transcript": {
                        "video_id": video_id,
                        "source": "youtube_verified_auto_subtitles",
                        "full_text": transcript_text,
                    }
                }
                with open(task_file, "w", encoding="utf-8") as tf:
                    json.dump(task_data, tf, ensure_ascii=False, indent=2)
                
                logger.info(f"  💾 真实字幕任务已落盘: {task_file}")

            summarizer.indexer.update_channel_index(ch_name)

        except Exception as e:
            logger.error(f"处理频道 {ch_name} 异常: {e}", exc_info=True)

    summarizer.indexer.update_global_index()
    logger.info("🏁 本轮流水线扫描与抓取结束。")


if __name__ == "__main__":
    run_pipeline()
