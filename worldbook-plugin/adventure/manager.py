"""adventure.manager - 模组管理器

管理已安装的模组，支持激活/停用/叠加，模组数据持久化。
- 模组来源：data/adventures/ 目录下的所有模组
- 激活状态：存在 state.campaign.active_modules 里
- 激活流程：调用 adventure.loader.import_module 把数据导入运行时系统
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class ModuleManager:
    """模组管理器"""

    def __init__(self, state_mgr, adventures_dir: Path, worldbook_store=None):
        self.state = state_mgr
        self.adventures_dir = Path(adventures_dir)
        self.wb_store = worldbook_store

    # ----------------------------------------------------------------
    # 发现/列出模组
    # ----------------------------------------------------------------

    def list_available(self) -> List[Dict[str, Any]]:
        """列出所有可用模组（data/adventures/ 下的）"""
        from .loader import detect_format

        if not self.adventures_dir.exists():
            return []

        result = []
        for item in sorted(self.adventures_dir.iterdir()):
            if item.name.startswith('.') or item.name.startswith('_'):
                continue
            if not item.is_dir():
                continue

            # 找 adventure.json 或 zim wiki 源
            info = {"id": item.name, "name": item.name}

            adv_json = item / "adventure.json"
            if adv_json.exists():
                try:
                    with open(adv_json, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    info["name"] = data.get("name", item.name)
                    info["description"] = data.get("description", "")
                    info["system"] = data.get("system", "dnd5e")
                    info["format"] = "native"
                    # 统计条目数
                    entries = data.get("worldbook_entries", [])
                    info["entry_count"] = len(entries)
                    info["npc_count"] = len(data.get("npcs", []))
                    info["quest_count"] = len(data.get("quests", []))
                    info["encounter_count"] = len(data.get("encounters", []))
                except Exception as e:
                    info["error"] = str(e)
                result.append(info)
                continue

            # 检查 source 子目录（zim wiki）
            source_dir = item / "source"
            if source_dir.exists():
                fmt = detect_format(str(source_dir))
                if fmt:
                    info["format"] = fmt
                    # 粗略统计
                    txt_count = len(list(source_dir.glob("**/*.txt")))
                    info["entry_count"] = txt_count
                    result.append(info)

            # 根目录就是 zim wiki
            fmt = detect_format(str(item))
            if fmt and "format" not in info:
                info["format"] = fmt
                txt_count = len(list(item.glob("**/*.txt")))
                info["entry_count"] = txt_count
                result.append(info)

        return result

    def list_active(self) -> List[str]:
        """列出当前已激活的模组 ID 列表"""
        campaign = self.state.get("campaign")
        if isinstance(campaign, dict):
            return list(campaign.get("active_modules", []))
        # campaign 是字符串（旧格式），返回空列表
        return []

    def is_active(self, module_id: str) -> bool:
        """检查模组是否已激活"""
        return module_id in self.list_active()

    # ----------------------------------------------------------------
    # 激活 / 停用
    # ----------------------------------------------------------------

    def activate(self, module_id: str, **kwargs) -> Dict[str, Any]:
        """激活一个模组

        将模组数据导入到运行时系统：世界书 + NPC + 任务 + 遭遇 + 世界标记
        """
        # 找模组路径
        module_dir = self.adventures_dir / module_id
        if not module_dir.exists():
            return {"success": False, "error": f"模组不存在: {module_id}"}

        if self.is_active(module_id):
            return {"success": False, "error": f"模组已激活: {module_id}"}

        # 确定加载路径
        adv_json = module_dir / "adventure.json"
        source_dir = module_dir / "source"

        if adv_json.exists():
            load_path = str(adv_json)
        elif source_dir.exists():
            load_path = str(source_dir)
        else:
            load_path = str(module_dir)

        # 加载模组
        try:
            from .loader import load_module, import_module
            mod = load_module(load_path, module_id=module_id)
        except Exception as e:
            return {"success": False, "error": f"加载模组失败: {e}"}

        # 获取各管理器
        quest_mgr = kwargs.get("quest_mgr")
        npc_mgr = kwargs.get("npc_mgr")
        chron_mgr = kwargs.get("chron_mgr")

        # 导入
        result = import_module(
            mod,
            worldbook_store=self.wb_store,
            state_mgr=self.state,
            quest_mgr=quest_mgr,
            npc_mgr=npc_mgr,
            chron_mgr=chron_mgr,
            worldbook_name=module_id,
        )

        # 记录到激活列表（campaign.active_modules 路径）
        state = self.state.get()
        campaign = state.get("campaign", {})
        if isinstance(campaign, str):
            campaign = {}
        active = list(campaign.get("active_modules", []))
        if module_id not in active:
            active.append(module_id)
        campaign["active_modules"] = active
        state["campaign"] = campaign
        self.state.update(
            state,
            reason=f"激活模组: {mod.name}",
            actor="系统"
        )

        return {
            "success": True,
            "module_id": module_id,
            "module_name": mod.name,
            "entries_imported": result.get("entries_imported", 0),
            "npcs_imported": result.get("npcs_imported", 0),
            "quests_imported": result.get("quests_imported", 0),
            "encounters_imported": result.get("encounters_imported", 0),
            "world_flags_set": result.get("world_flags_set", 0),
            "errors": result.get("errors", []),
        }

    def deactivate(self, module_id: str) -> Dict[str, Any]:
        """停用模组（从激活列表移除，数据保留在状态里）

        注意：停用不会删除已经导入的数据（防止误操作丢数据）。
        如果需要完全清理，调用 purge 方法。
        """
        if not self.is_active(module_id):
            return {"success": False, "error": f"模组未激活: {module_id}"}

        # 从激活列表移除
        state = self.state.get()
        campaign = state.get("campaign", {})
        if isinstance(campaign, str):
            campaign = {}
        active = list(campaign.get("active_modules", []))
        if module_id in active:
            active.remove(module_id)
        campaign["active_modules"] = active
        state["campaign"] = campaign
        self.state.update(
            state,
            reason=f"停用模组: {module_id}",
            actor="系统"
        )

        return {
            "success": True,
            "module_id": module_id,
            "message": "模组已停用（数据保留在状态中）",
        }

    def get_module_info(self, module_id: str) -> Optional[Dict[str, Any]]:
        """获取模组详细信息"""
        available = self.list_available()
        for m in available:
            if m["id"] == module_id:
                m["active"] = self.is_active(module_id)
                return m
        return None
