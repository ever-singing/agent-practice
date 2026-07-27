# GitHub Webhook + ngrok + Flask + AI 代码审查 自动化系统

## 项目完整知识文档

> 记录日期：2026年7月27日
> 目标：实现 GitHub 代码推送后，自动通知到本地程序并转发飞书；同时打通 GitHub Actions，让每一次提交都能自动接受 AI 代码审查，并将结果同步到飞书

---

## 一、整体架构图

本项目包含两条并行的自动化链路：**本地实时通知链路** 和 **CI/CD 智能审查链路**。

### 链路一：本地 Webhook 实时通知

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
```

**核心价值**：让外部系统（GitHub）的事件，能够触达运行在自己电脑上、原本无法被外网访问的程序。

### 链路二：GitHub Actions AI 代码审查（CI/CD）

```
开发者 git push / 发起 Pull Request
      ↓
GitHub Actions 自动触发（ubuntu-latest 云端环境）
      ↓
拉取代码 + 安装依赖
      ↓
生成 git diff（对比 base/head 分支或前后 commit）
      ↓
调用 DeepSeek API 对 diff 内容进行代码审查
      ↓
审查结果保存为 review_result.txt
      ↓
审查结果 + CI 状态 一并推送到飞书
```

**核心价值**：不再依赖人工肉眼审查每一次提交，而是让 AI 在代码合入前，自动识别安全漏洞、逻辑问题和代码规范风险，并第一时间同步到团队沟通渠道。

两条链路的共同底层逻辑是一致的：**利用 Webhook / Actions 机制，把 GitHub 上发生的事件，自动转化为可执行的后续动作（本地处理 或 云端审查），并最终以飞书通知的形式闭环。**

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
```

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

### 4. GitHub Actions 工作流 (.github/workflows/test.yml)

**作用**：在 GitHub 云端环境中自动执行 CI 测试 + AI 代码审查 + 飞书通知，无需依赖本地机器保持在线。

**核心配置要点**：

```yaml
- name: Checkout code
  uses: actions/checkout@v4
  with:
    fetch-depth: 0 # 关键：拉取完整历史，否则 git diff 对比不出结果

- name: Generate diff
  run: |
    git diff origin/${{ github.base_ref }} origin/${{ github.head_ref }} --output=diff.txt || echo "diff generation failed" > diff.txt

- name: 运行 AI 代码审查
  env:
    DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
  run: python code_review.py

- name: 发送飞书通知
  if: always() # 关键：无论审查/测试成功与否，都要通知
  env:
    FEISHU_WEBHOOK_URL: ${{ secrets.FEISHU_WEBHOOK_URL }}
  run: python notify_feishu.py
```

**关键点**：

- `secrets.DEEPSEEK_API_KEY` / `secrets.FEISHU_WEBHOOK_URL`：敏感信息存放在 GitHub Repository Secrets 中，不会出现在代码或日志里，安全性和本地 `.env` 文件是同一思路，只是换到了云端
- `fetch-depth: 0`：Actions 默认只拉取最近一次提交（浅克隆），如果不加这个参数，`git diff` 大概率会因为找不到对比分支而失败
- `pull_request` 事件下对比的是两个分支（`base_ref` vs `head_ref`）；`push` 事件下需要对比前后两次 commit，逻辑略有不同，需要在 workflow 里做区分处理
- `if: always()`：保证飞书通知这一步，即使前面的审查或测试步骤失败/报错，也一定会执行，不会出现"CI 挂了却没人知道"的情况

---

### 5. code_review.py（AI 代码审查脚本）

**作用**：读取 `git diff` 生成的差异文件，调用 DeepSeek API，让 AI 对本次改动进行代码审查，并将结果落盘保存。

**核心处理逻辑**：

```python
def read_diff_file(path='diff.txt'):
    # 防御性读取：先以二进制方式读取，再根据 BOM 头自动判断编码
    with open(path, 'rb') as f:
        raw = f.read()

    if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
        text = raw.decode('utf-16')
    elif raw.startswith(b'\xef\xbb\xbf'):
        text = raw.decode('utf-8-sig')
    else:
        text = raw.decode('utf-8', errors='replace')

    return text
```

