# 雨云 + 海绵科创 自动签到

每天自动完成两个平台的签到任务：

| 平台 | 网站 | 方式 | 需要的凭据 |
|------|------|------|-----------|
| 雨云 | rainyun.com | 官方 API 提交「每日签到」积分任务 | API Key |
| 海绵科创(海绵联机) | yunmc.vip | 邮箱密码登录 → 积分商城签到接口 | 邮箱 + 密码 |

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

**方式 B：配置文件**（本地运行方便）

```bash
cp config.example.json config.json
# 编辑 config.json 填入凭据（多账号时逗号分隔）
```

> 优先级：环境变量 > config.json。`config.json` 含账号密码，注意不要提交到公开仓库。

### 3. 运行

**本地运行**（需要 Python 3.10+）：

```bash
pip install requests
python checkin.py                  # 全部签到
python checkin.py --platform rainyun   # 只签雨云
python checkin.py --platform hmc      # 只签海绵科创
```

每天定时的话，加一条 cron（Linux）或任务计划程序（Windows）即可，例如每天 8:10：

```bash
10 8 * * * cd /path/to/checkin && python3 checkin.py >> checkin.log 2>&1
```

**GitHub Actions 托管（推荐，免维护）**：

1. 新建一个 GitHub 仓库，把本目录所有文件推上去（包括 `.github/workflows/checkin.yml`）
2. 仓库 Settings → Secrets and variables → Actions → New repository secret，添加：
   - `RAINYUN_API_KEY`
   - `HMC_EMAIL`、`HMC_PASSWORD`
3. 打开 Actions 页面启用 workflow。之后每天北京时间 08:10 自动运行，也可在 Actions → 每日签到 → Run workflow 手动触发

## 签到结果说明

- ✅ 成功 — 签到完成
- ⏭️ 跳过 — 今日已签到（不报错）
- ❌ 失败 — 会输出具体原因（凭据错误、网络问题等）

退出码：全部成功为 0，存在失败为 1（CI 里会标红提醒）。

## 已知限制（雨云人机验证）

雨云自 2024 年底在签到环节加入了腾讯 TCaptcha 拼图人机验证。本项目为纯 API 版本：

- 若签到返回「需要人机验证 / captcha」类错误，说明纯 API 已被拦截，需等待后续加入自动过验证模块（可参考 [RainyunCheckIn](https://github.com/FalseHappiness/RainyunCheckIn) 的图像匹配方案）
- 部分账号 / IP 可能不受影响，先跑一次看实际返回

## 目录结构

```
checkin/
├── checkin.py                     # 主程序
├── config.example.json            # 配置模板
├── .github/workflows/checkin.yml  # GitHub Actions 定时任务
└── README.md
```
