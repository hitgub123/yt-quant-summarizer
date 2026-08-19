from pathlib import Path
from summarizer.indexer import IndexBuilder
from summarizer.storage import StorageManager
from summarizer.models import VideoMetadata, VideoRecord, ProcessingStatus


def test_indexer_report_and_indices(tmp_path: Path):
    output_dir = tmp_path / "output"
    storage = StorageManager(output_dir / ".cache" / "test.db")
    indexer = IndexBuilder(output_dir, storage)

    meta = VideoMetadata(
        video_id="abc12345678",
        title="Dual Moving Average Crossover",
        channel="AlgoTrader",
        upload_date="2024-02-10",
        duration_seconds=500,
        duration_formatted="08:20",
        url="https://www.youtube.com/watch?v=abc12345678"
    )

    report_md = "# Dual Moving Average Crossover\n\n## 1. 核心论点\n这是一个经典双均线策略。"
    report_file = indexer.save_report(meta, report_md, model_name="gemini-2.5-flash")

    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "title: Dual Moving Average Crossover" in content
    assert "channel: AlgoTrader" in content
    assert "# Dual Moving Average Crossover" in content

    # Save to storage
    rec = VideoRecord(
        video_id=meta.video_id,
        channel=meta.channel,
        title=meta.title,
        upload_date=meta.upload_date,
        duration=meta.duration_formatted,
        status=ProcessingStatus.COMPLETED,
        report_path=str(report_file)
    )
    storage.save_record(rec)

    # Test channel index
    ch_index = indexer.update_channel_index("AlgoTrader")
    assert ch_index.exists()
    ch_content = ch_index.read_text(encoding="utf-8")
    assert "AlgoTrader - 量化策略研报索引" in ch_content
    assert "Dual Moving Average Crossover" in ch_content

    # Test global index
    g_index = indexer.update_global_index()
    assert g_index.exists()
    g_content = g_index.read_text(encoding="utf-8")
    assert "YouTube 量化投资研报知识库" in g_content
    assert "AlgoTrader" in g_content
