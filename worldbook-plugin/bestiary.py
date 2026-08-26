"""怪物图鉴（Bestiary）

独立的怪物静态数据库。和世界书分离——世界书是战役设定，图鉴是怪物模板库。
战斗开始时从图鉴实例化怪物。

数据存储：data/bestiary/ 目录下的 JSON 文件，每个文件一个怪物（或一组同类型）。
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import atomic_write_json

logger = logging.getLogger(__name__)


# 怪物模板示例结构
MONSTER_TEMPLATE = {
    "id": "",           # 唯一标识，如 "goblin"
    "name": "",         # 中文名
    "name_en": "",      # 英文名
    "size": "中型",     # 微型/小型/中型/大型/巨型/超巨型
    "type": "类人生物",  # 怪物类型
    "alignment": "中立邪恶",
    "cr": 0,            # 挑战等级
    "xp": 0,            # 经验值
    "source": "",       # 来源（SRD/自制/模组名）
    "stats": {
        "hp": "",               # HP 骰子表达，如 "7 (2d6)"
        "hp_average": 0,        # HP 平均值
        "ac": 10,               # 护甲等级
        "ac_source": "",        # AC 来源，如 "皮甲 + 盾牌"
        "speed": 30,            # 步行速度（尺）
        "speed_special": {},    # 特殊速度，如 {"游泳": 30, "飞行": 60}
    },
    "abilities": {
        "str": 10, "dex": 10, "con": 10,
        "int": 10, "wis": 10, "cha": 10,
    },
    "saving_throws": {},     # 豁免熟练，如 {"dex": 2, "con": 2}
    "skills": {},            # 技能熟练，如 {"隐匿": 6, "察觉": 4}
    "damage_resistances": [], # 伤害抗性
    "damage_immunities": [],  # 伤害免疫
    "condition_immunities": [], # 状态免疫
    "senses": {},            # 感官，如 {"黑暗视觉": 60, "被动察觉": 10}
    "languages": [],         # 语言
    "challenge": "",         # CR 字符串，如 "1/4"
    "proficiency_bonus": 2,
    "attacks": [
        # {
        #   "name": "短剑",
        #   "type": "近战武器攻击",
        #   "hit_bonus": 4,
        #   "range": "5尺",
        #   "damage": "1d6+2",
        #   "damage_type": "穿刺",
        #   "extra": ""  # 额外效果
        # }
    ],
    "special_abilities": [
        # {"name": "鬼祟偷袭", "desc": "..."},
    ],
    "actions": [
        # {"name": "多重攻击", "desc": "..."},
    ],
    "reactions": [
        # {"name": "盾牌格挡", "desc": "..."},
    ],
    "legendary_actions": [],   # 传奇动作
    "lair_actions": [],        # 巢穴动作
    "equipment": [],           # 携带物品
    "description": "",         # 风味描述
    "tags": [],                # 标签，用于搜索分类
    "aliases": [],             # 别名（英文原名等），用于中文搜索
}


class Bestiary:
    """怪物图鉴管理器"""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir) / "bestiary"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, dict] = {}

    # ----------------------------------------------------------------
    # CRUD
    # ----------------------------------------------------------------

    def list_monsters(self, tag: str = "", type_filter: str = "",
                      cr_min: float = None, cr_max: float = None) -> List[Dict]:
        """列出怪物，可按标签/类型/CR 过滤"""
        results = []
        for f in self.data_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    m = json.load(fp)
                # 过滤
                if tag and tag not in m.get("tags", []):
                    continue
                if type_filter and m.get("type", "") != type_filter:
                    continue
                if cr_min is not None and m.get("cr", 0) < cr_min:
                    continue
                if cr_max is not None and m.get("cr", 0) > cr_max:
                    continue
                # 返回精简信息
                results.append({
                    "id": m.get("id", f.stem),
                    "name": m.get("name", f.stem),
                    "type": m.get("type", ""),
                    "cr": m.get("cr", 0),
                    "size": m.get("size", ""),
                    "alignment": m.get("alignment", ""),
                })
            except Exception as e:
                logger.warning(f"[bestiary] 怪物文件损坏，跳过: {f} ({type(e).__name__}: {e})")
                continue

        results.sort(key=lambda m: (m.get("cr", 0), m.get("name", "")))
        return results

    def get_monster(self, monster_id: str) -> Optional[Dict]:
        """获取怪物完整数据"""
        if monster_id in self._cache:
            return self._cache[monster_id]

        f = self.data_dir / f"{monster_id}.json"
        if not f.exists():
            return None

        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            self._cache[monster_id] = data
            return data
        except Exception as e:
            logger.warning(f"[bestiary] 怪物卡损坏: {monster_id} ({type(e).__name__}: {e})")
            return None

    def add_monster(self, monster_data: dict, overwrite: bool = False) -> Dict[str, Any]:
        """添加怪物（原子写入）

        Args:
            monster_data: 怪物数据
            overwrite: 已存在时是否覆盖（默认 False 返回错误）
        """
        mid = monster_data.get("id")
        if not mid:
            # 用名字生成 id
            name = monster_data.get("name", "monster")
            mid = name.lower().replace(" ", "_")
            monster_data["id"] = mid

        f = self.data_dir / f"{mid}.json"
        if f.exists() and not overwrite:
            return {"success": False, "error": f"怪物 {mid} 已存在"}

        atomic_write_json(f, monster_data)

        self._cache.pop(mid, None)
        return {"success": True, "id": mid, "name": monster_data.get("name", mid)}

    def update_monster(self, monster_id: str, updates: dict) -> Dict[str, Any]:
        """更新怪物数据（原子写入）"""
        existing = self.get_monster(monster_id)
        if not existing:
            return {"success": False, "error": f"怪物不存在: {monster_id}"}

        # 深度合并
        def merge(base, override):
            for k, v in override.items():
                if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                    merge(base[k], v)
                else:
                    base[k] = v

        merge(existing, updates)

        f = self.data_dir / f"{monster_id}.json"
        atomic_write_json(f, existing)

        self._cache.pop(monster_id, None)
        return {"success": True, "id": monster_id}

    def delete_monster(self, monster_id: str) -> Dict[str, Any]:
        """删除怪物"""
        f = self.data_dir / f"{monster_id}.json"
        if not f.exists():
            return {"success": False, "error": f"怪物不存在: {monster_id}"}
        f.unlink()
        self._cache.pop(monster_id, None)
        return {"success": True, "id": monster_id}

    # ----------------------------------------------------------------
    # 搜索
    # ----------------------------------------------------------------

    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """搜索怪物（名称/标签/类型/描述）"""
        query_lower = query.lower()
        results = []
        for f in self.data_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    m = json.load(fp)
            except Exception as e:
                logger.warning(f"[bestiary] 搜索跳过损坏文件: {f} ({type(e).__name__}: {e})")
                continue

            score = 0
            name = m.get("name", "").lower()
            name_en = m.get("name_en", "").lower()
            mid = m.get("id", "").lower()

            if query_lower in name:
                score += 10
            if query_lower in name_en:
                score += 8
            for alias in m.get("aliases", []):
                if query_lower in str(alias).lower():
                    score += 6
                    break
            if query_lower in mid:
                score += 5

            for tag in m.get("tags", []):
                if query_lower in tag.lower():
                    score += 3

            mtype = m.get("type", "").lower()
            if query_lower in mtype:
                score += 3

            desc = m.get("description", "").lower()
            if query_lower in desc:
                score += 2

            if score > 0:
                results.append({
                    "id": m.get("id", ""),
                    "name": m.get("name", ""),
                    "type": m.get("type", ""),
                    "cr": m.get("cr", 0),
                    "score": score,
                })

        results.sort(key=lambda m: (-m["score"], m.get("cr", 0)))
        return results[:limit]

    # ----------------------------------------------------------------
    # 实例化（用于战斗）
    # ----------------------------------------------------------------

    def instantiate(self, monster_id: str, instance_name: str = "") -> Optional[Dict]:
        """从模板实例化一个战斗用怪物

        返回实例数据（静态数据 + 动态字段的初始值）
        """
        template = self.get_monster(monster_id)
        if not template:
            return None

        stats = template.get("stats", {})
        hp_max = stats.get("hp_average", 0)

        instance = {
            "template_id": monster_id,
            "name": instance_name or template.get("name", monster_id),
            "hp": {
                "max": hp_max,
                "current": hp_max,
                "temp": 0,
            },
            "ac": stats.get("ac", 10),
            "speed": stats.get("speed", 30),
            "conditions": [],
            "position": None,
            "reactions_used": 0,
            "concentration_on": None,
            "legendary_used": 0,
            "is_alive": True,
            # 模板引用（不复制，节省空间）
            "_template": template,
        }
        return instance

    def get_template_stats(self, monster_id: str) -> Optional[Dict]:
        """获取怪物模板的战斗相关静态数据（精简版）"""
        m = self.get_monster(monster_id)
        if not m:
            return None
        return {
            "id": m.get("id"),
            "name": m.get("name"),
            "hp_average": m.get("stats", {}).get("hp_average", 0),
            "hp_formula": m.get("stats", {}).get("hp", ""),
            "ac": m.get("stats", {}).get("ac", 10),
            "speed": m.get("stats", {}).get("speed", 30),
            "abilities": m.get("abilities", {}),
            "attacks": m.get("attacks", []),
            "special_abilities": m.get("special_abilities", []),
            "damage_resistances": m.get("damage_resistances", []),
            "damage_immunities": m.get("damage_immunities", []),
            "damage_vulnerabilities": m.get("damage_vulnerabilities", []),
            "condition_immunities": m.get("condition_immunities", []),
            "cr": m.get("cr", 0),
            "size": m.get("size", ""),
        }

    # ----------------------------------------------------------------
    # 批量操作
    # ----------------------------------------------------------------

    def import_from_json(self, filepath: str) -> Dict[str, Any]:
        """从 JSON 批量导入怪物"""
        fpath = Path(filepath)
        if not fpath.exists():
            return {"success": False, "error": "文件不存在"}

        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 支持两种格式：单个怪物 dict / 怪物列表
        if isinstance(data, dict) and "id" in data:
            monsters = [data]
        elif isinstance(data, list):
            monsters = data
        elif isinstance(data, dict) and "monsters" in data:
            monsters = data["monsters"]
        else:
            return {"success": False, "error": "格式不支持"}

        imported = []
        failed = []
        for m in monsters:
            r = self.add_monster(m)
            if r.get("success"):
                imported.append(r["name"])
            else:
                failed.append(m.get("name", m.get("id", "?")) + ": " + r.get("error", ""))

        return {
            "success": True,
            "imported_count": len(imported),
            "failed_count": len(failed),
            "imported": imported,
            "failed": failed,
        }

    def count(self) -> int:
        """怪物总数"""
        return len(list(self.data_dir.glob("*.json")))

    def import_from_srd(self, srd_data: dict, overwrite: bool = False) -> Dict[str, Any]:
        """从 dnd-rules SRD 数据导入一只怪物到本地图鉴

        Args:
            srd_data: dnd_get_creature 返回的 structuredContent
            overwrite: 已存在是否覆盖

        Returns:
            导入结果
        """
        from .bestiary_import import convert_creature_to_bestiary

        converted = convert_creature_to_bestiary(srd_data)
        monster_id = converted["id"]

        # 检查是否已存在
        existing = self.get_monster(monster_id)
        if existing and not overwrite:
            return {
                "success": False,
                "error": f"怪物已存在: {monster_id}",
                "monster_id": monster_id,
                "name": converted["name"],
            }

        result = self.add_monster(converted, overwrite=overwrite)
        result["monster_id"] = result.get("id") or monster_id
        result["name"] = converted["name"]
        return result
