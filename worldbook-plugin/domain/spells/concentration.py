"""concentration - 专注法术

D&D 5e：玩家同时只能维持一个专注法术。
新专注法术开始时，旧法术自动结束（DM 描述效果）。
"""

from __future__ import annotations

from typing import Any, Dict


def start_concentration(player: Dict, new_spell_id: str) -> Dict[str, Any]:
    """开始一个专注法术

    Args:
        player: player state dict（就地修改）
        new_spell_id: 新的专注法术 ID

    Returns:
        {"previous": str|None, "current": str}
    """
    previous = player.get("concentration")
    player["concentration"] = new_spell_id
    return {
        "previous": previous,
        "current": new_spell_id,
    }


def break_concentration(player: Dict, reason: str = "") -> Dict[str, Any]:
    """中断当前专注

    Returns:
        {"previous": str|None, "reason": str}
    """
    previous = player.get("concentration")
    if previous:
        player["concentration"] = None
    return {
        "previous": previous,
        "reason": reason,
    }


def is_concentrating(player: Dict) -> bool:
    return bool(player.get("concentration"))


def get_concentration(player: Dict) -> str | None:
    return player.get("concentration")
