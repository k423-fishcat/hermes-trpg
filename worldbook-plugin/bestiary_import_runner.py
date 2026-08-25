#!/usr/bin/env python
"""SRD 怪物批量导入脚本

通过 dnd-rules MCP 拉取所有 SRD 2024 怪物，转换成 bestiary 格式保存。

用法:
  python bestiary_import_runner.py [--overwrite] [--cr-min 0] [--cr-max 30]

因为需要调用 MCP 工具，脚本会通过 Hermes 的 MCP 调用方式来做。
但我们这里直接用 Python 代码调 dnd-rules 的底层 API 不现实（需要 MCP 客户端）。

实际操作方式：
  1. 先通过 dnd_search_creatures 获取所有怪物列表和 key
  2. 逐个 dnd_get_creature 拉详细数据
  3. convert_creature_to_bestiary 转换
  4. 保存到 bestiary 目录
"""

import json
import sys
import time
from pathlib import Path

# 确保能导入插件模块
sys.path.insert(0, str(Path(__file__).parent))

from bestiary import Bestiary
from bestiary_import import convert_creature_to_bestiary


def import_from_json_dump(dump_path: str, bestiary_dir: str, overwrite: bool = False) -> dict:
    """从 JSON dump 文件导入怪物

    dump 文件格式: [{key, structuredContent}, ...]
    """
    dump_file = Path(dump_path)
    if not dump_file.exists():
        return {"success": False, "error": f"文件不存在: {dump_path}"}

    data = json.loads(dump_file.read_text(encoding="utf-8"))
    bestiary = Bestiary(Path(bestiary_dir).parent)  # bestiary_dir 是 .../bestiary，其父目录是 data

    imported = 0
    skipped = 0
    errors = []

    for entry in data:
        try:
            structured = entry.get("structuredContent") or entry
            key = structured.get("key", "")
            if not key:
                continue

            converted = convert_creature_to_bestiary(structured)
            monster_id = converted["id"]

            # 检查是否已存在
            existing = bestiary.get_monster(monster_id)
            if existing and not overwrite:
                skipped += 1
                continue

            # 保存
            bestiary.add_monster(converted)
            imported += 1

        except Exception as e:
            errors.append(f"{entry.get('key', '?')}: {e}")

    return {
        "success": True,
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "total": len(data),
    }


if __name__ == "__main__":
    # 这个主函数是给手动导入用的
    # 正常情况下我们在 Hermes 会话里通过 MCP 工具获取数据然后调用转换函数
    print("SRD 怪物导入工具")
    print("=" * 40)
    print("使用方式：在 Hermes 里通过 dnd-rules MCP 获取怪物数据，")
    print("然后调用 convert_creature_to_bestiary() 转换并保存。")
    print()
    print("批量导入见上方注释。")
