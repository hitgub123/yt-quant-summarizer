import os
import re
import json
import time
from pathlib import Path
from google import genai
import requests

with open(".env") as f:
    for line in f:
        if line.startswith("GEMINI_API_KEY="):
            api_key = line.strip().split("=", 1)[1].strip("\"'")

client = genai.Client(api_key=api_key)

video_url = "https://www.youtube.com/watch?v=hoi59k5zh1A"
video_title = "Tesla (TSLA): ARK's Stock Stories"
channel_name = "ARK Invest"

prompt = f"""你是一名顶级买方量化基金投资总监与机构分析师。
请针对以下 YouTube 视频内容，撰写一份严格结构化的【7 维度机构级量化与交易策略研报】。

视频标题：{video_title}
视频链接：{video_url}
发布机构：{channel_name}

【严格格式要求】：
请输出标准 Markdown 格式，包含以下 7 个核心章节：
# 📊 【量化/交易研报】{video_title}

- **分析机构/博主**：`{channel_name}`
- **原始视频链接**：[YouTube 视频]({video_url})
- **分析引擎**：Google Gemini 官方深度多模态分析

---

## 🎯 一、核心投资观点与交易假设 (Core Investment Thesis & Hypotheses)
（详细提炼视频中的核心观点、逻辑链条、宏观与行业背景）

## 📈 二、涉及标的资产与适用市场环境 (Target Assets & Market Regime)
（核心标的代码，如 TSLA，适用的波动率与流动性环境）

## 🛠️ 三、交易指标与关键触发逻辑 (Key Technical/Quantitative Signals)
（买入/入场触发条件、卖出/止盈触发条件）

## 🛡️ 四、资金管理与风控止损规则 (Risk Management & Position Sizing)
（仓位建议、止损止盈逻辑）

## 📊 五、历史表现与统计数据 (Historical Performance & Evidence)
（视频中披露的数据或估值模型数据。若博主未披露回测数据，请如实声明“博主未在视频中提供回测数据”，严禁捏造）

## 💻 六、量化回测与指标实现示例 (Quantitative Implementation Code)
（给出高质量、可运行的 Python 代码，包含数据加载与信号生成函数）

## ⚠️ 七、策略局限性与实盘失效风险 (Limitations & Risk Disclaimers)
（市场风险、模型过拟合、流动性冲击等）
"""

print(f"🚀 正在调用 Gemini 官方 API 生成研报: {video_title}...")
response = client.models.generate_content(
    model="gemini-3.6-flash",
    contents=prompt
)

out_file = Path("output/ARK_Invest/2026-08-14_hoi59k5zh1A_Tesla_TSLA_ARKs_Stock_Stories.md")
out_file.parent.mkdir(parents=True, exist_ok=True)
with open(out_file, "w", encoding="utf-8") as f:
    f.write(response.text)

print(f"🎉 成功生成真实量化研报！已保存至: {out_file}")
print("\n" + "="*80)
print(response.text[:600])
print("="*80)
