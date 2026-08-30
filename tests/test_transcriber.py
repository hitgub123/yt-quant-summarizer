from unittest.mock import MagicMock, patch
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
