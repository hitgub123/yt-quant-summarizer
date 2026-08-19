from summarizer.models import VideoMetadata, TranscriptResult, ProcessingStatus, VideoRecord


def test_video_metadata_creation():
    metadata = VideoMetadata(
        video_id="test1234567",
        title="Test Quant Strategy",
        channel="AlgorithmTradingIn",
        upload_date="2024-03-15",
        duration_seconds=600,
        duration_formatted="10:00",
        url="https://www.youtube.com/watch?v=test1234567"
    )
    assert metadata.video_id == "test1234567"
    assert metadata.duration_formatted == "10:00"
    assert metadata.channel == "AlgorithmTradingIn"


def test_video_record_status():
    rec = VideoRecord(
        video_id="test1234567",
        channel="AlgoChannel",
        title="Strategy Alpha",
        status=ProcessingStatus.COMPLETED,
        report_path="output/AlgoChannel/report.md"
    )
    assert rec.status == ProcessingStatus.COMPLETED
    assert rec.report_path == "output/AlgoChannel/report.md"
