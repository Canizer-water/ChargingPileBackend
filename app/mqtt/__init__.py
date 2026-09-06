"""【三期预留】华为云 IoTDA / MQTT 接入包。

本期不引入 MQTT 客户端依赖，不建立任何连接。规划：
- topics.py  : 主题约定（桩状态上报 up / 平台指令下行 cmd）
- consumer.py: 订阅桩上报 → 写入 realtime 缓存 → 供 MqttProvider 读取；
               平台侧启动/停止经 cmd 主题下发（业务裁决仍在 services/charging.py）。
启用开关：Settings.mqtt_enabled / realtime_source="mqtt"（.env），默认关闭。
"""
