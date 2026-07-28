# GitHub Webhook + ngrok + Flask + AI 代码审查 自动化系统

## 项目完整知识文档

> 记录日期：2026年7月27日（最近更新：2026年7月28日）
> 目标：实现 GitHub 代码推送后，自动通知到本地程序并转发飞书；同时打通 GitHub Actions，让每一次提交都能自动接受 AI 代码审查，审查结果以结构化卡片形式推送到飞书

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

### 链路二：GitHub Actions AI 代码审查（CI/CD）

```
开发者 git push / 发起 Pull Request
      ↓
GitHub Actions 自动触发（ubuntu-latest 云端环境）
      ↓
拉取代码 + 安装依赖
      ↓
区分事件类型（push / pull_request），生成对应 git diff
      ↓
code_review.py：读取 diff → 按人格模式拼接 Prompt → 调用 DeepSeek API
      ↓
审查结果保存为 review_result.txt
      ↓
notify_feishu.py：拼接飞书卡片（区分Push/PR样式，带按钮跳转日志）
      ↓
飞书收到结构化卡片通知
```

两条链路的共同底层逻辑：**利用 Webhook / Actions 机制，把 GitHub 事件转化为可执行的后续动作，并最终以飞书通知的形式闭环。**

---

## 二、核心组件说明

### 1. Flask 本地服务器 (step2.py)

接收 HTTP POST 请求，解析 GitHub 事件类型和数据。

```python
from flask import Flask, request

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def receive_data():
    event_type = request.headers.get('X-GitHub-Event')
    data = request.json

    print(f"收到了一个【{event_type}】类型的事件")

    if event_type == 'ping':
        print("这是GitHub发来的测试请求，说明连接成功了！")
        return "pong收到，连接测试成功！"

    if event_type == 'push':
        repo_name = data['repository']['name']
        pusher_name = data['pusher']['name']
        commit_msg = data['head_commit']['message']
        print(f"【{pusher_name}】在项目【{repo_name}】提交了：{commit_msg}")
        return "推送事件处理完成！"

    print("暂时还没处理这种类型的事件")
    return "收到，但暂未处理"

app.run(port=5000)
```

**关键点**：先判断 `X-GitHub-Event` 事件类型，再决定怎么解析 `request.json`，避免对不同结构的 payload 硬取值导致 KeyError。

---

### 2. ngrok（内网穿透工具）

```bash
ngrok http 5000
```

运行后会显示一个 `https://xxxx.ngrok-free.dev` 的外网地址，映射到本地 5000 端口。

---

### 3. GitHub Webhook 配置

| 字段         | 填写内容                                       |
| ------------ | ---------------------------------------------- |
| Payload URL  | `https://你的ngrok地址.ngrok-free.dev/webhook` |
| Content type | `application/json`                             |
| 触发事件     | 先选 `Just the push event`                     |
| Active       | 保持勾选                                       |

⚠️ Webhook 是绑定在"具体某一个仓库"上的，不是全局生效。

---

### 4. GitHub Actions 工作流 (.github/workflows/test.yml)

完整流程包含：拉取代码 → 装环境 → 装依赖 → 简单CI检查 → 生成diff（区分push/PR）→ AI审查 → 飞书通知。

```yaml
- name: 拉取代码
  uses: actions/checkout@v4
  with:
    fetch-depth: 0 # 拉取完整历史，否则 git diff 对比不出结果

- name: 生成代码 diff
  run: |
    if [ "${{ github.event_name }}" = "pull_request" ]; then
      git diff origin/${{ github.base_ref }} origin/${{ github.head_ref }} --output=diff.txt
    else
      git diff HEAD~1 HEAD --output=diff.txt || echo "首次提交，无历史可比对" > diff.txt
    fi

- name: 记录提交信息
  run: echo "COMMIT_MSG=$(git log -1 --pretty=%s || echo '无法获取提交信息')" >> $GITHUB_ENV

- name: 运行 AI 代码审查
  env:
    DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
    REVIEW_PERSONA: "normal" # 可选: normal / catgirl
    VERBOSE: "true"
  run: python .github/workflows/code_review.py

- name: 通知飞书(无论成功失败都发送)
  if: always()
  env:
    FEISHU_WEBHOOK_URL: ${{ secrets.FEISHU_WEBHOOK_URL }}
    JOB_STATUS: ${{ job.status }}
    EVENT_NAME: ${{ github.event_name }}
    REPO: ${{ github.repository }}
    ACTOR: ${{ github.actor }}
    SHA: ${{ github.sha }}
    COMMIT_MSG: ${{ env.COMMIT_MSG }}
    PR_NUMBER: ${{ github.event.pull_request.number || '' }}
    PR_TITLE: ${{ github.event.pull_request.title || '' }}
    RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
  run: python .github/workflows/notify_feishu.py
```

