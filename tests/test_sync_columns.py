"""create_all 轻量补列测试：旧表缺列时 sync_missing_columns 幂等补齐。"""

from __future__ import annotations

import os
import sqlite3
import tempfile

from sqlalchemy import create_engine

from app.db import sync_missing_columns


def _make_old_db() -> str:
    """建一个缺 `stations.lat/lng`、缺 `piles.lat/lng` 的“旧库”（模拟地图合并前）。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE stations (
          id VARCHAR(16) PRIMARY KEY, name VARCHAR(64) NOT NULL,
          address VARCHAR(128) NOT NULL, distance_km REAL NOT NULL DEFAULT 0,
          price_per_kwh REAL NOT NULL DEFAULT 0, business_hours VARCHAR(32) NOT NULL DEFAULT '00:00-24:00'
        );
        CREATE TABLE piles (
          id VARCHAR(16) PRIMARY KEY, station_id VARCHAR(16) NOT NULL,
          code VARCHAR(16) NOT NULL UNIQUE, power_kw REAL NOT NULL DEFAULT 0,
          price_per_kwh REAL NOT NULL DEFAULT 0, interface_type VARCHAR(32) NOT NULL DEFAULT '',
          status VARCHAR(16) NOT NULL DEFAULT 'IDLE'
        );
        """
    )
    con.close()
    return path


def test_sync_adds_missing_columns():
    path = _make_old_db()
    try:
        eng = create_engine(f"sqlite:///{path}")
        with eng.connect() as conn:
            conn.exec_driver_sql("INSERT INTO stations (id,name,address) VALUES ('s1','x','a')")
            conn.commit()
            sync_missing_columns(conn)
            # 缺的坐标列已补上，且默认 0 可读
            cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(stations)")}
            assert {"lat", "lng"} <= cols
            # 幂等：再跑一次不报错
            sync_missing_columns(conn)
            row = conn.exec_driver_sql("SELECT lat, lng FROM stations WHERE id='s1'").fetchone()
            assert row == (0.0, 0.0)
        eng.dispose()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_sync_idempotent_after_create_all():
    """全新库（create_all 已含全部列）跑 sync 是无操作、可重复。"""
    from sqlalchemy import inspect as sa_inspect

    from app.db import Base
    eng = create_engine("sqlite://")
    try:
        with eng.connect() as conn:
            Base.metadata.create_all(conn)
            before = {t: {c["name"] for c in sa_inspect(conn).get_columns(t)}
                      for t in sa_inspect(conn).get_table_names()}
            sync_missing_columns(conn)
            sync_missing_columns(conn)  # 第二次仍应无操作
            after = {t: {c["name"] for c in sa_inspect(conn).get_columns(t)}
                     for t in sa_inspect(conn).get_table_names()}
            assert after == before
    finally:
        eng.dispose()
