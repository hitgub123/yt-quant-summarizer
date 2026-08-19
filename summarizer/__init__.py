"""YouTube Quantitative Investment Strategy Summarizer & Knowledge Extractor."""

from summarizer.core import QuantSummarizer
from summarizer.models import VideoMetadata, VideoRecord, ProcessingStatus, TranscriptResult
from summarizer.classifier import is_investment_related

__version__ = "0.1.0"
__all__ = [
    "QuantSummarizer",
    "VideoMetadata",
    "VideoRecord",
    "ProcessingStatus",
    "TranscriptResult",
    "is_investment_related",
]