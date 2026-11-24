# -*- mode: python ; coding: utf-8 -*-
# PyInstaller yapılandırması:  python -m PyInstaller --noconfirm gor-bak.spec
from PyInstaller.utils.hooks import collect_submodules, copy_metadata

gizli = (
    collect_submodules("pydicom.pixels")
    + collect_submodules("pylibjpeg")
    + collect_submodules("libjpeg")
    + collect_submodules("openjpeg")
    + collect_submodules("rle")
    + ["pydicom.encoders", "pydicom.uid"]
)
# pylibjpeg çözücüleri giriş noktalarıyla (entry points) bulur: paket bilgileri gerekli
veri = [("varliklar/gor-bak.ico", "varliklar")]
for paket in ("pylibjpeg", "pylibjpeg-libjpeg", "pylibjpeg-openjpeg", "pylibjpeg-rle", "pydicom"):
    veri += copy_metadata(paket)

a = Analysis(
    ["gor_bak.py"],
    pathex=[],
    binaries=[],
    datas=veri,
    hiddenimports=gizli,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter", "matplotlib", "reportlab", "IPython", "pytest", "scipy", "pandas",
        "pymupdf4llm", "pydicom.data.test_files",
        "PySide6.QtNetwork", "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.QtQuick",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="gor-bak",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon="varliklar/gor-bak.ico",
    version="surum.txt",
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="gor-bak")
