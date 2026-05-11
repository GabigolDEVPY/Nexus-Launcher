# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPECPATH).resolve()
icon_path = project_root / "assets" / "app.ico"

datas = []
for relative_dir in ["assets", "ui/resources", "vendor/PortableGit"]:
    source_dir = project_root / relative_dir
    if source_dir.exists():
        datas.append((str(source_dir), relative_dir.replace("\\", "/")))

hiddenimports = (
    collect_submodules("sqlalchemy")
    + collect_submodules("git")
    + collect_submodules("gitdb")
    + collect_submodules("watchdog")
    + collect_submodules("PIL")
)


a = Analysis(
    ["main.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NexusLauncher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(icon_path) if icon_path.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="NexusLauncher",
)
