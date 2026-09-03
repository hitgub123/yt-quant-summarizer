import pytest
from unittest.mock import MagicMock

from summarizer.analyzer import GeminiAnalyzer
from summarizer.models import TranscriptResult, VideoMetadata


def test_report_validation_requires_all_seven_sections():
    valid = "\n".join(f"## {number}. Section" for number in range(1, 8))
    GeminiAnalyzer._validate_report(valid)

    with pytest.raises(ValueError, match="missing sections: 7"):
        GeminiAnalyzer._validate_report(valid.replace("## 7. Section", ""))


def test_summary_mode_does_not_require_seven_sections():
    analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
    analyzer.report_mode = "summary"
    analyzer.model_name = "test-model"
    analyzer.max_retries = 1
    analyzer.base_delay = 0
    analyzer.client = MagicMock()
    analyzer.client.models.generate_content.return_value.text = "# 视频摘要\n\n## 摘要\n这是摘要。"

    result = analyzer.analyze(
        VideoMetadata(
            video_id="summary12345",
            title="Summary video",
            channel="Channel",
            url="https://www.youtube.com/watch?v=summary12345",
        ),
        TranscriptResult(
            video_id="summary12345",
            source="youtube_subtitles",
            full_text="A short transcript.",
            formatted_transcript="[00:00:00] A short transcript.",
        ),
    )

    assert result.startswith("# 视频摘要")
    prompt = analyzer.client.models.generate_content.call_args.kwargs["contents"]
    assert "简洁摘要" in prompt
