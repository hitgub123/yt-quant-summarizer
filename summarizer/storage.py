from __future__ import annotations
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from summarizer.models import VideoRecord, ProcessingStatus


class StorageManager:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path("output/.cache/records.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS records (
                    video_id TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    title TEXT NOT NULL,
                    upload_date TEXT,
                    duration TEXT,
                    status TEXT NOT NULL,
                    transcript_source TEXT,
                    report_path TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transcript_cache (
                    video_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    transcript_text TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def is_processed(self, video_id: str) -> bool:
        """Check if video was already successfully processed."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT status FROM records WHERE video_id = ? AND status = ?",
                (video_id, ProcessingStatus.COMPLETED.value)
            )
            row = cursor.fetchone()
            return row is not None

    def get_record(self, video_id: str) -> Optional[VideoRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM records WHERE video_id = ?", (video_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return VideoRecord(
                video_id=row["video_id"],
                channel=row["channel"],
                title=row["title"],
                upload_date=row["upload_date"],
                duration=row["duration"] or "00:00",
                status=ProcessingStatus(row["status"]),
                transcript_source=row["transcript_source"],
                report_path=row["report_path"],
                error_message=row["error_message"],
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )

    def save_record(self, record: VideoRecord):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        created_at = record.created_at or now
        updated_at = now

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO records (
                    video_id, channel, title, upload_date, duration,
                    status, transcript_source, report_path, error_message,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    channel = excluded.channel,
                    title = excluded.title,
                    upload_date = excluded.upload_date,
                    duration = excluded.duration,
                    status = excluded.status,
                    transcript_source = excluded.transcript_source,
                    report_path = excluded.report_path,
                    error_message = excluded.error_message,
                    updated_at = excluded.updated_at
            """, (
                record.video_id,
                record.channel,
                record.title,
                record.upload_date,
                record.duration,
                record.status.value,
                record.transcript_source,
                record.report_path,
                record.error_message,
                created_at,
                updated_at
            ))
            conn.commit()

    def get_all_records(self) -> List[VideoRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM records ORDER BY updated_at DESC")
            records = []
            for row in cursor.fetchall():
                records.append(VideoRecord(
                    video_id=row["video_id"],
                    channel=row["channel"],
                    title=row["title"],
                    upload_date=row["upload_date"],
                    duration=row["duration"] or "00:00",
                    status=ProcessingStatus(row["status"]),
                    transcript_source=row["transcript_source"],
                    report_path=row["report_path"],
                    error_message=row["error_message"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"]
                ))
            return records

    def get_channel_records(self, channel: str) -> List[VideoRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM records WHERE channel = ? ORDER BY upload_date DESC, updated_at DESC",
                (channel,)
            )
            records = []
            for row in cursor.fetchall():
                records.append(VideoRecord(
                    video_id=row["video_id"],
                    channel=row["channel"],
                    title=row["title"],
                    upload_date=row["upload_date"],
                    duration=row["duration"] or "00:00",
                    status=ProcessingStatus(row["status"]),
                    transcript_source=row["transcript_source"],
                    report_path=row["report_path"],
                    error_message=row["error_message"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"]
                ))
            return records
