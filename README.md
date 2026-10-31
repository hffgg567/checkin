# 雨云 + 海绵科创 自动签到

每天自动完成两个平台的签到任务，并把结果推送到你手机：

| 平台 | 网站 | 方式 | 需要的凭据 |
|------|------|------|-----------|
| 雨云 | rainyun.com | **自动过腾讯验证码**（图像模板匹配）→ 提交「每日签到」积分任务 | API Key |
| 海绵科创(海绵联机) | yunmc.vip | 邮箱密码登录 → 积分商城签到接口 | 邮箱 + 密码 |

支持推送渠道（配了哪个发哪个）：**Bark / Server酱 / PushPlus / Telegram**

## 快速开始

### 1. 获取凭据

- **雨云 API Key**：登录雨云 → 总览/用户中心 → 账户设置 → API 密钥 → 复制
- **海绵科创**：直接用官网的注册邮箱和密码

### 2. 配置凭据（二选一）

**方式 A：环境变量**（GitHub Actions 用这种方式）

| 变量名 | 说明 |
|--------|------|
| `RAINYUN_API_KEY` | 雨云 API Key，多账号用英文逗号分隔 |
| `HMC_EMAIL` | 海绵科创邮箱，多账号逗号分隔 |
| `HMC_PASSWORD` | 海绵科创密码，与邮箱一一对应，逗号分隔 |
| `BARK_URL` | (可选) Bark 完整推送地址，如 `https://api.day.app/xxxx` |
| `SERVERCHAN_KEY` | (可选) Server酱 SendKey |
| `PUSHPLUS_TOKEN` | (可选) PushPlus token |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | (可选) 两个都配才发 |

**方式 B：配置文件**（本地运行方便）

```bash
cp config.example.json config.json
# 编辑 config.json 填入凭据（多账号时逗号分隔）
```

> 优先级：环境变量 > config.json。`config.json` 含账号密码，注意不要提交到公开仓库。

### 3. 运行

**本地运行**（需要 Python 3.10+）：

```bash
pip install -r requirements.txt
python checkin.py                     # 全部签到
python checkin.py --platform rainyun  # 只签雨云
python checkin.py --platform hmc     # 只签海绵科创
python checkin.py --no-notify        # 本次不推送
```

每天定时的话，加一条 cron（Linux）或任务计划程序（Windows），例如每天 8:10：

```bash
10 8 * * * cd /path/to/checkin && python3 checkin.py >> checkin.log 2>&1
```

**GitHub Actions 托管（推荐，免维护）**：

1. 新建一个 GitHub 仓库，把本目录所有文件推上去（包括 `.github/workflows/checkin.yml`）
2. 仓库 Settings → Secrets and variables → Actions → New repository secret，添加：
   - `RAINYUN_API_KEY`（必填）
   - `HMC_EMAIL`、`HMC_PASSWORD`（必填）
   - 推送渠道任选：`BARK_URL` / `SERVERCHAN_KEY` / `PUSHPLUS_TOKEN` / `TELEGRAM_BOT_TOKEN`+`TELEGRAM_CHAT_ID`
3. 打开 Actions 页面启用 workflow。之后每天北京时间 08:10 自动运行，也可在 Actions → 每日签到 → Run workflow 手动触发

## 签到结果说明

- ✅ 成功 — 签到完成
- ⏭️ 跳过 — 今日已签到（不报错）
- ❌ 失败 — 会输出具体原因（凭据错误、网络问题等）

退出码：全部成功为 0，存在失败为 1（CI 里会标红提醒）。

## 关于雨云验证码

雨云在签到环节使用腾讯 TCaptcha 点选验证码。本项目内置**全自动识别**（OpenCV 模板匹配定位需点选的图块，附带 PoW 工作量证明和设备指纹模拟），无需人工、无需打码服务：

- 单次识别约 2~20 秒，失败自动换图重试（默认 10 次）
- 实测识别准确率高；若多次失败会输出具体错误便于排查

## 目录结构

```
checkin/
├── checkin.py                     # 主程序（签到 + 推送）
├── requirements.txt               # 依赖
├── config.example.json            # 配置模板
├── src/                           # 验证码自动识别模块
├── static/env.js                  # 验证码环境垫片
├── .github/workflows/checkin.yml  # GitHub Actions 定时任务
└── README.md
```

## 致谢

验证码识别模块基于 [FalseHappiness/RainyunCheckIn](https://github.com/FalseHappiness/RainyunCheckIn)（MIT License），在此致谢。
