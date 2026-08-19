# YouTube 量化投资视频知识提炼与学习报告生成器 (yt-quant-summarizer)
## 产品需求规格说明书 (PRD)

---

## 1. 项目背景与目标

在 YouTube 等平台上，有大量优质的量化交易、程序化交易与投资策略分享频道（如 `@AlgorithmTradingIn`）。这些视频通常包含交易理论、数学公式、技术指标计算、风控逻辑以及 Python 策略代码。

**核心目标**：
开发一款高效、自动化、开箱即用的命令行工具（CLI），能够自动化批量解析指定频道或单个视频，利用混合字幕与语音转录技术提取全量文本，并通过专精设计的量化分析 Prompt 调用 Google Gemini API 进行深度提炼，输出结构化、严谨的量化研报 Markdown 文档并自动建立索引目录，方便投资者与量化学习者进行系统化学习与知识沉淀。

---

## 2. 目标用户与使用场景

1. **量化策略研究员/学习者**：希望快速拆解 YouTube 上各类交易策略的核心数学逻辑与代码实现，而无需耗费数小时逐秒观看视频。
2. **批量知识库归档者**：希望一键将整个频道的历史视频批量总结并导入 Obsidian、Notion 或个人知识库中长期保存。
3. **策略复现与回测者**：需要从视频中提炼出精确的进出场条件、止损止盈规则、Python/伪代码实现及回测注意事项。

---

## 3. 功能需求规格

### 3.1 视频与元数据采集模块 (Video & Metadata Ingestion)
- **单视频与频道批量解析**：
  - 支持直接输入单个视频 URL（如 `https://www.youtube.com/watch?v=xxx`）。
  - 支持输入频道 URL（如 `https://m.youtube.com/@AlgorithmTradingIn`），自动通过 `yt-dlp` 解析视频列表。
- **批量处理参数控制**：
  - 支持 `--limit N` 参数，限制最多抓取并处理前 N 个最新视频。
  - 支持按发布时间排序筛选。
- **网络与代理支持**：
  - 支持配置 HTTP / SOCKS5 代理（如 `http://127.0.0.1:7890`），保障国内网络环境的顺畅访问。

### 3.2 混合文稿转录模块 (Hybrid Transcript Engine)
- **优先策略（字幕提取）**：
  - 优先调用 YouTube 字幕 API 提取原生字幕或自动生成字幕（支持多语言自动选择，优先 English/Chinese）。
  - 无需下载视频音频流，秒级完成，大幅节省带宽与时间成本。
- **兜底策略（语音转录）**：
  - 若视频无任何可用字幕，自动通过 `yt-dlp` 下载极低码率的轻量音频（`.m4a` / `.mp3`）。
  - 调用 `faster-whisper` 本地转录或直接利用 Gemini 多模态音频理解能力进行转录，转录完成后自动清理临时音频文件。

### 3.3 量化深度分析与 LLM 引擎 (Gemini Analysis Engine)
- **专精适配 Google Gemini API**：
  - 采用官方最新 SDK (`google-genai`)。
  - 默认使用超大上下文窗口模型（如 `gemini-2.5-flash` / `gemini-2.5-pro`），从容应对 1~2 小时长视频的全文本分析。
- **量化交易定制化 Prompt 设计**：
  模型需严格按照如下 7 大维度提炼生成标准报告：
  1. **视频基础信息**：标题、频道、发布日期、视频时长、视频直链、核心论点摘要（200字以内）。
  2. **核心理念与策略逻辑**：策略假说、盈利驱动因素、适合的市场行情（震荡、趋势、高波动等）。
  3. **指标与数学公式**：所有涉及的指标公式、参数设定及计算逻辑。
  4. **交易与风控规则速查**：
     - 买入/做多信号（Long Entry）
     - 卖出/做空信号（Short Entry）
     - 止盈与出场条件（Take-Profit & Exit）
     - 止损与仓位管理（Stop-Loss & Position Sizing / Max Drawdown）
  5. **Python / 伪代码实现**：给出结构清晰、符合规范的策略代码实现片段（基于 `pandas`、`numpy` 或通用回测框架）。
  6. **回测评估与局限性**：过拟合风险、交易摩擦（滑点、手续费）影响、前视偏差提醒及实盘注意事项。
  7. **时间戳重点导航**：核心章节与精彩观点的时间轴索引。

### 3.4 报告生成与目录组织模块 (Report & Storage Management)
- **文件与目录结构**：
  - 输出根目录结构：
    ```text
    output/
    ├── INDEX.md                        # 全局视频研报总索引
    └── AlgorithmTradingIn/             # 频道专属目录
        ├── INDEX.md                    # 频道内研报索引
        ├── 2024-03-15_Strategy_A.md    # 具体视频研报
        └── .cache/                     # Raw JSON 缓存与状态
    ```
- **Obsidian / Notion 兼容性**：
  - 头部包含 YAML Frontmatter 元数据（tags, channel, date, source_url, status）。
- **去重与本地缓存**：
  - 本地维护已处理视频的 SQLite 或 JSON 缓存索引。
  - 重复运行时自动跳过已成功生成的视频，避免重复消耗 Gemini Token 和带宽。

---

## 4. 命令行接口 (CLI) 设计

```bash
# 1. 总结单个视频
python -m summarizer summarize "https://www.youtube.com/watch?v=VIDEO_ID"

# 2. 批量处理频道最近 5 个视频
python -m summarizer channel "https://www.youtube.com/@AlgorithmTradingIn" --limit 5

# 3. 强制重新生成已缓存的视频
python -m summarizer summarize "https://www.youtube.com/watch?v=VIDEO_ID" --force

# 4. 生成或刷新全局/频道 INDEX 目录
python -m summarizer index
```

---

## 5. 技术选型与依赖

| 模块 | 推荐选型 | 说明 |
| :--- | :--- | :--- |
| **开发语言** | Python 3.10+ | 兼容性好，生态成熟 |
| **CLI 交互与展示** | `typer` + `rich` | 提供美观的终端交互、彩色日志与进度条 |
| **视频与字幕抓取** | `yt-dlp`, `youtube-transcript-api` | 稳定解析频道列表及 YouTube 字幕 |
| **LLM 客户端** | `google-genai` | 官方 Google Gemini 客户端 |
| **配置管理** | `pydantic-settings` / `pyyaml` | 支持 `.env` 和 `config.yaml` 灵活配置 |
| **本地缓存** | `sqlite3` 或 `json` | 轻量级本地去重与元数据持久化 |

---

## 6. 非功能性需求与安全性规范

1. **网络弹性**：针对 YouTube 访问可能存在的网络波动，具备重试机制与代理透传能力。
2. **凭据安全**：`GEMINI_API_KEY` 通过 `.env` 或环境变量注入，严禁硬编码至代码仓库。
3. **轻量与清洁**：下载的临时音频在转录完成后自动清理，避免占用本地磁盘。
