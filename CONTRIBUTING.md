# Contributing

Keep examples small enough that another modder can follow every reference.

For a correction or new technique, include:

1. The game version or relevant format version and the starting configuration.
2. The exact record type, field or resource relationship involved.
3. The smallest set of changes that reproduces the result.
4. What was checked offline and what was observed in game.
5. Any unresolved behavior, including differences between a direct grant and a real loot drop.

Use synthetic examples or assets you can distribute. Do not attach extracted game databases, game models, textures, save files, account credentials or personal paths.

Do not turn a build-specific record offset into a general instruction. Prefer named references and explain how the target is resolved against the current database.

Run the examples before submitting a change:

```powershell
python tools/loot_odds.py examples/loot-pools.json
python -m unittest discover -s tests -v
```

The calculator is a fixed-weight teaching example. Changes to it must not imply that it simulates native adaptive loot trackers, selection predicates or the complete reward system.
