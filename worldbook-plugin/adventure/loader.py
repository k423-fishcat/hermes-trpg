"""模组统一加载器

自动识别格式，解析成中间模型，然后导入到跑团系统。

支持的格式：
- native: 原生 adventure.json
- zim_wiki: Zim Desktop Wiki 目录
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import AdventureModule


def detect_format(path: str) -> Optional[str]:
    """自动检测模组格式

    Returns:
        'native' / 'zim_wiki' / None
    """
    p = Path(path)

    if not p.exists():
        return None

    # 单个 JSON 文件 → 原生格式
    if p.is_file() and p.suffix == '.json':
        return "native"

    # 目录 → 判断是不是 Zim Wiki
    if p.is_dir():
        # 有 notebook.zim → 肯定是 zim
        if (p / "notebook.zim").exists():
            return "zim_wiki"
        # 有大量 txt 文件，且头部有 Zim 格式标记
        txt_files = list(p.glob("*.txt"))
        if len(txt_files) >= 3:
            for tf in txt_files[:5]:
                with open(tf, "r", encoding="utf-8", errors="ignore") as f:
                    first_line = f.readline()
                if "Content-Type: text/x-zim-wiki" in first_line:
                    return "zim_wiki"

    return None


def load_module(path: str, module_id: str = "", module_name: str = "") -> AdventureModule:
    """加载模组（自动检测格式）

    Args:
        path: 模组路径（文件或目录）
        module_id: 模组 ID（不填则自动生成）
        module_name: 模组名称（不填则用目录/文件名）

    Returns:
        AdventureModule 中间模型
    """
    fmt = detect_format(path)
    if not fmt:
        raise ValueError(f"无法识别的模组格式: {path}")

    if fmt == "native":
        from .formats.native import parse_native_adventure
        mod = parse_native_adventure(path)
    elif fmt == "zim_wiki":
        from .formats.zim_wiki import parse_zim_directory
        mid = module_id or Path(path).stem.lower().replace(' ', '-')
        mod = parse_zim_directory(path, mid, module_name)
    else:
        raise ValueError(f"不支持的格式: {fmt}")

    if module_id:
        mod.id = module_id
    if module_name:
        mod.name = module_name

    return mod


def import_module(mod: AdventureModule,
                  worldbook_store=None,
                  state_mgr=None,
                  quest_mgr=None,
                  npc_mgr=None,
                  chron_mgr=None,
                  worldbook_name: str = None,
                  conflict_strategy: str = "skip") -> Dict[str, Any]:
    """将模组导入到跑团系统

    Args:
        mod: AdventureModule 中间模型
        worldbook_store: WorldBookStore 实例
        state_mgr: StateManager 实例
        quest_mgr: QuestManager 实例
        npc_mgr: NPCManager 实例
        chron_mgr: ChronicleManager 实例
        worldbook_name: 世界书名称（默认用 mod.id）
        conflict_strategy: 同名 NPC 冲突处理策略
            - "skip"（默认）：跳过，记录冲突警告
            - "overwrite"：覆盖已有 NPC 的静态字段
            - "rename"：改名导入（追加模组名后缀）

    Returns:
        导入结果统计
    """
    if conflict_strategy not in ("skip", "overwrite", "rename"):
        conflict_strategy = "skip"

    stats = {
        "module_id": mod.id,
        "module_name": mod.name,
        "format": mod.source_format,
        "entries_imported": 0,
        "entries_failed": 0,
        "npcs_imported": 0,
        "npcs_skipped": 0,
        "quests_imported": 0,
        "encounters_imported": 0,
        "world_flags_set": 0,
        "errors": [],
    }

    wb_name = worldbook_name or mod.id

    # 1. 导入世界书条目（批量导入，支持指定 ID）
    if worldbook_store and mod.entries:
        try:
            # 收集有效条目
            valid_entries = []
            skipped = 0
            for entry in mod.entries:
                if not entry.content or len(entry.content.strip()) < 20:
                    skipped += 1
                    continue
                valid_entries.append({
                    "id": entry.id,
                    "title": entry.title,
                    "content": entry.content,
                    "category": entry.category,
                    "keys": entry.keywords,
                })

            # 批量导入
            count = worldbook_store.import_book(wb_name, {"entries": valid_entries})
            stats["entries_imported"] = count
            stats["entries_failed"] = skipped

            if skipped:
                stats["errors"].append(f"跳过了 {skipped} 个内容过短的条目")
        except Exception as e:
            stats["entries_failed"] = len(mod.entries)
            stats["errors"].append(f"批量导入失败: {e}")

    # 2. 导入 NPC（同名冲突按 conflict_strategy 处理）
    if npc_mgr and mod.npcs:
        for npc in mod.npcs:
            try:
                existing = npc_mgr._get_npc(npc.name)
                target_name = npc.name
                if existing is not None:
                    # 同名 NPC 已存在
                    if conflict_strategy == "skip":
                        stats["npcs_skipped"] += 1
                        stats["errors"].append(
                            f"NPC 冲突（skip）: {npc.name} 已存在，跳过"
                        )
                        continue
                    elif conflict_strategy == "rename":
                        target_name = f"{npc.name}（{mod.name}）"
                        stats["errors"].append(
                            f"NPC 冲突（rename）: {npc.name} → {target_name}"
                        )
                    # overwrite：保留 target_name = npc.name，走下方覆盖流程

                # 确保 NPC 存在（_ensure_npc 返回的是 deepcopy，改后必须 _save_npc 写回）
                npc_mgr._ensure_npc(target_name)
                npc_obj = npc_mgr._get_npc(target_name)
                if npc_obj:
                    npc_obj["description"] = npc.description
                    npc_obj["personality"] = npc.personality
                    npc_obj["attitude"] = npc.initial_attitude
                    npc_obj["location"] = npc.location
                    npc_obj["id"] = npc.id
                    # known_info 去重追加
                    known = npc_obj.setdefault("known_info", [])
                    for info in npc.known_info:
                        if info not in known:
                            known.append(info)
                    # schedule 直接赋值
                    for slot, act in npc.schedule.items():
                        npc_obj.setdefault("schedule", {})[slot] = act
                    # 一次写回所有字段（关键：直接改 deepcopy 不持久化，必须显式 _save_npc）
                    npc_mgr._save_npc(target_name, npc_obj, f"导入 NPC: {target_name}")
                stats["npcs_imported"] += 1
            except Exception as e:
                stats["errors"].append(f"NPC {npc.name}: {e}")

    # 3. 导入任务
    if quest_mgr and mod.quests:
        for q in mod.quests:
            try:
                quest_mgr.add_quest(
                    quest_id=q.id,
                    title=q.title,
                    description=q.description,
                    quest_type=q.quest_type,
                    giver=q.giver,
                    rewards=q.rewards,
                    steps=q.steps,
                    prerequisites=q.prerequisites,
                )
                stats["quests_imported"] += 1
            except Exception as e:
                stats["errors"].append(f"任务 {q.title}: {e}")

    # 4. 导入遭遇（存到 world.encounters）
    if state_mgr and mod.encounters:
        world = state_mgr.get("world") or {}
        encounters = world.setdefault("encounters", {})
        for enc in mod.encounters:
            encounters[enc.id] = {
                "name": enc.name,
                "type": enc.encounter_type,
                "description": enc.description,
                "location": enc.location,
                "creatures": enc.creatures,
                "dc_info": enc.dc_info,
                "rewards": enc.rewards,
            }
            stats["encounters_imported"] += 1
        state_mgr.update(
            {"world": world},
            reason=f"导入 {len(mod.encounters)} 个遭遇",
            actor="模组导入")

    # 5. 设置世界标记
    if state_mgr and mod.world_flags:
        world = state_mgr.get("world") or {}
        flags = world.setdefault("flags", {})
        for k, v in mod.world_flags.items():
            flags[k] = v
            stats["world_flags_set"] += 1
        state_mgr.update(
            {"world": world},
            reason=f"导入 {len(mod.world_flags)} 个世界标记",
            actor="模组导入")

    # 6. 创建开场章节
    if chron_mgr and mod.opening_title:
        try:
            # 检查是否已有章节
            recap = chron_mgr.recap()
            if isinstance(recap, str) or recap is None:
                pass  # 没章节
            else:
                if recap.get("current_chapter") and recap["current_chapter"] != mod.opening_title:
                    chron_mgr.end_chapter("导入新模组，章节重置")
            chron_mgr.start_chapter(mod.opening_title, mod.opening_summary)
            if mod.opening_hook:
                chron_mgr.add_event(mod.opening_hook, importance="major")
        except Exception as e:
            stats["errors"].append(f"开场章节: {e}")

    return stats


def list_adventures(data_dir: str) -> List[Dict[str, str]]:
    """列出 data/adventures 目录下的可用模组"""
    adv_dir = Path(data_dir)
    if not adv_dir.exists():
        return []

    result = []
    for item in sorted(adv_dir.iterdir()):
        if item.name.startswith('.') or item.name.startswith('_'):
            continue
        if item.is_dir():
            # 找 adventure.json
            adv_json = item / "adventure.json"
            if adv_json.exists():
                try:
                    with open(adv_json, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    result.append({
                        "id": item.name,
                        "name": data.get("name", item.name),
                        "path": str(adv_json),
                        "format": "native",
                    })
                except Exception:
                    result.append({
                        "id": item.name,
                        "name": item.name,
                        "path": str(item),
                        "format": "unknown",
                    })
            else:
                # 判断是不是 zim wiki
                fmt = detect_format(str(item))
                if fmt:
                    result.append({
                        "id": item.name,
                        "name": item.name,
                        "path": str(item),
                        "format": fmt,
                    })

    return result


def export_module_json(mod: AdventureModule, output_path: str) -> str:
    """将中间模型导出为原生 adventure.json 格式"""
    data = {
        "id": mod.id,
        "name": mod.name,
        "system": mod.system,
        "version": mod.version,
        "author": mod.author,
        "description": mod.description,
        "worldbook_entries": [
            {
                "id": e.id,
                "title": e.title,
                "category": e.category,
                "content": e.content,
                "summary": e.summary,
                "keywords": e.keywords,
            }
            for e in mod.entries
        ],
        "npcs": [
            {
                "id": n.id,
                "name": n.name,
                "description": n.description,
                "personality": n.personality,
                "initial_attitude": n.initial_attitude,
                "location": n.location,
                "known_info": n.known_info,
                "schedule": n.schedule,
            }
            for n in mod.npcs
        ],
        "quests": [
            {
                "id": q.id,
                "title": q.title,
                "description": q.description,
                "type": q.quest_type,
                "giver": q.giver,
                "rewards": q.rewards,
                "steps": q.steps,
                "prerequisites": q.prerequisites,
            }
            for q in mod.quests
        ],
        "encounters": [
            {
                "id": e.id,
                "name": e.name,
                "type": e.encounter_type,
                "description": e.description,
                "location": e.location,
                "creatures": e.creatures,
                "dc": e.dc_info,
                "rewards": e.rewards,
            }
            for e in mod.encounters
        ],
        "world_flags": mod.world_flags,
        "opening": {
            "chapter_title": mod.opening_title,
            "chapter_summary": mod.opening_summary,
            "hook_text": mod.opening_hook,
        },
        "source_format": mod.source_format,
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return output_path
