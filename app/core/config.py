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

    # ---- 华为云 IoTDA / MQTT（三期：device 直接接入，MQTTS 8883）----
    mqtt_enabled: bool = False
    mqtt_host: str = ""
    mqtt_port: int = 8883
    mqtt_username: str = ""
    mqtt_access_token: str = ""  # IoTDA 设备口令（MQTT password）
    mqtt_client_id: str = ""
    # 第 2 台设备上报三元组（MQTT2_*）
    mqtt2_username: str = ""
    mqtt2_access_token: str = ""
    mqtt2_client_id: str = ""

    # ---- IoTDA 应用侧（影子查询，AK/SK 鉴权）----
    iotda_enabled: bool = False
    iotda_region: str = "cn-north-4"
    iotda_ak: str = ""
    iotda_sk: str = ""
    iotda_project_id: str = ""
    iotda_endpoint: str = ""  # 应用侧 REST 地址（iotda-app 域名）
    iotda_service_id: str = ""
    iotda_device1_id: str = ""
    iotda_device2_id: str = ""
    iotda_poll_sec: int = 3   # 收端：查影子周期
    iotda_report_sec: int = 3  # 上报端：设备上报周期


@lru_cache
def get_settings() -> Settings:
    return Settings()
