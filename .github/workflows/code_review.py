"""
review_code.py
读取代码改动(diff)，调用 DeepSeek API 进行 Code Review，
并把审查结果写入 review_result.txt
"""

import os

print("当前工作目录是：", os.getcwd())


import os
import sys
import requests

# ============ 配置区 ============
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"  # 也可以用 deepseek-coder，代码任务更专精

DIFF_FILE = "diff.txt"
RESULT_FILE = "review_result.txt"

# diff 内容过长时的截断长度(避免超出模型上下文/浪费token)
MAX_DIFF_CHARS = 12000


def read_diff(file_path: str) -> str:
    """读取 diff 文件内容"""
    if not os.path.exists(file_path):
        print(f"❌ 找不到 diff 文件: {file_path}")
        sys.exit(1)

    # 尝试用二进制方式读取，自动判断编码，避免UnicodeDecodeError
    with open(file_path, "rb") as f:
        raw = f.read()

    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        # UTF-16编码（带BOM）
        content = raw.decode("utf-16")
    else:
        # utf-8-sig 能同时兼容"纯UTF-8"和"带BOM的UTF-8"
        content = raw.decode("utf-8-sig")

    if not content.strip():
        print("⚠️ diff 内容为空，本次没有代码改动，跳过审查")
        sys.exit(0)

    return content


def build_prompt(diff_content: str) -> str:
    """把diff内容拼接成给LLM的完整指令"""

    # 如果diff太长，做截断处理，避免浪费token或报错
    if len(diff_content) > MAX_DIFF_CHARS:
        diff_content = diff_content[:MAX_DIFF_CHARS] + "\n\n...(diff内容过长，已截断)"

    prompt = f"""你是一位资深的代码审查专家(Code Reviewer)，请审查以下 Git diff 中的代码改动。

请从以下几个角度进行审查:
1. **潜在Bug**: 是否存在逻辑错误、边界条件遗漏、空指针风险等
2. **代码规范**: 命名是否清晰、是否符合该语言的最佳实践
3. **安全隐患**: 是否存在硬编码密钥、SQL注入、未做输入校验等风险
4. **优化建议**: 是否有更简洁/高效的写法

请用简洁清晰的中文输出审查结果，按以下格式:

## 📋 审查总结
(一句话总体评价)

## ⚠️ 发现的问题
- 问题1: ...
- 问题2: ...
(如果没有问题，写"未发现明显问题")

## 💡 优化建议
- 建议1: ...

---

以下是本次代码改动的 diff 内容:

```diff
{diff_content}
```
"""
    return prompt


def call_deepseek(prompt: str, api_key: str) -> str:
    """调用 DeepSeek API 获取审查结果"""

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": "你是一个专业、严谨、有帮助的代码审查助手。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,  # 审查任务需要严谨，温度调低
        "max_tokens": 1500,
    }

    response = requests.post(
        DEEPSEEK_API_URL, headers=headers, json=payload, timeout=60
    )

    if response.status_code != 200:
        print(f"❌ DeepSeek API 调用失败: {response.status_code}")
        print(response.text)
        sys.exit(1)

    result = response.json()
    review_text = result["choices"][0]["message"]["content"]
    return review_text


def main():
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ 未找到环境变量 DEEPSEEK_API_KEY，请先设置")
        sys.exit(1)

    print("📖 正在读取代码改动...")
    diff_content = read_diff(DIFF_FILE)

    print("✍️ 正在生成审查Prompt...")
    prompt = build_prompt(diff_content)

    print("🤖 正在调用 DeepSeek 进行代码审查(请稍候)...")
    review_result = call_deepseek(prompt, api_key)

    print("✅ 审查完成，结果如下:\n")
    print(review_result)

    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        f.write(review_result)

    print(f"\n💾 审查结果已保存到 {RESULT_FILE}")


if __name__ == "__main__":
    main()
