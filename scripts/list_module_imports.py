"""List every job_hunter module and which other job_hunter modules it imports.

Supports architecture audits: run before moving a file to see who would break.

    uv run python scripts/list_module_imports.py
    uv run python scripts/list_module_imports.py --target job_hunter.pipeline.runner
"""

from __future__ import annotations

import argparse
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1] / "job_hunter"


def _module_name(path: pathlib.Path) -> str:
    rel = path.relative_to(ROOT.parent).with_suffix("")
    parts = rel.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imports(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return sorted({name for name in found if name.startswith("job_hunter")})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", help="Only show modules that import this exact module path")
    args = parser.parse_args()

    graph = {_module_name(p): _imports(p) for p in sorted(ROOT.rglob("*.py")) if "templates" not in p.parts}

    for module, imports in graph.items():
        if args.target:
            hits = [imp for imp in imports if imp == args.target or imp.startswith(args.target + ".")]
            for hit in hits:
                print(f"{module} -> {hit}")
            continue
        if imports:
            print(f"{module}:")
            for imp in imports:
                print(f"  {imp}")


if __name__ == "__main__":
    main()
