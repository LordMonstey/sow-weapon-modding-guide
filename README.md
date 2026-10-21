# Shadow of War database tools

Find a sword in your game, follow its model references, and see which loot tables contain it.

**Requirements:** Python 3.10+. Compressed game archives require 64-bit Windows and the Oodle DLL supplied with your game. No pip packages.

## Quick start

Clone this repository, open PowerShell in its folder, and set your game path:

```powershell
$game = 'D:\Games\ShadowOfWar'
New-Item -ItemType Directory -Force scratch | Out-Null
python tools/archive_read.py "$game" extract database/game/game.gamedb --output scratch/game.gamedb
python tools/gadb_read.py scratch/game.gamedb demo-sword --brief
```

Already have `game.gamedb`? Run the last command against that file.

The tools read the game without modifying it. Extraction creates a new file and refuses to overwrite an existing one.

## Next

- [First sword](docs/FIRST_SWORD.md): exact commands for inspecting an item and planning an addition.
- [GADB format](docs/GADB_FORMAT.md): offsets, fields, references, hashes and record/list extension.
- [Archive and string formats](docs/ARCHIVE_FORMAT.md): LTAR, patch lists and SKDB v9.
- [Validation](docs/appendices/VALIDATION.md): tests and real-file checks.

`gadb_read.py` also provides `categories`, `find`, `record`, `resolve`, `chain`, `loot` and `validate`. Output is JSON unless `--brief` is selected. Use each command's `--help`.

Database writing and mod installation are not implemented. Their binary requirements are documented in the format references.

```powershell
python -m unittest discover -s tests -v
```

Original code and documentation: [MIT](LICENSE). Fixtures are synthetic; no game assets are included.
