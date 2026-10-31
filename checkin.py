#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
雨云 + 海绵科创 双平台自动签到
================================
- 雨云(Rainyun)  : 自动完成腾讯 TCaptcha 点选验证码(模板匹配, 无需打码服务)后签到
- 海绵科创(YunMC) : 邮箱密码登录后调用积分商城签到接口
- 结果推送        : 支持 Bark / Server酱 / PushPlus / Telegram, 配了哪个发哪个

凭据配置(二选一, 环境变量优先):
  1. 环境变量:
       RAINYUN_API_KEY   雨云 API Key, 多账号用英文逗号分隔
       HMC_EMAIL         海绵科创邮箱, 多账号用英文逗号分隔
       HMC_PASSWORD      海绵科创密码, 与邮箱一一对应, 逗号分隔
     推送(全部可选, 配了哪个渠道就发哪个):
       BARK_URL          Bark 完整推送地址, 如 https://api.day.app/xxxx
       SERVERCHAN_KEY    Server酱 SendKey
       PUSHPLUS_TOKEN    PushPlus token
       TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID  两个都配才发
  2. config.json(参考 config.example.json)

用法:
  python checkin.py                     # 全部平台签到
  python checkin.py --platform rainyun  # 只签雨云
  python checkin.py --platform hmc     # 只签海绵科创
  python checkin.py --no-notify        # 本次不推送

退出码: 0 = 全部成功/跳过, 1 = 存在失败(便于 CI 标红)

