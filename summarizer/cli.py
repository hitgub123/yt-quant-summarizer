from __future__ import annotations
import sys
from pathlib import Path
from typing import Literal, Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn

from summarizer.config import settings
from summarizer.core import QuantSummarizer
from summarizer.models import VideoMetadata, VideoRecord, ProcessingStatus
from summarizer.transcriber import SubtitleCircuitOpenError, SubtitleRateLimitError

app = typer.Typer(
    name="yt-quant",
    help="YouTube Quantitative Investment Strategy Summarizer & Knowledge Extractor",
    add_completion=False
)
console = Console()


@app.command()
def fetch(
    target: str = typer.Argument(..., help="YouTube channel homepage URL (e.g. https://www.youtube.com/@AlgorithmTradingIn) or video URL"),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Number of latest videos to process"),
    all_videos: bool = typer.Option(False, "--all-videos", "-a", help="Process all videos without filtering for investment relevance"),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-fetch even if already processed"),
    stop_on_error: bool = typer.Option(
        True, "--stop-on-error/--continue-on-error", help="遇到第一个 URL 失败就停止，下一次从检查点继续"
    ),
    proxy: Optional[str] = typer.Option(None, "--proxy", "-p", help="HTTP/SOCKS5 Proxy (e.g. http://127.0.0.1:7890)"),
    output_dir: Optional[str] = typer.Option(None, "--output-dir", "-o", help="Output directory"),
    transcript_mode: Literal["subtitles", "auto", "gemini-video"] = typer.Option(
        "subtitles", "--transcript-mode", help="字幕来源：仅字幕、自动兜底或直接使用 Gemini 视频"
    ),
):
    """
    [Antigravity 最佳模式 - 零 API Key] 预抓取频道或单视频的元数据与文稿。
    抓取后直接在 Antigravity 聊天中发送“帮我提炼研报”，即可由你的 Gemini Pro 账号生成 7 维度研报并自动入库！
    """
    try:
        pipeline = QuantSummarizer(
            proxy=proxy,
            output_dir=output_dir,
            transcript_mode=transcript_mode,
        )
    except Exception as e:
        console.print(f"[bold red]初始化失败: {e}[/bold red]")
        raise typer.Exit(code=1)

    from summarizer.utils import is_channel_url, extract_video_id

    # 1. Single video fetch
    if not is_channel_url(target) and (extract_video_id(target) or "watch" in target):
        console.print(Panel.fit(f"[bold cyan]正在提取单视频元数据与文稿 (免 Key):[/bold cyan] {target}", border_style="cyan"))
        try:
            with console.status("[bold green]正在抓取元数据并提取文稿...", spinner="dots"):
                metadata, transcript, task_file = pipeline.fetch_video(target, force=force)

            console.print(f"[green]✓[/green] 视频标题: [bold]{metadata.title}[/bold]")
            console.print(f"[green]✓[/green] 频道: {metadata.channel} | 时长: {metadata.duration_formatted} | 发布: {metadata.upload_date or '未知'}")
            console.print(f"[green]✓[/green] 文稿字数: {len(transcript.full_text)} 字 (来源: {transcript.source})")
            console.print(f"📁 预抓取任务文件: [dim]{task_file}[/dim]\n")

            console.print(Panel(
                f"✨ [bold green]单视频文稿提取完成！[/bold green]\n\n"
                f"🤖 [bold yellow]下一步操作：[/bold yellow]\n"
                f"回到 Antigravity 对话框，直接发送：\n"
                f"👉 [bold cyan]“帮我提炼刚刚抓取的研报”[/bold cyan]\n"
                f"系统将使用你的 Gemini Pro 订阅生成 7 大维度专业量化研报并保存至 [bold]{pipeline.output_dir}[/bold]！",
                title="🎯 准备就绪",
                border_style="green"
            ))
            return
        except Exception as e:
            console.print(f"[bold red]❌ 提取失败: {e}[/bold red]")
            raise typer.Exit(code=1)

    # 2. Channel batch fetch
    channel_url = target
    limit_desc = f"前 {limit} 个" if (limit and limit > 0) else "频道全部视频"
    filter_desc = "智能筛选量化投资相关" if not all_videos else "全部视频 (不过滤)"
    console.print(Panel.fit(
        f"[bold cyan]正在扫描 UP 主频道并提取文稿 (免 API Key):[/bold cyan] {channel_url}\n"
        f"[dim]范围: {limit_desc} | 策略: {filter_desc}[/dim]",
        border_style="cyan"
    ))

    try:
        with console.status("[bold green]正在扫描频道视频列表...", spinner="dots"):
            raw_videos = pipeline.ingester.get_channel_videos(channel_url, limit=limit)

        if not raw_videos:
            console.print("[bold yellow]未在该频道找到任何视频。[/bold yellow]")
            return

        from summarizer.classifier import is_investment_related

        to_fetch: list[VideoMetadata] = []
        filtered_out: list[tuple[VideoMetadata, str]] = []

        for v in raw_videos:
            if not all_videos:
                is_rel, reason = is_investment_related(v.title, v.description, v.tags)
                if is_rel:
                    to_fetch.append(v)
                else:
                    filtered_out.append((v, reason))
            else:
                to_fetch.append(v)

        console.print(f"\n📊 频道扫描完成: 共发现 [bold]{len(raw_videos)}[/bold] 个视频")
        console.print(f"🎯 量化投资相关视频: [bold green]{len(to_fetch)}[/bold green] 个")
        if filtered_out:
            console.print(f"⏭️ 自动过滤非投资/闲聊视频: [dim yellow]{len(filtered_out)}[/dim yellow] 个")

        if not to_fetch:
            console.print("[bold yellow]未找到与量化/投资相关的视频。若需抓取全部视频，请加上 `--all-videos` 参数。[/bold yellow]")
            return

        # Prepare table
        table = Table(title="待提取文稿清单", show_header=True, header_style="bold magenta")
        table.add_column("No.", style="dim", width=4)
        table.add_column("视频标题", style="cyan")
        table.add_column("时长", justify="center", width=10)
        table.add_column("状态", justify="center", width=16)

        need_fetch = []
        for idx, vid in enumerate(to_fetch, 1):
            has_report = pipeline.storage.is_report_available(vid.video_id)
            has_transcript = pipeline.is_transcript_available(vid.video_id)
            if (has_report or has_transcript) and not force:
                status_str = "[yellow]文稿已抓取 (跳过)[/yellow]" if has_transcript else "[yellow]研报已存在 (跳过)[/yellow]"
            else:
                status_str = "[green]待提取文稿[/green]"
                need_fetch.append(vid)
            table.add_row(str(idx), vid.title, vid.duration_formatted, status_str)

        console.print(table)
        console.print(f"\n本次需提取文稿: [bold green]{len(need_fetch)}[/bold green] 篇, 本地已存在跳过: [yellow]{len(to_fetch) - len(need_fetch)}[/yellow] 篇\n")

        if not need_fetch:
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
            task = progress.add_task("[cyan]批量提取字幕与文稿...", total=len(need_fetch))

            for vid in need_fetch:
                progress.update(task, description=f"[cyan]提取中: {vid.title[:28]}...")
                try:
                    metadata, transcript, task_file = pipeline.fetch_video(vid.video_id, force=force)
                    success_count += 1
                except Exception as e:
                    failed_count += 1
                    console.print(f"\n[red]❌ 提取文稿失败 [{vid.title}]: {e}[/red]")
                    if isinstance(e, (SubtitleRateLimitError, SubtitleCircuitOpenError)):
                        console.print("[yellow]检测到 YouTube 429，已立即终止批处理；24 小时内不会再次访问字幕接口。[/yellow]")
                        raise typer.Exit(code=1)
                    if stop_on_error:
                        console.print("[yellow]已停止。下次运行将跳过已有文稿，并从本次失败项继续。[/yellow]")
                        break

                progress.advance(task)

        console.print(f"\n[bold green]🎉 文稿抓取与预处理完成！[/bold green]")
        console.print(f"✅ 成功抓取: [bold green]{success_count}[/bold green] 篇 | ❌ 失败: [bold red]{failed_count}[/bold red] 篇")
        console.print(f"📁 任务文件已存放至: [dim]{pipeline.output_dir / '.transcripts'}[/dim]\n")

        console.print(Panel(
            f"🤖 [bold yellow]下一步操作指南：[/bold yellow]\n\n"
            f"回到 Antigravity 对话框，直接发送：\n"
            f"👉 [bold cyan]“帮我提炼刚刚抓取的研报”[/bold cyan] 或 [bold cyan]“帮我把这些视频生成量化研报”[/bold cyan]\n\n"
            f"系统将全自动使用你当前登录的 Gemini Pro 账号权益，深度复现 7 维度研报并自动更新全局索引！",
            title="✨ 准备就绪",
            border_style="green"
        ))

    except Exception as e:
        console.print(f"[bold red]❌ 抓取失败: {e}[/bold red]")
        raise typer.Exit(code=1)


