# IoTDA 影子查询 + 设备模拟回环 —— 设计（三期 MQTT 落地）

> 状态：**已按本文落地并通过验证**（2026-09-09）：离线单测 61 全绿；真机回环验证——双设备 MQTT 连接、影子拉取写缓存、充电中遥测经 MQTT→影子→后端逐 tick 上升。
> 相关：`doc/后端设计文档.md`（契约/领域）、`app/mqtt/consumer.py`（MQTT consumer 骨架）、`services/realtime.py`（取数抽象）。
> 本机制属于**实现层/数据源**，不改前后端接口字段，故不升契约版本；落地后回填 §7/§11。

---

## 1. 背景与目标

- 前端充电页目前取数 `GET /charging/current`（+WS），数据源经 `RealtimeProvider` 抽象切换。
- 一期/二期已实现 `sim`（服务端推导）与 `simulator`（B2 REST 独立模拟桩）。
- 需求：两台"桩"（=华为 IoTDA 上两台设备）**真走一遍 MQTT**：后端本地模拟设备按桩状态上报 → IoTDA 存影子 → 后端按影子拉取 → 喂给前端，实现"数值在动"的联动，且链路真实（绕平台一圈）。

## 2. 已实测验证（2026-09-09，勿重复踩坑）

| 项 | 结果 |
|---|---|
| IAM AK/SK → `X-Auth-Token` | HTTP 201，用户/项目正确 |
| 应用侧 REST 查影子 `GET /v5/iot/{project}/devices/{device}/shadow` | 200；空影子返回 `{"device_id":..,"shadow":[]}` |
| 设备 MQTT 上报 `$oc/devices/{device}/sys/properties/report` | CONNACK 0 + QoS1 PUBACK；**service_id/属性必须与产品模型一致，否则被静默丢弃** |
| 产品真身 | 产品 id `6aa0…70`，名"实训"，**service_id=`test`**；属性：`voltage/current/powerKw/energyKwh`(decimal)、`durationSec/pileStatus`(int) |
| 双设备 | `…_test`(p1) / `…_test2`(p2)，同产品 |
| 完整回环 | 上报(service test, 数值型) → 影子可查 `{voltage,current,powerKw,energyKwh,durationSec,pileStatus}` |

> 教训：上报 JSON 里属性须为**数值**、service_id 取产品真实名（曾用 `SmartChargingPile`+字符串值 → 影子为空）。

## 3. 架构

```
充电桩设备(模拟)  MQTT properties/report
   └─> 华为 IoTDA（影子按 service 缓存最近上报）
         ▲                      │ 应用侧 REST 查影子 (AK/SK→token)
         │ 设备上报(桥上报端)    ▼
   ┌─────┴─────────┐   ┌────────────────┐
   │ device_bridge │──►│ app/services/   │ 写 SNAPSHOT_CACHE
   │ (上报+收影子) │   │ iotda.py(拉取)   │
   └───────────────┘   └────────────────┘
                                │ services/realtime: REALTIME_SOURCE=shadow
                                ▼
                    GET /charging/current + WS ──> 前端
```

角色：
- **设备（=桩）**：由后端内置模拟器扮演（见 §6 上报端），也可未来替换成真实桩。
- **华为 IoTDA**：仅作 MQTT 消息平台 + 设备影子存储（用户要求"绕一圈"）。
- **后端**：应用身份（AK/SK）轮询影子取数（pull），替代 MQTT 订阅（规避"设备收不到别台上报"的单会话/隔离限制）。

## 4. 数据语义

### 4.1 桩↔设备映射
| 桩码(seed) | 设备 | device_id(=MQTT username) |
|---|---|---|
| `p000000002` | 设备1 | `6aa0bcd37f2e6c302f978a70_test` |
| `p000000003` | 设备2 | `6aa0bcd37f2e6c302f978a70_test2` |

