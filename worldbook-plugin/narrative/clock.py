"""世界时钟系统（World Clock）

游戏内时间系统，时间流逝触发事件，影响世界状态。
"""

import time as _time
from typing import Any, Dict, List, Optional


# 简化历法：12 个月，每月 30 天，一周 7 天
MONTHS = [
    "深冬月", "寒霜月", "初春月", "耕播月", "繁花月", "盛夏月",
    "烈阳月", "金秋月", "收获月", "凋零月", "初雪月", "星夜月"
]

DAYS_OF_WEEK = ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"]

SEASONS = {"深冬月": "冬", "寒霜月": "冬", "初春月": "春", "耕播月": "春",
           "繁花月": "春", "盛夏月": "夏", "烈阳月": "夏", "金秋月": "夏",
           "收获月": "秋", "凋零月": "秋", "初雪月": "秋", "星夜月": "冬"}

TIME_SLOTS = {
    (6, 11): ("早晨", "morning"),
    (12, 16): ("下午", "afternoon"),
    (17, 20): ("傍晚", "evening"),
    (21, 23): ("夜晚", "night"),
    (0, 5): ("深夜", "night"),
}


class WorldClock:
    """世界时钟"""

    def __init__(self, state_mgr):
        self.state = state_mgr

    def _ensure_time(self) -> dict:
        t = self.state.get("world_time")
        if t is None:
            t = {
                "year": 1492,
                "month": 3,
                "day": 15,
                "hour": 10,
                "minute": 0,
                "day_of_week": 1,  # 星期一
                "weather": "晴朗",
                "season": "春",
            }
            self.state.update({"world_time": t}, reason="初始化世界时间", actor="系统")
        return t

    def _save_time(self, t: dict, reason: str) -> None:
        self.state.update({"world_time": t}, reason=reason, actor="系统")

    # ----------------------------------------------------------------
    # 时间查询
    # ----------------------------------------------------------------

    def now(self) -> Dict[str, Any]:
        """获取当前时间信息"""
        t = self._ensure_time()
        month_name = MONTHS[t["month"] - 1] if 1 <= t["month"] <= 12 else f"{t['month']}月"
        dow = DAYS_OF_WEEK[t["day_of_week"] % 7]
        season = SEASONS.get(month_name, t.get("season", ""))

        # 时段
        hour = t["hour"]
        time_slot = "白天"
        slot_key = "day"
        for (start, end), (label, key) in TIME_SLOTS.items():
            if start <= hour <= end:
                time_slot = label
                slot_key = key
                break

        return {
            "year": t["year"],
            "month": t["month"],
            "month_name": month_name,
            "day": t["day"],
            "hour": t["hour"],
            "minute": t["minute"],
            "day_of_week": t["day_of_week"],
            "day_of_week_name": dow,
            "season": season,
            "weather": t.get("weather", "晴朗"),
            "time_slot": time_slot,
            "time_slot_key": slot_key,
            "is_night": slot_key == "night",
            "formatted": f"{t['year']}年 {month_name} {t['day']}日 {dow} {t['hour']:02d}:{t['minute']:02d}",
        }

    def format_time(self) -> str:
        """格式化时间字符串"""
        info = self.now()
        lines = [
            f"🕐 {info['formatted']}",
            f"   季节: {info['season']}  |  天气: {info['weather']}",
            f"   时段: {info['time_slot']}",
        ]
        return "\n".join(lines)

    # ----------------------------------------------------------------
    # 时间推进
    # ----------------------------------------------------------------

    def advance_minutes(self, minutes: int, reason: str = "") -> Dict[str, Any]:
        """推进 N 分钟"""
        if minutes < 0:
            return {"success": False, "error": "时间不能倒退"}
        t = self._ensure_time()
        old_time = self.now()

        t["minute"] += minutes
        while t["minute"] >= 60:
            t["minute"] -= 60
            t["hour"] += 1

        while t["hour"] >= 24:
            t["hour"] -= 24
            t["day"] += 1
            t["day_of_week"] = (t["day_of_week"] + 1) % 7

        # 简化：每月 30 天
        while t["day"] > 30:
            t["day"] -= 30
            t["month"] += 1
            if t["month"] > 12:
                t["month"] = 1
                t["year"] += 1

        # 更新季节
        month_name = MONTHS[t["month"] - 1] if 1 <= t["month"] <= 12 else ""
        t["season"] = SEASONS.get(month_name, t.get("season", ""))

        reason = reason or f"时间流逝 {minutes} 分钟"
        self._save_time(t, reason)

        new_time = self.now()
        day_changed = old_time["day"] != new_time["day"]
        slot_changed = old_time["time_slot"] != new_time["time_slot"]

        # 检查定时事件
        triggered = self._check_timed_events()

        return {
            "success": True,
            "minutes_advanced": minutes,
            "old_time": old_time["formatted"],
            "new_time": new_time["formatted"],
            "day_changed": day_changed,
            "slot_changed": slot_changed,
            "events_triggered": triggered,
        }

    def advance_hours(self, hours: int, reason: str = "") -> Dict[str, Any]:
        """推进 N 小时"""
        return self.advance_minutes(hours * 60, reason or f"时间流逝 {hours} 小时")

    def advance_days(self, days: int, reason: str = "") -> Dict[str, Any]:
        """推进 N 天"""
        return self.advance_minutes(days * 24 * 60, reason or f"时间流逝 {days} 天")

    def set_time(self, year: int = None, month: int = None, day: int = None,
                 hour: int = None, minute: int = None) -> Dict[str, Any]:
        """直接设置时间（校验范围）"""
        t = self._ensure_time()
        if year is not None: t["year"] = max(1, year)
        if month is not None: t["month"] = max(1, min(12, month))
        if day is not None: t["day"] = max(1, min(30, day))
        if hour is not None: t["hour"] = max(0, min(23, hour))
        if minute is not None: t["minute"] = max(0, min(59, minute))
        self._save_time(t, "设置游戏时间")
        return {"success": True, "time": self.now()["formatted"]}

    # ----------------------------------------------------------------
    # 天气
    # ----------------------------------------------------------------

    def set_weather(self, weather: str) -> Dict[str, Any]:
        """设置当前天气"""
        t = self._ensure_time()
        old = t.get("weather", "")
        t["weather"] = weather
        self._save_time(t, f"天气变化: {old} → {weather}")
        return {"success": True, "weather": weather, "old_weather": old}

    # ----------------------------------------------------------------
    # 定时事件
    # ----------------------------------------------------------------

    def add_event(self, event_time: str, description: str) -> Dict[str, Any]:
        """添加定时事件

        event_time 格式: "YYYY-MM-DD HH:MM" 或 "MM-DD HH:MM"
        """
        events = self.state.get("time_events") or []
        # 解析时间
        try:
            parts = event_time.split()
            date_part = parts[0]
            time_part = parts[1] if len(parts) > 1 else "00:00"

            date_parts = date_part.split("-")
            if len(date_parts) == 3:
                y, m, d = int(date_parts[0]), int(date_parts[1]), int(date_parts[2])
            else:
                t = self.now()
                y = t["year"]
                m, d = int(date_parts[0]), int(date_parts[1])

            h, mi = [int(x) for x in time_part.split(":")]
        except Exception as e:
            return {"success": False, "error": f"时间格式错误: {e}"}

        event_id = f"ev{len(events) + 1}"
        event = {
            "id": event_id,
            "year": y, "month": m, "day": d,
            "hour": h, "minute": mi,
            "description": description,
            "triggered": False,
        }
        events.append(event)
        self.state.update({"time_events": events},
                         reason=f"添加定时事件: {description}")
        return {"success": True, "event_id": event_id, "description": description,
                "time": f"{y}-{m:02d}-{d:02d} {h:02d}:{mi:02d}"}

    def list_events(self, include_triggered: bool = False) -> List[Dict]:
        """列出定时事件"""
        events = self.state.get("time_events") or []
        if not include_triggered:
            events = [e for e in events if not e.get("triggered")]
        # 按时间排序
        events.sort(key=lambda e: (e["year"], e["month"], e["day"], e["hour"], e["minute"]))
        return events

    def _check_timed_events(self) -> List[Dict]:
        """检查并触发到期事件（内部调用）"""
        t = self._ensure_time()
        events = self.state.get("time_events") or []
        triggered = []

        for ev in events:
            if ev.get("triggered"):
                continue

            # 比较时间
            ev_time = (ev["year"], ev["month"], ev["day"], ev["hour"], ev["minute"])
            now_time = (t["year"], t["month"], t["day"], t["hour"], t["minute"])

            if now_time >= ev_time:
                ev["triggered"] = True
                ev["triggered_time"] = _time.time()
                triggered.append({
                    "id": ev["id"],
                    "description": ev["description"],
                })

        if triggered:
            self.state.update({"time_events": events},
                             reason=f"定时事件触发: {[e['description'] for e in triggered]}")

        return triggered

    def check_events(self) -> List[Dict]:
        """手动检查到期事件"""
        return self._check_timed_events()