@app.command()
def summarize(
    url: str = typer.Argument(..., help="YouTube video URL or Video ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-generate even if cached"),
    research: bool = typer.Option(False, "--research", help="Generate the full 7-section quant research report"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Gemini model name (e.g. gemini-2.5-flash)"),
    proxy: Optional[str] = typer.Option(None, "--proxy", "-p", help="HTTP/SOCKS5 Proxy (e.g. http://127.0.0.1:7890)"),
    output_dir: Optional[str] = typer.Option(None, "--output-dir", "-o", help="Output directory"),
    transcript_mode: Literal["auto", "subtitles", "gemini-video"] = typer.Option(
        "auto", "--transcript-mode", help="字幕来源：仅字幕、自动兜底或直接使用 Gemini 视频"
    ),
):
    """Summarize a single YouTube quant/investment video and generate markdown report."""
    try:
        pipeline = QuantSummarizer(
            proxy=proxy,
            model=model,
            output_dir=output_dir,
            report_mode="research" if research else "summary",
            transcript_mode=transcript_mode,
        )
    except Exception as e:
        console.print(f"[bold red]初始化失败: {e}[/bold red]")
        raise typer.Exit(code=1)

    if not pipeline.analyzer:
        console.print(Panel(
            "[bold yellow]未检测到 GEMINI_API_KEY。[/bold yellow]\n\n"
            "🌟 [bold green]推荐使用 Antigravity 免 Key 模式：[/bold green]\n"
            f"1. 运行预抓取命令（无需 API Key）：\n"
            f"   [cyan]python -m summarizer fetch \"{url}\"[/cyan]\n"
            f"2. 抓取完成后，在 Antigravity 聊天框中发送：\n"
            f"   [bold white]“帮我提炼刚抓取的研报”[/bold white]\n"
            f"   即可直接利用你当前登录的 Gemini Pro 账号权益生成 7 维度量化研报！",
            title="💡 免 API Key 提示",
            border_style="yellow"
        ))
        raise typer.Exit(code=0)

    console.print(Panel.fit(f"[bold cyan]正在解析单视频:[/bold cyan] {url}", border_style="cyan"))

    try:
        with console.status("[bold green]正在抓取元数据并提取文稿...", spinner="dots"):
            metadata = pipeline.ingester.get_video_metadata(url)

        console.print(f"[green]✓[/green] 视频标题: [bold]{metadata.title}[/bold]")
        console.print(f"[green]✓[/green] 频道: {metadata.channel} | 时长: {metadata.duration_formatted} | 发布: {metadata.upload_date or '未知'}")

        if not force and pipeline.storage.is_report_available(metadata.video_id):
            record = pipeline.storage.get_record(metadata.video_id)
            console.print(f"[yellow]⚡ 视频已存在于缓存中，跳过生成。[/yellow] (使用 --force 重新生成)")
            if record and record.report_path:
                console.print(f"📄 研报路径: [bold underline]{record.report_path}[/bold underline]")
            return

        output_type = "7 维度量化研报" if research else "视频摘要"
        with console.status(f"[bold green]Gemini [{pipeline.model}] 正在生成{output_type}...", spinner="dots"):
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
    research: bool = typer.Option(False, "--research", help="Generate full 7-section quant research reports"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Gemini model name"),
    proxy: Optional[str] = typer.Option(None, "--proxy", "-p", help="Proxy URL"),
    output_dir: Optional[str] = typer.Option(None, "--output-dir", "-o", help="Output directory"),
    transcript_mode: Literal["auto", "subtitles", "gemini-video"] = typer.Option(
        "auto", "--transcript-mode", help="字幕来源：仅字幕、自动兜底或直接使用 Gemini 视频"
    ),
):
    """Batch analyze all investment-related videos from a creator's homepage."""
    try:
        pipeline = QuantSummarizer(
            proxy=proxy,
            model=model,
            output_dir=output_dir,
            report_mode="research" if research else "summary",
            transcript_mode=transcript_mode,
        )
    except Exception as e:
        console.print(f"[bold red]初始化失败: {e}[/bold red]")
        raise typer.Exit(code=1)

    if not pipeline.analyzer:
        console.print(Panel(
            "[bold yellow]未检测到 GEMINI_API_KEY。[/bold yellow]\n\n"
            "🌟 [bold green]推荐使用 Antigravity 免 Key 模式：[/bold green]\n"
            f"1. 运行预抓取命令（无需 API Key）：\n"
            f"   [cyan]python -m summarizer fetch \"{channel_url}\"[/cyan]\n"
            f"2. 抓取完成后，在 Antigravity 聊天框中发送：\n"
            f"   [bold white]“帮我提炼刚抓取的研报”[/bold white]\n"
            f"   即可直接利用你当前登录的 Gemini Pro 账号权益生成 7 维度量化研报！",
            title="💡 免 API Key 提示",
            border_style="yellow"
        ))
        raise typer.Exit(code=0)

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
            is_cached = pipeline.storage.is_report_available(vid.video_id)
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
        channels_to_index = {video.channel for video in to_analyze}

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
                    vid = pipeline._refresh_metadata(vid)
                    channels_to_index.add(vid.channel)

                    transcript = pipeline.transcriber.get_transcript(vid)
                    report_md = pipeline.analyzer.analyze(vid, transcript)
                    report_file = pipeline.indexer.save_report(vid, report_md, model_name=pipeline.model)

                    record = pipeline._completed_record(vid, transcript, report_file)
                    pipeline.storage.save_record(record)
                    success_count += 1
                except Exception as e:
                    failed_count += 1
                    err_str = str(e)
                    if not pipeline.storage.is_report_available(vid.video_id):
                        pipeline.storage.save_record(pipeline._failed_record(vid, err_str))
                    console.print(f"\n[red]❌ 跳过异常视频 [{vid.title}]: {err_str}[/red]")

                progress.advance(task)

        # Update all indices
        with console.status("[bold green]正在更新频道与全局索引...", spinner="dots"):
            for channel_name in channels_to_index:
                pipeline.indexer.update_channel_index(channel_name)
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


@app.command()
def record(
    video_id: str = typer.Argument(..., help="Video ID of the pre-fetched task"),
    report_file: str = typer.Argument(..., help="Path to markdown file containing the generated report content"),
    model_name: str = typer.Option("antigravity-gemini-pro", "--model", "-m", help="Model name used for generation"),
    output_dir: Optional[str] = typer.Option(None, "--output-dir", "-o", help="Output directory"),
):
    """Save an externally generated (e.g. Antigravity) report into the knowledge base and update indices."""
    pipeline = QuantSummarizer(output_dir=output_dir)
    
    # Locate task json
    task_files = list((pipeline.output_dir / ".transcripts").glob(f"*/{video_id}.json"))
    if not task_files:
        console.print(f"[bold red]错误: 未找到视频 {video_id} 的预抓取任务文件。[/bold red]")
        raise typer.Exit(code=1)

    import json
    from summarizer.models import VideoTask
    
    task_data = json.loads(task_files[0].read_text(encoding="utf-8"))
    task = VideoTask(**task_data)
    
    report_path_obj = Path(report_file)
    if not report_path_obj.exists():
        console.print(f"[bold red]错误: 研报文件不存在: {report_file}[/bold red]")
        raise typer.Exit(code=1)

    report_md = report_path_obj.read_text(encoding="utf-8")
    saved_record, final_report_path = pipeline.record_report(
        metadata=task.metadata,
        report_markdown=report_md,
        model_name=model_name,
        transcript_source=task.transcript.source
    )
    console.print(f"[bold green]✓ 研报已归档入库:[/bold green] {final_report_path}")
    console.print(f"[green]✓ 全局与频道索引已同步更新！[/green]")
