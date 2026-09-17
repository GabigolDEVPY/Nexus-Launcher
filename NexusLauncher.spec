# -*- mode: python ; coding: utf-8 -*-
# Build onefile portatil: gera um unico NexusLauncher.exe
# que roda em qualquer Windows, sem Git, Python ou instalacao previa.
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPECPATH).resolve()
icon_path = project_root / "icon.ico"

datas = []
for relative_dir in ["assets", "ui/resources"]:
    source_dir = project_root / relative_dir
    if source_dir.exists():
        datas.append((str(source_dir), relative_dir.replace("\\", "/")))

hiddenimports = (
    collect_submodules("watchdog")
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="NexusLauncher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(icon_path) if icon_path.exists() else None,
)
