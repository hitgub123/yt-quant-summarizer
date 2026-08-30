import os
from google import genai

with open(".env") as f:
    for line in f:
        if line.startswith("GEMINI_API_KEY="):
            api_key = line.strip().split("=", 1)[1].strip("\"'")

client = genai.Client(api_key=api_key)

models_to_test = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-pro-exp-02-05",
]

print("🔍 正在测试各个模型的免费可用性与配额...", flush=True)
for m in models_to_test:
    try:
        resp = client.models.generate_content(
            model=m,
            contents="回复1个词：OK",
        )
        print(f"✅ 模型 [{m}]: 调用成功！响应: {resp.text.strip()}", flush=True)
    except Exception as e:
        err_msg = str(e)
        if "429" in err_msg:
            print(f"⚠️ 模型 [{m}]: 429 配额限制", flush=True)
        elif "404" in err_msg or "not found" in err_msg.lower():
            print(f"❌ 模型 [{m}]: 模型不存在或已下线", flush=True)
        else:
            print(f"❌ 模型 [{m}]: 异常 -> {err_msg[:100]}", flush=True)