**关键点**：

- 审查结果会保存到 `review_result.txt`，供后续步骤读取并转发到飞书
- Prompt 设计上重点关注：**安全漏洞（硬编码密码、危险函数调用）、代码规范（命名冲突）、CI/CD 配置本身的风险**，实测下来 DeepSeek 对这几类问题的识别率相当高

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

### 坑4：Windows 本地生成的 diff 文件，Python 读取时报 UnicodeDecodeError

**现象**：在 Windows 上用 PowerShell 执行 `git diff > diff.txt` 生成差异文件，再用 Python 的 `open()` 读取时，直接抛出 `UnicodeDecodeError`。

**原因**：

- Git 本身输出的是 UTF-8 编码内容
- 但 PowerShell 的 `>` 重定向符，会把输出重新转码成 UTF-16 或 GBK，导致 Python 默认按 UTF-8 解码时直接失败

**解决方案**：

- **规范化生成方式**：改用 `git diff --output=diff.txt` 参数直接生成文件，绕开 PowerShell 重定向的转码干扰
- **防御性读取**：Python 端改为二进制模式读取文件，先检测文件开头的 BOM 头，据此判断是 UTF-8 还是 UTF-16，再进行相应解码，代码见上文 `code_review.py` 部分
- **换到 Linux 环境后问题自动消失**：GitHub Actions 使用 `ubuntu-latest` 运行环境，本身对 UTF-8 支持良好，不存在 Windows 特有的编码转换问题，这也是把审查流程迁移到云端 CI 的一个附带好处

---

### 坑5：git diff 在 Actions 里因为浅克隆而失败

**现象**：本地手动跑 `git diff` 一切正常，但放到 GitHub Actions 里，同样的命令却提示找不到对比的分支或 commit。

**原因**：`actions/checkout` 默认只拉取最近一次提交（浅克隆），历史记录不完整，导致 `git diff` 找不到用来对比的另一端。

**解决方案**：

- 在 `actions/checkout` 步骤里加上 `fetch-depth: 0`，拉取完整的提交历史
- 同时针对"仓库刚创建、只有一次提交"这种边界情况做兜底处理（比如用 `||` 接一个默认的错误提示文本，而不是让整个 workflow 直接失败）

---

## 四、调试排查技巧

### 1. GitHub 端排查："Recent Deliveries"（Webhook 场景）

在 Webhook 详情页面，能看到每一次投递记录：

- ✅ 绿色：请求成功送达并被处理
- ❌ 红色：请求失败，点开可看具体报错原因

支持点击 **Redeliver**（重新发送），无需重新 push 代码即可重复测试。

### 2. 本地端排查：终端日志

Flask 运行的终端窗口，会实时打印：

- 每一次收到的请求（状态码 200 表示成功接收，500 表示处理报错）
- 你在代码里用 `print()` 打印的自定义调试信息

### 3. GitHub Actions 端排查："Actions" 标签页日志（CI/CD 场景）

仓库页面 → `Actions` 标签 → 点开对应的一次运行记录，可以逐步查看每一个 step 的详细日志：

- 每个 step 前面有 ✅ / ❌ 标识，一眼看出哪一步失败
- 点开具体某一步，能看到完整的命令输出（比如 diff 内容、DeepSeek 返回的原始审查结果）
- 支持在 workflow 文件修改后重新触发一次运行，反复调试 Prompt 或脚本逻辑

---

## 五、当前已实现的功能清单

**本地 Webhook 通知链路**

- [x] 本地 Flask 服务器接收 HTTP POST 请求
- [x] ngrok 实现内网穿透，外网可访问本地服务
- [x] GitHub Webhook 正确配置，绑定到指定仓库
- [x] 正确处理 `ping` 事件（连接测试），不再报错
- [x] 正确解析 `push` 事件，提取仓库名、推送人、提交信息
- [x] 将解析结果转发到飞书机器人，实现即时通知

**CI/CD AI 代码审查链路**