### 4.2 影子属性 ↔ 后端（与 `schemas/charging.py: RealtimeOut` 基本同名）
| 影子属性 | 类型 | 含义 | 后端用途 |
|---|---|---|---|
| `voltage` | decimal | 电压 V | RealtimeOut.voltage |
| `current` | decimal | 电流 A | RealtimeOut.current |
| `powerKw` | decimal | 功率 kW | RealtimeOut.power_kw |
| `energyKwh` | decimal | 累计电量 kWh | RealtimeOut.energy_kwh |
| `durationSec` | int | 已充时长 s | RealtimeOut.duration_sec |
| `pileStatus` | int | **0=空闲 1=充电中 2=故障** | 仅展示/诊断；**桩状态权威仍在我们 DB** |

`estimatedCost` 影子不给，后端按 `round(energyKwh × 订单单价, 2)` 补齐。

### 4.3 权威源不变式
- 会话与桩状态以我们 DB（`services/charging.py` 裁决）为准；影子 `pileStatus` 只用于展示核对，不驱动业务。
- 影子只存**最近一次上报**；电量/时长"上升"由上报端周期性上报实现。

## 5. 配置（新增键，均入 gitignored `.env`；`.env.example` 仅占位）

```
IOTDA_REGION=cn-north-4
IOTDA_AK=…              # IAM 访问密钥
IOTDA_SK=…
IOTDA_PROJECT_ID=…
IOTDA_ENDPOINT=https://…iotda-app.cn-north-4.myhuaweicloud.com
IOTDA_SERVICE_ID=test
IOTDA_DEVICE1_ID=…_test
IOTDA_DEVICE2_ID=…_test2
# 上报用 MQTT 三元组（设备接入）
MQTT_HOST=…iotda-device.cn-north-4.myhuaweicloud.com   # 已有
MQTT_PORT=8883 / MQTT_USERNAME / MQTT_ACCESS_TOKEN / MQTT_CLIENT_ID   # device1 已有
MQTT2_USERNAME / MQTT2_ACCESS_TOKEN / MQTT2_CLIENT_ID                 # device2
# 开关
REALTIME_SOURCE=shadow     # 取数走影子（缺数据回退 sim）
IOTDA_ENABLED=true         # 起桥（上报+收影子）
MQTT_ENABLED=false         # 停旧 MQTT 订阅 consumer（与 shadow 二选一）
IOTDA_POLL_SEC=3
IOTDA_REPORT_SEC=3
```

`app/core/config.py` 新增对应 `Settings` 字段：`iotda_*`、`mqtt2_*`、`iotda_poll_sec`、`iotda_report_sec`。

## 6. 组件设计

### 6.1 `app/services/iotda.py`（应用侧，只读拉取）
- `IamToken`：缓存 token；请求 401 → 清除并重取一次。
- `query_shadow_properties(device_id) -> dict[str, float | int] | None`
  `GET {endpoint}/v5/iot/{project}/devices/{device_id}/shadow`，取 `shadow[]` 中 `service_id==SERVICE_ID` 的 `reported.properties`（`None` 表示未上报/无 service）。
- 用标准库 `urllib`（同步、短超时），由桥的线程调用，避免引入 HTTP 异步依赖。

### 6.2 `app/services/device_bridge.py`（桥：后台线程）
单线程驱动，`start_bridge()/stop_bridge()`，`IOTDA_ENABLED=true` 时由 `main` lifespan 启动。

- **上报端**（每 `IOTDA_REPORT_SEC`）：
  - 维护每台设备的 paho client（MQTTS，三元组；沿用 `consumer.py` 已验证的 paho 线程模式）。
  - 每 tick 读一次 DB 拿桩状态/会话（桥线程内用**同步 `sqlite3` 只读**连 `data/app.db`，查 `piles.status` 与 `charging_orders.start_time/end_time`；避免与异步会话纠缠，只读演示足够）。
  - 按状态组帧：
    - IDLE/无订单：`pileStatus=0`，电压≈0/微载；
    - CHARGING（有进行中订单）：`pileStatus=1`，`durationSec=now-start`，按功率曲线推 `energyKwh`，派 `voltage/current/powerKw`；
    - FAULT：`pileStatus=2`。
  - `publish($oc/devices/{device}/sys/properties/report, {"services":[{service_id, properties}]})`，QoS1。
