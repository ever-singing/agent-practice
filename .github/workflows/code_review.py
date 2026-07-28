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

    prompt = """你是一名资深代码审查专家，请对以下 git diff 内容进行审查。

【审查内容要求】（这部分不变，原样保留）
请重点关注：
1. 安全漏洞（如硬编码密码、危险函数调用、注入风险等）
2. 代码规范问题（命名、格式、潜在冲突等）
3. 逻辑错误或边界情况处理不当

【输出格式要求】（新增，专门适配飞书消息展示）
请严格按以下格式输出，注意：
- 不要使用 Markdown 标题语法（不要用 # 或 ##）
- 不要使用 Markdown 列表符号（不要用 1. 2. 或 -），改用中文顿号或换行分隔
- 可以使用少量emoji作为分类标记，替代标题的作用
- 每一类问题控制在2-3条以内，简明扼要，不要长篇大论
- 如果某一类没有问题，直接写"未发现明显问题"，不要跳过这个分类

请按如下结构输出：

🔒 安全性
（这里写安全性方面的发现，没有则写"未发现明显问题"）

📐 代码规范
（这里写规范性方面的发现）

🧠 逻辑与健壮性
（这里写逻辑方面的发现）

💡 总体建议
（一句话总结本次改动是否可以合并，以及最需要优先处理的一项）

以下是本次代码变更内容：
{diff_content}
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
