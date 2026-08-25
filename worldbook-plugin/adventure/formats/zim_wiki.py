"""Zim Wiki 格式解析器

解析 Zim Desktop Wiki 格式的 txt 文件和目录结构，
转换成 AdventureModule 中间模型。

Zim Wiki 格式要点：
  • 一级标题: ====== Title ======
  • 二级标题: ===== Title =====
  • 三级标题: ==== Title ====
  • 斜体/旁白: //text// （DM 读给玩家的内容）
  • 粗体: **text**
  • 链接: [[PageName]] 或 [[Page|Label]]
  • 图片: {{path/to/image.png}}
  • 列表: 缩进 + 项目
  • 水平线: ----
  • 代码块/引用: ''' ... '''
  • 文件头有 Content-Type, Wiki-Format, Creation-Date 等元数据
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..models import (
    AdventureModule, AdventureEntry, AdventureNPC,
    AdventureQuest, AdventureEncounter,
)


# 分类关键词映射（根据文件路径和内容判断条目类型）
CATEGORY_KEYWORDS = {
    "location": ["castle", "cave", "tower", "village", "town", "city", "forest",
                 "mountain", "river", "lake", "coast", "island", "keep", "manor",
                 "hall", "inn", "tavern", "shop", "temple", "shrine", "mine",
                 "hideout", "fort", "ruins", "wood", "road", "trail", "bridge",
                 "farm", "orchard", "lair", "graveyard", "docks", "harbor"],
    "npc": [],  # 默认按大小和内容判断
    "item": ["potion", "sword", "ring", "rod", "staff", "wand", "amulet",
             "cloak", "boots", "gloves", "shield", "armor", "weapon",
             "figurine", "bow", "axe", "dagger", "dust", "mask", "horn",
             "spellbook", "scroll"],
    "organization": ["coven", "guild", "order", "faction", "society",
                     "alliance", "network", "brigands", "bandits", "harpers",
                     "zhentarim", "lord's alliance"],
    "creature": [],  # statblocks 目录的算
    "dungeon": [],   # dungeon 目录的算
}


def parse_zim_file(filepath: Path) -> Dict[str, Any]:
    """解析单个 Zim Wiki 文件

    返回：{title, content, summary, sections, metadata, dm_text}
    """
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()

    lines = raw.split('\n')

    # 提取头部元数据
    metadata = {}
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith('======'):
            body_start = i
            break
        if ':' in line and not line.startswith(' '):
            key, _, val = line.partition(':')
            key = key.strip()
            val = val.strip()
            if key and key[0].isalpha():
                metadata[key] = val

    body_lines = lines[body_start:] if body_start < len(lines) else []

    # 提取标题（第一个一级标题）
    title = filepath.stem.replace('_', ' ')
    for line in body_lines:
        if line.startswith('======'):
            m = re.match(r'^=+\s*(.*?)\s*=+\s*$', line)
            if m:
                title = m.group(1).strip()
            break

    # 提取摘要（标题后的第一段正文）
    summary = ""
    for line in body_lines[1:]:
        line = line.strip()
        if not line:
            continue
        if line.startswith('=') or line.startswith('-') or line.startswith('{'):
            break
        if line.startswith('Created '):
            continue
        # 第一段正文
        summary = line
        break

    # 提取 DM 旁白（//...// 内容，即读给玩家的描述）
    dm_text_parts = []
    # 清理后的内容（去掉 Zim 标记，保留可读文本）
    content_lines = []
    for line in body_lines:
        # 去掉标题行的 = 号，但保留文字
        if re.match(r'^=+', line):
            # 转换为 markdown 标题
            level = len(line) - len(line.lstrip('='))
            text = line.strip().strip('=').strip()
            # 一级标题是 ======（6个=），所以 level 就是 = 数
            md_level = max(1, 7 - (level // 2) if level >= 6 else 7 - level)
            # 简化：直接保留原文，标题加 #
            content_lines.append(f"{'#' * max(1, min(6, 7 - level//2))} {text}")
            continue

        # 去掉图片标记
        line = re.sub(r'\{\{.*?\}\}', '', line)

        # 转换链接 [[Page]] → Page（加粗）
        line = re.sub(r'\[\[:?([^|\]]+?)\]\]', r'**\1**', line)
        line = re.sub(r'\[\[([^|\]]+?)\|([^\]]+?)\]\]', r'**\2**', line)

        # 转换斜体 //text// → *text* (Markdown 斜体)
        # 同时记录 DM 旁白
        dm_match = re.findall(r'//(.*?)//', line)
        if dm_match:
            dm_text_parts.extend(dm_match)
        line = re.sub(r'//(.*?)//', r'*\1*', line)

        # 转换粗体 **text**（已经是了，不动）

        # 三引号块直接保留
        content_lines.append(line)

    content = '\n'.join(content_lines).strip()

    # DM 旁白（读给玩家的描述）
    dm_text = '\n\n'.join(dm_text_parts).strip()

    # 分段（sections）
    sections = _extract_sections(body_lines)

    return {
        "title": title,
        "content": content,
        "summary": summary,
        "dm_text": dm_text,
        "sections": sections,
        "metadata": metadata,
        "raw_size": len(raw),
    }


def _extract_sections(lines: List[str]) -> List[Dict[str, str]]:
    """提取二级和三级标题分段"""
    sections = []
    current_title = "概述"
    current_lines = []

    for line in lines:
        # 二级或三级标题
        if re.match(r'^={3,5}\s', line):
            if current_lines:
                sections.append({
                    "title": current_title,
                    "content": '\n'.join(current_lines).strip(),
                })
            level = len(line) - len(line.lstrip('='))
            title = line.strip().strip('=').strip()
            current_title = title
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append({
            "title": current_title,
            "content": '\n'.join(current_lines).strip(),
        })

    return sections


def _categorize_file(rel_path: str, parsed: Dict) -> str:
    """判断条目分类"""
    rel_lower = rel_path.lower().replace('\\', '/')
    name_lower = Path(rel_path).stem.lower()
    parts = set(rel_lower.split('/'))

    # 路径优先（看所有父目录）
    if any('statblock' in p for p in parts):
        return "creature"
    if any(p in ('dungeon', 'dungeons') for p in parts):
        return "dungeon"
    if any('encounter' in p for p in parts):
        return "encounter"
    if any(p in ('quest', 'quests') for p in parts):
        return "quest"
    if any(p in ('item', 'items') for p in parts):
        return "item"
    if any(p in ('wilderness_encounter', 'wilderness') for p in parts):
        return "encounter"

    # 文件名关键词（物品类关键词最明确，优先判断）
    for kw in CATEGORY_KEYWORDS["item"]:
        if kw in name_lower:
            return "item"

    # 组织类关键词
    for kw in CATEGORY_KEYWORDS["organization"]:
        if kw in name_lower:
            return "organization"

    # 地点类关键词
    for kw in CATEGORY_KEYWORDS["location"]:
        if kw in name_lower:
            return "location"

    # 根据内容启发式
    content_lower = parsed.get("content", "")[:800].lower()
    raw_size = parsed.get("raw_size", 0)
    sections = parsed.get("sections", [])

    # 遭遇特征
    if '@encounter' in parsed.get("content", ""):
        return "encounter"
    if '**encounter**' in content_lower:
        return "encounter"

    # 物品特征
    if any(phrase in content_lower for phrase in ['requires attunement', 'wondrous item',
                                                   'weapon, ', 'armor, ', 'ring, ',
                                                   'staff of ', 'wand of ', 'potion of ']):
        return "item"

    # NPC 特征（描述某人）
    first_sentence = parsed.get("summary", "")
    if first_sentence and len(first_sentence) < 200:
        if any(pattern in first_sentence.lower() for pattern in
               [' is a ', ' is an ', ' was a ', ' is the ', ' serves as ',
                ' works as ', ' runs the ', ' owns the ']):
            # 而且后面不是地方名
            if not any(kw in first_sentence.lower() for kw in
                       ['village', 'town', 'city', 'castle', 'cave',
                        'forest', 'mountain', 'river', 'keep', 'tower']):
                return "npc"

    # 大文件 + 多个分段 → 地点/地下城
    if raw_size > 3000 and len(sections) > 3:
        # 检查是否有房间编号（1. 2. 3.）
        section_titles = ' '.join(s["title"] for s in sections)
        if any(c.isdigit() for c in section_titles[:30]):
            return "dungeon"
        return "location"

    # 中等文件 + 多段也可能是地点
    if raw_size > 1000 and len(sections) > 2:
        return "location"

    return "other"


def parse_zim_directory(dir_path: str, module_id: str, module_name: str = "") -> AdventureModule:
    """解析整个 Zim Wiki 目录为 AdventureModule

    Args:
        dir_path: Zim Wiki 根目录
        module_id: 模组 ID
        module_name: 模组名称（可选，默认用目录名）

    Returns:
        AdventureModule 中间模型
    """
    root = Path(dir_path)
    if not module_name:
        module_name = root.stem

    module = AdventureModule(
        id=module_id,
        name=module_name,
        source_format="zim_wiki",
        source_path=str(root),
    )

    # 遍历所有 txt 文件
    txt_files = []
    for fpath in root.rglob("*.txt"):
        # 跳过 .git
        if '.git' in fpath.parts:
            continue
        # 跳过 zim 内部文件
        if fpath.name == 'notebook.zim':
            continue
        rel = fpath.relative_to(root)
        txt_files.append((fpath, rel))

    # 解析每个文件
    for fpath, rel in txt_files:
        try:
            parsed = parse_zim_file(fpath)
        except Exception as e:
            print(f"  ⚠️  解析失败 {rel}: {e}")
            continue

        category = _categorize_file(str(rel), parsed)

        # 生成 ID
        rel_id = str(rel).replace('\\', '/').replace('.txt', '').lower()
        rel_id = re.sub(r'[^a-z0-9/_-]', '_', rel_id)
        entry_id = f"{module_id}-{category}-{rel_id.replace('/', '-')}"

        # 关键词（从标题 + 前几段提取）
        keywords = _extract_keywords(parsed)

        # 组装条目
        entry = AdventureEntry(
            id=entry_id,
            title=parsed["title"],
            category=category,
            content=parsed["content"],
            summary=parsed["summary"],
            keywords=keywords,
            metadata={
                "sections": [s["title"] for s in parsed.get("sections", [])],
                "dm_text": parsed.get("dm_text", ""),
                "source_file": str(rel),
            },
            source_format="zim_wiki",
        )
        module.entries.append(entry)

        # 同时尝试解析为任务/NPC/遭遇
        if category == "quest":
            quest = _try_parse_quest(entry_id, parsed)
            if quest:
                module.quests.append(quest)

        elif category == "npc":
            npc = _try_parse_npc(entry_id, parsed)
            if npc:
                module.npcs.append(npc)

        elif category == "encounter":
            enc = _try_parse_encounter(entry_id, parsed)
            if enc:
                module.encounters.append(enc)

    module.entry_count = len(module.entries)
    return module


def _extract_keywords(parsed: Dict) -> List[str]:
    """从内容中提取关键词（标题词 + 专有名词）"""
    keywords = []
    title = parsed.get("title", "")
    keywords.append(title)

    # 提取所有 [[链接]] 里的名称作为关键词
    raw = parsed.get("content", "")
    links = re.findall(r'\*\*([A-Z][a-zA-Z\s]+?)\*\*', raw)
    seen = set()
    for link in links:
        link = link.strip()
        if len(link) > 2 and len(link) < 50 and link not in seen:
            seen.add(link)
            keywords.append(link)
            if len(keywords) >= 15:
                break

    return keywords[:12]


def _try_parse_quest(entry_id: str, parsed: Dict) -> Optional[AdventureQuest]:
    """尝试从条目解析出任务结构"""
    title = parsed.get("title", "")
    content = parsed.get("content", "")
    summary = parsed.get("summary", "")

    # 从 sections 提取步骤
    sections = parsed.get("sections", [])
    steps = []
    for i, sec in enumerate(sections[1:5], 1):  # 跳过第一个（概述）
        if sec["title"] and sec["content"]:
            steps.append({
                "id": f"step-{i}",
                "title": sec["title"],
                "description": sec["content"][:200],
            })

    # 判断任务类型（粗略）
    qtype = "side"
    content_lower = content.lower()
    if any(kw in content_lower for kw in ['main quest', 'main story', 'primary']):
        qtype = "main"

    return AdventureQuest(
        id=entry_id,
        title=title,
        description=summary or content[:300],
        quest_type=qtype,
        steps=steps,
    )


def _try_parse_npc(entry_id: str, parsed: Dict) -> Optional[AdventureNPC]:
    """尝试从条目解析出 NPC"""
    title = parsed.get("title", "")
    summary = parsed.get("summary", "")
    content = parsed.get("content", "")

    # 提取 DM 笔记（"Notes for the DM" 之类的段落）
    personality = ""
    for sec in parsed.get("sections", []):
        if any(kw in sec["title"].lower() for kw in ['personality', 'dm note', 'notes for', 'description']):
            personality = sec["content"][:300]
            break

    return AdventureNPC(
        id=entry_id,
        name=title,
        description=summary or content[:200],
        personality=personality,
    )


def _try_parse_encounter(entry_id: str, parsed: Dict) -> Optional[AdventureEncounter]:
    """尝试从条目解析出遭遇"""
    title = parsed.get("title", "")
    summary = parsed.get("summary", "")
    content = parsed.get("content", "")

    # 判断遭遇类型
    content_lower = content.lower()
    if any(kw in content_lower for kw in ['dc ', 'check', 'skill', 'insight', 'persuasion', 'deception']):
        etype = "social"
    elif any(kw in content_lower for kw in ['trap', 'pit', 'alarm', 'poison']):
        etype = "trap"
    elif any(kw in content_lower for kw in ['monster', 'goblin', 'orc', 'skeleton', 'zombie', 'attack', 'combat']):
        etype = "combat"
    else:
        etype = "exploration"

    return AdventureEncounter(
        id=entry_id,
        name=title,
        encounter_type=etype,
        description=summary or content[:300],
    )
