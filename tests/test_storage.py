from pathlib import Path
from summarizer.storage import StorageManager
from summarizer.models import VideoRecord, ProcessingStatus


def test_storage_crud(tmp_path: Path):
    db_file = tmp_path / "test_records.db"
    storage = StorageManager(db_file)

    assert not storage.is_processed("vid001")

    record = VideoRecord(
        video_id="vid001",
        channel="QuantHub",
        title="Mean Reversion Strategy",
        upload_date="2024-01-01",
        duration="15:30",
        status=ProcessingStatus.COMPLETED,
        transcript_source="youtube_subtitles",
        report_path="output/QuantHub/2024-01-01_Mean_Reversion.md"
    )
    storage.save_record(record)

    assert storage.is_processed("vid001")
    fetched = storage.get_record("vid001")
    assert fetched is not None
    assert fetched.title == "Mean Reversion Strategy"
    assert fetched.channel == "QuantHub"

    all_records = storage.get_all_records()
    assert len(all_records) == 1
    assert all_records[0].video_id == "vid001"

    ch_records = storage.get_channel_records("QuantHub")
    assert len(ch_records) == 1
