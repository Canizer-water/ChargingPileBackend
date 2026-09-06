# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

电动汽车充电桩（充电站）物联网平台的后端（FastAPI）。一期已完成：auth / stations / charging / orders 四组接口 + SQLite 持久化 + JWT 鉴权 + 服务端实时数据模拟，全部通过 pytest 与真实服务冒烟。

配套前端是独立的 HarmonyOS App，位于 `E:\StartChargingPile`（ArkTS）。2026-09-04 前端已按 `doc/开发设计文档.md` 的 16 个 Story 完成本地对齐；超纲页面（钱包/充值/发票/爱车/通知）代码在仓、入口已撤。

**前后端契约的唯一事实源是本仓库 `doc/后端设计文档.md`（当前 v0.2）**：含字段映射表（前端 `Types.ets` ↔ 后端 schema/表，§1.1）、端点表（§5）、防割裂变更协议（§9）。实现任何接口前先对照该文档；**改字段必须先改文档、再改两端代码**；`tests/test_contract.py` 做契约快照，字段漂移即测试红。JSON 一律 camelCase，与 ArkTS 逐字对齐；时间字符串口径 `YYYY-MM-DD HH:MM:SS`。

## 运行命令

所有命令基于项目本地虚拟环境 `.venv/`（Python 3.12.10）：

```bash
# 启动开发服务器（默认 127.0.0.1:8000，交互式文档在 /docs）
.venv/Scripts/python.exe -m uvicorn app.main:app --reload

# 运行全部测试（临时 SQLite，不污染 data/）
.venv/Scripts/python.exe -m pytest -q

# 运行单个测试文件 / 用例
.venv/Scripts/python.exe -m pytest tests/test_charging.py -q
.venv/Scripts/python.exe -m pytest tests/test_contract.py::test_model_field_contracts -q
```

首次启动自动建表（`data/app.db`，SQLite/aiosqlite）并写入 4 站 9 桩种子数据。本地配置复制 `.env.example` 为 `.env`（不提交）；`SECRET_KEY` 生产必须换成 ≥32 字节随机串。

`test_main.http` 是 JetBrains HTTP Client 脚本，覆盖完整业务流（注册→登录→电站→充电→订单），需先启动服务器。

## 代码结构

```
app/
├── main.py        # create_app：lifespan 建表+种子、CORS、BizError→HTTP 处理器
├── core/          # config(pydantic-settings) / security(bcrypt+JWT) / deps(get_db, get_current_user) / timeutil(naive UTC)
├── db.py          # async engine / sessionmaker / Base（init_engine 供测试替换）
├── models/        # SQLAlchemy 表：user station pile order
├── schemas/       # Pydantic：CamelModel 基类(alias_generator=to_camel)，字段=前端 Types.ets
├── routers/       # auth stations charging orders（挂到 /api/v1）
├── services/
│   ├── charging.py   # start/stop/current 业务规则与三条不变式（唯一裁决处）
│   └── realtime.py   # RealtimeProvider 抽象：SimulatedProvider(解析式无状态推导) / MqttProvider(读上报缓存,预留)
├── mqtt/          # 【三期预留】华为云 IoTDA 接入桩：topics + SnapshotCache；默认关闭，本期不引入 MQTT 依赖
└── seed.py        # 站点/桩种子（源自前端 MockData；p000000003 以 IDLE 入库以守不变式）
tests/             # conftest(临时库+TestClient) + 四业务文件 + test_contract(契约快照)
```

## 关键设计约束（改动前必读）

- **计价统一元/度（pricePerKwh）**，历史元/时（pricePerHour）已废弃，禁止回流。
- 三条业务不变式（设计文档 §4）：单用户至多 1 个进行中订单；会话期间桩 CHARGING、结算回 IDLE；FINISHED 订单不可变。
- 越权访问资源一律 404（不泄露存在性）；错误体用 FastAPI `{"detail"}`，前端 service 层映射为 `{success,message}`。
- 全库时间用 naive UTC（`core/timeutil`），出口统一 `fmt_datetime`。
- `data/`、`.env`、日志均不入库（.gitignore）；桩展示元数据（slotCode/地图坐标等）故意留在前端 DisplayMeta，后端不建模（§10 决策 1）。
- MQTT/华为云接入是传输层扩展：实时数据一律经 `RealtimeProvider` 抽象取数，`REALTIME_SOURCE=sim|mqtt` 切换，业务裁决始终在 `services/charging.py`。

## 工程约定

- 遵循用户级全局 CLAUDE.md（`~/.claude/CLAUDE.md`）：现代类型注解、Conventional Commits、提交前隐私扫描、敏感配置走 `.env`。
- 新增依赖必须同步 `requirements.txt`（当前已固化 fastapi 0.141.1 / SQLAlchemy 2.0.52 / pydantic 2.13.5 / PyJWT 2.13 / bcrypt 5.0 等）。
