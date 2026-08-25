"""rules.validate - 规则书快照校验脚本

启动时 / 手动跑都过 schema；返回所有错误的清单。

用法：
    # 命令行：扫描默认目录 rules/builtin/
    python -m worldbook_plugin.rules.validate

    # 指定系统
    python -m worldbook_plugin.rules.validate --system dnd5e

    # 详细模式
    python -m worldbook_plugin.rules.validate -v

    # 程序调用
    from worldbook_plugin.rules.validate import validate_builtin, validate_file
    errors = validate_builtin(Path("rules/builtin"))
    ok = validate_file(Path("rules/builtin/dnd5e/spells.json"))
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .schema import validate_category

logger = logging.getLogger(__name__)


def _infer_category(json_path: Path) -> Optional[str]:
    """从文件名推断 category（spells.json → "spells"）。"""
    name = json_path.stem  # 不含后缀
    return name if name else None


def validate_file(json_path: Path) -> Tuple[bool, List[str]]:
    """校验单个 JSON 文件。

    Returns:
        (ok, errors) - ok=True 表示无错误
    """
    errors: List[str] = []
    if not json_path.exists():
        return False, [f"文件不存在: {json_path}"]

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return False, [f"JSON 解析失败: {e}"]

    category = data.get("category") or _infer_category(json_path)
    if not category:
        return False, ["无法识别 category（文件无 category 字段且文件名非标准）"]

    errs = validate_category(category, data)
    return (len(errs) == 0), errs


def validate_builtin(builtin_dir: Path,
                      system: Optional[str] = None) -> Dict[str, List[str]]:
    """扫描 builtin 目录下所有 JSON，返回 {rel_path: errors}。

    Args:
        builtin_dir: rules/builtin 根目录
        system: 只校验某系统（None = 全部）

    Returns:
        dict, key 是相对 builtin_dir 的路径，value 是错误列表。
        空列表表示该文件无错误。
    """
    if not builtin_dir.exists():
        return {str(builtin_dir): [f"目录不存在: {builtin_dir}"]}

    results: Dict[str, List[str]] = {}
    systems = [system] if system else [p.name for p in builtin_dir.iterdir()
                                       if p.is_dir() and not p.name.startswith("_")]

    for sys_name in systems:
        sys_dir = builtin_dir / sys_name
        if not sys_dir.is_dir():
            results[f"{sys_name}/"] = [f"系统目录不存在: {sys_dir}"]
            continue
        # 递归扫所有 *.json：兼容 system/edition/*.json 与 system/*.json 平铺两种结构
        for json_path in sorted(sys_dir.rglob("*.json")):
            ok, errs = validate_file(json_path)
            rel = str(json_path.relative_to(builtin_dir))
            # 通过的文件也记录（空列表）—— 让报告能算"通过数"
            results[rel] = errs if not ok else []

    return results


def _format_report(results: Dict[str, List[str]], verbose: bool = False) -> str:
    """格式化为可读报告。"""
    lines: List[str] = []
    if not results:
        return "✅ 所有快照校验通过（0 个文件）"

    n_ok = sum(1 for errs in results.values() if not errs)
    n_bad = len(results) - n_ok
    lines.append(f"扫描 {len(results)} 个文件：通过 {n_ok}，失败 {n_bad}")
    lines.append("")

    for path, errs in results.items():
        if not errs:
            if verbose:
                lines.append(f"  ✅ {path}")
            continue
        lines.append(f"  ❌ {path}（{len(errs)} 错误）")
        for e in errs:
            lines.append(f"     - {e}")
        lines.append("")

    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="校验 rules/builtin 下的所有规则书快照"
    )
    parser.add_argument("--system", "-s", help="只校验指定系统 (e.g. dnd5e)")
    parser.add_argument("--dir", "-d", help="指定 builtin 根目录")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="详细模式（连通过的文件也显示）")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="静默模式（只输出失败项）")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    builtin_dir = Path(args.dir) if args.dir else (
        Path(__file__).parent / "builtin"
    )
    results = validate_builtin(builtin_dir, system=args.system)

    if args.quiet:
        # 只输出有错误的
        bad = {p: e for p, e in results.items() if e}
        if bad:
            print(_format_report(bad, verbose=True))
        return 0 if not bad else 1

    print(_format_report(results, verbose=args.verbose))
    n_bad = sum(1 for errs in results.values() if errs)
    return 0 if n_bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
