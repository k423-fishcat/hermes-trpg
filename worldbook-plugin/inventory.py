"""背包与物品系统（Inventory & Items）

物品模型 + 背包管理器 + 装备系统。
数据存在 state.inventory 列表中，装备状态影响玩家属性（AC、攻击加值等）。

物品类型：
- weapon: 武器
- armor: 护甲
- shield: 盾牌
- potion: 药水
- scroll: 卷轴
- tool: 工具
- wondrous: 奇物（魔法物品）
- ring / amulet / cloak / boots / helmet: 各种装备位
- consumable: 消耗品
- treasure: 财宝（宝石、艺术品等）
- misc: 杂物

装备槽位：
- main_hand（主手武器）
- off_hand（副手武器/盾牌）
- body（护甲）
- head（头盔/帽子）
- feet（靴子）
- hands（手套/护腕）
- neck（护符/项链）
- ring_right（右戒指）
- ring_left（左戒指）
- back（披风）
- waist（腰带）
"""

import time
from typing import Any, Dict, List, Optional


# 装备槽位定义
EQUIPMENT_SLOTS = [
    "main_hand", "off_hand", "body", "head", "feet",
    "hands", "neck", "ring_right", "ring_left", "back", "waist",
]

# 物品类型 → 默认装备槽映射
TYPE_TO_SLOT = {
    "weapon": "main_hand",
    "armor": "body",
    "shield": "off_hand",
    "helmet": "head",
    "boots": "feet",
    "gloves": "hands",
    "amulet": "neck",
    "ring": "ring_right",
    "cloak": "back",
    "belt": "waist",
}


class Item:
    """物品数据模型"""

    def __init__(self, item_id: str = "", name: str = "",
                 item_type: str = "misc",
                 description: str = "",
                 weight: float = 0.0,
                 value: int = 0,  # 铜币？用金币简化
                 rarity: str = "普通",
                 properties: Dict[str, Any] = None,
                 quantity: int = 1,
                 equipped: bool = False,
                 slot: str = "",
                 attunement_required: bool = False,
                 attuned: bool = False,
                 magical: bool = False,
                 **kwargs):
        self.id = item_id
        self.name = name
        self.type = item_type
        self.description = description
        self.weight = weight
        self.value = value  # 金币
        self.rarity = rarity
        self.properties = properties or {}
        self.quantity = max(1, quantity)
        self.equipped = equipped
        self.slot = slot or TYPE_TO_SLOT.get(item_type, "")
        self.attunement_required = attunement_required
        self.attuned = attuned
        self.magical = magical
        # 额外属性
        for k, v in kwargs.items():
            if not hasattr(self, k):
                setattr(self, k, v)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "weight": self.weight,
            "value": self.value,
            "rarity": self.rarity,
            "properties": self.properties,
            "quantity": self.quantity,
            "equipped": self.equipped,
            "slot": self.slot,
            "attunement_required": self.attunement_required,
            "attuned": self.attuned,
            "magical": self.magical,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Item":
        return cls(**data)


