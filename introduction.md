# GitHub Webhook + ngrok + Flask 自动化通知系统

## 项目完整知识文档

```markdown
# GitHub → Flask → 飞书 自动通知系统搭建笔记

> 记录日期：2026年7月27日
> 目标：实现 GitHub 代码推送后，自动通知到本地程序，并转发到飞书

---

## 一、整体架构图
```

本地开发者 git push

↓

GitHub 仓库

↓ (触发 Webhook)

POST 请求 (JSON数据)

↓

ngrok 隧道 (外网 → 内网穿透)

↓

本地 Flask 服务器 (step2.py, 端口5000)

↓ (解析JSON，提取字段)

终端打印 + 转发飞书机器人

````

**核心价值**：让外部系统（GitHub）的事件，能够触达运行在自己电脑上、原本无法被外网访问的程序。

---

## 二、核心组件说明

### 1. Flask 本地服务器 (step2.py)

**作用**：接收 HTTP POST 请求，解析数据，做相应处理。

**最终版核心代码逻辑**：

```python
from flask import Flask, request

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def receive_data():
    # 关键：先判断事件类型，再决定怎么处理
    event_type = request.headers.get('X-GitHub-Event')
    data = request.json

    print(f"收到了一个【{event_type}】类型的事件")

    if event_type == 'ping':
        # GitHub连接测试请求，结构简单，无repository等字段
        print("这是GitHub发来的测试请求，说明连接成功了！")
        return "pong收到，连接测试成功！"

    if event_type == 'push':
        # 真实代码推送事件，才有完整字段
        repo_name = data['repository']['name']
        pusher_name = data['pusher']['name']
        commit_msg = data['head_commit']['message']
        print(f"【{pusher_name}】在项目【{repo_name}】提交了：{commit_msg}")
        return "推送事件处理完成！"

    # 兜底：其他类型事件先记录，不报错
    print("暂时还没处理这种类型的事件")
    return "收到，但暂未处理"

app.run(port=5000)
````

**关键点**：

- `@app.route('/webhook', methods=['POST'])`：定义一个只接受 POST 请求的接口地址
- `request.json`：自动把请求体的 JSON 字符串，解析成 Python 字典
- `request.headers.get('X-GitHub-Event')`：读取请求头，判断这次事件的类型

---

### 2. ngrok（内网穿透工具）

**作用**：把本地 `127.0.0.1:5000`（只有自己电脑能访问），映射成一个外网能访问的公开网址。

**启动命令**：

```bash
ngrok http 5000
```

**运行后会显示**：

```
Forwarding: https://xxxx-xxxx.ngrok-free.dev -> http://localhost:5000
```

这个 `https://xxxx.ngrok-free.dev` 就是外网可访问的临时地址。

---

### 3. GitHub Webhook 配置

**位置**：仓库页面 → `Settings` → `Webhooks` → `Add webhook`

| 字段         | 填写内容                                       |
| ------------ | ---------------------------------------------- |
| Payload URL  | `https://你的ngrok地址.ngrok-free.dev/webhook` |
| Content type | `application/json`                             |
| Secret       | 可选，用于安全验证（进阶功能）                 |
| 触发事件     | 先选 `Just the push event`                     |
| Active       | 保持勾选                                       |

**极其重要的一点**：⚠️ **Webhook 是绑定在"具体某一个仓库"上的**，不是全局生效。在哪个仓库配置的 Webhook，只有那个仓库发生 push 才会触发通知，在别的仓库操作不会有任何反应。

---

## 三、踩过的坑 & 解决方案

### 坑1：ngrok 免费版网址每次重启都会变

**现象**：关掉重启 ngrok 后，生成的网址完全不同。

**影响**：之前在 GitHub 配置的 Webhook 网址会失效，需要手动去改。

**解决方案**：

- 学习阶段：每次重启后，去 GitHub 仓库 Webhook 设置里，手动更新一下 Payload URL
- 长期使用：申请 ngrok 付费版的固定域名（Static Domain）

---

