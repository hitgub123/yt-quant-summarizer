from unittest.mock import MagicMock, patch
import pytest
from summarizer.models import VideoMetadata, TranscriptResult
from summarizer.transcriber import HybridTranscriber


def test_gemini_video_url_fallback():
    mock_gemini = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "[00:00:01] Welcome to algorithmic trading."
    mock_gemini.models.generate_content.return_value = mock_response

    transcriber = HybridTranscriber(gemini_client=mock_gemini)

    meta = VideoMetadata(
        video_id="test12345",
        title="Super Strategy",
        channel="QuantLab",
        url="https://www.youtube.com/watch?v=test12345"
    )

    # Force failure on subtitle extraction to trigger fallback Strategy 3
    with patch.object(transcriber, "_extract_via_transcript_api", return_value=None), \
         patch.object(transcriber, "_extract_via_ytdlp_subtitles", return_value=None):
        res = transcriber.get_transcript(meta)

    assert res.source == "gemini_video_url"
    assert res.video_id == "test12345"
    assert "[00:00:01] Welcome to algorithmic trading." in res.full_text

    # Verify Gemini was called with Part containing video URL
    mock_gemini.models.generate_content.assert_called_once()
    call_args = mock_gemini.models.generate_content.call_args
    contents = call_args.kwargs.get("contents") or call_args[1].get("contents")
    
    # Check that contents contains Part with file_uri
    has_video_part = any(getattr(c, "file_data", None) and c.file_data.file_uri == meta.url for c in contents if hasattr(c, "file_data")) or \
                     any("test12345" in str(getattr(c, "file_data", "")) or (hasattr(c, "file_data") and getattr(c.file_data, "file_uri", None) == meta.url) for c in contents)
    assert len(contents) == 2


def test_ytdlp_vtt_parser_returns_timed_transcript():
    parsed = HybridTranscriber._parse_vtt(
        "WEBVTT\n\n00:00.000 --> 00:01.500\nHello <b>world</b>\n\n"
        "00:01.500 --> 00:03.000\nQuant trading\n"
    )

    assert parsed == [
        (0.0, 1.5, "Hello world"),
        (1.5, 1.5, "Quant trading"),
    ]


def test_subtitle_429_stops_without_retry():
    transcriber = HybridTranscriber(
        min_request_interval=0,
        max_retries=2,
        backoff_seconds=0,
    )
    operation = MagicMock(side_effect=RuntimeError("HTTP 429 Too Many Requests"))

    with patch("summarizer.transcriber.time.sleep") as sleep:
        with pytest.raises(RuntimeError, match="429"):
            transcriber._with_subtitle_retries(operation, "test subtitle")

    assert operation.call_count == 1
    sleep.assert_not_called()


def test_subtitle_429_opens_circuit_after_retries():
    transcriber = HybridTranscriber(
        min_request_interval=0,
        max_retries=1,
        backoff_seconds=0,
        cooldown_seconds=60,
    )
    operation = MagicMock(side_effect=RuntimeError("429"))

    with patch("summarizer.transcriber.time.sleep"):
        with pytest.raises(RuntimeError, match="429"):
            transcriber._with_subtitle_retries(operation, "test subtitle")

    with pytest.raises(RuntimeError, match="temporarily paused"):
        transcriber._with_subtitle_retries(lambda: "should not run", "test subtitle")


def test_subtitle_cooldown_survives_process_restart(tmp_path):
    state_file = tmp_path / "subtitle_cooldown.json"
    first = HybridTranscriber(
        min_request_interval=0,
        max_retries=0,
        cooldown_seconds=86400,
        cooldown_state_file=state_file,
    )
    with patch("summarizer.transcriber.time.sleep"):
        with pytest.raises(RuntimeError, match="429"):
            first._with_subtitle_retries(lambda: (_ for _ in ()).throw(RuntimeError("429")), "test subtitle")

    restarted = HybridTranscriber(
        min_request_interval=0,
        max_retries=0,
        cooldown_seconds=86400,
        cooldown_state_file=state_file,
    )
    operation = MagicMock(return_value="should not run")
    with pytest.raises(RuntimeError, match="temporarily paused"):
        restarted._with_subtitle_retries(operation, "test subtitle")
    operation.assert_not_called()


def test_transcript_api_receives_proxy_config():
    fake_transcript = MagicMock(language_code="en")
    fake_transcript.fetch.return_value = [{"start": 0, "duration": 1, "text": "hello"}]
    fake_list = MagicMock()
    fake_list.find_manually_created_transcript.return_value = fake_transcript
    fake_api = MagicMock()
    fake_api.return_value.list.return_value = fake_list

    with patch("youtube_transcript_api.YouTubeTranscriptApi", fake_api):
        transcriber = HybridTranscriber(proxy="http://127.0.0.1:7890", min_request_interval=0)
        result = transcriber._extract_via_transcript_api("abc123")

    assert result.full_text == "hello"
    proxy_config = fake_api.call_args.kwargs["proxy_config"]
    assert proxy_config.to_requests_dict() == {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890",
    }


def test_subtitles_only_never_calls_gemini_fallback():
    mock_gemini = MagicMock()
    transcriber = HybridTranscriber(
        gemini_client=mock_gemini,
        transcript_mode="subtitles",
        min_request_interval=0,
    )
    meta = VideoMetadata(
        video_id="test12345",
        title="No captions",
        channel="QuantLab",
        url="https://www.youtube.com/watch?v=test12345",
    )

    with patch.object(transcriber, "_extract_via_transcript_api", return_value=None), \
         patch.object(transcriber, "_extract_via_ytdlp_subtitles", return_value=None):
        with pytest.raises(RuntimeError, match="subtitles-only mode"):
            transcriber.get_transcript(meta)

    mock_gemini.models.generate_content.assert_not_called()
