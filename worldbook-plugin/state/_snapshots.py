"""state/ 包的快照管理（版本快照 + 命名快照 + 回滚）

被 StateManager facade 调用，外部不要直接用。
"""

from __future__ import annotations

import copy
import datetime
import json
import os
from typing import Any, Dict, List

from . import _core


def snapshot(state_mgr) -> None:
    """保存版本快照（每次 update 自动调用）"""
    if state_mgr._state is None:
        return
    v = state_mgr._state.get("version", 0)
    state_mgr.history_dir.mkdir(parents=True, exist_ok=True)
    snap_file = state_mgr.history_dir / f"state_v{v}.json"

    tmp = snap_file.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state_mgr._state, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, snap_file)

    _prune_version_snapshots(state_mgr)


def _prune_version_snapshots(state_mgr, max_snapshots: int = 20) -> None:
    """清理旧版本快照，只保留最近 N 个"""
    if not state_mgr.history_dir.exists():
        return
    snaps = sorted(
        state_mgr.history_dir.glob("state_v*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old_snap in snaps[max_snapshots:]:
        try:
            old_snap.unlink()
        except OSError:
            pass


def save_named(state_mgr, name: str, reason: str = "") -> Dict[str, Any]:
    """保存命名快照（关键节点：战斗前/场次结束/升级）"""
    if state_mgr._state is None:
        _core.load(state_mgr)

    state_mgr.named_snapshots_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = name.replace(" ", "_").replace("/", "_")[:50]
    snap_file = state_mgr.named_snapshots_dir / f"{ts}_{safe_name}.json"

    snapshot_data = {
        "snapshot_name": name,
        "snapshot_reason": reason,
        "snapshot_time": ts,
        "version": state_mgr._state.get("version", 0),
        "state": copy.deepcopy(state_mgr._state),
    }

    tmp = snap_file.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snapshot_data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, snap_file)

    _prune_named_snapshots(state_mgr, 30)

    return {
        "success": True,
        "snapshot_file": str(snap_file.name),
        "name": name,
        "version": state_mgr._state.get("version", 0),
    }


def list_named(state_mgr) -> List[Dict[str, Any]]:
    """列出所有命名快照"""
    if not state_mgr.named_snapshots_dir.exists():
        return []
    snaps = sorted(
        state_mgr.named_snapshots_dir.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    result = []
    for s in snaps:
        try:
            with open(s, "r", encoding="utf-8") as f:
                data = json.load(f)
            result.append({
                "file": s.name,
                "name": data.get("snapshot_name", s.stem),
                "reason": data.get("snapshot_reason", ""),
                "time": data.get("snapshot_time", ""),
                "version": data.get("version", 0),
            })
        except Exception:
            result.append({"file": s.name, "name": s.stem, "time": "", "version": 0})
    return result


def rollback(state_mgr, snapshot_file: str) -> Dict[str, Any]:
    """回滚到指定命名快照（先自动备份当前状态）"""
    snap_path = state_mgr.named_snapshots_dir / snapshot_file
    if not snap_path.exists():
        return {"success": False, "error": f"快照不存在: {snapshot_file}"}

    with open(snap_path, "r", encoding="utf-8") as f:
        snap_data = json.load(f)

    old_state = snap_data["state"] if "state" in snap_data else snap_data

    current_ver = state_mgr._state.get("version", 0) if state_mgr._state else 0
    save_named(state_mgr, f"pre_rollback_v{current_ver}", reason="回滚前备份")

    state_mgr._state = copy.deepcopy(old_state)
    _core.save_state(state_mgr)

    return {
        "success": True,
        "restored_from": snapshot_file,
        "restored_version": old_state.get("version", 0),
        "backup_saved": True,
    }


def _prune_named_snapshots(state_mgr, max_snapshots: int = 30) -> None:
    """清理旧命名快照（pre_rollback 优先删）"""
    if not state_mgr.named_snapshots_dir.exists():
        return
    snaps = sorted(
        state_mgr.named_snapshots_dir.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    backups = [s for s in snaps if "pre_rollback" in s.name]
    others = [s for s in snaps if "pre_rollback" not in s.name]

    for old in backups[5:]:
        try:
            old.unlink()
        except OSError:
            pass

    remaining = others + backups[:5]
    if len(remaining) > max_snapshots:
        sorted_remaining = sorted(
            remaining, key=lambda p: p.stat().st_mtime, reverse=True
        )
        for old in sorted_remaining[max_snapshots:]:
            try:
                old.unlink()
            except OSError:
                pass


__all__ = ["snapshot", "save_named", "list_named", "rollback"]