**关键点**：

- `fetch-depth: 0`：不加的话 Actions 默认浅克隆，`git diff` 会因为找不到对比历史而失败
- `github.event_name` 判断：push 和 pull_request 的 diff 生成方式不同，一个对比两个分支，一个对比前后两次commit
- `PR_NUMBER`/`PR_TITLE` 用 `|| ''` 兜底：push事件下 `github.event.pull_request` 是 null，直接访问其属性会报错
- `if: always()`：保证无论审查/测试是否失败，飞书通知这一步都会执行

---

### 5. code_review.py（AI 代码审查脚本 · 双人格模式）

**核心设计**：

- **公共格式常量**：`OUTPUT_FORMAT_RULES` 单独抽出，避免 normal/catgirl 两套 Prompt 重复维护、改一处忘另一处
- **双人格切换**：通过环境变量 `REVIEW_PERSONA` 控制，`normal` 为专业审查语气，`catgirl` 为猫娘语气（专业审查标准不因人格设定降低，只改变表达方式）
- **VERBOSE 开关**：控制日志详细程度，避免非交互式 CI 环境产生过多冗余输出
- **防御性 diff 读取**：找不到文件或内容为空时返回 `None` 而非中文提示字符串，避免这段提示被误当作代码内容拼进 Prompt 误导 AI；`main` 函数判断 `None` 后直接跳过 API 调用，节省一次请求
- **temperature=0.3**：审查任务需要稳定、严谨的输出，不需要"创造力"，特意调低（曾经手滑改成0.7，被AI审查自己发现了这个问题）

```python
def build_prompt(diff_content):
    persona = os.environ.get('REVIEW_PERSONA', 'normal').strip().lower()
    if persona not in PERSONA_MAP:
        persona = 'normal'
    template = PERSONA_MAP[persona]
    return template.format(format_rules=OUTPUT_FORMAT_RULES, diff_content=diff_content)
```

---

### 6. notify_feishu.py（飞书通知脚本 · 卡片消息版）

**从纯文本升级为交互式卡片**，核心改进：

- `msg_type` 从 `text` 改为 `interactive`，让 `**加粗**` 等markdown语法能被飞书正确渲染，不再是裸露的符号堆砌
- 根据 `EVENT_NAME` 判断 push/PR，卡片**标题文案和颜色都不同**（绿色=Push，蓝色=Pull Request），群里一眼区分
- 卡片底部加了"查看完整日志"按钮，直接跳转到 Actions 运行页
- 审查结果做**总长度截断保护**（预留基础信息长度后再计算审查内容可用长度），避免超出飞书约4096字符的上限导致发送失败
- `safe_env()` 统一处理环境变量缺失/为字符串"None"的情况，避免消息里出现难看的"None"字样

---

## 三、踩过的坑 & 解决方案

### 坑1：ngrok 免费版网址每次重启都会变

每次重启后需去 GitHub Webhook 设置里手动更新 Payload URL；长期使用建议申请 ngrok 固定域名。

### 坑2：GitHub 的 ping 事件 导致 500 报错

`ping` 事件没有 `repository`/`pusher` 等字段，需先判断 `X-GitHub-Event` 再决定取值方式。**通用编程思维**：不能假设外部数据结构永远一致。

### 坑3：在错误的仓库里 push，代码毫无反应

Webhook 是仓库级别订阅，用 `git remote -v` 核对当前文件夹绑定的远程仓库是否匹配。

### 坑4：Windows 本地生成的 diff 文件，Python 读取报 UnicodeDecodeError

PowerShell 的 `>` 重定向会把 UTF-8 转码成 UTF-16/GBK。解决：改用 `git diff --output=diff.txt` 绕开重定向，Python端二进制读取+BOM头检测自动判断编码。

### 坑5：git diff 在 Actions 里因浅克隆而失败

