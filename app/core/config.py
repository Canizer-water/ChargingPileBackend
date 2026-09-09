"""全局配置：仅从环境变量 / .env 读取，严禁硬编码密钥（.env 不提交）。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ChargingPile API"
    api_prefix: str = "/api/v1"

    secret_key: str = "change-me"  # 生产必须经环境变量覆盖
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 120
    refresh_token_expire_days: int = 7

    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    cors_origins: list[str] = ["*"]

    # 实时数据来源：sim=服务端模拟（一期，默认）；simulator=B2 独立模拟桩遥测；mqtt=MQTT 桩上报（三期预留）
    realtime_source: str = "sim"

    # ---- B2 独立模拟充电桩进程（scripts/charger_sim.py）----
    simulator_heartbeat_interval_sec: int = 10

    # ---- 华为云 IoTDA / MQTT（三期启用，本期仅预留）----
    mqtt_enabled: bool = False
    mqtt_host: str = ""
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_access_token: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