- **收端**（每 `IOTDA_POLL_SEC`）：对两 device 调 `query_shadow_properties`，非空 → `SNAPSHOT_CACHE.update(pile_code, RealtimeOut(...))`。
- 断线策略：paho 自动重连（keepalive）；某台查询失败/未上报跳过并记日志。

> 备选（本版不做）：影子 `desired` 下发开充 —— 命令控制仍走我们 REST `/charging/start|stop`，不动 IoTDA 下行。

### 6.3 `services/realtime.py`：新增取数
- `REALTIME_SOURCE=shadow` → `ShadowProvider`：读 `SNAPSHOT_CACHE`（与 Mqtt/SimulatorTelemetry 同构），陈旧/缺 → 回退 `SimulatedProvider`。
- `SNAPSHOT_STALE_SECONDS` 对 shadow 可放宽（如 5×report 周期）避免误回退。

### 6.4 `app/main.py` lifespan
`if settings.iotda_enabled: start_bridge()`；shutdown `stop_bridge()`。（与 `mqtt_enabled` 消费端互斥，二选一。）

## 7. 时序示例
1. 启动：桥连 2 设备、查 DB 初值；无订单 → 各报空闲帧。
2. 前端 `POST /charging/start {pileId:p000000002}` → DB 转 CHARGING。
3. 桥下一 tick 读到充电中 → device1 上报上升帧；IoTDA 影子刷新。
4. 桥拉影子 → `SNAPSHOT_CACHE[p000000002]` 更新。
5. 前端轮询 `GET /charging/current` / WS → 数值在动。
6. `stop` → DB 结算回 IDLE → 上报空闲帧。

## 8. 测试与隔离
- `tests/conftest.py`：导入 app 前强制 `IOTDA_ENABLED=false`、`MQTT_ENABLED=false`、`REALTIME_SOURCE=sim`（不连云）。
- 新增单测（**不真连云**）：
  - `test_iotda_shadow_parse`：样例影子 JSON → properties 解析/映射（含空、无 service、字符串容错）。
  - `test_bridge_payload_build`：给定桩状态/会话时长 → 上报帧正确（0/1/2、数值型）。
- 现有 53 用例保持全绿。

## 9. 验收
- `.env` 打开 `IOTDA_ENABLED=true`、`REALTIME_SOURCE=shadow` 后启动：
  1. 日志见 2 设备 MQTT CONNACK + 周期上报/拉取；
  2. 对 `p000000002` 走真实 start→charge 流程，前端 `GET /charging/current` 的 energyKwh/powerKw 随上报上升；
  3. 影子偶发缺失时自动回退 sim，页面不空窗。

## 10. 风险与未决
- 影子轮询是**拉**：实时性 = 上报间隔 + 轮询间隔（当前 3+3≈6s 步进），够演示；要更顺可缩到 1~2s（注意配额/频率）。
- 桥线程同步 `sqlite3` 直读与本进程写库：SQLite 并发读没问题；写冲突时短暂等待，单用户 demo 可接受。
- AK/SK 仅存后端 `.env`，**绝不入前端/仓库**；生产建议最小权限 IAM 子账号 + 换短时 token。
- 桥仅支持"上报+轮询"两台映射桩；新增桩需扩展映射与 `sqlite3` 目标表，可后续参数化。
- paho 双设备线程若与真实桩同 clientId 并发会互踢（同设备只能单会话）：联调阶段模拟器与真实桩勿同时用同一凭证。
