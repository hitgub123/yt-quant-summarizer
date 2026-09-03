from __future__ import annotations
import time
import logging
import re
from typing import Literal, Optional
from google import genai
from google.genai import types

from summarizer.config import settings
from summarizer.models import VideoMetadata, TranscriptResult
from summarizer.prompts import (
    QUANT_REPORT_PROMPT_TEMPLATE,
    QUANT_SYSTEM_INSTRUCTION,
    SUMMARY_PROMPT_TEMPLATE,
    SUMMARY_SYSTEM_INSTRUCTION,
)

logger = logging.getLogger(__name__)


class GeminiAnalyzer:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_retries: Optional[int] = None,
        base_delay: float = 5.0,
        report_mode: Literal["summary", "research"] = "summary",
    ):
        self.api_key = api_key or settings.GEMINI_API_KEY
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Please provide it in .env file or pass via command line."
            )
        self.model_name = model or settings.GEMINI_MODEL
        if report_mode not in {"summary", "research"}:
            raise ValueError("report_mode must be 'summary' or 'research'.")
        self.report_mode = report_mode
        self.client = genai.Client(api_key=self.api_key)
        self.max_retries = max(1, max_retries if max_retries is not None else settings.MAX_RETRIES)
        self.base_delay = base_delay

    def analyze(self, metadata: VideoMetadata, transcript: TranscriptResult) -> str:
        """Generate structured quant report using Gemini model with retry."""
        transcript_text = transcript.formatted_transcript or transcript.full_text
        if not transcript_text.strip():
            raise ValueError(f"Transcript is empty for video {metadata.video_id}.")

        prompt_template = (
            QUANT_REPORT_PROMPT_TEMPLATE
            if self.report_mode == "research"
            else SUMMARY_PROMPT_TEMPLATE
        )
        system_instruction = (
            QUANT_SYSTEM_INSTRUCTION
            if self.report_mode == "research"
            else SUMMARY_SYSTEM_INSTRUCTION
        )
        prompt = prompt_template.format(
            title=metadata.title,
            channel=metadata.channel,
            upload_date=metadata.upload_date or "未知",
            duration=metadata.duration_formatted,
            url=metadata.url,
            transcript=transcript_text
        )

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
        )

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config
                )

                if not response.text:
                    raise RuntimeError("Gemini returned empty response for video analysis.")

                if self.report_mode == "research":
                    self._validate_report(response.text)
                return response.text

            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    wait_time = self.base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        f"Gemini API attempt {attempt} failed: {e}. Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    break

        raise RuntimeError(f"Gemini analysis failed after {self.max_retries} attempts. Error: {last_error}")

    @staticmethod
    def _validate_report(report_markdown: str) -> None:
        """Reject successful-but-incomplete model output before persistence."""
        required_sections = [
            rf"^##\s+{number}\.\s+"
            for number in range(1, 8)
        ]
        missing = [
            str(number)
            for number, section in enumerate(required_sections, 1)
            if not re.search(section, report_markdown, flags=re.MULTILINE)
        ]
        if missing:
            raise ValueError(
                "Gemini returned an incomplete quant report; "
                f"missing sections: {', '.join(missing)}."
            )
