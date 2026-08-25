"""state/ 包的战役生命周期管理（创建/切换/列出/删除）

被 StateManager facade 调用，外部不要直接用。
"""

from __future__ import annotations

import copy
import json
import shutil
from typing import Any, Dict, List

from . import _core


def create(state_mgr, name: str, template: str = "dnd5e",
           display_name: str = "") -> Dict[str, Any]:
    """创建新战役"""
    tmpl = _core.load_template(state_mgr, template)
    default_state = copy.deepcopy(tmpl.get("default_state", {}))
    default_state["campaign"] = display_name or name
    default_state["template"] = template
    default_state["version"] = 0

    campaign_dir = state_mgr.campaigns_dir / name
    campaign_dir.mkdir(parents=True, exist_ok=True)

    state_file = campaign_dir / "state.json"
    if state_file.exists():
        return {"success": False, "error": f"战役 {name} 已存在"}

    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(default_state, f, ensure_ascii=False, indent=2)

    (campaign_dir / "history").mkdir(exist_ok=True)

    return {
        "success": True,
        "campaign": name,
        "template": template,
        "display_name": display_name or name,
    }


def switch(state_mgr, name: str) -> Dict[str, Any]:
    """切换到另一个战役"""
    campaign_dir = state_mgr.campaigns_dir / name
    state_file = campaign_dir / "state.json"
    if not state_file.exists():
        return {"success": False, "error": f"战役 {name} 不存在"}

    state_mgr.campaign_name = name
    state_mgr._state = None  # 清空缓存

    with open(state_file, "r", encoding="utf-8") as f:
        s = json.load(f)
    state_mgr.template_name = s.get("template", "dnd5e")

    return {"success": True, "campaign": name, "template": state_mgr.template_name}


def list_all(state_mgr) -> List[Dict]:
    """列出所有战役"""
    campaigns = []
    if state_mgr.campaigns_dir.exists():
        for d in state_mgr.campaigns_dir.iterdir():
            if d.is_dir():
                state_file = d / "state.json"
                info = {"name": d.name}
                if state_file.exists():
                    try:
                        with open(state_file, "r", encoding="utf-8") as f:
                            s = json.load(f)
                        info["display_name"] = s.get("campaign", d.name)
                        info["template"] = s.get("template", "")
                        info["version"] = s.get("version", 0)
                    except Exception:
                        pass
                campaigns.append(info)
    return campaigns


def delete(state_mgr, name: str) -> Dict[str, Any]:
    """删除战役（危险操作）"""
    campaign_dir = state_mgr.campaigns_dir / name
    if not campaign_dir.exists():
        return {"success": False, "error": f"战役 {name} 不存在"}
    shutil.rmtree(campaign_dir)
    if state_mgr.campaign_name == name:
        state_mgr.campaign_name = "default"
        state_mgr._state = None
    return {"success": True, "deleted": name}


__all__ = ["create", "switch", "list_all", "delete"]
