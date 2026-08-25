"""从 Open5e REST API 拉取 SRD 数据并写入本地规则书快照。

这是**构建时工具**，不在插件运行时调用。
dnd-rules MCP 的后端就是 Open5e，所以这里直接调 REST API 更直接。

数据源：
- 2024 SRD: https://api.open5e.com/v2/  (document__key=srd-2024)
- 2014 SRD: https://api.open5e.com/v1/  (document__slug=wotc-srd)

使用方式：
    # 完整拉取 dnd5e 2024 SRD
    python -m worldbook_plugin.rules.mcp_sync --system dnd5e --edition 2024

    # 只拉某个分类
    python -m worldbook_plugin.rules.mcp_sync --category spells --edition 2024

    # 限速（默认 1 req/sec，避免触发 rate limit）
    python -m worldbook_plugin.rules.mcp_sync --rate 0.5
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import httpx
except ImportError:
    print("需要安装 httpx: pip install httpx")
    sys.exit(1)

from .zh_mapping import translate as _translate_zh


# Open5e API 基础 URL
OPEN5E_V1 = "https://api.open5e.com/v1"  # 2014 SRD
OPEN5E_V2 = "https://api.open5e.com/v2"  # 2024 SRD

# v1 vs v2 的 document 过滤参数不同
# v1 用 ?document__slug=wotc-srd
# v2 用 ?document__key=srd-2024

DEFAULT_TIMEOUT = 30.0
USER_AGENT = "worldbook-plugin-rules-sync/0.1 (TRPG plugin)"


# ═════════════════════════════════════════════════════════════
# 通用分页拉取
# ═════════════════════════════════════════════════════════════

def paginate(url: str, params: dict | None, rate: float = 1.0,
             transform: Optional[Callable[[dict], dict]] = None) -> list[dict]:
    """拉取一个分页 API 端点的所有结果"""
    results: list[dict] = []
    next_url: Optional[str] = url
    next_params = params or {}
    page = 0

    while next_url:
        try:
            resp = httpx.get(
                next_url,
                params=next_params if next_url == url else None,
                timeout=DEFAULT_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            print(f"  ✗ 请求失败 ({next_url}): {e}")
            break

        data = resp.json()
        items = data.get("results", [])
        if transform:
            items = [transform(item) for item in items]
        results.extend(items)

        next_url = data.get("next")
        next_params = {}  # next URL 已包含参数
        page += 1

        if page % 5 == 0:
            print(f"    ...已拉 {len(results)} 条（第 {page} 页）")

        time.sleep(rate)  # 限速

    return results


# ═════════════════════════════════════════════════════════════
# 数据规范化（v2 / v1 → 统一 schema）
# ═════════════════════════════════════════════════════════════

def normalize_spell_v2(s: dict) -> dict:
    """v2 spell → 本地 schema

    Open5e v2 没有中文名——name_zh 和 name_en 暂时都用英文。
    未来可加一个 zh_mapping.json 做英文→中文映射。
    """
    school = s.get("school", {})
    if isinstance(school, dict):
        school = school.get("name", "")

    # range 可能是 int（英尺数）或 str（如 "Self", "Touch"）
    range_val = s.get("range", "")
    if isinstance(range_val, int):
        range_str = f"{range_val} 尺"
    elif isinstance(range_val, str):
        range_str = range_val
    else:
        range_str = str(range_val)

    # 提取 name（不带 srd- 前缀）
    raw_name = s.get("name_en") or s.get("name") or s.get("key", "")
    name_slug = _slugify(raw_name)

    higher_levels = s.get("higher_level", "")
    if isinstance(higher_levels, str) and len(higher_levels) > 500:
        higher_levels = higher_levels[:500] + "..."

    return _translate_zh({
        "rule_id": f"rules.dnd5e.spells.{name_slug}",
        "name_zh": raw_name,  # Open5e v2 无中文——目前等同 name_en
        "name_en": s.get("name_en", s.get("name", "")),
        "level": int(s.get("level", 0)) if s.get("level") is not None else 0,
        "school": school,
        "casting_time": s.get("casting_time", ""),
        "range": range_str,
        "components": _parse_components(s.get("components", "")),
        "duration": s.get("duration", ""),
        "description": _truncate(s.get("desc", ""), 800),
        "higher_levels": higher_levels,
        "tags": _extract_spell_tags(s),
        "phb_page": s.get("page_no") or s.get("page") or None,
    })


def _slugify(name: str) -> str:
    """从法术名提取 slug（去掉 srd- 前缀、转下划线）"""
    import re
    s = str(name).lower().strip()
    # 去掉 document key 前缀（Open5e v2 会把 "srd-2024_fireball" 整个丢进 key）
    s = re.sub(r"^srd[-_]\d+[-_]?", "", s)
    s = re.sub(r"^wotc[-_]srd[-_]?", "", s)
    s = s.replace(" ", "_").replace("-", "_")
    s = re.sub(r"[^a-z0-9_一-鿿]", "", s)
    return s or "unnamed"


def normalize_spell_v1(s: dict) -> dict:
    """v1 spell → 本地 schema"""
    # v1 的 page 可能是 str（如 "Player's Handbook, p. 241"），要提取 int
    raw_page = s.get("page", "")
    phb_page = None
    if isinstance(raw_page, int):
        phb_page = raw_page
    elif isinstance(raw_page, str):
        import re
        m = re.search(r"(\d+)", raw_page)
        if m:
            phb_page = int(m.group(1))
    return _translate_zh({
        "rule_id": f"rules.dnd5e.spells.{s.get('slug', s.get('name', '').lower().replace(' ', '_'))}",
        "name_zh": s.get("name", ""),
        "name_en": s.get("name", ""),
        "level": int(s.get("level_int", s.get("level", 0)) or 0),
        "school": s.get("school", ""),
        "casting_time": s.get("casting_time", ""),
        "range": s.get("range_text", s.get("range", "")),
        "components": _parse_components(s.get("components", "")),
        "duration": s.get("duration", ""),
        "description": _truncate(s.get("desc", ""), 800),
        "higher_levels": s.get("higher_level", ""),
        "tags": _extract_spell_tags(s),
        "phb_page": phb_page,
    })


def normalize_class_v2(c: dict) -> dict:
    """v2 class → 本地 schema"""
    # 已知/准备型标记
    raw_name = c.get("name_en") or c.get("name") or c.get("key", "")
    name_en = raw_name.lower()
    name_slug = _slugify(raw_name)
    caster_type = _infer_caster_type(name_en, c)

    hit_die = c.get("hit_dice", "")
    if isinstance(hit_die, str) and hit_die.startswith("1d"):
        hit_die = hit_die  # 已经是 "1d6" 格式
    else:
        hit_die = ""

    return _translate_zh({
        "rule_id": f"rules.dnd5e.classes.{name_slug}",
        "name_zh": c.get("name", c.get("name_en", "")),
        "name_en": raw_name,
        "hit_die": hit_die,
        "primary_ability": _extract_primary_ability(c),
        "saves": _extract_saves(c),
        "caster_type": caster_type,
        "spellcasting_ability": _extract_spellcasting_ability(c),
        "phb_page": c.get("page_no") or None,
    })


def normalize_class_v1(c: dict) -> dict:
    """v1 class → 本地 schema"""
    raw_name = c.get("name") or ""
    name_slug = _slugify(raw_name)
    return _translate_zh({
        "rule_id": f"rules.dnd5e.classes.{name_slug}",
        "name_zh": raw_name,
        "name_en": raw_name,
        "hit_die": "",  # v1 没有这个字段
        "primary_ability": "",
        "saves": [],
        "caster_type": _infer_caster_type(raw_name.lower(), c),
        "spellcasting_ability": "",
        "phb_page": None,
    })


def normalize_condition_v2(c: dict) -> dict:
    """v2 condition → 本地 schema"""
    raw_name = c.get("name_en") or c.get("name") or c.get("key", "")
    return _translate_zh({
        "rule_id": f"rules.dnd5e.conditions.{_slugify(raw_name)}",
        "name_zh": raw_name,
        "name_en": raw_name,
        "summary": _truncate(c.get("desc", ""), 300),
        "phb_page": c.get("page_no") or None,
    })


def normalize_condition_v1(c: dict) -> dict:
    """v1 condition → 本地 schema"""
    raw_name = c.get("name") or c.get("key", "")
    return _translate_zh({
        "rule_id": f"rules.dnd5e.conditions.{_slugify(raw_name)}",
        "name_zh": raw_name,
        "name_en": raw_name,
        "summary": _truncate(c.get("desc", ""), 300),
        "phb_page": None,
    })


def normalize_creature_v2(cr: dict) -> dict:
    """v2 creature → 本地 schema

    v2 creature 在 `?expand=` 模式下返回完整结构化数据；
    非 expand 模式下走 desc 摘要。
    """
    raw_name = cr.get("name_en") or cr.get("name") or cr.get("key", "")

    # abilities: v2 两种格式
    # - 非 expand: list[dict{abbr, score}]
    # - expand: dict{strength: 21, dexterity: 9, ...}
    abilities = {}
    raw_abs = cr.get("ability_scores")
    if isinstance(raw_abs, dict):
        for k, v in raw_abs.items():
            if isinstance(v, (int, float)):
                abilities[k[:3].lower()] = int(v)
    elif isinstance(raw_abs, list):
        for ab in raw_abs:
            if isinstance(ab, dict):
                abbr = ab.get("abbr", "").lower()
                score = ab.get("score")
                if abbr and score is not None:
                    abilities[abbr] = score

    # 抗/免/易伤：v2 expand 模式下都在 resistances_and_immunities
    ri = cr.get("resistances_and_immunities", {}) or {}
    if ri:
        immunities = _extract_dmg_types(ri.get("damage_immunities", []))
        resistances = _extract_dmg_types(ri.get("damage_resistances", []))
        vulnerabilities = _extract_dmg_types(ri.get("damage_vulnerabilities", []))
    else:
        # 非 expand 模式：直接顶层 list
        immunities = _extract_dmg_types(cr.get("damage_immunities", []))
        resistances = _extract_dmg_types(cr.get("damage_resistances", []))
        vulnerabilities = _extract_dmg_types(cr.get("damage_vulnerabilities", []))

    # attacks: v2 list 端点的 expand 不展开 actions.attacks
    # （结构化攻击数据只有 detail 端点才完整；rules 摘要版只取 actions 文本）
    attacks = []
    # 非 expand 模式可能直接给 attacks
    if not attacks:
        for atk in cr.get("attacks", []) or []:
            if not isinstance(atk, dict):
                continue
            dmg_die = atk.get("damage_die", "d6").lower()
            dmg_count = atk.get("damage_die_count", 1)
            dmg_bonus = atk.get("damage_bonus", 0)
            dmg_str = f"{dmg_count}{dmg_die}"
            if dmg_bonus:
                dmg_str += f"{dmg_bonus:+d}"
            dt = atk.get("damage_type")
            if isinstance(dt, dict):
                dt = dt.get("name", "")
            attacks.append({
                "name": atk.get("name", "攻击"),
                "hit_bonus": atk.get("to_hit_mod", 0),
                "damage": dmg_str,
                "damage_type": dt or "",
            })

    # type: v2 expand 是 dict{"name": ...}
    type_info = cr.get("type", "")
    if isinstance(type_info, dict):
        type_info = type_info.get("name", "")

    # CR: expand 模式是 challenge_rating，float
    cr_val = cr.get("challenge_rating_decimal") or cr.get("challenge_rating") or cr.get("cr") or 0

    return _translate_zh({
        "rule_id": f"rules.dnd5e.creatures.{_slugify(raw_name)}",
        "name_zh": raw_name,
        "name_en": raw_name,
        "cr": cr_val,
        "type": type_info,
        "ac": cr.get("armor_class", 10),
        "hp_average": cr.get("hit_points", 0),
        "hp_formula": cr.get("hit_dice", ""),
        "speed": _extract_speed(cr.get("speed", {})),
        "abilities": abilities,
        "damage_resistances": resistances,
        "damage_immunities": immunities,
        "damage_vulnerabilities": vulnerabilities,
        "actions_summary": [
            {
                "name": a.get("name", ""),
                "action_type": a.get("action_type", "ACTION"),
                "desc": _truncate(a.get("desc", ""), 200),
            }
            for a in cr.get("actions", []) or []
            if isinstance(a, dict)
        ][:8],  # 限 8 条避免 JSON 爆炸
        "summary": _truncate(cr.get("desc", ""), 300),
        "phb_page": cr.get("page_no") or None,
    })


def _extract_dmg_types(items) -> list[str]:
    """从 v2 的 list[dict|str] 提取伤害类型字符串"""
    result = []
    for it in items or []:
        if isinstance(it, dict):
            name = it.get("name") or it.get("key", "")
            if name:
                result.append(name)
        elif isinstance(it, str):
            result.append(it)
    return result


def _extract_speed(speed) -> int:
    """从 v2 speed 提取步行速度（int）"""
    if isinstance(speed, int):
        return speed
    if isinstance(speed, dict):
        walk = speed.get("walk", 30)
        if isinstance(walk, dict):
            return walk.get("distance", 30)
        if isinstance(walk, (int, float)):
            return int(walk)
    return 30


def normalize_magic_item_v1(mi: dict) -> dict:
    """v1 magic item → 本地 schema"""
    raw_name = mi.get("name") or mi.get("slug", "")
    rarity = mi.get("rarity", "")
    if isinstance(rarity, dict):
        rarity = rarity.get("name", "")
    return _translate_zh({
        "rule_id": f"rules.dnd5e.items.{_slugify(raw_name)}",
        "name_zh": raw_name,
        "name_en": raw_name,
        "rarity": rarity,
        "attunement": bool(mi.get("requires_attunement", False)),
        "summary": _truncate(mi.get("desc", ""), 400),
        "phb_page": mi.get("page") or None,
    })


# ═════════════════════════════════════════════════════════════
# 辅助函数
# ═════════════════════════════════════════════════════════════

def _truncate(s: str, max_len: int) -> str:
    if not s:
        return ""
    s = s.strip()
    return s if len(s) <= max_len else s[:max_len] + "..."


def _parse_components(c: Any) -> dict:
    """解析 V/S/M 成分"""
    if isinstance(c, dict):
        return c
    if not isinstance(c, str):
        return {"v": False, "s": False, "m": ""}
    s = c.lower()
    return {
        "v": "v" in s,
        "s": "s" in s,
        "m": c.split("M:")[-1].strip() if "M:" in c else "",
    }


def _extract_spell_tags(s: dict) -> list[str]:
    """从法术数据提取标签"""
    tags = []
    if s.get("concentration") or "concentration" in (s.get("duration", "") or "").lower():
        tags.append("专注")
    if s.get("ritual"):
        tags.append("仪式")
    school = s.get("school", "")
    if isinstance(school, dict):
        school = school.get("name", "")
    if school:
        tags.append(school)
    if s.get("damage"):
        tags.append("伤害")
    if "heal" in (s.get("name_en", "") or "").lower() or "cure" in (s.get("name_en", "") or "").lower():
        tags.append("治疗")
    return tags


def _infer_caster_type(name_en: str, c: dict) -> str:
    """根据职业名推断 caster_type"""
    # 已知型施法者
    known_casters = {"sorcerer", "bard", "warlock"}
    # 准备型施法者
    prepared_casters = {"cleric", "druid", "paladin", "wizard", "ranger"}

    # 优先看 v2 的 spellcasting.prepared 字段
    sc = c.get("spellcasting", {})
    if isinstance(sc, dict):
        if sc.get("preparation") == "prepared_list":
            return "prepared"
        if sc.get("preparation") == "known_list":
            return "known"

    if name_en in known_casters:
        return "known"
    if name_en in prepared_casters:
        return "prepared"
    return "none"


def _extract_primary_ability(c: dict) -> str:
    sc = c.get("spellcasting", {})
    if isinstance(sc, dict):
        ability = sc.get("ability", "")
        if ability:
            return _ability_to_zh(ability)
    return ""


def _extract_saves(c: dict) -> list[str]:
    """从 v2 提取豁免"""
    profs = c.get("proficiencies", [])
    saves = []
    for p in profs:
        if isinstance(p, dict):
            name = p.get("name", "") or p.get("key", "")
            if "Saving Throw" in name or "save" in name.lower():
                abbr = name.split()[-1] if name else ""
                if abbr in ("STR", "DEX", "CON", "INT", "WIS", "CHA"):
                    saves.append(_ability_to_zh(abbr))
    return saves


def _extract_spellcasting_ability(c: dict) -> str:
    sc = c.get("spellcasting", {})
    if isinstance(sc, dict):
        ability = sc.get("ability", "")
        if ability:
            return _ability_to_zh(ability)
    return ""


def _ability_to_zh(abbr: str) -> str:
    return {
        "STR": "力量", "DEX": "敏捷", "CON": "体质",
        "INT": "智力", "WIS": "感知", "CHA": "魅力",
    }.get(abbr.upper(), abbr)


# ═════════════════════════════════════════════════════════════
# 各分类的拉取函数
# ═════════════════════════════════════════════════════════════

def sync_spells(edition: str, rate: float, out_dir: Path) -> int:
    """拉取法术"""
    print("[1/8] 拉取法术 (spells)...")
    if edition == "2024":
        url = f"{OPEN5E_V2}/spells/"
        params = {"document__key": "srd-2024", "limit": 100}
        items = paginate(url, params, rate, normalize_spell_v2)
    else:
        url = f"{OPEN5E_V1}/spells/"
        params = {"document__slug": "wotc-srd", "limit": 100}
        items = paginate(url, params, rate, normalize_spell_v1)

    _write_json(out_dir / "spells.json", {
        "version": f"{edition}-srd",
        "category": "spells",
        "synced_at": _now_iso(),
        "count": len(items),
        "spells": items,
    })
    print(f"  ✓ {len(items)} 个法术已写入 spells.json")
    return len(items)


def sync_classes(edition: str, rate: float, out_dir: Path) -> int:
    """拉取职业"""
    print("[2/8] 拉取职业 (classes)...")
    if edition == "2024":
        url = f"{OPEN5E_V2}/classes/"
        params = {"document__key": "srd-2024", "limit": 100}
        items_list = paginate(url, params, rate, normalize_class_v2)
    else:
        url = f"{OPEN5E_V1}/classes/"
        params = {"document__slug": "wotc-srd", "limit": 100}
        items_list = paginate(url, params, rate, normalize_class_v1)

    # 转为 dict
    classes_dict = {item["name_en"].lower(): item for item in items_list}
    _write_json(out_dir / "classes.json", {
        "version": f"{edition}-srd",
        "category": "classes",
        "synced_at": _now_iso(),
        "count": len(classes_dict),
        "classes": classes_dict,
    })
    print(f"  ✓ {len(classes_dict)} 个职业已写入 classes.json")
    return len(classes_dict)


def sync_conditions(edition: str, rate: float, out_dir: Path) -> int:
    """拉取状态效果"""
    print("[3/8] 拉取状态效果 (conditions)...")
    # conditions 在 v2 和 v1 都不带 edition 过滤
    url = f"{OPEN5E_V2}/conditions/" if edition == "2024" else f"{OPEN5E_V1}/conditions/"
    params = {"limit": 100}
    norm = normalize_condition_v2 if edition == "2024" else normalize_condition_v1
    items = paginate(url, params, rate, norm)

    _write_json(out_dir / "conditions.json", {
        "version": f"{edition}-srd",
        "category": "conditions",
        "synced_at": _now_iso(),
        "count": len(items),
        "conditions": items,
    })
    print(f"  ✓ {len(items)} 个状态已写入 conditions.json")
    return len(items)


def sync_combat_rules(edition: str, rate: float, out_dir: Path) -> int:
    """合成战斗规则快照（damage_immunity / critical_hit 等）"""
    print("[4/8] 生成 combat.json（手写固定规则）...")

    # 战斗规则主要是 PHB 文字规则——Open5e 没有专门端点
    # 这里手写关键规则的"摘要"（这部分是数据，不是叙事）
    rules = [
        {
            "rule_id": "rules.dnd5e.combat.damage_immunity",
            "name_zh": "伤害免疫",
            "name_en": "Damage Immunity",
            "summary": "受该类型伤害时减为 0。优先级最高：先免疫 → 再易伤 → 最后抗性。",
            "phb_page": 197,
        },
        {
            "rule_id": "rules.dnd5e.combat.damage_vulnerability",
            "name_zh": "伤害易伤",
            "name_en": "Damage Vulnerability",
            "summary": "受该类型伤害时翻倍。仅在通过免疫判定后才考虑。",
            "phb_page": 197,
        },
        {
            "rule_id": "rules.dnd5e.combat.damage_resistance",
            "name_zh": "伤害抗性",
            "name_en": "Damage Resistance",
            "summary": "受该类型伤害时减半（向下取整）。在免疫/易伤判定之后。",
            "phb_page": 197,
        },
        {
            "rule_id": "rules.dnd5e.combat.critical_hit",
            "name_zh": "暴击",
            "name_en": "Critical Hit",
            "summary": "攻击检定自然 20：伤害骰数量翻倍（加值不翻倍）。暴击后再应用抗/免/易伤。",
            "phb_page": 196,
        },
        {
            "rule_id": "rules.dnd5e.combat.advantage",
            "name_zh": "优势",
            "name_en": "Advantage",
            "summary": "掷 d20 两次取高。多个优势不叠加。",
            "phb_page": 173,
        },
        {
            "rule_id": "rules.dnd5e.combat.disadvantage",
            "name_zh": "劣势",
            "name_en": "Disadvantage",
            "summary": "掷 d20 两次取低。多个劣势不叠加。优势与劣势同时存在时抵消。",
            "phb_page": 173,
        },
        {
            "rule_id": "rules.dnd5e.combat.death_saving_throw",
            "name_zh": "死亡豁免",
            "name_en": "Death Saving Throw",
            "summary": "HP 归 0 时开始：每回合掷 d20。≥10=成功 1 次，自然 20=恢复 1HP 醒来，<10=失败 1 次，自然 1=计 2 次失败。3 成功=稳定，3 失败=死亡。",
            "phb_page": 197,
        },
    ]

    _write_json(out_dir / "combat.json", {
        "version": f"{edition}-srd",
        "category": "combat",
        "synced_at": _now_iso(),
        "count": len(rules),
        "rules": rules,
    })
    print(f"  ✓ {len(rules)} 条战斗规则已写入 combat.json")
    return len(rules)


def sync_rest_rules(edition: str, rate: float, out_dir: Path) -> int:
    """合成休息规则"""
    print("[5/8] 生成 rest.json（手写固定规则）...")

    rules = [
        {
            "rule_id": "rules.dnd5e.rest.short_rest",
            "name_zh": "短休",
            "name_en": "Short Rest",
            "summary": "至少 1 小时。HP 必须 ≥ 1 才能短休。消耗 1+ 命中骰，按骰结果 + 体质调整值恢复 HP。邪术师短休恢复所有契约法术位。",
            "phb_page": 186,
        },
        {
            "rule_id": "rules.dnd5e.rest.long_rest",
            "name_zh": "长休",
            "name_en": "Long Rest",
            "summary": "至少 8 小时（6 小时睡眠 + 最多 2 小时轻活动）。HP 必须 ≥ 1。HP 满，所有法术位满，恢复一半命中骰（向下取整，最少 1，0 命中骰的角色不获骰），清空临时 HP，重置死亡豁免，exhaustion -1。24 小时内只能长休一次。",
            "phb_page": 186,
        },
        {
            "rule_id": "rules.dnd5e.rest.warlock_pact_magic",
            "name_zh": "邪术师契约法术位",
            "name_en": "Warlock Pact Magic",
            "summary": "邪术师的法术位称为'契约法术位'，所有位同环级。短休恢复全部契约法术位。",
            "phb_page": 107,
        },
    ]

    _write_json(out_dir / "rest.json", {
        "version": f"{edition}-srd",
        "category": "rest",
        "synced_at": _now_iso(),
        "count": len(rules),
        "rules": rules,
    })
    print(f"  ✓ {len(rules)} 条休息规则已写入 rest.json")
    return len(rules)


def sync_spell_slots(edition: str, rate: float, out_dir: Path) -> int:
    """法术位表（手写，因为是结构化数据）"""
    print("[6/8] 生成 spell_slots.json（手写完整表）...")

    # PHB 法师/牧/德 全施法者 1-20 级法术位表
    full_caster = {
        1:  {1: 2},
        2:  {1: 3},
        3:  {1: 4, 2: 2},
        4:  {1: 4, 2: 3},
        5:  {1: 4, 2: 3, 3: 2},
        6:  {1: 4, 2: 3, 3: 3},
        7:  {1: 4, 2: 3, 3: 3, 4: 1},
        8:  {1: 4, 2: 3, 3: 3, 4: 2},
        9:  {1: 4, 2: 3, 3: 3, 4: 3, 5: 1},
        10: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2},
        11: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1},
        12: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1},
        13: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1},
        14: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1},
        15: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1, 8: 1},
        16: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1, 8: 1},
        17: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1, 8: 1, 9: 1},
        18: {1: 4, 2: 3, 3: 3, 4: 3, 5: 3, 6: 1, 7: 1, 8: 1, 9: 1},
        19: {1: 4, 2: 3, 3: 3, 4: 3, 5: 3, 6: 2, 7: 1, 8: 1, 9: 1},
        20: {1: 4, 2: 3, 3: 3, 4: 3, 5: 3, 6: 2, 7: 2, 8: 1, 9: 1},
    }

    # 圣/游 半施法者
    half_caster = {
        1:  {},
        2:  {1: 2},
        3:  {1: 3},
        4:  {1: 3},
        5:  {1: 4, 2: 2},
        6:  {1: 4, 2: 2},
        7:  {1: 4, 2: 3},
        8:  {1: 4, 2: 3},
        9:  {1: 4, 2: 3, 3: 2},
        10: {1: 4, 2: 3, 3: 2},
        11: {1: 4, 2: 3, 3: 3},
        12: {1: 4, 2: 3, 3: 3},
        13: {1: 4, 2: 3, 3: 3, 4: 1},
        14: {1: 4, 2: 3, 3: 3, 4: 1},
        15: {1: 4, 2: 3, 3: 3, 4: 2},
        16: {1: 4, 2: 3, 3: 3, 4: 2},
        17: {1: 4, 2: 3, 3: 3, 4: 3, 5: 1},
        18: {1: 4, 2: 3, 3: 3, 4: 3, 5: 1},
        19: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2},
        20: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2},
    }

    # 邪术师契约法术位（pact_count, pact_level）
    warlock = {
        1:  {"pact": 1, "level": 1},
        2:  {"pact": 2, "level": 1},
        3:  {"pact": 2, "level": 2},
        4:  {"pact": 2, "level": 2},
        5:  {"pact": 2, "level": 3},
        6:  {"pact": 2, "level": 3},
        7:  {"pact": 2, "level": 4},
        8:  {"pact": 2, "level": 4},
        9:  {"pact": 2, "level": 5},
        10: {"pact": 2, "level": 5},
        11: {"pact": 3, "level": 5},
        12: {"pact": 3, "level": 5},
        13: {"pact": 3, "level": 5},
        14: {"pact": 3, "level": 5},
        15: {"pact": 3, "level": 5},
        16: {"pact": 3, "level": 5},
        17: {"pact": 4, "level": 5},
        18: {"pact": 4, "level": 5},
        19: {"pact": 4, "level": 5},
        20: {"pact": 4, "level": 5},
    }

    payload = {
        "version": f"{edition}-srd",
        "category": "spell_slots",
        "synced_at": _now_iso(),
        "full_caster": full_caster,
        "half_caster": half_caster,
        "warlock": warlock,
        "notes": {
            "full_caster_classes": ["法师", "牧师", "德鲁伊"],
            "half_caster_classes": ["圣武士", "游侠"],
            "warlock_class": ["邪术师"],
            "known_caster_classes": ["术士", "吟游诗人", "邪术师"],
            "prepared_caster_classes": ["牧师", "德鲁伊", "圣武士", "法师", "游侠"],
        },
    }

    _write_json(out_dir / "spell_slots.json", payload)
    print(f"  ✓ 20 级法术位表已写入 spell_slots.json")
    return 1


def sync_checks(edition: str, rate: float, out_dir: Path) -> int:
    """技能 + 豁免（手写固定）"""
    print("[7/8] 生成 checks.json（手写技能表）...")

    skills = [
        # 力量
        {"rule_id": "rules.dnd5e.checks.athletics", "name_zh": "运动", "name_en": "Athletics", "ability": "力量", "phb_page": 175},
        # 敏捷
        {"rule_id": "rules.dnd5e.checks.acrobatics", "name_zh": "体操", "name_en": "Acrobatics", "ability": "敏捷", "phb_page": 175},
        {"rule_id": "rules.dnd5e.checks.sleight_of_hand", "name_zh": "巧手", "name_en": "Sleight of Hand", "ability": "敏捷", "phb_page": 175},
        {"rule_id": "rules.dnd5e.checks.stealth", "name_zh": "隐匿", "name_en": "Stealth", "ability": "敏捷", "phb_page": 175},
        # 智力
        {"rule_id": "rules.dnd5e.checks.arcana", "name_zh": "奥秘", "name_en": "Arcana", "ability": "智力", "phb_page": 175},
        {"rule_id": "rules.dnd5e.checks.history", "name_zh": "历史", "name_en": "History", "ability": "智力", "phb_page": 175},
        {"rule_id": "rules.dnd5e.checks.investigation", "name_zh": "调查", "name_en": "Investigation", "ability": "智力", "phb_page": 175},
        {"rule_id": "rules.dnd5e.checks.nature", "name_zh": "自然", "name_en": "Nature", "ability": "智力", "phb_page": 175},
        {"rule_id": "rules.dnd5e.checks.religion", "name_zh": "宗教", "name_en": "Religion", "ability": "智力", "phb_page": 175},
        # 感知
        {"rule_id": "rules.dnd5e.checks.animal_handling", "name_zh": "驯兽", "name_en": "Animal Handling", "ability": "感知", "phb_page": 175},
        {"rule_id": "rules.dnd5e.checks.insight", "name_zh": "洞察", "name_en": "Insight", "ability": "感知", "phb_page": 175},
        {"rule_id": "rules.dnd5e.checks.medicine", "name_zh": "医药", "name_en": "Medicine", "ability": "感知", "phb_page": 175},
        {"rule_id": "rules.dnd5e.checks.perception", "name_zh": "察觉", "name_en": "Perception", "ability": "感知", "phb_page": 175},
        {"rule_id": "rules.dnd5e.checks.survival", "name_zh": "生存", "name_en": "Survival", "ability": "感知", "phb_page": 175},
        # 魅力
        {"rule_id": "rules.dnd5e.checks.deception", "name_zh": "欺瞒", "name_en": "Deception", "ability": "魅力", "phb_page": 175},
        {"rule_id": "rules.dnd5e.checks.intimidation", "name_zh": "威吓", "name_en": "Intimidation", "ability": "魅力", "phb_page": 175},
        {"rule_id": "rules.dnd5e.checks.performance", "name_zh": "表演", "name_en": "Performance", "ability": "魅力", "phb_page": 175},
        {"rule_id": "rules.dnd5e.checks.persuasion", "name_zh": "说服", "name_en": "Persuasion", "ability": "魅力", "phb_page": 175},
    ]

    saves = [
        {"rule_id": "rules.dnd5e.checks.save_str", "name_zh": "力量豁免", "name_en": "Strength Save", "ability": "力量", "phb_page": 179},
        {"rule_id": "rules.dnd5e.checks.save_dex", "name_zh": "敏捷豁免", "name_en": "Dexterity Save", "ability": "敏捷", "phb_page": 179},
        {"rule_id": "rules.dnd5e.checks.save_con", "name_zh": "体质豁免", "name_en": "Constitution Save", "ability": "体质", "phb_page": 179},
        {"rule_id": "rules.dnd5e.checks.save_int", "name_zh": "智力豁免", "name_en": "Intelligence Save", "ability": "智力", "phb_page": 179},
        {"rule_id": "rules.dnd5e.checks.save_wis", "name_zh": "感知豁免", "name_en": "Wisdom Save", "ability": "感知", "phb_page": 179},
        {"rule_id": "rules.dnd5e.checks.save_cha", "name_zh": "魅力豁免", "name_en": "Charisma Save", "ability": "魅力", "phb_page": 179},
    ]

    _write_json(out_dir / "checks.json", {
        "version": f"{edition}-srd",
        "category": "checks",
        "synced_at": _now_iso(),
        "skills": skills,
        "saves": saves,
        "skill_count": len(skills),
        "save_count": len(saves),
    })
    print(f"  ✓ {len(skills)} 技能 + {len(saves)} 豁免已写入 checks.json")
    return len(skills) + len(saves)


def sync_equipment(edition: str, rate: float, out_dir: Path) -> int:
    """起始装备（手写）"""
    print("[8/8] 生成 equipment.json（手写起始装备）...")

    # by_class 顶层是 dict[职业中文名, {items: [...], default_kit: [...]}]
    equipment = {
        "法师": {
            "items": [
                {"name": "法杖", "type": "focus", "description": "奥术法器"},
                {"name": "法术书", "type": "gear", "description": "记录已准备法术"},
            ],
            "default_kit": ["冒险者套件", "背包", "睡袋", "火绒盒", "10 支火把", "10 日口粮", "水袋", "50 尺麻绳"],
        },
        "战士": {
            "items": [
                {"name": "长剑", "type": "weapon", "description": "1d8 挥砍，通用"},
                {"name": "盾牌", "type": "armor", "description": "AC +2"},
                {"name": "鳞甲", "type": "armor", "description": "AC 14 + 敏捷调整（上限 2）"},
            ],
            "default_kit": ["冒险者套件", "背包", "睡袋", "火绒盒", "10 支火把", "10 日口粮", "水袋", "50 尺麻绳"],
        },
        "游荡者": {
            "items": [
                {"name": "短剑", "type": "weapon", "description": "1d6 穿刺，灵巧"},
                {"name": "短弓", "type": "weapon", "description": "1d6 穿刺，弹药 20"},
                {"name": "皮甲", "type": "armor", "description": "AC 11 + 敏捷调整"},
                {"name": "盗贼工具", "type": "tool", "description": "开锁与解除陷阱"},
            ],
            "default_kit": ["冒险者套件", "背包", "睡袋", "火绒盒", "10 支火把", "10 日口粮", "水袋", "50 尺麻绳"],
        },
        "牧师": {
            "items": [
                {"name": "硬头锤", "type": "weapon", "description": "1d6 钝击"},
                {"name": "盾牌", "type": "armor", "description": "AC +2"},
                {"name": "鳞甲", "type": "armor", "description": "AC 14 + 敏捷调整（上限 2）"},
                {"name": "圣徽", "type": "focus", "description": "神术法器"},
            ],
            "default_kit": ["冒险者套件", "背包", "睡袋", "火绒盒", "10 支火把", "10 日口粮", "水袋", "50 尺麻绳"],
        },
        "游侠": {
            "items": [
                {"name": "长剑", "type": "weapon", "description": "1d8 挥砍"},
                {"name": "长弓", "type": "weapon", "description": "1d8 穿刺，弹药 20"},
                {"name": "皮甲", "type": "armor", "description": "AC 11 + 敏捷调整"},
            ],
            "default_kit": ["探险套件", "背包", "铺盖", "炊具", "火绒盒", "10 支火把", "10 日口粮", "水袋", "50 尺麻绳"],
        },
        "吟游诗人": {
            "items": [
                {"name": "细剑", "type": "weapon", "description": "1d8 穿刺，灵巧"},
                {"name": "鲁特琴", "type": "focus", "description": "乐器法器"},
                {"name": "皮甲", "type": "armor", "description": "AC 11 + 敏捷调整"},
            ],
            "default_kit": ["冒险者套件", "背包", "睡袋", "火绒盒", "10 支火把", "10 日口粮", "水袋", "50 尺麻绳"],
        },
        "武僧": {
            "items": [
                {"name": "短棍", "type": "weapon", "description": "1d6 钝击，武僧武器"},
                {"name": "飞镖", "type": "weapon", "quantity": 10, "description": "1d4 穿刺，投掷（20/60）"},
            ],
            "default_kit": ["探险套件", "背包", "铺盖", "炊具", "火绒盒", "10 支火把", "10 日口粮", "水袋", "50 尺麻绳"],
        },
        "德鲁伊": {
            "items": [
                {"name": "短弯刀", "type": "weapon", "description": "1d6 挥砍，灵巧"},
                {"name": "木盾", "type": "armor", "description": "AC +2"},
                {"name": "皮甲", "type": "armor", "description": "AC 11 + 敏捷调整"},
                {"name": "德鲁伊法器", "type": "focus", "description": "槲寄生枝"},
            ],
            "default_kit": ["探险套件", "背包", "铺盖", "炊具", "火绒盒", "10 支火把", "10 日口粮", "水袋", "50 尺麻绳"],
        },
        "圣武士": {
            "items": [
                {"name": "长剑", "type": "weapon", "description": "1d8 挥砍"},
                {"name": "盾牌", "type": "armor", "description": "AC +2"},
                {"name": "链甲", "type": "armor", "description": "AC 16，力量 13 方可穿着"},
                {"name": "圣徽", "type": "focus", "description": "神术法器"},
            ],
            "default_kit": ["冒险者套件", "背包", "睡袋", "火绒盒", "10 支火把", "10 日口粮", "水袋", "50 尺麻绳"],
        },
        "术士": {
            "items": [
                {"name": "轻弩", "type": "weapon", "description": "1d8 穿刺，弹药 20"},
                {"name": "奥术法器", "type": "focus", "description": "龙晶/法珠任选"},
            ],
            "default_kit": ["冒险者套件", "背包", "睡袋", "火绒盒", "10 支火把", "10 日口粮", "水袋", "50 尺麻绳"],
        },
        "野蛮人": {
            "items": [
                {"name": "巨斧", "type": "weapon", "description": "1d12 挥砍，重型，双手"},
                {"name": "手斧", "type": "weapon", "quantity": 2, "description": "1d6 挥砍，投掷（20/60）"},
            ],
            "default_kit": ["探险套件", "背包", "铺盖", "炊具", "火绒盒", "10 支火把", "10 日口粮", "水袋", "50 尺麻绳"],
        },
        "邪术师": {
            "items": [
                {"name": "轻弩", "type": "weapon", "description": "1d8 穿刺，弹药 20"},
                {"name": "奥术法器", "type": "focus", "description": "秘术法器"},
                {"name": "皮甲", "type": "armor", "description": "AC 11 + 敏捷调整"},
            ],
            "default_kit": ["冒险者套件", "背包", "睡袋", "火绒盒", "10 支火把", "10 日口粮", "水袋", "50 尺麻绳"],
        },
    }

    _write_json(out_dir / "equipment.json", {
        "version": f"{edition}-srd",
        "category": "equipment",
        "synced_at": _now_iso(),
        "by_class": equipment,
    })
    print(f"  ✓ {len(equipment)} 个职业起始装备已写入 equipment.json")
    return len(equipment)


# ═════════════════════════════════════════════════════════════
# 工具
# ═════════════════════════════════════════════════════════════

def _now_iso() -> str:
    return datetime.now().isoformat() + "Z"


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ═════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════

def sync_creatures(edition: str, rate: float, out_dir: Path) -> int:
    """拉取怪物图鉴"""
    print("[+] 拉取怪物 (creatures)...")
    if edition == "2024":
        url = f"{OPEN5E_V2}/creatures/"
        # expand 模式：resistances/abilities/actions 全部结构化
        params = {
            "document__key": "srd-2024",
            "limit": 100,
            "expand": "resistances_and_immunities,actions,actions.attacks,"
                      "actions.damage_type,type,size,speed,languages,speed_all,"
                      "ability_scores,modifiers,skill_bonuses,saving_throws",
        }
        items = paginate(url, params, rate, normalize_creature_v2)
    else:
        # 2014 v1 没 creatures 端点，跳过
        print("  ! 2014 SRD v1 无 creatures 端点，跳过")
        return 0

    _write_json(out_dir / "creatures.json", {
        "version": f"{edition}-srd",
        "category": "creatures",
        "synced_at": _now_iso(),
        "count": len(items),
        "creatures": items,
    })
    print(f"  ✓ {len(items)} 个怪物已写入 creatures.json")
    return len(items)


def sync_items(edition: str, rate: float, out_dir: Path) -> int:
    """拉取魔法物品"""
    print("[+] 拉取魔法物品 (items)...")
    if edition == "2014":
        url = f"{OPEN5E_V1}/magicitems/"
        params = {"document__slug": "wotc-srd", "limit": 100}
        items = paginate(url, params, rate, normalize_magic_item_v1)
    else:
        # 2024 v2 magicitems 端点不存在，跳过
        print("  ! 2024 SRD v2 无 magicitems 端点，跳过")
        return 0

    _write_json(out_dir / "items.json", {
        "version": f"{edition}-srd",
        "category": "items",
        "synced_at": _now_iso(),
        "count": len(items),
        "items": items,
    })
    print(f"  ✓ {len(items)} 个魔法物品已写入 items.json")
    return len(items)


CATEGORIES = {
    "spells": sync_spells,
    "classes": sync_classes,
    "conditions": sync_conditions,
    "creatures": sync_creatures,
    "items": sync_items,
    "combat": sync_combat_rules,
    "rest": sync_rest_rules,
    "spell_slots": sync_spell_slots,
    "checks": sync_checks,
    "equipment": sync_equipment,
}


def main():
    parser = argparse.ArgumentParser(
        description="从 Open5e 拉取 SRD 数据并写入本地规则书快照"
    )
    parser.add_argument(
        "--system", default="dnd5e",
        choices=["dnd5e", "dnd3r", "coc7e", "custom"],
        help="规则系统（默认 dnd5e）",
    )
    parser.add_argument(
        "--edition", default="2024",
        choices=["2024", "2014"],
        help="SRD 版本（默认 2024 = 5.5e）",
    )
    parser.add_argument(
        "--category", default=None,
        choices=list(CATEGORIES.keys()) + [None],
        help="只拉某个分类（默认全部）",
    )
    parser.add_argument(
        "--rate", type=float, default=1.0,
        help="请求间隔秒数（默认 1.0）",
    )
    parser.add_argument(
        "--out-dir", default=None,
        help="输出目录（默认 worldbook-plugin/rules/builtin/{system}）",
    )

    args = parser.parse_args()

    # 输出目录：默认按 system/edition/ 拆分
    if args.out_dir:
        out_dir = Path(args.out_dir)
    else:
        out_dir = Path(__file__).parent / "builtin" / args.system / args.edition

    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== 同步规则书快照 ===")
    print(f"系统: {args.system}")
    print(f"版本: {args.edition} SRD")
    print(f"输出: {out_dir}")
    print()

    categories_to_sync = [args.category] if args.category else list(CATEGORIES.keys())

    for cat in categories_to_sync:
        try:
            CATEGORIES[cat](args.edition, args.rate, out_dir)
        except Exception as e:
            print(f"  ✗ {cat} 同步失败: {e}")
            import traceback
            traceback.print_exc()

    print()
    print("=== 完成 ===")


if __name__ == "__main__":
    main()
