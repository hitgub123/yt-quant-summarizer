from __future__ import annotations
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import yaml

from summarizer.models import VideoMetadata, VideoRecord, ProcessingStatus
from summarizer.utils import escape_markdown_cell, sanitize_filename
from summarizer.storage import StorageManager


class IndexBuilder:
    def __init__(self, output_dir: Path, storage: StorageManager):
        self.output_dir = output_dir
        self.storage = storage

    def save_report(
        self,
        metadata: VideoMetadata,
        report_markdown: str,
        model_name: str,
        tags: Optional[List[str]] = None
    ) -> Path:
        """Save report with Obsidian/Notion compatible YAML Frontmatter."""
        channel_dir_name = sanitize_filename(metadata.channel)
        channel_dir = self.output_dir / channel_dir_name
        channel_dir.mkdir(parents=True, exist_ok=True)

        date_prefix = metadata.upload_date or datetime.now().strftime("%Y-%m-%d")
        safe_title = sanitize_filename(metadata.title, max_length=60)
        # The video id prevents two videos with the same title/date from
        # overwriting each other's reports.
        file_name = f"{date_prefix}_{safe_title}_{metadata.video_id}.md"
        report_path = channel_dir / file_name

        all_tags = ["quant", "trading", "strategy", sanitize_filename(metadata.channel).lower()]
        if tags:
            all_tags.extend(tags)
        all_tags = list(dict.fromkeys(all_tags))

        frontmatter = {
            "title": metadata.title,
            "channel": metadata.channel,
            "date": metadata.upload_date or date_prefix,
            "duration": metadata.duration_formatted,
            "source_url": metadata.url,
            "video_id": metadata.video_id,
            "tags": all_tags,
            "status": "completed",
            "model": model_name,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        frontmatter_str = yaml.dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
        full_content = f"---\n{frontmatter_str}\n---\n\n{report_markdown.strip()}\n"

        report_path.write_text(full_content, encoding="utf-8")
        return report_path

    def update_channel_index(self, channel: str) -> Path:
        """Generate/update INDEX.md for a specific channel."""
        channel_dir_name = sanitize_filename(channel)
        channel_dir = self.output_dir / channel_dir_name
        channel_dir.mkdir(parents=True, exist_ok=True)

        records = self.storage.get_channel_records(channel)
        completed = [r for r in records if r.status == ProcessingStatus.COMPLETED]

        lines = [
            f"# {channel} - 量化策略研报索引",
            "",
            f"> 本目录汇总了 **{channel}** 频道的量化交易视频提炼研报，共收录 **{len(completed)}** 篇。",
            "",
            "## 研报列表",
            "",
            "| 发布日期 | 视频标题 | 时长 | 研报链接 | 原始视频 |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]

        for r in completed:
            date_str = r.upload_date or "未知日期"
            file_name = Path(r.report_path).name if r.report_path else ""
            report_link = f"[{r.title}]({file_name})" if file_name else r.title
            video_link = f"[观看 YouTube](https://www.youtube.com/watch?v={r.video_id})"
            lines.append(
                f"| {escape_markdown_cell(date_str)} | {escape_markdown_cell(r.title)} | "
                f"{escape_markdown_cell(r.duration)} | {report_link} | {video_link} |"
            )

        lines.append("")
        lines.append(f"---")
        lines.append(f"*最后更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        lines.append("")

        index_path = channel_dir / "INDEX.md"
        index_path.write_text("\n".join(lines), encoding="utf-8")
        return index_path

    def update_global_index(self) -> Path:
        """Generate/update global output/INDEX.md across all channels."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        records = self.storage.get_all_records()
        completed = [r for r in records if r.status == ProcessingStatus.COMPLETED]

        channels: Dict[str, List[VideoRecord]] = {}
        for r in completed:
            channels.setdefault(r.channel, []).append(r)

        lines = [
            "# YouTube 量化投资研报知识库 (Quant Knowledge Base)",
            "",
            "欢迎使用 **yt-quant-summarizer** 自动生成的量化投资策略知识库。本项目自动化解析优质量化频道的视频，运用 Google Gemini 进行 7 大维度深度提炼与代码复现。",
            "",
            "## 知识库概览",
            "",
            f"- **收录频道总数**: {len(channels)} 个",
            f"- **已生成研报总数**: {len(completed)} 篇",
            f"- **最后同步时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 频道目录导航",
            "",
            "| 频道名称 | 已收录研报数 | 频道索引 |",
            "| :--- | :--- | :--- |",
        ]

        for ch_name, ch_records in sorted(channels.items(), key=lambda x: len(x[1]), reverse=True):
            ch_dir = sanitize_filename(ch_name)
            ch_index_link = f"[{ch_name} 研报列表]({ch_dir}/INDEX.md)"
            lines.append(f"| **{ch_name}** | {len(ch_records)} 篇 | {ch_index_link} |")

        lines.append("")
        lines.append("## 最新生成的 15 篇量化研报")
        lines.append("")
        lines.append("| 频道 | 发布日期 | 研报标题 | 耗时/时长 | 研报直链 |")
        lines.append("| :--- | :--- | :--- | :--- | :--- |")

        recent_15 = sorted(completed, key=lambda r: r.created_at or "", reverse=True)[:15]
        for r in recent_15:
            ch_dir = sanitize_filename(r.channel)
            file_name = Path(r.report_path).name if r.report_path else ""
            rel_link = f"[{r.title}]({ch_dir}/{file_name})" if file_name else r.title
            lines.append(
                f"| {escape_markdown_cell(r.channel)} | {escape_markdown_cell(r.upload_date or '未知')} | "
                f"{escape_markdown_cell(r.title)} | {escape_markdown_cell(r.duration)} | {rel_link} |"
            )

        lines.append("")
        lines.append("---")
        lines.append(f"*由 [yt-quant-summarizer](https://github.com/) 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        lines.append("")

        global_index_path = self.output_dir / "INDEX.md"
        global_index_path.write_text("\n".join(lines), encoding="utf-8")
        return global_index_path
