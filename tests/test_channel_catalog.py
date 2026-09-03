from summarizer.channel_catalog import (
    AI_CHANNELS,
    QUANT_CHANNELS,
    QUANT_CHANNELS_WITH_OPTIONAL,
)


def test_channel_catalog_has_stable_groups():
    assert len(QUANT_CHANNELS) == 13
    assert len(QUANT_CHANNELS_WITH_OPTIONAL) == 14
    assert len(AI_CHANNELS) == 7
    assert "TheStockMarket" in {name for name, _ in QUANT_CHANNELS_WITH_OPTIONAL}
    assert "AI Explained" in {name for name, _ in AI_CHANNELS}


def test_channel_catalog_urls_are_unique():
    all_channels = QUANT_CHANNELS_WITH_OPTIONAL + AI_CHANNELS
    urls = [url for _, url in all_channels]
    assert len(urls) == len(set(urls))
