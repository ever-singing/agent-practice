"""
飞书通知脚本 v2
改动点：
1. msg_type 从 text 改为 interactive（卡片消息），让 **加粗** 能正常渲染
2. 用卡片的分栏结构，把"基础信息"和"审查结果"视觉上分开，不再挤成一坨
3. 消息总长度做统一截断保护，避免超出飞书限制导致发送失败
4. 环境变量读取加默认值兜底，避免出现 "None" 字样
"""

import os
import requests

FEISHU_TEXT_LIMIT = 3500  # 留出余量，飞书官方上限约4096字符


def read_review_result(path="review_result.txt"):
    """读取审查结果，自动识别编码"""
    if not os.path.exists(path):
        return "⚠️ 未找到审查结果文件（审查步骤可能未执行或失败）"

    with open(path, "rb") as f:
        raw = f.read()

    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        text = raw.decode("utf-16")
    elif raw.startswith(b"\xef\xbb\xbf"):
        text = raw.decode("utf-8-sig")
    else:
        text = raw.decode("utf-8", errors="replace")

    return text.strip() or "（审查结果为空）"


def safe_env(key, default=""):
    """统一处理环境变量，避免出现字符串 'None'"""
    value = os.environ.get(key, default)
    if value is None or value.strip().lower() == "none":
        return default
    return value


def build_card_payload():
    event_name = safe_env("EVENT_NAME", "push")
    job_status = safe_env("JOB_STATUS", "unknown")
    repo = safe_env("REPO")
    actor = safe_env("ACTOR")
    sha = safe_env("SHA")[:7]
    commit_msg = safe_env("COMMIT_MSG", "（无提交信息）")
    pr_number = safe_env("PR_NUMBER")
    pr_title = safe_env("PR_TITLE")
    run_url = safe_env("RUN_URL")
    review = read_review_result()

    status_icon = "✅" if job_status == "success" else "❌"
    is_pr = event_name == "pull_request"

    # 卡片头部颜色 + 标题：PR用蓝色，push用绿色，一眼区分
    template_color = "blue" if is_pr else "green"
    header_title = f"{status_icon} CI Pipeline【{'Pull Request' if is_pr else 'Push'}】"

    # 触发信息行
    if is_pr:
        trigger_info = (
            f"**触发方式**：Pull Request #{pr_number}\n**PR标题**：{pr_title}"
        )
    else:
        trigger_info = f"**触发方式**：Push\n**提交信息**：{commit_msg}"

    base_info = (
        f"**仓库**：{repo}\n"
        f"**操作人**：{actor}\n"
        f"**Commit**：`{sha}`\n"
        f"{trigger_info}"
    )

    # 控制总长度，优先保证基础信息完整，压缩审查结果部分
    reserved = len(base_info) + 300  # 给标题/链接/分隔符预留空间
    max_review_len = max(FEISHU_TEXT_LIMIT - reserved, 200)
    if len(review) > max_review_len:
        review = (
            review[:max_review_len] + "\n\n...(内容过长，完整结果请查看 Actions 日志)"
        )

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": header_title},
                "template": template_color,
            },
            "elements": [
                {"tag": "markdown", "content": base_info},
                {"tag": "hr"},
                {"tag": "markdown", "content": f"**📋 AI审查结果**\n\n{review}"},
                {"tag": "hr"},
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "查看完整日志"},
                            "url": run_url,
                            "type": "primary",
                        }
                    ],
                },
            ],
        },
    }
    return payload


def send_to_feishu():
    webhook_url = os.environ.get("FEISHU_WEBHOOK_URL")
    if not webhook_url:
        print("⚠️ 未配置 FEISHU_WEBHOOK_URL，跳过通知")
        return

    resp = requests.post(webhook_url, json=build_card_payload())
    print(f"飞书返回状态码: {resp.status_code}")
    print(f"飞书返回内容: {resp.text}")


if __name__ == "__main__":
    send_to_feishu()
