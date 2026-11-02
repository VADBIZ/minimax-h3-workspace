# PyInstaller spec for macOS: python -m PyInstaller app/build/h3studio-mac.spec --distpath app/build/dist --workpath app/build/work
# then app/build/make-dmg.sh packs the .app into a drag-to-Applications disk image
from pathlib import Path

APP = Path(SPECPATH).parent
VERSION = "1.0.0"

a = Analysis(
    [str(APP / "main.py")],
    pathex=[str(APP)],
    datas=[(str(APP / "ui" / "index.html"), "ui"), (str(APP / "skills"), "skills")],
    # whisper.cpp has no official Mac build: our own static one (Metal, arm64 + x86_64) ships with the app
    binaries=[(str(APP / "bin" / "whisper-cli"), "bin")],
    hiddenimports=["webview.platforms.cocoa"],
    excludes=["tkinter", "matplotlib", "numpy", "PIL", "pandas", "scipy", "IPython"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="MinimaxH3Workspace",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="MinimaxH3Workspace")
app = BUNDLE(
    coll,
    name="Minimax H3 Workspace.app",
    icon=str(APP / "build" / "icon.icns"),
    bundle_identifier="community.minimax-h3-workspace",
    version=VERSION,
    info_plist={
        "CFBundleDisplayName": "Minimax H3 Workspace",
        "CFBundleShortVersionString": VERSION,
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": "Голосовой ввод для агента: запись распознаётся на этом компьютере.",
        "LSApplicationCategoryType": "public.app-category.video",
    },
)
