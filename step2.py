from flask import Flask, request

app = Flask(__name__)


@app.route("/webhook", methods=["POST"])
def receive_data():
    # 先看看这次是什么类型的事件
    event_type = request.headers.get("X-GitHub-Event")
    data = request.json

    print(f"收到了一个【{event_type}】类型的事件")

    if event_type == "ping":
        print("这是GitHub发来的测试请求，说明连接成功了！")
        return "pong收到，连接测试成功！"

    if event_type == "push":
        repo_name = data["repository"]["name"]
        pusher_name = data["pusher"]["name"]
        commit_msg = data["head_commit"]["message"]
        print(f"【{pusher_name}】在项目【{repo_name}】提交了：{commit_msg}")
        return "推送事件处理完成！"

    # 其他类型的事件，先不处理，只打个日志
    print("暂时还没处理这种类型的事件")
    return "收到，但暂未处理"


app.run(port=5000)
