"""
【新增文件】飞书通知脚本
替代原来 workflow 里的 curl 命令，解决三个问题：
1. 消息带上 commit哈希/PR信息，避免"看起来重复"
2. 读取 review_result.txt，把AI审查结果带进消息
3. 用 github.event_name 区分 push 还是 pull_request
"""

import os
import requests


def read_review_result(path="review_result.txt", max_length=1500):
    """读取审查结果，自动识别编码，防止乱码或读取报错"""
    if not os.path.exists(path):
        return "⚠️ 未找到审查结果文件（审查步骤可能未执行或已失败）"

    with open(path, "rb") as f:
        raw = f.read()

    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        text = raw.decode("utf-16")
    elif raw.startswith(b"\xef\xbb\xbf"):
        text = raw.decode("utf-8-sig")
    else:
        text = raw.decode("utf-8", errors="replace")

    text = text.strip()
    if len(text) > max_length:
        text = text[:max_length] + "\n...(内容过长，完整结果请查看 Actions 日志)"

    return text or "（审查结果为空）"


def build_message():
    event_name = os.environ.get("EVENT_NAME", "unknown")
    job_status = os.environ.get("JOB_STATUS", "unknown")
    repo = os.environ.get("REPO", "")
    actor = os.environ.get("ACTOR", "")
    sha = os.environ.get("SHA", "")[:7]
    commit_msg = os.environ.get("COMMIT_MSG", "")
    pr_number = os.environ.get("PR_NUMBER", "")
    pr_title = os.environ.get("PR_TITLE", "")
    run_url = os.environ.get("RUN_URL", "")
    review = read_review_result()

    status_icon = "✅" if job_status == "success" else "❌"

    # 关键：区分 push 和 pull_request，展示不同的关键信息
    if event_name == "pull_request":
        trigger_line = f"📌 触发方式：Pull Request #{pr_number}\n📝 标题：{pr_title}"
    else:
        trigger_line = f"📌 触发方式：Push\n📝 提交信息：{commit_msg}"

    text = (
        f"{status_icon} CI Pipeline 状态: {job_status}\n"
        f"仓库: {repo}\n"
        f"提交者: {actor}\n"
        f"Commit: {sha}\n"
        f"{trigger_line}\n"
        f"\n📋 AI审查结果:\n{review}\n"
        f"\n🔗 详情: {run_url}"
    )
    return text


def send_to_feishu():
    webhook_url = os.environ.get("FEISHU_WEBHOOK_URL")
    if not webhook_url:
        print("⚠️ 未配置 FEISHU_WEBHOOK_URL，跳过通知")
        return

    payload = {"msg_type": "text", "content": {"text": build_message()}}

    resp = requests.post(webhook_url, json=payload)
    print(f"飞书返回状态码: {resp.status_code}")
    print(f"飞书返回内容: {resp.text}")


if __name__ == "__main__":
    send_to_feishu()
