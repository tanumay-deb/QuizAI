# PyInstaller spec for QuizAI Assistant.
#
# Build with: pyinstaller quizai.spec
# Output:     dist/QuizAI(.exe)
#
# This produces a single-file executable. Drop --onefile (set EXE() arg `onefile=False`)
# if you prefer a folder layout — much faster startup, but more files to ship.

# ruff: noqa
# flake8: noqa

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Excluding libraries we don't use cuts binary size noticeably (PyInstaller
# bundles transitive imports aggressively). NOTE: numpy is REQUIRED (RapidOCR /
# OpenCV / onnxruntime depend on it) — do not exclude it.
EXCLUDES = [
    "tkinter",
    "matplotlib",
    "pandas",
    "scipy",
    "IPython",
    "jupyter",
    "notebook",
    "PyQt5",
    "PyQt6",
]

# Some PySide6 multimedia modules need to be force-included for sound playback.
HIDDEN = [
    "PySide6.QtMultimedia",
    "PySide6.QtNetwork",  # transitively required by multimedia
]

# The OCR-first path needs RapidOCR (ONNX model files + config), onnxruntime
# (native provider DLLs), and OpenCV. collect_all pulls their data files,
# binaries, and hidden submodules so the frozen exe can do local OCR.
_datas, _binaries = [], []
for _pkg in ("rapidocr_onnxruntime", "onnxruntime", "cv2"):
    _d, _b, _h = collect_all(_pkg)
    _datas += _d
    _binaries += _b
    HIDDEN += _h

a = Analysis(
    ["quizai/__main__.py"],
    pathex=["."],
    binaries=_binaries,
    datas=_datas,
    hiddenimports=HIDDEN,
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Single-file build. UPX compression reduces size further if UPX is on PATH.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="QuizAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,     # GUI mode: no terminal window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,         # add 'icon.ico' (Win), 'icon.icns' (Mac) when you have one
)

# macOS bundle. PyInstaller automatically uses this on darwin builds.
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="QuizAI.app",
        icon=None,
        bundle_identifier="com.tanumay.quizai",
        info_plist={
            "NSHighResolutionCapable": True,
            "LSUIElement": True,  # background app (no Dock icon, lives in menu bar)
            # Permission-prompt strings.
            "NSCameraUsageDescription": "Not used.",
            "NSAppleEventsUsageDescription": "Used for global hotkeys.",
        },
    )
