# Gunshot

Every key you press fires a gunshot. Works on **Windows 10/11** and **macOS 11+**
(Apple Silicon and Intel). Lives in the system tray / menu bar.

## Install

Download the latest release from the **Releases** page:

| System | File | How |
| --- | --- | --- |
| Windows | `GunshotSetup-<version>.exe` | Run it and click through. No admin rights needed. |
| Mac (M1 and newer) | `Gunshot-<version>-macos-arm64.dmg` | Open it and drag **Gunshot** into **Applications**. |
| Mac (Intel) | `Gunshot-<version>-macos-x86_64.dmg` | Same as above. |

**Mac, first launch:** macOS asks you to let Gunshot see your keyboard. Open
**System Settings → Privacy & Security → Input Monitoring**, switch Gunshot on,
then quit and reopen it. Every app that responds to typing needs this permission.

**Uninstall:** on Windows use *Settings → Apps → Gunshot → Uninstall*. On a Mac,
quit Gunshot and move it to the Bin. Windows also removes your settings and the
start-at-login entry.

## Use

- **Toggle on/off:** `Ctrl+Alt+G` (Mac: `Ctrl+Option+G`), or click the tray icon.
  The crosshair is red when it's on and grey when it's off.
- **Menu:** Enabled · Sound · Volume (Quiet/Low/Medium/High/Max) · Start at login · Quit
- Holding a key fires once, so there's no machine-gun auto-repeat. Fast typing overlaps the shots.

## Safety & privacy

- **Keys are never recorded.** The app reacts to *that* a key was pressed. It
  doesn't log, store or transmit *which* keys were pressed. See `gunshot/app.py`, the
  only place keys are handled.
- **No internet.** Gunshot makes no network connections: no analytics, no
  updates, no accounts.
- **Nothing hidden at install.** Start-at-login is off unless you turn it on.
  The app only writes its settings file (`%APPDATA%\Gunshot` /
  `~/Library/Application Support/Gunshot`).
- **Verifiable downloads.** Every release includes `SHA256SUMS.txt`. Check a
  file with `certutil -hashfile GunshotSetup-x.y.z.exe SHA256` (Windows) or
  `shasum -a 256 Gunshot-*.dmg` (Mac).
- **Signed builds.** Release builds are code-signed (and notarized by Apple on
  macOS) once the signing secrets are configured. See *Releasing* below.

## Sounds

| Sound | What you hear |
| --- | --- |
| Gunshot | A gunshot per key (default) |
| Mechanical Keyboard | Real Cherry MX Blue clicky switches |
| Thocky Keyboard | Real linear switches, deep "thock" |
| IBM Model M | The classic 1986 buckling-spring keyboard |
| Typewriter | Real typewriter keys, with a bell on Enter |
| Yamete Kudasai | One syllable per key: ya-me-te-ku-da-sa-i (real Japanese voice) |
| Moan | Human sighs and moans |
| Zombie | Zombie moan |
| Cat | Meows |
| Duck | Quacks and a rubber-duck squeak |
| Fart | Classic prank |
| Laser | Sci-fi pew-pew |
| Punch | Punch hits |

The recorded sounds are openly licensed (CC0, public domain, CC BY, CC BY-SA)
from Wikimedia Commons. Authors and licenses are listed in
[`gunshot/packs/CREDITS.md`](gunshot/packs/CREDITS.md). Rebuild them with
`python tools/fetch_sounds.py`.

## Adding sounds

Drop a folder of `.wav` files into `gunshot/packs/` and it appears under
**Sound** in the menu. Files named `enter*.wav`, `space*.wav` or
`backspace*.wav` play only on that key. See [`gunshot/packs/README.md`](gunshot/packs/README.md).

## Develop

```powershell
py -3 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt pytest pyinstaller
.\.venv\Scripts\python -m gunshot      # run from source
.\.venv\Scripts\python -m pytest       # tests
.\build.ps1                            # local Windows build -> dist\
```

On Windows you can also double-click `Gunshot.vbs` to run from source with no console window.

| Path | What |
| --- | --- |
| `gunshot/app.py` | Tray menu + keyboard listener |
| `gunshot/sounds.py` | Synthesized gunshot + `.wav` sound-pack loading |
| `gunshot/audio.py` | Low-latency playback (Windows MCI / macOS NSSound) |
| `gunshot/system.py` | Start-at-login, single instance, macOS permission |
| `packaging/`, `installer/` | PyInstaller spec, DMG script, Inno Setup installer |
| `.github/workflows/release.yml` | CI builds + releases for both platforms |

## Releasing

1. Bump `__version__` in `gunshot/__init__.py`.
2. `git tag v1.2.0 && git push --tags`
3. GitHub Actions builds the Windows installer and both Mac disk images, then
   publishes them with checksums as a GitHub Release.

### Code signing (so Windows/macOS don't warn users)

Without signing, the builds still work, but Windows SmartScreen shows "Windows
protected your PC" (users click *More info → Run anyway*) and macOS blocks the
first launch (users right-click → *Open*). To remove those warnings, add these
repository secrets and the workflow signs automatically:

- **Windows:** `WINDOWS_CERT_PFX` (base64 of a code-signing `.pfx`) and
  `WINDOWS_CERT_PASSWORD`. Get a certificate from a CA (e.g. Certum, Sectigo),
  or use Azure Trusted Signing. Free signing for open-source projects is
  available via SignPath Foundation.
- **macOS:** an Apple Developer account ($99/year). Add `MACOS_CERT_P12`,
  `MACOS_CERT_PASSWORD`, `MACOS_SIGN_IDENTITY`, `APPLE_ID`, `APPLE_TEAM_ID` and
  `APPLE_APP_PASSWORD`.