`actions/checkout` 默认浅克隆，需加 `fetch-depth: 0` 拉取完整历史。

### 坑6：飞书消息看起来"每次都一样"

**现象**：飞书收到的CI通知除了状态外没有任何区分度信息，多次push看起来像重复消息。

**原因**：原始通知直接用 `curl` 拼接，只带了 `job.status`、`repository`、`actor` 三个字段，没有commit哈希、提交信息这些能区分"这是哪一次改动"的关键信息。

**解决**：把 `curl` 换成 Python 脚本（`notify_feishu.py`），补充 commit 短哈希、提交信息/PR标题等字段，且 push 和 PR 展示不同内容。

### 坑7：AI 审查结果没有真正发到飞书

**现象**：飞书只收到了CI通过/失败的状态，`review_result.txt` 里辛辛苦苦生成的审查内容完全没被用上。

**原因**：原来的 `curl` 命令消息体是写死的固定文案，压根没读取过 `review_result.txt` 文件。

**解决**：`notify_feishu.py` 里新增 `read_review_result()`，读取文件内容并拼进消息体，同时做长度截断保护。

### 坑8：飞书纯文本消息无法渲染 Markdown，DeepSeek 输出的 `##`、`**` 变成裸符号

**现象**：DeepSeek 审查结果里用了 `##` 标题、`**加粗**`，飞书 `text` 类型消息不支持渲染，导致这些符号原样显示，观感很差。

**解决**：双管齐下——① Prompt 里明确要求"不要使用Markdown标题/列表语法"；② `notify_feishu.py` 把 `msg_type` 从 `text` 升级为 `interactive` 卡片消息，卡片内的 `markdown` 组件能正确渲染剩余的加粗语法。

### 坑9：Prompt 里两套人格模板"输出格式要求"重复维护

**现象**：`PROMPT_NORMAL` 和 `PROMPT_CATGIRL` 里格式规则几乎完全一样，写了两份，容易改一处忘另一处。

**解决**：提取成 `OUTPUT_FORMAT_RULES` 公共常量，两个模板通过 `.format()` 引用同一份规则。

### 坑10：diff 为空时返回中文提示字符串，可能误导 AI

**现象**：`read_diff_file` 找不到文件时返回类似"（未找到 diff 文件...）"的中文字符串，`main` 函数没做判断就直接拿去拼 Prompt，AI 可能把这段提示误当成代码内容来审查。

**解决**：改为返回 `None`，`main` 函数判断 `None` 后直接跳过 API 调用，写入固定的"无差异"提示，顺便节省一次 API 调用。

### 坑11：调试时把 temperature 手滑改高，输出变得不稳定

审查任务追求的是稳定、严谨，`temperature` 曾一度被改到 `0.7`（更适合创意写作场景），导致输出风格波动较大。改回 `0.3` 后审查结论明显更一致。

---

## 四、调试排查技巧

1. **GitHub 端**：Webhook详情页 "Recent Deliveries" 查看每次投递记录，支持 Redeliver 重新发送
2. **本地端**：Flask 终端实时打印请求日志和自定义 `print()` 信息
3. **Actions 端**：仓库 "Actions" 标签页逐 step 查看日志，能看到 diff 内容、DeepSeek 原始返回
4. **飞书调试**：`notify_feishu.py` 打印 `resp.status_code` 和 `resp.text`，飞书接口报错信息通常直接说明原因

---

## 五、当前已实现的功能清单

**本地 Webhook 通知链路**

- [x] Flask 服务器接收 HTTP POST 请求
- [x] ngrok 内网穿透
- [x] GitHub Webhook 正确配置
- [x] 正确处理 ping / push 事件
- [x] 转发飞书机器人

**CI/CD AI 代码审查链路**

- [x] Actions 自动触发（支持 push 和 pull_request）
- [x] 区分 push/PR 生成不同的 git diff
- [x] 编码问题彻底修复（BOM检测+自动解码）
- [x] 敏感信息通过 GitHub Secrets 存储
- [x] DeepSeek AI 审查，双人格模式（normal / catgirl）可切换
- [x] Prompt 公共格式规则提取，避免重复维护
- [x] diff 为空时的空值处理，不再误导 AI 也不浪费 API 调用
- [x] temperature 调优至 0.3，保证审查稳定性
- [x] 飞书通知从纯文本升级为交互式卡片消息
- [x] 卡片区分 Push/PR（不同标题+颜色），带跳转日志按钮
- [x] 消息长度截断保护，环境变量空值兜底（不再出现"None"字样）
- [x] `if: always()` 保证CI状态无论成败都通知

