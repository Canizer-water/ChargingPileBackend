"""B2 独立模拟充电桩进程（与后端不同进程、不连前端）。

状态机：空闲(IDLE) → 充电(CHARGING) → 完成/停止(done) → 空闲。
只与后端 REST 通信（register/heartbeat/telemetry/done），绝不绕过后端规则；
订单创建/结算全部发生在 services/charging.py（本脚本仅模拟桩侧计量与上报）。

用法示例（在项目根目录运行）：
    python scripts/charger_sim.py --phone 13800000000 --password pwd-123456 --pile-code p000000002

自动演示：注册用户 → 选空闲桩 start（REST，与 App 同一条业务路）→ 注册模拟设备 →
每秒按 services/realtime.py 同一公式上报遥测 → 到时长/电量条件后调 done，由后端结算。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# 复用与后端实时链路完全相同的推导公式（SimulatedProvider），保证上报帧与结算口径一致
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.timeutil import utc_now  # noqa: E402
from app.services.realtime import simulate_snapshot  # noqa: E402


class BackendError(RuntimeError):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail
        super().__init__(f"HTTP {status}: {detail}")


class ChargerBackendClient:
    """scripts/charger_sim.py 专用的极简 REST 客户端（stdlib，不新增依赖）。"""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, body: dict | None = None,
                 token: str | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read())["detail"]
            except Exception:
                detail = exc.reason or str(exc)
            raise BackendError(exc.code, detail) from exc

    def register_user(self, phone: str, password: str) -> tuple[str, dict[str, Any]]:
        try:
            res = self._request("POST", "/api/v1/auth/register", {"username": phone, "password": password})
        except BackendError as exc:
            if exc.status != 409:
                raise
            res = self._request("POST", "/api/v1/auth/login", {"username": phone, "password": password})
        return res["token"], res["user"]

    def list_stations(self, token: str) -> list[dict[str, Any]]:
        return self._request("GET", "/api/v1/stations", token=token)

    def start_charging(self, token: str, pile_id: str) -> dict[str, Any]:
        return self._request("POST", "/api/v1/charging/start", {"pileId": pile_id}, token=token)

    def register_device(self, device_id: str, pile_code: str) -> dict[str, Any]:
        return self._request(
            "POST", "/api/v1/simulator/register",
            {"deviceId": device_id, "pileCode": pile_code},
        )

    def heartbeat(self, simulator_id: str) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/simulator/{simulator_id}/heartbeat")

    def telemetry(self, simulator_id: str, frame: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/simulator/{simulator_id}/telemetry", frame)

    def done(self, simulator_id: str) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/simulator/{simulator_id}/done")


def _find_pile(stations: list[dict[str, Any]], pile_code: str) -> dict[str, Any]:
    for st in stations:
        for pile in st.get("piles", []):
            if pile.get("code") == pile_code:
                return pile
    raise BackendError(404, f"未找到桩 {pile_code}")


def run(backend: ChargerBackendClient, *, phone: str, password: str, pile_code: str,
        max_seconds: int, max_energy_kwh: float, telemetry_interval: float) -> None:
    print(f"[sim] 后端 {backend.base_url} / 桩 {pile_code} 启动")

    # 1) 模拟器身份：设备重启复用同一 device_id（后端按 device_id 幂等注册）
    device_id = f"charger-sim-{pile_code}"
    reg = backend.register_device(device_id, pile_code)
    sim_id: str = reg["simulatorId"]
    print(f"[sim] 已注册：simulatorId={sim_id} pileStatus={reg['pileStatus']}")

    # 2) 用户会话：若桩空闲则通过 App 同一条业务路 start（后端裁决，不绕过规则）
    token, _user = backend.register_user(phone, password)
    stations = backend.list_stations(token)
    pile = _find_pile(stations, pile_code)
    if pile.get("status") != "IDLE":
        print(f"[sim] 桩 {pile_code} 当前状态 {pile.get('status')}，仅上报心跳，等待空闲后重试")
        backend.done(sim_id)
        return

    order = backend.start_charging(token, pile["id"])
    print(f"[sim] 会话已启动 orderId={order['id']} startTime={order['startTime']} "
          f"power={pile['powerKw']}kW price={pile['pricePerKwh']}元/kWh")

    heartbeat_at = time.monotonic()
    next_telemetry_at = time.monotonic()
    # 设备侧计时：t0 墙钟 + 单调钟同相采样；此后 elapsed 只依赖单调钟，避免时钟/解析漂移。
    session_started_wall = utc_now()
    session_started_mono = time.monotonic()
    stop_reason = ""
    while True:
        now = time.monotonic()
        if now - heartbeat_at >= 10:
            hb = backend.heartbeat(sim_id)
            heartbeat_at = now
            if hb.get("pileStatus") != "CHARGING":
                stop_reason = f"后端桩状态变为 {hb.get('pileStatus')}（外部停止）"
                break

        if now >= next_telemetry_at:
            next_telemetry_at = now + telemetry_interval
            t_sec = now - session_started_mono
            frame = simulate_snapshot(pile["pricePerKwh"], pile["powerKw"], session_started_wall,
                                      session_started_wall + timedelta(seconds=t_sec))
            backend.telemetry(sim_id, frame.model_dump(by_alias=True))
            print(f"[sim] 遥测 t={frame.duration_sec:.0f}s "
                  f"P={frame.power_kw:.1f}kW E={frame.energy_kwh:.2f}kWh "
                  f"V={frame.voltage:.1f}V I={frame.current:.1f}A")
            if t_sec >= max_seconds:
                stop_reason = f"达到演示时长 {max_seconds}s"
                break
            if frame.energy_kwh >= max_energy_kwh:
                stop_reason = f"达到演示电量 {max_energy_kwh}kWh"
                break

        time.sleep(0.2)

    # 3) 停止条件到达 → 通知后端裁决结算（done；FINISHED 后回空闲，由后端写订单）
    print(f"[sim] 停止条件：{stop_reason}")
    result = backend.done(sim_id)
    print(f"[sim] done 结算完成 settledOrderId={result.get('settledOrderId') or '(空闲桩，无待结算订单)'} "
          f"pileStatus={result.get('pileStatus')}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="B2 独立模拟充电桩进程（只与后端 REST 通信）")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="后端地址")
    parser.add_argument("--pile-code", default="p000000002", help="绑定的桩编号（种子桩 code）")
    parser.add_argument("--phone", default=None, help="用户手机号（未注册则自动注册）")
    parser.add_argument("--password", default=None, help="用户密码（6-20 位）")
    parser.add_argument("--max-seconds", type=int, default=60, help="演示充电时长（秒）")
    parser.add_argument("--max-energy-kwh", type=float, default=100.0, help="演示电量上限（kWh）")
    parser.add_argument("--telemetry-interval", type=float, default=1.0, help="遥测上报间隔（秒）")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    phone = args.phone or input("请输入用户手机号（11 位，未注册将自动注册）：").strip()
    password = args.password or input("请输入用户密码（6-20 位）：").strip()
    run(
        ChargerBackendClient(args.base_url),
        phone=phone,
        password=password,
        pile_code=args.pile_code,
        max_seconds=args.max_seconds,
        max_energy_kwh=args.max_energy_kwh,
        telemetry_interval=args.telemetry_interval,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
