from summarizer.utils import extract_video_id, is_channel_url, sanitize_filename, format_seconds, format_timestamp


def test_extract_video_id():
    assert extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id("https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=10s") == "dQw4w9WgXcQ"
    assert extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_is_channel_url():
    assert is_channel_url("https://www.youtube.com/@AlgorithmTradingIn")
    assert is_channel_url("https://m.youtube.com/@AlgorithmTradingIn/videos")
    assert is_channel_url("https://www.youtube.com/channel/UC1234567890")
    assert not is_channel_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


def test_sanitize_filename():
    assert sanitize_filename("Strategy: Alpha/Beta & RSI > 70?") == "Strategy_AlphaBeta_RSI_70"
    assert sanitize_filename("A" * 100, max_length=50) == "A" * 50


def test_format_seconds():
    assert format_seconds(65) == "01:05"
    assert format_seconds(3665) == "01:01:05"
    assert format_seconds(0) == "00:00"


def test_format_timestamp():
    assert format_timestamp(75.5) == "[00:01:15]"
    assert format_timestamp(3605) == "[01:00:05]"