### 坑2：GitHub 的 ping 事件 导致 500 报错

**现象**：Webhook 刚配置好，GitHub 自动发送一次 `ping` 测试请求，但 Flask 报 500 Internal Server Error。

**原因**：

- `ping` 事件的 JSON 数据结构里，**没有** `repository`、`pusher`、`head_commit` 这些字段
- 代码却直接尝试读取 `data['repository']['name']`，导致 `KeyError`

**解决方案**：

- 先通过请求头 `X-GitHub-Event` 判断"这是什么类型的事件"
- 针对不同事件类型分别处理，`ping` 事件简单返回即可，不要尝试读取不存在的字段

**这是一个通用的编程思维**：处理外部系统传来的数据时，不能假设数据结构永远一致，要先做类型判断，再决定怎么取值。

---

### 坑3：在错误的仓库里 push，代码毫无反应

**现象**：配置好 Webhook 后，在另一个仓库 push 代码，本地终端毫无动静。

**原因**：Webhook 是仓库级别的订阅，配置在 A 仓库，B 仓库的操作不会触发它。

**解决方案**：

- 确认本地终端所在文件夹对应的仓库，和 GitHub 网页上配置 Webhook 的仓库，是否一致
- 用命令 `git remote -v` 查看当前文件夹绑定的远程仓库地址，核对仓库名是否匹配

---

## 四、调试排查技巧

### 1. GitHub 端排查："Recent Deliveries"

在 Webhook 详情页面，能看到每一次投递记录：

- ✅ 绿色：请求成功送达并被处理
- ❌ 红色：请求失败，点开可看具体报错原因

支持点击 **Redeliver**（重新发送），无需重新 push 代码即可重复测试。

### 2. 本地端排查：终端日志

Flask 运行的终端窗口，会实时打印：

- 每一次收到的请求（状态码 200 表示成功接收，500 表示处理报错）
- 你在代码里用 `print()` 打印的自定义调试信息

---

## 五、当前已实现的功能清单

- [x] 本地 Flask 服务器接收 HTTP POST 请求
- [x] ngrok 实现内网穿透，外网可访问本地服务
- [x] GitHub Webhook 正确配置，绑定到指定仓库
- [x] 正确处理 `ping` 事件（连接测试），不再报错
- [x] 正确解析 `push` 事件，提取仓库名、推送人、提交信息
- [x] 将解析结果转发到飞书机器人，实现即时通知

---

## 六、后续可优化方向

1. **消息美化**：将纯文本通知改成飞书卡片消息，支持链接、颜色、按钮等更丰富的展示
2. **安全性增强**：给 Webhook 配置 Secret 密钥，Flask 端做签名校验，防止伪造请求
3. **支持更多事件类型**：目前只处理了 push，可扩展处理 issues（提问）、pull_request（合并请求）等
4. **稳定性提升**：目前依赖本机 + ngrok 常开，后续可考虑部署到云服务器，实现 7x24 小时稳定运行
5. **固定域名**：申请 ngrok 付费静态域名，或使用其他内网穿透方案，避免每次重启都要重新配置 Webhook 地址

---

## 七、关键术语速查表

| 术语              | 含义                                                             |
| ----------------- | ---------------------------------------------------------------- |
| Webhook           | 一种"事件通知"机制，某个动作发生时，自动向指定网址发送 HTTP 请求 |
| ngrok             | 内网穿透工具，把本地服务映射到外网可访问的地址                   |
| Flask             | Python 的轻量级 Web 框架，用于快速搭建接收请求的服务器           |
| Payload           | Webhook 请求携带的具体数据内容（通常是 JSON 格式）               |
| ping 事件         | GitHub 配置 Webhook 后自动发送的连接测试请求                     |
| push 事件         | 代码真实推送到仓库时触发的事件                                   |
| Recent Deliveries | GitHub Webhook 详情页里的历史投递记录，用于排查问题              |
| X-GitHub-Event    | HTTP 请求头字段，标识本次 Webhook 请求的事件类型                 |

```
