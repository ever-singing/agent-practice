# 🤖 GitHub AI Code Review Bot

自动化代码审查 + 实时飞书通知系统。每次 `push` 或 `Pull Request`，自动生成 diff，交给 DeepSeek AI 审查，结果以卡片消息推送到飞书，无需人工盯着 CI 日志。

```
git push  →  GitHub Actions 自动触发  →  AI 审查代码  →  飞书收到卡片通知
```

---

## ✨ 功能特性

- ✅ **自动触发**：支持 `push` 到 main 分支 和 `Pull Request` 两种场景，自动区分处理
- ✅ **AI 代码审查**：基于 DeepSeek API，从安全性、代码规范、逻辑健壮性三个维度审查每一次改动
- ✅ **双人格模式**：可切换专业审查语气 / 猫娘语气 🐾，改一个环境变量即可
- ✅ **飞书卡片通知**：结构化展示审查结果，Push 和 PR 用不同颜色卡片区分，带一键跳转日志按钮
- ✅ **健壮的编码处理**：自动识别 UTF-8 / UTF-16 编码，兼容 Windows 和 Linux 环境生成的 diff 文件
- ✅ **本地 Webhook 通知**：另配一套基于 Flask + ngrok 的本地实时通知方案，适合本地开发调试场景

---

## 📦 项目结构

```
.
├── .github/
│   └── workflows/
│       ├── test.yml            # CI 工作流配置
│       ├── code_review.py      # AI 代码审查脚本
│       └── notify_feishu.py    # 飞书通知脚本
├── step1.py                    # （本地Webhook方案）示例脚本
├── step2.py                    # Flask 本地服务器，接收 GitHub Webhook
├── introduction.md             # 开发笔记 / 踩坑记录
└── README.md                   # 本文件
```

---

## 🚀 快速开始

### 1. 准备两个密钥

| 密钥                 | 获取方式                                                                   |
| -------------------- | -------------------------------------------------------------------------- |
| `DEEPSEEK_API_KEY`   | 前往 [DeepSeek 开放平台](https://platform.deepseek.com) 注册并创建 API Key |
| `FEISHU_WEBHOOK_URL` | 飞书群 → 设置 → 群机器人 → 添加"自定义机器人"，复制 Webhook 地址           |

### 2. 配置 GitHub Secrets

仓库页面 → `Settings` → `Secrets and variables` → `Actions` → `New repository secret`，依次添加：

- `DEEPSEEK_API_KEY`
- `FEISHU_WEBHOOK_URL`

⚠️ **不要**把这两个值直接写在代码或 workflow 文件里，务必使用 Secrets 存储。

### 3. 推送代码触发流水线

```bash
git add .
git commit -m "test: 触发AI代码审查"
git push
```

推送后进入仓库的 `Actions` 标签页，即可看到工作流运行状态；运行完成后，飞书群会收到审查结果卡片。

---

## ⚙️ 配置项说明

在 `.github/workflows/test.yml` 中，`运行 AI 代码审查` 这一步支持以下环境变量：

```yaml
- name: 运行 AI 代码审查
  env:
    DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
    REVIEW_PERSONA: "normal" # 审查语气：normal（专业）/ catgirl（猫娘 🐾）
    VERBOSE: "true" # 是否打印详细日志：true / false
  run: python .github/workflows/code_review.py
```

| 变量             | 可选值               | 说明                                          |
| ---------------- | -------------------- | --------------------------------------------- |
| `REVIEW_PERSONA` | `normal` / `catgirl` | 控制 AI 审查的语气风格，审查标准本身不受影响  |
| `VERBOSE`        | `true` / `false`     | 控制脚本是否在 Actions 日志中打印详细过程信息 |

---

## 🖼️ 效果预览

飞书收到的通知卡片大致长这样：

```
✅ CI Pipeline【Push】
──────────────────────────
仓库：your-name/your-repo
操作人：your-name
Commit: 5e1eb28
触发方式：Push
提交信息：优化了通知格式
──────────────────────────
📋 AI审查结果

🔒 安全性
未发现明显问题

📐 代码规范
建议为环境变量读取添加默认值兜底

🧠 逻辑与健壮性
未发现明显问题

💡 总体建议
改动合理，可以合并
──────────────────────────
[ 查看完整日志 ]
```

---

## 🧩 本地 Webhook 通知（可选组件）

如果你还想在**本地开发时**实时收到 GitHub 事件通知（不依赖 Actions），可以使用配套的 Flask + ngrok 方案：

```bash
# 1. 启动本地服务
python step2.py

# 2. 另开一个终端，启动内网穿透
ngrok http 5000

# 3. 把 ngrok 生成的地址配置到 GitHub 仓库的 Webhook 设置中
#    Settings → Webhooks → Add webhook
#    Payload URL: https://你的ngrok地址.ngrok-free.dev/webhook
```

详细原理和踩坑记录见 [`introduction.md`](./introduction.md)。

---

## ⚠️ 已知限制

- 飞书消息长度约 4096 字符上限，审查结果过长会被自动截断（可在 Actions 日志中查看完整内容）
- 首次提交（无历史 commit 可对比）时会跳过 diff 生成，AI 审查步骤自动跳过
- `git diff` 依赖完整的提交历史，请确保 checkout 步骤保留了 `fetch-depth: 0`

---

## 🔒 安全提示

- 请勿在代码或日志中打印完整的 API Key
- 建议定期在 DeepSeek / 飞书后台轮换密钥
- 本工具会将代码变更内容（diff）发送至 DeepSeek 第三方 API 进行分析，若用于包含敏感信息的私有仓库，请提前评估数据合规性

---

## 📄 License

MIT License（如需修改，请替换为你实际采用的协议）

---

## 🙋 常见问题

<details>
<summary>Q: 为什么 push 之后飞书没收到消息？</summary>

1. 检查 GitHub Secrets 中 `FEISHU_WEBHOOK_URL` 是否配置正确
2. 进入 Actions 标签页，查看"通知飞书"这一步的日志，看 `resp.status_code` 和 `resp.text` 的具体报错
3. 确认飞书机器人没有被移出群聊

</details>

<details>
<summary>Q: 审查结果里出现 UnicodeDecodeError 怎么办？</summary>

脚本已内置 BOM 头自动检测，兼容 UTF-8 / UTF-16 编码。如果仍报错，请确认 diff 文件生成方式没有被 shell 环境二次转码（详见 introduction.md 中"坑4"）。

</details>

<details>
<summary>Q: 怎么切换回专业审查语气？</summary>

修改 `test.yml` 中 `REVIEW_PERSONA` 的值为 `"normal"` 即可，无需改动其他代码。

</details>