- [x] GitHub Actions 自动触发（支持 `push` 和 `pull_request` 两种场景）
- [x] 自动生成 `git diff`，并妥善处理编码问题（BOM 检测 + 自动解码）
- [x] 敏感信息（DeepSeek API Key、飞书 Webhook 地址）通过 GitHub Secrets 安全存储
- [x] 调用 DeepSeek API 对代码改动进行安全性、规范性、逻辑问题审查
- [x] 审查结果落盘保存为 `review_result.txt`
- [x] 无论 CI 是否通过，均通过 `if: always()` 保证飞书能收到状态通知
- [x] 在新分支上完成集成测试，验证了完整链路的可用性

---

## 六、后续可优化方向

**本地 Webhook 通知链路**

1. **消息美化**：将纯文本通知改成飞书卡片消息，支持链接、颜色、按钮等更丰富的展示
2. **安全性增强**：给 Webhook 配置 Secret 密钥，Flask 端做签名校验，防止伪造请求
3. **支持更多事件类型**：目前只处理了 push，可扩展处理 issues（提问）、pull_request（合并请求）等
4. **稳定性提升**：目前依赖本机 + ngrok 常开，后续可考虑部署到云服务器，实现 7x24 小时稳定运行
5. **固定域名**：申请 ngrok 付费静态域名，或使用其他内网穿透方案，避免每次重启都要重新配置 Webhook 地址

**CI/CD AI 代码审查链路**

6. **Prompt 精细化调优**：目前审查结果虽然已经能精准识别硬编码密码、`eval()` 注入等严重问题，下一步可以让输出更结构化（比如按"安全性 / 性能 / 代码规范"分类），便于后续做解析和统计
7. **审查结果回评到 PR**：目前审查结果只存在 `review_result.txt` 里，需要去 Actions 日志查看，后续可以调用 GitHub API，把审查意见自动评论到 PR 页面下方，方便开发者第一时间在合入前看到
8. **飞书通知内容升级**：目前飞书只推送 CI 整体状态，可以考虑把 `review_result.txt` 的核心内容也拼接进飞书消息，减少一次"跳转去 GitHub 看日志"的操作
9. **CI 配置可选化**：AI 审查步骤和飞书通知步骤，建议增加开关配置（比如通过 workflow 变量控制是否启用），方便团队按需灵活开启或关闭，而不是写死在流程里
10. **两条链路的整合**：目前 Webhook 通知（本地实时）和 Actions 审查（云端 CI）是两套相对独立的系统，未来可以考虑统一到同一个飞书群/同一套通知模板下，形成"push 即通知、PR 即审查"的完整开发者体验

---

## 七、关键术语速查表

| 术语              | 含义                                                                |
| ----------------- | ------------------------------------------------------------------- |
| Webhook           | 一种"事件通知"机制，某个动作发生时，自动向指定网址发送 HTTP 请求    |
| ngrok             | 内网穿透工具，把本地服务映射到外网可访问的地址                      |
| Flask             | Python 的轻量级 Web 框架，用于快速搭建接收请求的服务器              |
| Payload           | Webhook 请求携带的具体数据内容（通常是 JSON 格式）                  |
| ping 事件         | GitHub 配置 Webhook 后自动发送的连接测试请求                        |
| push 事件         | 代码真实推送到仓库时触发的事件                                      |
| Recent Deliveries | GitHub Webhook 详情页里的历史投递记录，用于排查问题                 |
| X-GitHub-Event    | HTTP 请求头字段，标识本次 Webhook 请求的事件类型                    |
| GitHub Actions    | GitHub 内置的 CI/CD 自动化平台，可基于事件（push/PR等）触发工作流   |
| Workflow          | Actions 的配置文件（YAML 格式），定义了一系列自动执行的 job 和 step |
| Secrets           | GitHub 仓库级别的加密变量存储区，用于安全保存 API Key 等敏感信息    |
| fetch-depth       | checkout 步骤的参数，控制拉取多少层提交历史，0 表示拉取全部历史     |
| git diff          | Git 命令，用于对比两个分支或提交之间的代码差异                      |
| BOM 头            | 文件开头的字节标记，用于标识文本编码方式（如 UTF-8 / UTF-16）       |
| DeepSeek API      | 本项目调用的大模型 API，用于对代码 diff 内容执行自动化审查          |
| if: always()      | Actions 语法，表示该 step 无论前序步骤成功或失败都必须执行          |
