"""
AI 代码审查脚本（双人格模式版 v2）
本轮修复：
1. 提取公共的"输出格式要求"常量，避免两套 Prompt 重复维护
2. VERBOSE 开关控制日志输出，避免 CI 环境产生多余打印
3. diff 为空/文件不存在时返回 None，main 里做空值判断，不再拼接中文提示误导 AI
4. temperature 改回 0.3，保证审查结果的稳定性和严谨性
"""

import os
import requests

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
VERBOSE = os.environ.get("VERBOSE", "true").strip().lower() != "false"

# ========== 公共的输出格式要求（两套人格共用，改一处即可） ==========

OUTPUT_FORMAT_RULES = """【输出格式要求】
- 不要使用 Markdown 标题语法（不要用 # 或 ##）
- 不要使用 Markdown 列表符号（不要用 1. 2. 或 -），改用中文顿号或换行分隔
- 每一类问题控制在2-3条以内，简明扼要，不要长篇大论
"""

# ========== 两套 Prompt 模板 ==========

PROMPT_NORMAL = """你是一名资深代码审查专家，请对以下 git diff 内容进行审查。

【审查内容要求】
请重点关注：
1. 安全漏洞（如硬编码密码、危险函数调用、注入风险等）
2. 代码规范问题（命名、格式、潜在冲突等）
3. 逻辑错误或边界情况处理不当

{format_rules}
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

{format_rules}
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


def log(msg):
    """受 VERBOSE 开关控制的打印函数"""
    if VERBOSE:
        print(msg)


def read_diff_file(path="diff.txt"):
    """
    防御性读取 diff 文件，自动识别编码。
    找不到文件或内容为空时返回 None（而不是中文提示字符串），
    避免这段中文被误当成代码内容拼进 prompt，误导 AI 判断。
    """
    if not os.path.exists(path):
        log(f"⚠️ 未找到 diff 文件: {path}")
        return None

    with open(path, "rb") as f:
        raw = f.read()

    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        text = raw.decode("utf-16")
    elif raw.startswith(b"\xef\xbb\xbf"):
        text = raw.decode("utf-8-sig")
    else:
        text = raw.decode("utf-8", errors="replace")

    if not text.strip():
        log("⚠️ diff 文件内容为空")
        return None

    return text


def build_prompt(diff_content):
    """根据环境变量选择人格模板，未设置或设置错误时兜底为 normal"""
    persona = os.environ.get("REVIEW_PERSONA", "normal").strip().lower()

    if persona not in PERSONA_MAP:
        log(f"⚠️ REVIEW_PERSONA='{persona}' 不是有效值，已自动兜底为 normal")
        persona = "normal"

    log(f"🎭 本次审查使用人格模式: {persona}")
    template = PERSONA_MAP[persona]
    return template.format(format_rules=OUTPUT_FORMAT_RULES, diff_content=diff_content)


def call_deepseek(prompt):
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return "⚠️ 未配置 DEEPSEEK_API_KEY，跳过 AI 审查"

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,  # 审查任务需要稳定、严谨，不需要"创造力"
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

    if diff_content is None:
        # 关键修复：diff 为空时，不再拼接中文提示去调用 AI，直接给出结果，节省一次 API 调用
        review_result = (
            "ℹ️ 本次未检测到代码差异，跳过 AI 审查（可能是首次提交或无实际改动）"
        )
        log(review_result)
    else:
        prompt = build_prompt(diff_content)
        review_result = call_deepseek(prompt)

    with open("review_result.txt", "w", encoding="utf-8") as f:
        f.write(review_result)

    log("✅ 审查完成，结果已保存到 review_result.txt")
    log("---- 审查结果预览 ----")
    log(review_result)


if __name__ == "__main__":
    main()
