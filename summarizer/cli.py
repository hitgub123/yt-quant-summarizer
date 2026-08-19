from __future__ import annotations
import sys
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn

from summarizer.config import settings
from summarizer.core import QuantSummarizer
from summarizer.models import VideoMetadata, VideoRecord, ProcessingStatus

app = typer.Typer(
    name="yt-quant",
    help="YouTube Quantitative Investment Strategy Summarizer & Knowledge Extractor",
    add_completion=False
)
console = Console()


@app.command()
def summarize(
    url: str = typer.Argument(..., help="YouTube video URL or Video ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-generate even if cached"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Gemini model name (e.g. gemini-2.5-flash)"),
    proxy: Optional[str] = typer.Option(None, "--proxy", "-p", help="HTTP/SOCKS5 Proxy (e.g. http://127.0.0.1:7890)"),
    output_dir: Optional[str] = typer.Option(None, "--output-dir", "-o", help="Output directory"),
):
    """Summarize a single YouTube quant/investment video and generate markdown report."""
    try:
        pipeline = QuantSummarizer(
            proxy=proxy,
            model=model,
            output_dir=output_dir,
        )
    except Exception as e:
        console.print(f"[bold red]初始化失败: {e}[/bold red]")
        raise typer.Exit(code=1)

    if not pipeline.analyzer:
        console.print("[bold red]错误: 未配置 GEMINI_API_KEY。请在 .env 中设置或设置环境变量。[/bold red]")
        raise typer.Exit(code=1)

    console.print(Panel.fit(f"[bold cyan]正在解析单视频:[/bold cyan] {url}", border_style="cyan"))

    try:
        with console.status("[bold green]正在抓取元数据并提取文稿...", spinner="dots"):
            metadata = pipeline.ingester.get_video_metadata(url)

        console.print(f"[green]✓[/green] 视频标题: [bold]{metadata.title}[/bold]")
        console.print(f"[green]✓[/green] 频道: {metadata.channel} | 时长: {metadata.duration_formatted} | 发布: {metadata.upload_date or '未知'}")

        if not force and pipeline.storage.is_processed(metadata.video_id):
            record = pipeline.storage.get_record(metadata.video_id)
            console.print(f"[yellow]⚡ 视频已存在于缓存中，跳过生成。[/yellow] (使用 --force 重新生成)")
            if record and record.report_path:
                console.print(f"📄 研报路径: [bold underline]{record.report_path}[/bold underline]")
            return

        with console.status(f"[bold green]Gemini [{pipeline.model}] 正在深度提炼 7 维度量化研报...", spinner="dots"):
            record, report_file = pipeline.summarize_video(url, force=force)

        console.print(f"[bold green]🎉 研报生成成功！[/bold green]")
        console.print(f"📄 研报路径: [bold underline cyan]{report_file}[/bold underline cyan]")
        console.print(f"📚 全局索引已更新: [dim]{pipeline.output_dir / 'INDEX.md'}[/dim]")

    except Exception as e:
        console.print(f"[bold red]❌ 处理失败: {e}[/bold red]")
        raise typer.Exit(code=1)


@app.command()
def channel(
    channel_url: str = typer.Argument(..., help="YouTube channel homepage URL (e.g. https://www.youtube.com/@AlgorithmTradingIn)"),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Number of latest videos to process (default: all videos in channel)"),
    all_videos: bool = typer.Option(False, "--all-videos", "-a", help="Process all videos without filtering for investment relevance"),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-generate even if cached"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Gemini model name"),
    proxy: Optional[str] = typer.Option(None, "--proxy", "-p", help="Proxy URL"),
    output_dir: Optional[str] = typer.Option(None, "--output-dir", "-o", help="Output directory"),
):
    """Batch analyze all investment-related videos from a creator's homepage."""
    try:
        pipeline = QuantSummarizer(
            proxy=proxy,
            model=model,
            output_dir=output_dir,
        )
    except Exception as e:
        console.print(f"[bold red]初始化失败: {e}[/bold red]")
        raise typer.Exit(code=1)

    if not pipeline.analyzer:
        console.print("[bold red]错误: 未配置 GEMINI_API_KEY。请在 .env 中设置或设置环境变量。[/bold red]")
        raise typer.Exit(code=1)

    limit_desc = f"前 {limit} 个" if (limit and limit > 0) else "频道全部视频"
    filter_desc = "智能筛选投资相关" if not all_videos else "全部视频 (不过滤)"
    console.print(Panel.fit(
        f"[bold cyan]正在扫描 UP 主首页:[/bold cyan] {channel_url}\n"
        f"[dim]范围: {limit_desc} | 策略: {filter_desc}[/dim]",
        border_style="cyan"
    ))

    try:
        with console.status("[bold green]正在解析频道视频列表并进行投资相关性判定...", spinner="dots"):
            raw_videos = pipeline.ingester.get_channel_videos(channel_url, limit=limit)

        if not raw_videos:
            console.print("[bold yellow]未在该频道找到任何视频。[/bold yellow]")
            return

        # Filtering
        from summarizer.classifier import is_investment_related

        to_analyze: list[VideoMetadata] = []
        filtered_out: list[tuple[VideoMetadata, str]] = []

        for v in raw_videos:
            if not all_videos:
                is_rel, reason = is_investment_related(v.title, v.description, v.tags)
                if is_rel:
                    to_analyze.append(v)
                else:
                    filtered_out.append((v, reason))
            else:
                to_analyze.append(v)

        console.print(f"\n📊 频道扫描完成: 共发现 [bold]{len(raw_videos)}[/bold] 个视频")
        console.print(f"🎯 投资相关视频: [bold green]{len(to_analyze)}[/bold green] 个")
        if filtered_out:
            console.print(f"⏭️ 自动过滤非投资/闲聊视频: [dim yellow]{len(filtered_out)}[/dim yellow] 个")

        if not to_analyze:
            console.print("[bold yellow]未找到与量化/投资相关的视频。若需强制分析全部视频，请加上 `--all-videos` 参数。[/bold yellow]")
            return

        # Prepare table
        table = Table(title="待处理量化投资视频清单", show_header=True, header_style="bold magenta")
        table.add_column("No.", style="dim", width=4)
        table.add_column("视频标题", style="cyan")
        table.add_column("时长", justify="center", width=10)
        table.add_column("状态", justify="center", width=16)

        need_process = []
        for idx, vid in enumerate(to_analyze, 1):
            is_cached = pipeline.storage.is_processed(vid.video_id)
            if is_cached and not force:
                status_str = "[yellow]已生成 (跳过)[/yellow]"
            else:
                status_str = "[green]待生成研报[/green]"
                need_process.append(vid)
            table.add_row(str(idx), vid.title, vid.duration_formatted, status_str)

        console.print(table)
        console.print(f"\n本次需生成: [bold green]{len(need_process)}[/bold green] 篇, 本地已存在跳过: [yellow]{len(to_analyze) - len(need_process)}[/yellow] 篇\n")

        if not need_process:
            console.print("[bold green]✨ 所有投资视频研报均已在本地生成完毕！[/bold green]")
            console.print(f"📚 全局索引目录: [bold underline cyan]{pipeline.output_dir / 'INDEX.md'}[/bold underline cyan]")
            return

        success_count = 0
        failed_count = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]批量提炼投资研报...", total=len(need_process))

            for vid in need_process:
                progress.update(task, description=f"[cyan]处理中: {vid.title[:28]}...")
                try:
                    # Single metadata refresh
                    try:
                        full_meta = pipeline.ingester.get_video_metadata(vid.video_id)
                        vid = full_meta
                    except Exception:
                        pass

                    transcript = pipeline.transcriber.get_transcript(vid)
                    report_md = pipeline.analyzer.analyze(vid, transcript)
                    report_file = pipeline.indexer.save_report(vid, report_md, model_name=pipeline.model)

                    record = VideoRecord(
                        video_id=vid.video_id,
                        channel=vid.channel,
                        title=vid.title,
                        upload_date=vid.upload_date,
                        duration=vid.duration_formatted,
                        status=ProcessingStatus.COMPLETED,
                        transcript_source=transcript.source,
                        report_path=str(report_file)
                    )
                    pipeline.storage.save_record(record)
                    success_count += 1
                except Exception as e:
                    failed_count += 1
                    err_str = str(e)
                    record = VideoRecord(
                        video_id=vid.video_id,
                        channel=vid.channel,
                        title=vid.title,
                        upload_date=vid.upload_date,
                        duration=vid.duration_formatted,
                        status=ProcessingStatus.FAILED,
                        error_message=err_str
                    )
                    pipeline.storage.save_record(record)
                    console.print(f"\n[red]❌ 跳过异常视频 [{vid.title}]: {err_str}[/red]")

                progress.advance(task)

        # Update all indices
        with console.status("[bold green]正在更新频道与全局索引...", spinner="dots"):
            if to_analyze:
                pipeline.indexer.update_channel_index(to_analyze[0].channel)
            pipeline.indexer.update_global_index()

        console.print(f"\n[bold green]🎉 UP 主频道投资研报批量处理完成！[/bold green]")
        console.print(f"✅ 成功生成: [bold green]{success_count}[/bold green] 篇 | ❌ 失败/跳过: [bold red]{failed_count}[/bold red] 篇")
        console.print(f"📚 全局索引目录: [bold underline cyan]{pipeline.output_dir / 'INDEX.md'}[/bold underline cyan]")

    except Exception as e:
        console.print(f"[bold red]❌ 频道抓取失败: {e}[/bold red]")
        raise typer.Exit(code=1)


