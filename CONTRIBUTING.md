# Contributing to Gunshot

Thanks for helping! Bug reports, new sound packs and code are all welcome.

## Run it from source

```powershell
py -3 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt pytest pyinstaller
.\.venv\Scripts\python -m gunshot      # run (tray icon appears)
.\.venv\Scripts\python -m pytest       # tests - please keep these passing
```

On macOS use `python3 -m venv .venv` and `.venv/bin/...`. The first run needs
**Input Monitoring** permission for your terminal.

## Adding a sound pack

1. Make a folder in `gunshot/packs/<Pack Name>/` with 3-12 short `.wav` clips.
   See [`gunshot/packs/README.md`](gunshot/packs/README.md) for the format,
   sequence packs and per-key sounds (`enter*.wav`, ...).
2. **Only use audio you're allowed to redistribute**: your own recordings, CC0,
   public domain, CC BY or CC BY-SA. Note the source and license in
   `gunshot/packs/CREDITS.md`. Sounds from Wikimedia Commons can be added
   to the `MANIFEST` in `tools/fetch_sounds.py`, which downloads, trims and
   credits them automatically.
3. Keep clips short (under ~0.5 s) and starting immediately. Silence before
   the sound feels like lag.

## Pull requests

- Keep each PR focused on one thing, and describe what you tested.
- Run `python -m pytest` before opening it. CI builds Windows and macOS too.
- Privacy is a core promise: never log, store or transmit which keys are
  pressed, and don't add network access.

## Releasing (maintainers)

Bump `__version__` in `gunshot/__init__.py`, then
`git tag vX.Y.Z && git push origin vX.Y.Z`. GitHub Actions builds the
installers and publishes the release.