---

## 六、后续可优化方向

1. **审查结果回评到 PR**：调用 GitHub API 把审查意见自动评论到 PR 页面，减少"跳去看Actions日志"的操作
2. **VERBOSE 开关落地验证**：目前已加入代码，需要实际在CI里测试 `VERBOSE=false` 时日志是否符合预期
3. **人格模式扩展**：`PERSONA_MAP` 字典化后新增人格成本很低，可以考虑"严厉学长"、"毒舌吐槽"等更多模式
4. **审查跳过机制**：commit信息或PR标题包含 `[skip-review]` 时跳过AI审查，应对纯文档改动等不需要审查的场景
5. **diff 大小上限控制**：超大 diff 可能导致 API 调用成本过高或超出上下文限制，需要加保护（比如超过阈值时只审查关键文件，或提示"改动过大建议拆分PR"）
6. **两条链路整合**：Webhook实时通知（本地）和 Actions审查（云端）目前相对独立，未来可考虑统一到同一套飞书消息模板下
7. **发布前的清理工作**（详见下方"七、发布准备清单"）

---

## 七、发布准备清单（若考虑开源/团队共享）

### 🔴 必须处理

- [ ] **密钥安全扫描**：检查 git 历史（`git log -p | grep -i "sk-"`）是否曾提交过真实API Key/Webhook地址；一旦发现，仅删除文件不够，必须去 DeepSeek/飞书后台**吊销旧密钥并重新生成**
- [ ] **清理测试代码**：移除调试用的 `bad_function`、`eval()` 等故意埋的坏代码
- [ ] **数据隐私说明**：明确告知使用者"本工具会将代码 diff 发送至 DeepSeek 第三方 API"，涉及公司/他人私有仓库时需额外评估合规性

### 🟡 建议处理

- [ ] 编写面向使用者的 `README.md`（区别于本文档这种"个人学习笔记"风格）
- [ ] 添加 `LICENSE` 文件（如 MIT）
- [ ] 补充 `.gitignore`（排除 `diff.txt`、`review_result.txt` 等运行时生成文件）
- [ ] 补充 `requirements.txt` 明确依赖版本
- [ ] 增加 diff 大小上限，控制 API 调用成本

### 🟢 锦上添花

- [ ] 给编码判断等核心逻辑补充单元测试
- [ ] 打 tag 做版本管理，维护 CHANGELOG
- [ ] 增加 `[skip-review]` 等逃生舱机制

---

## 八、关键术语速查表

| 术语              | 含义                                                                  |
| ----------------- | --------------------------------------------------------------------- |
| Webhook           | 事件发生时自动向指定网址发送 HTTP 请求的机制                          |
| ngrok             | 内网穿透工具，映射本地服务到公网地址                                  |
| Flask             | Python 轻量级 Web 框架                                                |
| Payload           | Webhook 请求携带的 JSON 数据内容                                      |
| ping / push 事件  | GitHub Webhook 的连接测试事件 / 代码推送事件                          |
| Recent Deliveries | Webhook 详情页的历史投递记录                                          |
| X-GitHub-Event    | 标识 Webhook 事件类型的请求头字段                                     |
| GitHub Actions    | GitHub 内置 CI/CD 自动化平台                                          |
| Secrets           | GitHub 仓库级加密变量存储，用于保存 API Key 等敏感信息                |
| fetch-depth       | checkout 步骤参数，控制拉取的提交历史深度，0 为全部历史               |
| BOM 头            | 文件开头标识编码方式的字节标记                                        |
| DeepSeek API      | 本项目调用的大模型 API，用于代码 diff 自动化审查                      |
| if: always()      | Actions 语法，无论前序步骤成功/失败都执行该 step                      |
| interactive 卡片  | 飞书消息类型，支持 Markdown 渲染、按钮等富交互元素，区别于纯文本 text |
| REVIEW_PERSONA    | 本项目自定义环境变量，控制 AI 审查语气（normal / catgirl）            |
| temperature       | LLM API 参数，控制输出随机性，审查类任务建议调低（如0.3）以保证稳定   |