@app.command()
def index(
    output_dir: Optional[str] = typer.Option(None, "--output-dir", "-o", help="Output directory")
):
    """Rebuild global and channel INDEX.md documents from local database."""
    pipeline = QuantSummarizer(output_dir=output_dir)
    console.print("[bold cyan]正在重新构建索引目录...[/bold cyan]")
    records = pipeline.storage.get_all_records()
    channels = set(r.channel for r in records if r.status == ProcessingStatus.COMPLETED)

    for ch in channels:
        ch_idx = pipeline.indexer.update_channel_index(ch)
        console.print(f"[green]✓[/green] 已刷新频道索引: {ch_idx}")

    g_idx = pipeline.indexer.update_global_index()
    console.print(f"[bold green]✓ 全局索引已生成: {g_idx}[/bold green]")


@app.command()
def status(
    output_dir: Optional[str] = typer.Option(None, "--output-dir", "-o", help="Output directory")
):
    """View processing statistics and cached reports status."""
    pipeline = QuantSummarizer(output_dir=output_dir)
    records = pipeline.storage.get_all_records()

    if not records:
        console.print("[yellow]当前数据库为空，暂无处理记录。[/yellow]")
        return

    table = Table(title="量化研报知识库状态", show_header=True, header_style="bold cyan")
    table.add_column("视频ID", style="dim", width=12)
    table.add_column("频道", style="blue")
    table.add_column("标题", style="white")
    table.add_column("时长", justify="center")
    table.add_column("状态", justify="center")
    table.add_column("更新时间", justify="center")

    for r in records[:30]:
        status_color = "green" if r.status == ProcessingStatus.COMPLETED else "red"
        table.add_row(
            r.video_id,
            r.channel,
            r.title[:35],
            r.duration,
            f"[{status_color}]{r.status.value}[/{status_color}]",
            r.updated_at or ""
        )

    console.print(table)
    total = len(records)
    completed = sum(1 for r in records if r.status == ProcessingStatus.COMPLETED)
    failed = sum(1 for r in records if r.status == ProcessingStatus.FAILED)
    console.print(f"\n统计: 总计 [bold]{total}[/bold] 条记录 | 成功 [bold green]{completed}[/bold green] | 失败 [bold red]{failed}[/bold red]")