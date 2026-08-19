from unittest.mock import MagicMock, patch
from pathlib import Path
from summarizer.core import QuantSummarizer
from summarizer.models import VideoMetadata, TranscriptResult


def test_quant_summarizer_pipeline(tmp_path: Path):
    summarizer = QuantSummarizer(api_key="mock_key", output_dir=tmp_path / "out")
    
    # Mock analyzer and transcriber
    summarizer.analyzer = MagicMock()
    summarizer.analyzer.analyze.return_value = "# Mock Report\n\n## 1. 核心论点\n测试研报"
    
    summarizer.ingester = MagicMock()
    summarizer.ingester.get_video_metadata.return_value = VideoMetadata(
        video_id="mock1234567",
        title="Python Algo Strategy",
        channel="QuantMaster",
        upload_date="2024-05-01",
        duration_seconds=300,
        duration_formatted="05:00",
        url="https://www.youtube.com/watch?v=mock1234567"
    )
    
    summarizer.transcriber = MagicMock()
    summarizer.transcriber.get_transcript.return_value = TranscriptResult(
        video_id="mock1234567",
        source="mock_sub",
        language="en",
        full_text="This is a test transcript about trading.",
        formatted_transcript="[00:00:00] This is a test transcript about trading."
    )
    
    record, report_file = summarizer.summarize_video("mock1234567")
    
    assert report_file.exists()
    assert record.video_id == "mock1234567"
    assert record.status.value == "completed"
    assert "QuantMaster" in str(report_file)

    # Check cache
    assert summarizer.storage.is_processed("mock1234567")