class InventoryManager:
    """背包管理器"""

    def __init__(self, state_mgr):
        self.state = state_mgr

    # ----------------------------------------------------------------
    # 基础 CRUD
    # ----------------------------------------------------------------

    def list_items(self, item_type: str = "", equipped_only: bool = False) -> List[Dict]:
        """列出背包物品"""
        inventory = self._get_inventory()
        result = []
        for item_data in inventory:
            if item_type and item_data.get("type") != item_type:
                continue
            if equipped_only and not item_data.get("equipped"):
                continue
            result.append(item_data)
        return result

    def get_item(self, item_id: str) -> Optional[Dict]:
        """获取单个物品"""
        inventory = self._get_inventory()
        for item in inventory:
            if item.get("id") == item_id:
                return item
        # 也试试按名字找
        for item in inventory:
            if item.get("name", "").lower() == item_id.lower():
                return item
        return None

    def add_item(self, item: Dict, quantity: int = 1,
                 source: str = "") -> Dict[str, Any]:
        """添加物品到背包

        如果是可堆叠的物品（同 ID 且数量 > 1），直接累加数量。
        否则添加新条目。
        """
        if quantity <= 0:
            return {"success": False, "error": "添加数量必须为正数"}
        inventory = self._get_inventory()
        item_id = item.get("id", item.get("name", ""))

        # 查找是否已存在
        existing = None
        for inv_item in inventory:
            if inv_item.get("id") == item_id and inv_item.get("type") in ["potion", "consumable", "ammo", "treasure", "misc"]:
                # 可堆叠物品
                existing = inv_item
                break

        if existing:
            existing["quantity"] = existing.get("quantity", 1) + quantity
            action = f"获得 {quantity}x {item.get('name', item_id)}（堆叠）"
        else:
            new_item = dict(item)
            new_item.setdefault("quantity", quantity)
            new_item.setdefault("id", item_id)
            new_item.setdefault("equipped", False)
            inventory.append(new_item)
            action = f"获得 {quantity}x {item.get('name', item_id)}"

        if source:
            action += f"（{source}）"

        self._save_inventory(inventory, action)
        return {
            "success": True,
            "item_id": item_id,
            "name": item.get("name", item_id),
            "quantity": quantity,
            "total_quantity": (existing or new_item).get("quantity", 1),
        }

    def remove_item(self, item_id: str, quantity: int = 1,
                    reason: str = "") -> Dict[str, Any]:
        """移除物品"""
        if quantity <= 0:
            return {"success": False, "error": "移除数量必须为正数"}
        inventory = self._get_inventory()

        for i, item in enumerate(inventory):
            if item.get("id") == item_id or item.get("name") == item_id:
                current_qty = item.get("quantity", 1)
                if quantity >= current_qty:
                    # 全部移除
                    removed = inventory.pop(i)
                    action = f"失去 {current_qty}x {item.get('name', item_id)}"
                    if reason:
                        action += f"（{reason}）"
                    self._save_inventory(inventory, action)
                    return {
                        "success": True,
                        "item_id": item_id,
                        "name": item.get("name", item_id),
                        "quantity_removed": current_qty,
                        "remaining": 0,
                    }
                else:
                    # 减少数量
                    item["quantity"] = current_qty - quantity
                    action = f"使用/失去 {quantity}x {item.get('name', item_id)}"
                    if reason:
                        action += f"（{reason}）"
                    self._save_inventory(inventory, action)
                    return {
                        "success": True,
                        "item_id": item_id,
                        "name": item.get("name", item_id),
                        "quantity_removed": quantity,
                        "remaining": current_qty - quantity,
                    }

        return {"success": False, "error": f"物品不存在: {item_id}"}

    # ----------------------------------------------------------------
    # 装备系统
    # ----------------------------------------------------------------

    def equip(self, item_id: str) -> Dict[str, Any]:
        """装备物品

        如果该槽位已有装备，先卸下旧的再装新的。
        装备后自动重新计算玩家 AC。

        D&D 5e 规则：
        - 需要同调的物品必须先 attune() 才能装备
        - 同时只能同调 3 件魔法物品
        """
        inventory = self._get_inventory()

        # 找到要装备的物品
        target = None
        target_idx = -1
        for i, item in enumerate(inventory):
            if item.get("id") == item_id or item.get("name") == item_id:
                target = item
                target_idx = i
                break

        if not target:
            return {"success": False, "error": f"物品不存在: {item_id}"}

        if target.get("type") not in TYPE_TO_SLOT and not target.get("slot"):
            return {"success": False,
                    "error": f"{target.get('name')} 不是可装备物品"}

        slot = target.get("slot") or TYPE_TO_SLOT.get(target.get("type"), "")
        if not slot:
            return {"success": False, "error": "无法确定装备槽位"}

        # 检查同调：先 attune 才能装备
        if target.get("attunement_required") and not target.get("attuned"):
            return {"success": False, "error": f"{target['name']} 需要先同调（attune）才能装备"}

        # 卸下同槽位的旧装备
        unequipped = None
        for i, item in enumerate(inventory):
            if item.get("equipped") and item.get("slot") == slot and i != target_idx:
                item["equipped"] = False
                unequipped = item.get("name")
                break

        # 装备新的
        target["equipped"] = True
        if not target.get("slot"):
            target["slot"] = slot

        action = f"装备: {target['name']}"
        if unequipped:
            action += f"（换下 {unequipped}）"

        self._save_inventory(inventory, action)

        # 重新计算 AC
        ac_change = self._recalculate_ac(inventory)

        return {
            "success": True,
            "item_name": target["name"],
            "slot": slot,
            "unequipped": unequipped,
            "new_ac": ac_change.get("new_ac", 10),
            "ac_change": ac_change.get("change", 0),
        }

    def attune(self, item_id: str) -> Dict[str, Any]:
        """同调魔法物品

        D&D 5e 规则（PHB p. 138, DMG p. 214-215）：
        - 需 1 短休或更长时间才能同调
        - 同时只能同调 3 件魔法物品
        - 同一物品只能被一个角色同调
        """
        inventory = self._get_inventory()
        target = None
        for item in inventory:
            if item.get("id") == item_id or item.get("name") == item_id:
                target = item
                break
        if not target:
            return {"success": False, "error": f"物品不存在: {item_id}"}

        if not target.get("attunement_required"):
            return {"success": False, "error": f"{target.get('name')} 不需要同调"}

        if target.get("attuned"):
            return {"success": False, "error": f"{target.get('name')} 已经同调过了"}

        # 同调上限检查（PHB 规则：同时最多 3 件）
        current_attuned = sum(
            1 for it in inventory
            if it.get("attunement_required") and it.get("attuned")
        )
        if current_attuned >= 3:
            return {
                "success": False,
                "error": (
                    f"同调槽已满（当前 {current_attuned}/3）。需先解除其他同调"
                    f"物品（attune 3 件上限，PHB 规则）"
                ),
                "attunement_count": current_attuned,
                "max": 3,
            }

        target["attuned"] = True
        self._save_inventory(inventory, f"同调: {target.get('name')}")
        return {
            "success": True,
            "item_name": target.get("name"),
            "attunement_count": current_attuned + 1,
            "max": 3,
        }

    def unattune(self, item_id: str) -> Dict[str, Any]:
        """解除同调"""
        inventory = self._get_inventory()
        for item in inventory:
            if item.get("id") == item_id or item.get("name") == item_id:
                if not item.get("attuned"):
                    return {"success": False, "error": f"{item.get('name')} 未同调"}
                item["attuned"] = False
                self._save_inventory(inventory, f"解除同调: {item.get('name')}")
                return {"success": True, "item_name": item.get("name")}
        return {"success": False, "error": f"物品不存在: {item_id}"}

    def list_attuned(self) -> List[Dict]:
        """列出所有已同调的物品"""
        return [it for it in self._get_inventory() if it.get("attuned")]

    def unequip(self, item_id: str) -> Dict[str, Any]:
        """卸下装备"""
        inventory = self._get_inventory()

        for item in inventory:
            if item.get("id") == item_id or item.get("name") == item_id:
                if not item.get("equipped"):
                    return {"success": False, "error": f"{item.get('name')} 未装备"}
                item["equipped"] = False
                action = f"卸下: {item['name']}"
                self._save_inventory(inventory, action)
                ac_change = self._recalculate_ac(inventory)
                return {
                    "success": True,
                    "item_name": item["name"],
                    "new_ac": ac_change.get("new_ac", 10),
                    "ac_change": ac_change.get("change", 0),
                }

        return {"success": False, "error": f"物品不存在: {item_id}"}

    def list_equipped(self) -> Dict[str, Dict]:
        """列出所有已装备物品（按槽位）"""
        inventory = self._get_inventory()
        equipped = {}
        for item in inventory:
            if item.get("equipped"):
                slot = item.get("slot", "unknown")
                equipped[slot] = item
        return equipped

    # ----------------------------------------------------------------
    # AC 计算
    # ----------------------------------------------------------------

    def _recalculate_ac(self, inventory: List[Dict] = None) -> Dict[str, Any]:
        """重新计算玩家 AC 并更新状态

        DnD 5e AC 计算规则（简化）：
        - 无护甲：10 + 敏捷调整
        - 轻甲：护甲 AC + 敏捷调整
        - 中甲：护甲 AC + 敏捷调整（最多 +2）
        - 重甲：护甲 AC（不加固敏）
        - 盾牌：+2 AC
        - 魔法加值：从装备 properties 累加
        """
        if inventory is None:
            inventory = self._get_inventory()

        player = self.state.get("player") or {}
        dex_score = player.get("abilities", {}).get("dex", 10)
        dex_mod = (dex_score - 10) // 2

        old_ac = player.get("ac", 10)
        base_ac = 10  # 无护甲
        armor_type = "none"
        shield_bonus = 0
        magic_bonus = 0

        for item in inventory:
            if not item.get("equipped"):
                continue
            itype = item.get("type")

            if itype == "armor":
                base_ac = item.get("ac", 10)
                armor_type = item.get("armor_type", "light")
                magic_bonus += item.get("properties", {}).get("ac_bonus", 0)

            elif itype == "shield":
                shield_bonus = 2
                magic_bonus += item.get("properties", {}).get("ac_bonus", 0)

            # 其他装备的 AC 加值（魔法物品）
            elif item.get("properties", {}).get("ac_bonus"):
                magic_bonus += item["properties"]["ac_bonus"]

        # 计算敏捷加值
        if armor_type == "none":
            dex_ac = dex_mod
        elif armor_type == "light":
            dex_ac = dex_mod
        elif armor_type == "medium":
            dex_ac = min(2, dex_mod)
        else:  # heavy
            dex_ac = 0

        new_ac = base_ac + dex_ac + shield_bonus + magic_bonus
        change = new_ac - old_ac

        # 更新状态
        player["ac"] = new_ac
        self.state.update(
            {"player": player},
            reason=f"AC 变化: {old_ac} → {new_ac}（{change:+d}）",
            actor="系统"
        )

        return {"old_ac": old_ac, "new_ac": new_ac, "change": change, "armor_type": armor_type}

    def current_ac(self) -> Dict[str, Any]:
        """当前 AC 详情"""
        player = self.state.get("player") or {}
        return {
            "ac": player.get("ac", 10),
            "details": self._ac_details(),
        }

    def _ac_details(self) -> str:
        """AC 详细组成"""
        player = self.state.get("player") or {}
        dex_score = player.get("abilities", {}).get("dex", 10)
        dex_mod = (dex_score - 10) // 2
        equipped = self.list_equipped()

        parts = []
        armor = equipped.get("body")
        if armor:
            parts.append(f"{armor['name']}({armor.get('ac', 0)})")
            atype = armor.get("armor_type", "light")
            if atype == "medium":
                parts.append(f"敏捷(最多+{min(2, dex_mod)})")
            elif atype == "heavy":
                parts.append("重甲(无敏捷)")
            else:
                parts.append(f"敏捷({dex_mod:+d})")
        else:
            parts.append(f"无甲 10 + 敏捷({dex_mod:+d})")

        shield = equipped.get("off_hand")
        if shield and shield.get("type") == "shield":
            parts.append("盾牌(+2)")

        # 魔法加值
        magic = 0
        for slot, item in equipped.items():
            bonus = item.get("properties", {}).get("ac_bonus", 0)
            if bonus:
                magic += bonus
                parts.append(f"{item['name']}(+{bonus})")

        return " + ".join(parts)

    # ----------------------------------------------------------------
    # 物品使用（消耗品）
    # ----------------------------------------------------------------

    def use_item(self, item_id: str, target: str = "self") -> Dict[str, Any]:
        """使用物品（消耗品）

        支持：药水、卷轴等
        效果包括：恢复 HP、获得状态效果、获得暂时 buff 等
        """
        inventory = self._get_inventory()

        for i, item in enumerate(inventory):
            if item.get("id") == item_id or item.get("name") == item_id:
                if item.get("type") not in ["potion", "scroll", "consumable"]:
                    return {"success": False, "error": f"{item['name']} 不是可使用物品"}

                effects = item.get("properties", {}).get("effects", {})
                result = {"success": True, "item_name": item["name"], "effects": {}}

                player = self.state.get("player") or {}

                # 恢复 HP
                if "heal" in effects:
                    hp = player.get("hp", {})
                    heal_amount = effects["heal"]
                    old_hp = hp.get("current", 0)
                    max_hp = hp.get("max", old_hp)
                    new_hp = min(max_hp, old_hp + heal_amount)
                    actual_heal = new_hp - old_hp
                    hp["current"] = new_hp
                    player["hp"] = hp
                    result["effects"]["healed"] = actual_heal

                # 暂时加值
                if "buff" in effects:
                    buff = effects["buff"]
                    # 存在 conditions 里，记为暂时效果
                    conds = player.setdefault("conditions", [])
                    conds.append({
                        "name": buff.get("name", item["name"]),
                        "type": "buff",
                        "effect": buff.get("effect", ""),
                        "duration": buff.get("duration", "1小时"),
                        "source": item["name"],
                    })
                    result["effects"]["buff"] = buff.get("name", item["name"])

                self.state.update(
                    {"player": player},
                    reason=f"使用 {item['name']}",
                    actor="玩家"
                )

                # 扣除物品
                qty = item.get("quantity", 1)
                if qty <= 1:
                    inventory.pop(i)
                else:
                    item["quantity"] = qty - 1

                self._save_inventory(inventory, f"使用 1x {item['name']}")

                return result

        return {"success": False, "error": f"物品不存在: {item_id}"}

    # ----------------------------------------------------------------
    # 金币
    # ----------------------------------------------------------------

    def add_gold(self, amount: int, reason: str = "") -> Dict[str, Any]:
        """获得金币"""
        player = self.state.get("player") or {}
        old = player.get("gold", 0)
        new = old + amount
        player["gold"] = new
        self.state.update(
            {"player": player},
            reason=f"获得 {amount} 金币" + (f"（{reason}）" if reason else ""),
            actor="系统"
        )
        return {"success": True, "amount": amount, "old": old, "new": new}

    def spend_gold(self, amount: int, reason: str = "") -> Dict[str, Any]:
        """花费金币"""
        if amount <= 0:
            return {"success": False, "error": "花费金额必须为正数"}
        player = self.state.get("player") or {}
        old = player.get("gold", 0)
        if old < amount:
            return {"success": False, "error": f"金币不足（有 {old}，需要 {amount}）"}
        new = old - amount
        player["gold"] = new
        self.state.update(
            {"player": player},
            reason=f"花费 {amount} 金币" + (f"（{reason}）" if reason else ""),
            actor="玩家"
        )
        return {"success": True, "amount": amount, "old": old, "new": new}

    def get_gold(self) -> int:
        """当前金币"""
        player = self.state.get("player") or {}
        return player.get("gold", 0)

    # ----------------------------------------------------------------
    # 内部方法
    # ----------------------------------------------------------------

    def _get_inventory(self) -> List[Dict]:
        """获取背包列表"""
        inv = self.state.get("inventory")
        if isinstance(inv, list):
            return inv
        return []

    def _save_inventory(self, inventory: List[Dict], reason: str):
        """保存背包"""
        self.state.update({"inventory": inventory}, reason=reason, actor="系统")

    def total_weight(self) -> float:
        """总负重（可选使用）"""
        inventory = self._get_inventory()
        total = 0.0
        for item in inventory:
            total += item.get("weight", 0) * item.get("quantity", 1)
        return round(total, 1)
