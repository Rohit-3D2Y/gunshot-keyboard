# PyInstaller spec - builds Gunshot.exe on Windows and Gunshot.app on macOS.
# Run from the repo root:  pyinstaller packaging/gunshot.spec
import sys
from pathlib import Path

root = Path(SPECPATH).parent
sys.path.insert(0, str(root))
from gunshot import __version__  # noqa: E402

icons = root / "packaging" / "icons"
mac = sys.platform == "darwin"

a = Analysis(
    [str(root / "packaging" / "launch.py")],
    pathex=[str(root)],
    datas=[(str(root / "gunshot" / "packs"), "gunshot/packs")],
    hiddenimports=["pynput.keyboard._win32", "pystray._win32"]
    if not mac
    else ["pynput.keyboard._darwin", "pystray._darwin"],
    excludes=["tkinter", "unittest", "pydoc", "pytest"],
)
pyz = PYZ(a.pure)

if mac:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Gunshot", console=False,
              target_arch=None, codesign_identity=None, entitlements_file=None)
    coll = COLLECT(exe, a.binaries, a.datas, name="Gunshot")
    app = BUNDLE(
        coll,
        name="Gunshot.app",
        icon=str(icons / "gunshot.icns"),
        bundle_identifier="com.gunshot.keyboard",
        version=__version__,
        info_plist={
            "CFBundleShortVersionString": __version__,
            "LSUIElement": True,  # menu-bar only, no Dock icon
            "LSMinimumSystemVersion": "11.0",
            "NSHumanReadableCopyright": "Gunshot",
        },
    )
else:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name="Gunshot",
        icon=str(icons / "gunshot.ico"),
        console=False,
        upx=False,  # UPX-packed exes trigger antivirus false positives
        version=str(root / "packaging" / "version_info.txt"),
    )
