from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import yaml


Channel = Tuple[str, str]
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "channels.yaml"


def _load_group(group: str) -> List[Channel]:
    if not CONFIG_PATH.is_file():
        raise FileNotFoundError(f"Channel catalogue not found: {CONFIG_PATH}")

    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    entries = data.get(group)
    if not isinstance(entries, list):
        raise ValueError(f"Channel group '{group}' must be a list in {CONFIG_PATH}")

    channels: List[Channel] = []
    seen_urls = set()
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("name") or not entry.get("url"):
            raise ValueError(f"Invalid channel entry in group '{group}': {entry!r}")
        name, url = str(entry["name"]).strip(), str(entry["url"]).strip()
        if url in seen_urls:
            raise ValueError(f"Duplicate channel URL in group '{group}': {url}")
        seen_urls.add(url)
        channels.append((name, url))
    return channels


QUANT_CHANNELS = _load_group("quant")
OPTIONAL_QUANT_CHANNELS = _load_group("optional_quant")
QUANT_CHANNELS_WITH_OPTIONAL = QUANT_CHANNELS + OPTIONAL_QUANT_CHANNELS
AI_CHANNELS = _load_group("ai")
