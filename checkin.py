#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
雨云 + 海绵科创 双平台自动签到
================================
- 雨云(Rainyun)  : 调用官方 API 完成「每日签到」积分任务
- 海绵科创(YunMC) : 邮箱密码登录后调用积分商城签到接口

凭据配置(二选一, 环境变量优先):
  1. 环境变量:
       RAINYUN_API_KEY   雨云 API Key, 多账号用英文逗号分隔
       HMC_EMAIL         海绵科创邮箱, 多账号用英文逗号分隔
       HMC_PASSWORD      海绵科创密码, 与邮箱一一对应, 逗号分隔
  2. config.json(参考 config.example.json)

用法:
  python checkin.py                # 全部平台签到
  python checkin.py --platform rainyun   # 只签雨云
  python checkin.py --platform hmc      # 只签海绵科创

退出码: 0 = 全部成功/跳过, 1 = 存在失败(便于 CI 标红)
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import requests
except ImportError:
    print("缺少依赖 requests, 请先执行: pip install requests", file=sys.stderr)
    sys.exit(1)

TIMEOUT = 30
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

# 平台签到结果状态
OK = "成功"
SKIP = "跳过"      # 今日已签到
FAIL = "失败"


@dataclass
class SignResult:
    platform: str
    account: str
    status: str = FAIL
    message: str = ""
    raw: str = field(default="", repr=False)


def load_config() -> dict:
    """读取 config.json, 环境变量同名配置优先生效。"""
    cfg = {"RAINYUN_API_KEY": "", "HMC_EMAIL": "", "HMC_PASSWORD": ""}

    config_path = Path(__file__).parent / "config.json"
    if config_path.exists():
        try:
            file_cfg = json.loads(config_path.read_text(encoding="utf-8"))
            cfg.update({k: v for k, v in file_cfg.items() if isinstance(v, str)})
        except (json.JSONDecodeError, OSError) as e:
            print(f"⚠️ config.json 解析失败: {e}", file=sys.stderr)

    for key in cfg:
        env_val = os.environ.get(key, "").strip()
        if env_val:
            cfg[key] = env_val
    return cfg


# ---------------------------------------------------------------- 雨云

RAINYUN_API = "https://api.v2.rainyun.com"


def rainyun_sign(api_key: str) -> SignResult:
    """雨云每日签到。POST /user/reward/tasks 提交积分任务。"""
    account = api_key[:6] + "****" if len(api_key) > 6 else "****"
    result = SignResult(platform="雨云", account=account)
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "User-Agent": UA,
    }

    try:
        # 先查询任务状态: 未签则签到, 已签则跳过
        resp = requests.get(
            f"{RAINYUN_API}/user/reward/tasks",
            headers=headers, timeout=TIMEOUT,
        )
        result.raw = resp.text[:500]

        if resp.status_code == 401:
            result.message = "API Key 无效或已过期"
            return result

        signed_today = False
        if resp.ok:
            try:
                tasks = resp.json().get("data") or []
                for t in tasks:
                    if t.get("task_name") == "每日签到":
                        # done/completed 字段名以实际返回为准, 均做兼容
                        signed_today = bool(t.get("done") or t.get("completed")
                                            or t.get("is_complete"))
                        break
            except (ValueError, AttributeError, TypeError):
                pass

        if signed_today:
            result.status = SKIP
            result.message = "今日已签到"
            return result

        # 提交签到任务
        resp = requests.post(
            f"{RAINYUN_API}/user/reward/tasks",
            headers=headers,
            json={"task_name": "每日签到"},
            timeout=TIMEOUT,
        )
        result.raw = resp.text[:500]
        body = {}
        try:
            body = resp.json()
        except ValueError:
            pass

        msg = str(body.get("message") or body.get("msg") or result.raw)
        code = body.get("code", resp.status_code)

        if resp.ok and (code in (0, 200) or "成功" in msg):
            result.status = OK
            result.message = msg
        elif "已签到" in msg or "重复" in msg or "未达成条件" in msg:
            # "未达成条件" = 当日已领过该任务
            result.status = SKIP
            result.message = msg
        else:
            result.message = f"HTTP {resp.status_code}: {msg}"

    except requests.RequestException as e:
        result.message = f"网络错误: {e}"
    return result


# ---------------------------------------------------------------- 海绵科创

HMC_BASE = "https://www.yunmc.vip"
HMC_SIGN_URL = f"{HMC_BASE}/addons?_plugin=points_mall&_controller=index&_action=sign"


def hmc_sign(email: str, password: str) -> SignResult:
    """海绵科创(海绵联机)签到: 登录 -> 积分商城签到。"""
    result = SignResult(platform="海绵科创", account=email)
    session = requests.Session()
    session.headers.update({"User-Agent": UA})

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
        result.raw = resp.text[:500]

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
        elif "已签到" in msg or "重复" in msg:
            result.status = SKIP
            result.message = msg
        elif "登录" in msg or code in (0, -1) and not msg:
            result.message = f"登录失败或会话过期: {msg or result.raw}"
        else:
            result.message = msg or f"code={code}"

    except requests.RequestException as e:
        result.message = f"网络错误: {e}"
    return result


# ---------------------------------------------------------------- 主流程

def split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def run(cfg: dict, platforms: set[str]) -> int:
    results: list[SignResult] = []

    if "rainyun" in platforms:
        keys = split(cfg.get("RAINYUN_API_KEY", ""))
        if not keys:
            print("⏭️  [雨云] 未配置 RAINYUN_API_KEY, 跳过")
        for key in keys:
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
    failed = 0
    for r in results:
        icon = {"成功": "✅", "跳过": "⏭️", "失败": "❌"}[r.status]
        print(f"{icon} [{r.platform}] {r.account}: {r.status} — {r.message}")
        if r.status == FAIL:
            failed += 1

    if not results:
        print("(未执行任何签到, 请检查凭据配置)")
    print(f"==================================")
    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="雨云 + 海绵科创 自动签到")
    parser.add_argument(
        "--platform",
        choices=["rainyun", "hmc", "all"],
        default="all",
        help="只签指定平台, 默认全部",
    )
    args = parser.parse_args()

    cfg = load_config()
    platforms = {"rainyun", "hmc"} if args.platform == "all" else {args.platform}
    sys.exit(run(cfg, platforms))


if __name__ == "__main__":
    main()