验证码识别模块来自 RainyunCheckIn(https://github.com/FalseHappiness/RainyunCheckIn), MIT License。
"""

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

try:
    import requests
except ImportError:
    print("缺少依赖 requests, 请先执行: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)

TIMEOUT = 30

# 平台签到结果状态
OK = "成功"
SKIP = "跳过"      # 今日已签到
FAIL = "失败"

ALL_CONFIG_KEYS = [
    "RAINYUN_API_KEY", "HMC_EMAIL", "HMC_PASSWORD",
    "BARK_URL", "SERVERCHAN_KEY", "PUSHPLUS_TOKEN",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
]


@dataclass
class SignResult:
    platform: str
    account: str
    status: str = FAIL
    message: str = ""


def load_config() -> dict:
    """读取 config.json, 同名环境变量优先。"""
    cfg = {k: "" for k in ALL_CONFIG_KEYS}

    config_path = Path(__file__).parent / "config.json"
    if config_path.exists():
        try:
            file_cfg = json.loads(config_path.read_text(encoding="utf-8"))
            cfg.update({k: v for k, v in file_cfg.items()
                        if k in cfg and isinstance(v, str)})
        except (json.JSONDecodeError, OSError) as e:
            print(f"⚠️ config.json 解析失败: {e}", file=sys.stderr)

    for key in cfg:
        env_val = os.environ.get(key, "").strip()
        if env_val:
            cfg[key] = env_val
    return cfg


# ---------------------------------------------------------------- 雨云(含验证码自动识别)

def rainyun_sign(api_key: str) -> SignResult:
    """雨云每日签到: 自动过 TCaptcha 点选验证码 -> 提交积分任务。"""
    account = api_key[:6] + "****" if len(api_key) > 6 else "****"
    result = SignResult(platform="雨云", account=account)

    try:
        # 延迟加载验证码模块(依赖 opencv/mini-racer, 不签雨云时无需加载)
        from src.main import MainLogic

        # 凭据写入临时配置文件(Cookie 会回写该文件, 不污染工作目录)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump({"auth": {"x-api-key": api_key, "name": account}}, f)
            config_path = f.name

        logic = MainLogic(config_path=config_path)
        raw = logic.auto_check_in(match_method="template")

        # 解析结果: 已签到 -> {'error': '...今日已经签到。'}
        #          签到响应 -> 雨云 API 原始 JSON {'code':..,'message':..}
        #          过程失败 -> {'error': '...'}
        if isinstance(raw, dict) and "data" in raw and isinstance(raw["data"], list):
            raw = raw["data"][0] if raw["data"] else {"error": "无返回数据"}

        if not isinstance(raw, dict):
            result.message = str(raw)
        elif raw.get("error"):
            err = str(raw["error"])
            if "已经签到" in err or "已签到" in err:
                result.status = SKIP
            result.message = err
        else:
            msg = str(raw.get("message") or raw.get("msg") or "")
            code = raw.get("code")
            if code in (0, 200) or "成功" in msg or "完成" in msg:
                result.status = OK
                result.message = msg or "签到成功"
            else:
                result.message = f"code={code} {msg}"[:200]

    except ImportError as e:
        result.message = f"验证码模块加载失败, 请安装依赖: pip install -r requirements.txt ({e})"
    except Exception as e:
        result.message = f"{type(e).__name__}: {e}"[:200]
    return result


# ---------------------------------------------------------------- 海绵科创

HMC_BASE = "https://www.yunmc.vip"
HMC_SIGN_URL = f"{HMC_BASE}/addons?_plugin=points_mall&_controller=index&_action=sign"


def hmc_sign(email: str, password: str) -> SignResult:
    """海绵科创(海绵联机)签到: 登录 -> 积分商城签到。"""
    result = SignResult(platform="海绵科创", account=email)
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    })

    try:
        # 1. 邮箱密码登录
        resp = session.post(
            f"{HMC_BASE}/login?action=email",
            data={"email": email, "password": password},
            timeout=TIMEOUT,
        )
        if not resp.ok:
            result.message = f"登录请求失败: HTTP {resp.status_code}"
            return result

        # 2. 进入签到页(拉取签到状态/必要 Cookie)
        session.get(HMC_SIGN_URL, timeout=TIMEOUT)

        # 3. 提交签到
        resp = session.post(
            HMC_SIGN_URL,
            headers={"x-requested-with": "XMLHttpRequest"},
            timeout=TIMEOUT,
        )
        try:
            body = resp.json()
        except ValueError:
            result.message = f"返回非 JSON(可能登录失败): {resp.text[:120]}"
            return result

        code = body.get("code")
        msg = str(body.get("msg") or body.get("message") or "")

        if code == 1:
            result.status = OK
            result.message = msg or "签到成功"
        elif ("已" in msg and "签到" in msg) or "重复" in msg or "签过" in msg:
            # 兼容各种"已签到/已经签到过了/重复签到"文案
            result.status = SKIP
            result.message = msg
        elif "登录" in msg or (code in (0, -1) and not msg):
            result.message = f"登录失败或会话过期: {msg or resp.text[:120]}"
        else:
            result.message = msg or f"code={code}"

    except requests.RequestException as e:
        result.message = f"网络错误: {e}"
    return result


# ---------------------------------------------------------------- 消息推送

def notify(cfg: dict, title: str, content: str) -> None:
    """尽力而为推送: 配了哪个渠道就发哪个, 单渠道失败不影响其他渠道和退出码。"""
    attempts = []

    # Bark
    if cfg.get("BARK_URL"):
        attempts.append(("Bark", lambda: requests.post(
            cfg["BARK_URL"].rstrip("/"),
            json={"title": title, "body": content, "group": "checkin"},
            timeout=TIMEOUT,
        )))

    # Server酱
    if cfg.get("SERVERCHAN_KEY"):
        attempts.append(("Server酱", lambda: requests.post(
            f"https://sctapi.ftqq.com/{cfg['SERVERCHAN_KEY']}.send",
            data={"title": title, "desp": content},
            timeout=TIMEOUT,
        )))

    # PushPlus
    if cfg.get("PUSHPLUS_TOKEN"):
        attempts.append(("PushPlus", lambda: requests.post(
            "https://www.pushplus.plus/send",
            json={"token": cfg["PUSHPLUS_TOKEN"], "title": title,
                  "content": content.replace("\n", "<br>")},
            timeout=TIMEOUT,
        )))

    # Telegram
    if cfg.get("TELEGRAM_BOT_TOKEN") and cfg.get("TELEGRAM_CHAT_ID"):
        attempts.append(("Telegram", lambda: requests.post(
            f"https://api.telegram.org/bot{cfg['TELEGRAM_BOT_TOKEN']}/sendMessage",
            json={"chat_id": cfg["TELEGRAM_CHAT_ID"], "text": f"{title}\n\n{content}"},
            timeout=TIMEOUT,
        )))

    if not attempts:
        print("  (未配置推送渠道, 如需通知请配置 BARK_URL / SERVERCHAN_KEY / PUSHPLUS_TOKEN / TELEGRAM)")
        return

    for name, send in attempts:
        try:
            resp = send()
            ok = resp.ok
            try:
                body = resp.json()
                # Telegram/PushPlus 用 ok 字段判断业务成功
                if isinstance(body, dict) and "ok" in body:
                    ok = ok and bool(body["ok"])
                if isinstance(body, dict) and body.get("code") not in (None, 200):
                    ok = False
            except ValueError:
                pass
            print(f"  推送[{name}]: {'成功' if ok else '失败 ' + resp.text[:100]}")
        except requests.RequestException as e:
            print(f"  推送[{name}]: 失败 {e}", file=sys.stderr)


# ---------------------------------------------------------------- 主流程

def split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def run(cfg: dict, platforms: set[str], do_notify: bool) -> int:
    results: list[SignResult] = []

    if "rainyun" in platforms:
        keys = split(cfg.get("RAINYUN_API_KEY", ""))
        if not keys:
            print("⏭️  [雨云] 未配置 RAINYUN_API_KEY, 跳过")
        for key in keys:
            print(f"🔐 [雨云] 正在签到(含验证码识别, 约需 10-30 秒)...")
            results.append(rainyun_sign(key))

    if "hmc" in platforms:
        emails = split(cfg.get("HMC_EMAIL", ""))
        passwords = split(cfg.get("HMC_PASSWORD", ""))
        if not emails:
            print("⏭️  [海绵科创] 未配置 HMC_EMAIL / HMC_PASSWORD, 跳过")
        elif len(emails) != len(passwords):
            print("❌ [海绵科创] HMC_EMAIL 与 HMC_PASSWORD 数量不一致", file=sys.stderr)
            results.append(SignResult("海绵科创", "-", FAIL, "邮箱与密码数量不一致"))
        for email, pwd in zip(emails, passwords):
            results.append(hmc_sign(email, pwd))

    # 汇总输出
    print("\n========== 签到结果汇总 ==========")
    lines = []
    failed = 0
    for r in results:
        icon = {"成功": "✅", "跳过": "⏭️", "失败": "❌"}[r.status]
        line = f"{icon} [{r.platform}] {r.account}: {r.status} — {r.message}"
        print(line)
        lines.append(f"{icon} [{r.platform}] {r.account}: {r.status} — {r.message}")
        if r.status == FAIL:
            failed += 1

    if not results:
        print("(未执行任何签到, 请检查凭据配置)")
    print("==================================")

    if do_notify and results:
        print("\n📮 发送结果推送...")
        icon = "❌" if failed else "✅"
        notify(cfg, f"{icon} 每日签到{'有失败' if failed else '完成'}", "\n".join(lines))

    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="雨云 + 海绵科创 自动签到")
    parser.add_argument(
        "--platform",
        choices=["rainyun", "hmc", "all"],
        default="all",
        help="只签指定平台, 默认全部",
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="本次运行不发送结果推送",
    )
    args = parser.parse_args()

    cfg = load_config()
    platforms = {"rainyun", "hmc"} if args.platform == "all" else {args.platform}
    sys.exit(run(cfg, platforms, do_notify=not args.no_notify))


if __name__ == "__main__":
    main()
