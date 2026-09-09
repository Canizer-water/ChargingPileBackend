"""表模型汇总（建表时 import 本包即可注册全部元数据）。"""

from app.models.daily_stat import DailyChargingStat
from app.models.order import ChargingOrder
from app.models.pile import Pile, PileStatus
from app.models.refresh_token import RefreshToken
from app.models.station import Station
from app.models.user import User
from app.models.user_setting import UserSetting
from app.models.vehicle import Vehicle

__all__ = [
    "ChargingOrder", "DailyChargingStat", "Pile", "PileStatus", "RefreshToken", "Station",
    "User", "UserSetting", "Vehicle",
]
