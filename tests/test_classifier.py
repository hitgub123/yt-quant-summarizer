from summarizer.classifier import is_investment_related


def test_investment_classifier_positive():
    # Quant / Algorithmic
    assert is_investment_related("Risk Management in Algo Trading")[0]
    assert is_investment_related("Build a Complete Trade Database Class in Python")[0]
    assert is_investment_related("BUILD First BUY SELL HOLD TRADING BOT using Python")[0]
    assert is_investment_related("Effective way to exit the Trading STRATEGY")[0]
    assert is_investment_related("How Smart Traders Detect Shooting Star Reversals Automatically")[0]
    assert is_investment_related("Backtesting a Momentum Strategy with Pandas and VectorBT")[0]

    # Chinese quant / trading titles
    assert is_investment_related("手把手教你写双均线量化交易策略")[0]
    assert is_investment_related("Python回测CTA网格交易系统与最大回撤控制")[0]
    assert is_investment_related("股票多因子选股模型实战")[0]
    assert is_investment_related("比特币以太坊高频套利策略分享")[0]


def test_investment_classifier_negative():
    # Life, vlog, games, cooking
    is_rel, reason = is_investment_related("My Morning Routine in Tokyo | Daily Vlog")
    assert not is_rel

    is_rel, reason = is_investment_related("How to bake the best chocolate cake at home")
    assert not is_rel

    is_rel, reason = is_investment_related("Playing Minecraft with Friends Episode 12")
    assert not is_rel

    is_rel, reason = is_investment_related("今天吃了顿火锅，聊聊最近的生活琐事")
    assert not is_rel