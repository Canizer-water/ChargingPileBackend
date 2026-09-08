"""模拟充电桩设备侧 REST 契约（B2：scripts/charger_sim.py ↔ 后端）。"""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel


class SimulatorRegisterRequest(CamelModel):
    """设备注册：deviceId 由模拟器自行生成并持久化（重启复用），pileCode 为绑定的桩编号。"""

    device_id: str = Field(min_length=1, max_length=64)
    pile_code: str = Field(min_length=1, max_length=32)


class SimulatorRegisterResponse(CamelModel):
    simulator_id: str
    device_id: str
    pile_code: str
    pile_status: str
    heartbeat_interval_sec: int


class SimulatorTelemetryRequest(CamelModel):
    """模拟器按秒上报的遥测帧（电压/电流/功率/电量由桩侧计量）。"""

    voltage: float = Field(ge=0)
    current: float = Field(ge=0)
    power_kw: float = Field(ge=0)
    energy_kwh: float = Field(ge=0)


class SimulatorStateResponse(CamelModel):
    """register/heartbeat/telemetry/done 通用回执：piles 的权威状态随帧带回。"""

    simulator_id: str
    pile_code: str
    pile_status: str
    online: bool = True


class SimulatorDoneResponse(SimulatorStateResponse):
    settled_order_id: str = ""
