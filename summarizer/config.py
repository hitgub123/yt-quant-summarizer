from __future__ import annotations
import os
from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    GEMINI_API_KEY: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    GEMINI_MODEL: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    HTTP_PROXY: Optional[str] = Field(default=None, alias="HTTP_PROXY")
    HTTPS_PROXY: Optional[str] = Field(default=None, alias="HTTPS_PROXY")
    OUTPUT_DIR: Path = Field(default=Path("output"), alias="OUTPUT_DIR")
    TRANSCRIPT_LANGUAGES: str = Field(
        default="en,zh-Hans,zh-Hant,zh,ja",
        alias="TRANSCRIPT_LANGUAGES"
    )
    AUTO_CLEAN_AUDIO: bool = Field(default=True, alias="AUTO_CLEAN_AUDIO")
    MAX_RETRIES: int = Field(default=3, alias="MAX_RETRIES")

    @property
    def language_list(self) -> List[str]:
        if isinstance(self.TRANSCRIPT_LANGUAGES, list):
            return self.TRANSCRIPT_LANGUAGES
        return [lang.strip() for lang in self.TRANSCRIPT_LANGUAGES.split(",") if lang.strip()]

    def setup_proxies(self, override_proxy: Optional[str] = None) -> Optional[str]:
        proxy = override_proxy or self.HTTP_PROXY or self.HTTPS_PROXY
        if proxy:
            os.environ["HTTP_PROXY"] = proxy
            os.environ["HTTPS_PROXY"] = proxy
            os.environ["http_proxy"] = proxy
            os.environ["https_proxy"] = proxy
            return proxy
        return None


settings = Settings()
