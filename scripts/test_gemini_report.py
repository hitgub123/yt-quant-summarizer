"""Manual Gemini smoke test.

This file intentionally does not call the API when imported or collected by
pytest. Run it explicitly when a real Gemini request is desired.
"""

import os
from pathlib import Path

from google import genai


def main() -> None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        env_file = Path(".env")
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("GEMINI_API_KEY="):
                    api_key = line.split("=", 1)[1].strip("\"'")
                    break
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is not configured.")

    video_url = "https://www.youtube.com/watch?v=hoi59k5zh1A"
    video_title = "Tesla (TSLA): ARK's Stock Stories"
    channel_name = "ARK Invest"
    prompt = f"""你是一名顶级买方量化基金投资总监与机构分析师。
请针对以下 YouTube 视频内容，撰写一份严格结构化的【7 维度机构级量化与交易策略研报】。

视频标题：{video_title}
视频链接：{video_url}
发布机构：{channel_name}

请输出标准 Markdown，包含核心投资观点、标的与市场环境、交易信号、风控、历史证据、回测实现示例和局限性。视频没有提供的数据必须明确标注，严禁捏造。
"""

    client = genai.Client(api_key=api_key)
    print(f"🚀 正在调用 Gemini 官方 API 生成研报: {video_title}...")
    response = client.models.generate_content(model="gemini-3.6-flash", contents=prompt)

    out_file = Path("output/ARK_Invest/2026-08-14_hoi59k5zh1A_Tesla_TSLA_ARKs_Stock_Stories.md")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(response.text or "", encoding="utf-8")
    print(f"🎉 成功生成真实量化研报！已保存至: {out_file}")
    print("\n" + "=" * 80)
    print((response.text or "")[:600])
    print("=" * 80)


if __name__ == "__main__":
    main()
