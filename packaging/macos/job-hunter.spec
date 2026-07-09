"""PyInstaller .app spike for macOS. This is intentionally not wired into releases.

Builds an unsigned .app bundle. Hardened-runtime signing, Apple notarization,
and DMG creation are separate steps (codesign / notarytool / hdiutil) run
after this spec, once real signing credentials are available — see
docs/macos-packaging.md.
"""

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
    (str(root / "job_hunter" / "config" / "countries.json"), "job_hunter/config"),
    (str(root / "job_hunter" / "config" / "filters.json"), "job_hunter/config"),
    (str(root / "job_hunter" / "catalog" / "companies.json"), "job_hunter/catalog"),
    *tree(root / "job_hunter" / "templates", "job_hunter/templates"),
]
hiddenimports = [
    *collect_submodules("anthropic", filter=runtime_module),
    *collect_submodules("openai", filter=runtime_module),
    *collect_submodules("google.genai", filter=runtime_module),
    *collect_submodules("webview", filter=runtime_module),
]

analysis = Analysis(
    [str(root / "packaging" / "macos" / "job_hunter_entry.py")],
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
    console=False,
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
app = BUNDLE(
    coll,
    name="Job Hunter.app",
    icon=None,
    bundle_identifier="com.jobhunterkit.jobhunter",
    info_plist={
        "CFBundleName": "Job Hunter",
        "CFBundleDisplayName": "Job Hunter",
        "CFBundleShortVersionString": "0.0.0",  # placeholder; a real release pipeline stamps this from pyproject.toml
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
    },
)
