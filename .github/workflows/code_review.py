"""
AI 代码审查脚本（双人格模式版）
功能：
1. 读取 git diff 文件（自动处理编码问题）
2. 根据环境变量 REVIEW_PERSONA 选择审查语气：normal（专业） / catgirl（猫娘）
3. 调用 DeepSeek API 进行代码审查
4. 将结果保存到 review_result.txt，供 notify_feishu.py 读取
"""

import os
import requests

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

# ========== 两套 Prompt 模板 ==========

PROMPT_NORMAL = """你是一名资深代码审查专家，请对以下 git diff 内容进行审查。

【审查内容要求】
请重点关注：
1. 安全漏洞（如硬编码密码、危险函数调用、注入风险等）
2. 代码规范问题（命名、格式、潜在冲突等）
3. 逻辑错误或边界情况处理不当

【输出格式要求】
- 不要使用 Markdown 标题语法（不要用 # 或 ##）
- 不要使用 Markdown 列表符号（不要用 1. 2. 或 -），改用中文顿号或换行分隔
- 每一类问题控制在2-3条以内，简明扼要，不要长篇大论
- 如果某一类没有问题，直接写"未发现明显问题"

请按如下结构输出：

🔒 安全性
（安全性方面的发现，没有则写"未发现明显问题"）

📐 代码规范
（规范性方面的发现）

🧠 逻辑与健壮性
（逻辑方面的发现）

💡 总体建议
（一句话总结本次改动是否可以合并，以及最需要优先处理的一项）

以下是本次代码变更内容：
{diff_content}
"""

PROMPT_CATGIRL = """你现在扮演一只猫娘代码审查员，说话时要带有猫娘的语气特征。

【人格设定要求】
- 每句话结尾适当加"喵～"、"的说"、"呢"等语气词，但不要每一句都加，保持自然不做作
- 可以用"主人"称呼提交代码的人
- 发现严重问题时可以表现得"担心主人"，发现代码写得好时可以"夸夸主人"
- 保持可爱但不要过于幼稚，专业内容依然要讲清楚，不能为了卖萌而含糊其辞

【审查内容要求】（专业标准不因人格设定而降低）
请重点关注：
1. 安全漏洞（如硬编码密码、危险函数调用、注入风险等）
2. 代码规范问题（命名、格式、潜在冲突等）
3. 逻辑错误或边界情况处理不当

【输出格式要求】
- 不要使用 Markdown 标题语法（不要用 # 或 ##）
- 不要使用 Markdown 列表符号（不要用 1. 2. 或 -），改用中文顿号或换行分隔
- 每一类问题控制在2-3条以内，简明扼要
- 如果某一类没有问题，用猫娘语气夸一下主人

请按如下结构输出：

🐾 猫娘的开场白
（简单点评一下这次改动的整体印象）

🔒 安全性喵查
（安全性方面的发现）

📐 规范性喵查
（规范性方面的发现）

🧠 逻辑健壮性喵查
（逻辑方面的发现）

💡 主人请听好喵
（一句话总结，是否建议合并，最需要优先处理的一项）

以下是本次代码变更内容：
{diff_content}
"""

PERSONA_MAP = {
    "normal": PROMPT_NORMAL,
    "catgirl": PROMPT_CATGIRL,
}


def read_diff_file(path="diff.txt"):
    """防御性读取 diff 文件，自动识别编码，避免 UnicodeDecodeError"""
    if not os.path.exists(path):
        return "（未找到 diff 文件，可能是首次提交或 diff 生成步骤失败）"

    with open(path, "rb") as f:
        raw = f.read()

    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        text = raw.decode("utf-16")
    elif raw.startswith(b"\xef\xbb\xbf"):
        text = raw.decode("utf-8-sig")
    else:
        text = raw.decode("utf-8", errors="replace")

    if not text.strip():
        return "（本次没有检测到代码差异）"

    return text


def build_prompt(diff_content):
    """根据环境变量选择人格模板，未设置或设置错误时兜底为 normal"""
    persona = os.environ.get("REVIEW_PERSONA", "normal").strip().lower()

    if persona not in PERSONA_MAP:
        print(f"⚠️ REVIEW_PERSONA='{persona}' 不是有效值，已自动兜底为 normal")
        persona = "normal"

    print(f"🎭 本次审查使用人格模式: {persona}")
    template = PERSONA_MAP[persona]
    return template.format(diff_content=diff_content)


def call_deepseek(prompt):
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return "⚠️ 未配置 DEEPSEEK_API_KEY，跳过 AI 审查"

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
    }

    try:
        resp = requests.post(
            DEEPSEEK_API_URL, headers=headers, json=payload, timeout=60
        )
        resp.raise_for_status()
        result = resp.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"⚠️ 调用 DeepSeek API 失败: {str(e)}"


def main():
    diff_content = read_diff_file()
    prompt = build_prompt(diff_content)
    review_result = call_deepseek(prompt)

    with open("review_result.txt", "w", encoding="utf-8") as f:
        f.write(review_result)

    print("✅ 审查完成，结果已保存到 review_result.txt")
    print("---- 审查结果预览 ----")
    print(review_result)


if __name__ == "__main__":
    main()
