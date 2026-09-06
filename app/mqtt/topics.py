"""华为云 IoTDA 风格主题常量（预留，三期启用时对齐产品实际 topic）。"""

# 占位前缀：接入 IoTDA 后替换为产品标识/设备实例 ID 体系
TOPIC_PREFIX = "t/charging-pile"

#: 桩实时状态上报：{prefix}/{pile_code}/charging/up
TOPIC_PILE_UP = f"{TOPIC_PREFIX}/{{pile_code}}/charging/up"
#: 平台下行指令（启动/停止等）：{prefix}/{pile_code}/charging/cmd
TOPIC_PILE_CMD = f"{TOPIC_PREFIX}/{{pile_code}}/charging/cmd"
