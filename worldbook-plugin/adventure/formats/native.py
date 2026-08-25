"""原生 adventure.json 格式解析器

我们自己定义的 adventure.json 格式，转换为中间模型。
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models import (
    AdventureModule, AdventureEntry, AdventureNPC,
    AdventureQuest, AdventureEncounter,
)


def parse_native_adventure(filepath: str) -> AdventureModule:
    """解析原生 adventure.json 文件"""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    mod_id = data.get("id", Path(filepath).stem)
    module = AdventureModule(
        id=mod_id,
        name=data.get("name", mod_id),
        system=data.get("system", "dnd5e"),
        version=data.get("version", "0.1"),
        author=data.get("author", ""),
        description=data.get("description", ""),
        source_format="native",
        source_path=str(filepath),
    )

    # 世界书条目
    for entry_data in data.get("worldbook_entries", []):
        module.entries.append(AdventureEntry(
            id=f"{mod_id}-{entry_data.get('id', entry_data.get('title','entry'))}",
            title=entry_data.get("title", ""),
            category=entry_data.get("category", "other"),
            content=entry_data.get("content", ""),
            summary=entry_data.get("summary", ""),
            keywords=entry_data.get("keywords", []),
            source_format="native",
        ))

    # NPC
    for npc_data in data.get("npcs", []):
        npc_id = npc_data.get("id", npc_data.get("name", "npc"))
        module.npcs.append(AdventureNPC(
            id=f"{mod_id}-npc-{npc_id}",
            name=npc_data.get("name", ""),
            description=npc_data.get("description", ""),
            personality=npc_data.get("personality", ""),
            initial_attitude=npc_data.get("initial_attitude", 0),
            location=npc_data.get("location", ""),
            known_info=npc_data.get("known_info", []),
            schedule=npc_data.get("schedule", {}),
        ))
        # 同时作为世界书条目
        module.entries.append(AdventureEntry(
            id=f"{mod_id}-npc-{npc_id}",
            title=npc_data.get("name", ""),
            category="npc",
            content=npc_data.get("description", "") + "\n\n" + npc_data.get("personality", ""),
            summary=npc_data.get("description", "")[:100],
            keywords=[npc_data.get("name", "")],
            source_format="native",
        ))

    # 任务
    for q_data in data.get("quests", []):
        qid = q_data.get("id", q_data.get("title", "quest"))
        steps = []
        for i, s in enumerate(q_data.get("steps", []), 1):
            steps.append({
                "id": s.get("id", f"step-{i}"),
                "title": s.get("title", f"步骤{i}"),
                "description": s.get("description", ""),
            })
        module.quests.append(AdventureQuest(
            id=f"{mod_id}-quest-{qid}",
            title=q_data.get("title", ""),
            description=q_data.get("description", ""),
            quest_type=q_data.get("type", q_data.get("quest_type", "side")),
            giver=q_data.get("giver", ""),
            rewards=q_data.get("rewards", ""),
            steps=steps,
            prerequisites=q_data.get("prerequisites", []),
        ))

    # 遭遇
    for enc_data in data.get("encounters", []):
        eid = enc_data.get("id", enc_data.get("name", "encounter"))
        module.encounters.append(AdventureEncounter(
            id=f"{mod_id}-enc-{eid}",
            name=enc_data.get("name", ""),
            encounter_type=enc_data.get("type", enc_data.get("encounter_type", "combat")),
            description=enc_data.get("description", ""),
            location=enc_data.get("location", ""),
            creatures=enc_data.get("creatures", []),
            dc_info=enc_data.get("dc", {}),
            rewards=enc_data.get("rewards", ""),
        ))

    # 世界标记
    module.world_flags = data.get("world_flags", {})

    # 开场
    opening = data.get("opening", {})
    module.opening_title = opening.get("chapter_title", "")
    module.opening_summary = opening.get("chapter_summary", "")
    module.opening_hook = opening.get("hook_text", "")

    module.entry_count = len(module.entries)
    return module
