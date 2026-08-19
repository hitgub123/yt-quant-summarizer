from __future__ import annotations
import re
from typing import List, Optional, Tuple

# Comprehensive multi-lingual quant & investment keyword vocabulary
INVESTMENT_KEYWORDS = [
    # Quant & Algorithmic Trading
    r"\balgo\b", r"\balgorithmic\b", r"\bquantitative\b", r"\bquant\b", r"\bbacktest\b",
    r"\bbacktesting\b", r"\bstrategy\b", r"\bstrategies\b", r"\btrading bot\b", r"\bbot\b",
    r"\bhft\b", r"\bhigh frequency\b", r"\barbitrage\b", r"\balpha\b", r"\bbeta\b",
    r"\bexecution\b", r"\border book\b", r"\bmarket maker\b", r"\bmarket making\b",
    r"\bposition sizing\b", r"\brisk management\b", r"\bdrawdown\b", r"\bsharpe\b",
    r"\bslippage\b", r"\blookahead bias\b", r"\bvectorized\b",
    r"\btrade\b", r"\btrades\b", r"\btrader\b", r"\btraders\b", r"\btrading\b",

    # Asset Classes & Markets
    r"\bstock\b", r"\bstocks\b", r"\bshare\b", r"\bshares\b", r"\bequity\b", r"\bequities\b",
    r"\bfutures\b", r"\boptions?\b", r"\bforex\b", r"\bfx\b", r"\bcrypto\b", r"\bcryptocurrency\b",
    r"\bbitcoin\b", r"\bbtc\b", r"\beth\b", r"\bethereum\b", r"\betf\b", r"\betfs\b",
    r"\bbond\b", r"\bbonds\b", r"\byield\b", r"\bcommodity\b", r"\bcommodities\b",
    r"\bnifty\b", r"\bbanknifty\b", r"\bsp500\b", r"\bs&p\b", r"\bnasdaq\b", r"\bdow\b",

    # Technical Indicators & Methods
    r"\brsi\b", r"\bmacd\b", r"\bmoving average\b", r"\bsma\b", r"\bema\b", r"\bwma\b",
    r"\bbollinger\b", r"\batr\b", r"\bvolume\b", r"\bvwap\b", r"\bobv\b", r"\bstochastic\b",
    r"\bcandlestick\b", r"\bprice action\b", r"\bsupport and resistance\b", r"\btrend\b",
    r"\bbreakout\b", r"\breversal\b", r"\bmean reversion\b", r"\bmomentum\b", r"\bscalping\b",
    r"\bday trad\w*\b", r"\bswing trad\w*\b", r"\blong\b", r"\bshort\b", r"\bstop loss\b",
    r"\btake profit\b", r"\bltp\b", r"\bohlc\w*\b",

    # Finance & Programming Platforms
    r"\bbacktrader\b", r"\bvectorbt\b", r"\bta-lib\b",
    r"\binteractive brokers\b", r"\bbinance\b", r"\bzerodha\b", r"\bangel one\b",
    r"\btradingview\b", r"\bpinescript\b", r"\bmetatrader\b", r"\bmt4\b", r"\bmt5\b",

    # Chinese Keywords
    r"量化", r"交易", r"策略", r"投资", r"回测", r"炒股", r"股票", r"期货", r"期权",
    r"外汇", r"加密货币", r"比特币", r"以太坊", r"基金", r"etf", r"指数", r"证券",
    r"动量", r"均值回归", r"网格交易", r"套利", r"高频", r"做市", r"仓位", r"止损",
    r"止盈", r"回撤", r"夏普", r"因子", r"多因子", r"研报", r"财报", r"估值",
    r"k线", r"均线", r"技术指标", r"趋势跟踪", r"波段", r"日内", r"短线", r"定投",
    r"资产配置", r"投资组合", r"宏观", r"美联储", r"加息", r"降息", r"牛市", r"熊市"
]

_COMPILED_PATTERNS = [re.compile(pattern, re.IGNORECASE) for pattern in INVESTMENT_KEYWORDS]


def is_investment_related(
    title: str,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None
) -> Tuple[bool, str]:
    """
    Classify whether a video is relevant to trading, finance, or quant investment.
    Returns: (is_relevant, matched_reason)
    """
    text_corpus = title
    if tags:
        text_corpus += " " + " ".join(tags)
    if description:
        # Take first 500 characters of description for fast checking
        text_corpus += " " + description[:500]

    for pattern in _COMPILED_PATTERNS:
        match = pattern.search(text_corpus)
        if match:
            return True, f"匹配投资关键词: '{match.group(0)}'"

    return False, "未检测到明确的量化/交易/投资相关关键词"