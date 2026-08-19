# 📈 yt-quant-summarizer: YouTube 量化投资研报知识库生成器

**yt-quant-summarizer** 是一款专为量化交易研究员、策略开发者及投资学习者打造的自动化研报提炼与知识归档工具。

只需输入任意 YouTube 量化/投资 UP 主的首页链接（如 `https://m.youtube.com/@AlgorithmTradingIn`），程序即可自动扫描全频道视频、**智能筛选出所有与投资/交易相关的视频**、秒级提取字幕或语音，并调用 **Google Gemini 2.5** 进行 7 大维度深度提炼与代码复现，按视频生成结构化 Markdown 研报并自动建立 Obsidian/Notion 知识库索引。

---

## 🌟 核心特性

- 🎯 **一键扫描 UP 主频道全量投资视频**：
  - 支持直接输入 UP 主主页 URL（例如 `https://www.youtube.com/@AlgorithmTradingIn`），默认自动获取频道**全部**视频。
  - 内置中英文量化与金融多语种分类器，自动识别并**过滤非投资类的生活/闲聊视频**，精准提炼投资硬核内容。
- 📊 **7 维度量化专属研报**：
  1. **视频基础信息与核心论点**（元数据概览 + 200字精炼摘要）
  2. **核心理念与策略逻辑**（Alpha 来源、盈利假说、适用/失效市场环境）
  3. **指标与数学公式**（标准 LaTeX 公式渲染、参数含义、计算步骤）
  4. **交易与风控规则速查**（做多/做空进出场、止损止盈、资金管理与仓位规则表）
  5. **Python 策略代码实现**（符合 pandas/numpy 规范的策略逻辑与向量化回测代码）
  6. **回测评估与实盘局限性**（过拟合风险、滑点/手续费摩擦、前视偏差防范）
  7. **时间戳重点导航**（核心观点与章节时间锚点直链）
- 🚀 **混合文稿转录引擎 (Hybrid Transcript Engine)**：
  - **秒级字幕提取**：优先调用 YouTube 原生/多语言自动字幕 API，无需下载视频与音频，极速省流。
  - **音频理解兜底**：无字幕视频自动轻量下载音频，交由 Google Gemini 多模态音频理解能力精准转录。
- 📚 **Obsidian & Notion 知识库友好**：
  - 每篇研报均包含标准 YAML Frontmatter（tags, channel, date, source_url 等）。
  - 自动维护全局 `output/INDEX.md` 与分频道 `output/<Channel>/INDEX.md` 索引目录。
- ⚡ **本地 SQLite 缓存与增量同步**：
  - 自动跳过已处理视频，避免重复消耗 Gemini Token 与网络带宽；支持 `--force` 重新生成。
- 🛡️ **网络弹性与高可用重试**：
  - 针对 Gemini API 及网络请求提供指数退避重试（Exponential Backoff），保障大批量处理百余个视频时不中断。
  - 完整支持 HTTP / SOCKS5 代理配置（支持 `.env`、环境变量及命令行参数 `--proxy`）。

---

## 🛠️ 安装与配置

### 1. 克隆与安装依赖

```bash
git clone https://github.com/your-repo/yt-quant-summarizer.git
cd yt-quant-summarizer

# 创建并激活虚拟环境
python3 -m venv .venv
source .venv/bin/activate  # Linux / macOS / WSL

# 安装依赖
pip install -r requirements.txt
pip install -e .
```

### 2. 配置环境变量

复制 `.env.example` 并重命名为 `.env`，填入你的 Google Gemini API Key：

```bash
cp .env.example .env
```

`.env` 示例配置：
```env
# Google Gemini API Key (必需)
GEMINI_API_KEY=AIzaSy...

# Gemini 模型选择 (默认 gemini-2.5-flash)
GEMINI_MODEL=gemini-2.5-flash

# 网络代理 (可选，国内网络环境推荐)
# HTTP_PROXY=http://127.0.0.1:7890
# HTTPS_PROXY=http://127.0.0.1:7890

# 研报输出根目录
OUTPUT_DIR=output
```

---

## 📖 快速上手

### 1. 批量分析 UP 主频道的所有投资视频（最常用）

只需传入 UP 主首页链接，程序将自动扫描并分析该频道**所有**投资相关视频：

```bash
python -m summarizer channel "https://www.youtube.com/@AlgorithmTradingIn"
```

> **参数说明**：
> - `--limit N` (或 `-n N`): 限制仅处理最新的 N 个视频（例如 `-n 5`）。不填则处理频道全量视频。
> - `--all-videos` (或 `-a`): 强制处理全部视频，不过滤非投资视频。
> - `--force` (或 `-f`): 强制重新生成已缓存的研报。

### 2. 总结单个量化视频

```bash
python -m summarizer summarize "https://www.youtube.com/watch?v=6HVkYX298qM"
```

### 3. 刷新与重建索引目录

```bash
python -m summarizer index
```

### 4. 查看知识库处理状态

```bash
python -m summarizer status
```

---

## 🐍 Python 代码调用 (API)

除 CLI 命令行外，你也可以在自己的 Python 脚本中直接调用：

```python
from summarizer import QuantSummarizer

# 初始化量化总结器
pipeline = QuantSummarizer()

# 1. 一键分析 UP 主首页所有投资视频
result = pipeline.summarize_channel(
    "https://www.youtube.com/@AlgorithmTradingIn",
    limit=10,               # 可选：限制视频数量，None 则处理全部
    filter_investment=True  # 智能筛选投资相关视频
)

print(f"已完成: {len(result['completed'])} 篇研报")
print(f"总索引文件: {result['global_index']}")

# 2. 分析单个视频
record, report_path = pipeline.summarize_video("https://www.youtube.com/watch?v=6HVkYX298qM")
print(f"研报生成至: {report_path}")
```

---

## 📁 目录组织结构

生成的研报与索引结构如下：

```text
output/
├── INDEX.md                        # 🌐 全局知识库研报总索引
└── AlgorithmTradingIn/             # 📺 UP主频道专属知识库
    ├── INDEX.md                    # 📑 该频道的研报索引
    ├── 2024-03-15_Risk_Management.md   # 📝 具体视频量化研报 (含 7 维度与 YAML Frontmatter)
    ├── 2024-03-20_Building_Algo.md
    └── ...
```

---

## 🧪 运行测试

```bash
pytest tests/ -v
```

---

## 📄 License
MIT License