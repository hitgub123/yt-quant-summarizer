import os
from google import genai

with open(".env") as f:
    for line in f:
        if line.startswith("GEMINI_API_KEY="):
            api_key = line.strip().split("=", 1)[1].strip("\"'")

client = genai.Client(api_key=api_key)

print("🚀 正在通过 Google 官方 SDK 测试 API Key...")
try:
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents="你好，请回复一句：Gemini 官方 SDK 验证成功！",
    )
    print("🎉 响应内容:", response.text.strip())
    print("✅ 验证结论：您的 GEMINI_API_KEY 完全有效可用！")
except Exception as e:
    print("❌ 异常:", e)
