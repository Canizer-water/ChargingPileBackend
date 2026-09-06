"""站点/桩种子数据（源自前端 MockData.ets，字段与《后端设计文档》§4 对齐）。

注意：前端种子桩 p000000003 为 CHARGING、p300000001 为 OFFLINE；
后端为守住「CHARGING 桩必须挂进行中订单」不变式，p000000003 一律以 IDLE 入库，
p300000001 保留 OFFLINE（离线桩无订单，语义不冲突）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pile import Pile, PileStatus
from app.models.station import Station

SEED_STATIONS: list[dict] = [
    {
        "station": {"id": "s1", "name": "诺得充电中心", "address": "「地上」五圆路东街159号诺得大厦",
                    "distance_km": 0.03, "price_per_kwh": 1.15, "business_hours": "00:00-22:22"},
        "piles": [
            {"id": "p000000002", "code": "p000000002", "power_kw": 150, "price_per_kwh": 1.35, "interface_type": "国标2015 国标2011", "status": "IDLE"},
            {"id": "p000000003", "code": "p000000003", "power_kw": 120, "price_per_kwh": 1.25, "interface_type": "国标2015", "status": "IDLE"},
            {"id": "p000000004", "code": "p000000004", "power_kw": 60, "price_per_kwh": 1.15, "interface_type": "国标2011", "status": "IDLE"},
        ],
    },
    {
        "station": {"id": "s2", "name": "智慧e充·天辰店", "address": "「地上」天辰大厦西路88号",
                    "distance_km": 0.8, "price_per_kwh": 1.20, "business_hours": "00:00-24:00"},
        "piles": [
            {"id": "p100000001", "code": "p100000001", "power_kw": 180, "price_per_kwh": 1.45, "interface_type": "国标2015 国标2011", "status": "IDLE"},
            {"id": "p100000002", "code": "p100000002", "power_kw": 90, "price_per_kwh": 1.20, "interface_type": "国标2015", "status": "IDLE"},
        ],
    },
    {
        "station": {"id": "s3", "name": "星充能源大厦站", "address": "「地下」会展大道199号能源大厦B2",
                    "distance_km": 1.6, "price_per_kwh": 1.05, "business_hours": "08:00-22:00"},
        "piles": [
            {"id": "p300000001", "code": "p300000001", "power_kw": 120, "price_per_kwh": 1.10, "interface_type": "国标2015 国标2011", "status": "OFFLINE"},
            {"id": "p300000002", "code": "p300000002", "power_kw": 60, "price_per_kwh": 1.05, "interface_type": "国标2011", "status": "IDLE"},
        ],
    },
    {
        "station": {"id": "s4", "name": "绿色出行会展中心站", "address": "「地上」会展大道100号",
                    "distance_km": 2.4, "price_per_kwh": 1.02, "business_hours": "00:00-24:00"},
        "piles": [
            {"id": "p400000001", "code": "p400000001", "power_kw": 7, "price_per_kwh": 1.02, "interface_type": "国标交流", "status": "IDLE"},
        ],
    },
]


async def seed_if_empty(db: AsyncSession) -> bool:
    """ stations 表为空时写入种子；返回是否执行了写入。"""
    existing = await db.execute(select(Station.id).limit(1))
    if existing.scalar_one_or_none() is not None:
        return False
    for item in SEED_STATIONS:
        station = Station(**item["station"])
        db.add(station)
        for pile in item["piles"]:
            db.add(Pile(station_id=station.id,
                        status=pile.get("status", PileStatus.IDLE.value),
                        **{k: v for k, v in pile.items() if k != "status"}))
    await db.commit()
    return True
