# Sound packs

Each sub-folder here is a sound pack that shows up in the tray menu under
**Sound**. To add one:

1. Create a folder named the way it should appear in the menu, e.g. `Shotgun/`.
2. Put one or more `.wav` files in it (8/16/32-bit PCM, any sample rate,
   mono or stereo). Each keypress plays one of them at random, so 3-5
   slightly different takes sound more natural than a single file.
3. Keep clips short (under ~0.5 s) and trimmed so the sound starts
   immediately - any silence at the start feels like lag.
4. Only add audio you made yourself or that is licensed for redistribution
   (e.g. CC0), and note the source in a `LICENSE.txt` inside the folder.

The packs are bundled into the installers automatically on the next build.
The built-in **Gunshot** pack is synthesized in code (`gunshot/sounds.py`).

## Sequence packs

To play the files **in order** (one per keypress) instead of at random, add a
`pack.json` containing `{"order": "sequence"}` and name the files so they sort
in order (`01_ya.wav`, `02_me.wav`, ...). The sequence restarts from the first
file after 2 seconds without typing. See `Yamete Kudasai/` for an example.
