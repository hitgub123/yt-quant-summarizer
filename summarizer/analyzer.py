from __future__ import annotations
import time
import logging
from typing import Optional
from google import genai
from google.genai import types
from google.genai.errors import APIError

from summarizer.config import settings
from summarizer.models import VideoMetadata, TranscriptResult
from summarizer.prompts import QUANT_SYSTEM_INSTRUCTION, QUANT_REPORT_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


class GeminiAnalyzer:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_retries: int = 3,
        base_delay: float = 5.0
    ):
        self.api_key = api_key or settings.GEMINI_API_KEY
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Please provide it in .env file or pass via command line."
            )
        self.model_name = model or settings.GEMINI_MODEL
        self.client = genai.Client(api_key=self.api_key)
        self.max_retries = max_retries
        self.base_delay = base_delay

    def analyze(self, metadata: VideoMetadata, transcript: TranscriptResult) -> str:
        """Generate structured quant report using Gemini model with retry."""
        prompt = QUANT_REPORT_PROMPT_TEMPLATE.format(
            title=metadata.title,
            channel=metadata.channel,
            upload_date=metadata.upload_date or "未知",
            duration=metadata.duration_formatted,
            url=metadata.url,
            transcript=transcript.formatted_transcript or transcript.full_text
        )

        config = types.GenerateContentConfig(
            system_instruction=QUANT_SYSTEM_INSTRUCTION,
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