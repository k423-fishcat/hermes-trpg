"""state/ 包的模板加载 + 状态 I/O 核心。

被 StateManager facade 调用，外部不要直接用。
"""

from __future__ import annotations

import copy
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

from ..schema import validate_and_fill, validate_write


def load_template(state_mgr, name: str) -> dict:
    """加载模板"""
    template_file = state_mgr.templates_dir / f"{name}.json"
    if not template_file.exists():
        raise ValueError(f"找不到模板: {name}（路径: {template_file}）")
    with open(template_file, "r", encoding="utf-8") as f:
        return json.load(f)


def list_templates(state_mgr) -> List[Dict]:
    """列出可用模板"""
    templates = []
    if state_mgr.templates_dir.exists():
        for f in state_mgr.templates_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                templates.append({
                    "name": data.get("name", f.stem),
                    "display_name": data.get("display_name", f.stem),
                    "description": data.get("description", ""),
                })
            except Exception:
                continue
    return templates


def load(state_mgr) -> dict:
    """加载当前战役状态（带 schema 校验 + 自动补字段）"""
    if state_mgr._state is not None:
        return state_mgr._state

    state_mgr.campaign_dir.mkdir(parents=True, exist_ok=True)
    state_mgr.history_dir.mkdir(exist_ok=True)

    tmpl = load_template(state_mgr, state_mgr.template_name)
    default_state = tmpl.get("default_state", {})

    if state_mgr.state_file.exists():
        try:
            with open(state_mgr.state_file, "r", encoding="utf-8") as f:
                raw_state = json.load(f)
            state_mgr._state, warnings = validate_and_fill(raw_state, default_state)
            if warnings:
                import logging
                logger = logging.getLogger(__name__)
                for w in warnings:
                    logger.debug(f"[state] {w}")
            state_mgr._state.setdefault("campaign", state_mgr.campaign_name)
            state_mgr._state.setdefault("template", state_mgr.template_name)
            state_mgr._state.setdefault("version", 0)
            return state_mgr._state
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(
                f"[state] 状态文件加载失败: {state_mgr.state_file} "
                f"({type(e).__name__}: {e})。"
                f"将从模板重建 —— 现有玩家数据可能丢失！"
                f"备份原文件以排查：{state_mgr.state_file}.broken"
            )
            try:
                broken_path = state_mgr.state_file.with_suffix(".json.broken")
                if not broken_path.exists():
                    state_mgr.state_file.rename(broken_path)
            except Exception:
                pass

    state_mgr._state = copy.deepcopy(default_state)
    state_mgr._state["campaign"] = state_mgr.campaign_name
    state_mgr._state["template"] = state_mgr.template_name
    state_mgr._state["version"] = 0
    save_state(state_mgr)
    return state_mgr._state


def save_state(state_mgr) -> None:
    """保存当前状态（原子写入 + schema 校验）"""
    if state_mgr._state is None:
        return
    state_mgr.campaign_dir.mkdir(parents=True, exist_ok=True)

    # 写入前 schema 校验（非阻塞）
    try:
        tmpl = load_template(state_mgr, state_mgr.template_name)
        default_state = tmpl.get("default_state", {})
        ok, errors = validate_write(state_mgr._state, default_state)
        if not ok:
            import logging
            logger = logging.getLogger(__name__)
            for err in errors[:5]:
                logger.warning(f"[state] 写入校验警告: {err}")
    except Exception:
        pass

    tmp_file = state_mgr.state_file.with_suffix(".tmp")
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(state_mgr._state, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_file, state_mgr.state_file)


def get(state_mgr, path: str = "") -> Any:
    """获取状态值（点路径）"""
    state = load(state_mgr)
    if not path:
        return copy.deepcopy(state)
    keys = path.split(".")
    current = state
    for k in keys:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return None
    return copy.deepcopy(current)


def update(state_mgr, changes: Dict[str, Any], reason: str = "",
           actor: str = "DM", snapshot: bool = True) -> Dict[str, Any]:
    """更新状态（单入口）

    Args:
        state_mgr: StateManager 实例
        changes: {路径: 新值} 字典
        reason: 变更原因
        actor: 执行者
        snapshot: 是否写版本快照。高频数值变更（战斗内伤害/回合）传 False，
                  只在关键节点（战斗开始/结束/升级/场次结束）写快照，
                  减少磁盘 I/O。state.json 始终会保存（不丢数据）。

    Returns:
        变更结果
    """
    state = load(state_mgr)
    events = []
    for path, value in changes.items():
        keys = path.split(".")
        current = state
        for i, k in enumerate(keys[:-1]):
            if k not in current or not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]
        old_val = current.get(keys[-1]) if isinstance(current, dict) else None
        current[keys[-1]] = copy.deepcopy(value)
        events.append({
            "time": time.time(),
            "actor": actor,
            "path": path,
            "old": old_val,
            "new": value,
            "reason": reason,
        })

    state["version"] = state.get("version", 0) + 1
    for ev in events:
        ev["version"] = state["version"]
    state.setdefault("event_log", []).extend(events)
    if len(state["event_log"]) > 500:
        state["event_log"] = state["event_log"][-500:]

    # 版本快照（默认写；高频路径传 snapshot=False 跳过）
    if snapshot:
        from . import _snapshots
        _snapshots.snapshot(state_mgr)
    # state.json 始终保存（原子写入，不丢数据）
    save_state(state_mgr)

    return {
        "success": True,
        "version": state["version"],
        "change_count": len(events),
        "events": events,
    }


def undo(state_mgr, steps: int = 1) -> Dict[str, Any]:
    """回滚到之前的版本"""
    state = load(state_mgr)
    current_v = state.get("version", 0)
    target_v = max(0, current_v - steps)

    if target_v == 0:
        tmpl = load_template(state_mgr, state_mgr.template_name)
        state_mgr._state = copy.deepcopy(tmpl.get("default_state", {}))
        state_mgr._state["campaign"] = state.get("campaign", state_mgr.campaign_name)
        state_mgr._state["template"] = state.get("template", state_mgr.template_name)
        state_mgr._state["version"] = 0
    else:
        snap_file = state_mgr.history_dir / f"state_v{target_v}.json"
        if not snap_file.exists():
            return {"success": False, "error": f"找不到版本 {target_v} 的快照"}
        with open(snap_file, "r", encoding="utf-8") as f:
            state_mgr._state = json.load(f)

    save_state(state_mgr)
    return {
        "success": True,
        "old_version": current_v,
        "new_version": state_mgr._state.get("version", 0),
        "steps_rolled_back": steps,
    }


__all__ = [
    "load_template", "list_templates", "load", "save_state", "get", "update", "undo",
]
