"""PyInstaller onedir spike. This is intentionally not wired into releases."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).parents[1]


def tree(source: Path, destination: str) -> list[tuple[str, str]]:
    return [
        (str(path), f"{destination}/{path.parent.relative_to(source).as_posix()}")
        for path in source.rglob("*")
        if path.is_file()
    ]


def runtime_module(name: str) -> bool:
    return ".tests" not in name and "._test" not in name


datas = [
    (str(root / "job_hunter" / "ux" / "web" / "dashboard.html"), "job_hunter/ux/web"),
    (str(root / "job_hunter" / "ux" / "web" / "dashboard.css"), "job_hunter/ux/web"),
    (str(root / "job_hunter" / "ux" / "web" / "dashboard.js"), "job_hunter/ux/web"),
    (str(root / "job_hunter" / "catalog" / "countries.json"), "job_hunter/catalog"),
    (str(root / "job_hunter" / "catalog" / "filters.json"), "job_hunter/catalog"),
    (str(root / "job_hunter" / "catalog" / "experience_levels.json"), "job_hunter/catalog"),
    (str(root / "job_hunter" / "catalog" / "job_titles.json"), "job_hunter/catalog"),
    # Company catalog moved from catalog/companies.json to a runtime store seeded from
    # per-country jsonl files; location data lives in its own resource tree. Both are
    # required package-data (pyproject.toml's [tool.setuptools.package-data]) that the
    # original catalog/companies.json-only datas list predates and never picked up.
    *tree(root / "job_hunter" / "companies" / "data", "job_hunter/companies/data"),
    *tree(root / "job_hunter" / "locations" / "data", "job_hunter/locations/data"),
    *tree(root / "job_hunter" / "templates", "job_hunter/templates"),
]
hiddenimports = [
    *collect_submodules("anthropic", filter=runtime_module),
    *collect_submodules("openai", filter=runtime_module),
    *collect_submodules("google.genai", filter=runtime_module),
    *collect_submodules("webview", filter=runtime_module),
]

analysis = Analysis(
    [str(root / "packaging" / "windows" / "job_hunter_entry.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="job-hunter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="job-hunter",
)
