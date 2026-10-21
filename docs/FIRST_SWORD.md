# First sword

Use a native sword as the donor. Give the new item its own identity; reuse the donor's art for this first exercise.

## 1. Extract and discover

From the repository folder, with your installation path:

```powershell
$game = 'D:\Games\ShadowOfWar'
New-Item -ItemType Directory -Force scratch | Out-Null
python tools/archive_read.py "$game" find database/game/game.gamedb
python tools/archive_read.py "$game" extract database/game/game.gamedb --output scratch/game.gamedb
python tools/gadb_read.py scratch/game.gamedb demo-sword --brief
```

The finder honors `x64/default.archcfg`, including loose folders. On a modded installation it selects the effective modded database. Pass a particular `.arch06` instead of the game folder to inspect that archive alone.

## 2. Inspect the chosen item

Save the full result to get its exact selector:

```powershell
python tools/gadb_read.py scratch/game.gamedb demo-sword > scratch/sword.json
$sword = Get-Content -Raw scratch/sword.json | ConvertFrom-Json

python tools/gadb_read.py scratch/game.gamedb record "$($sword.selector)"
python tools/gadb_read.py scratch/game.gamedb chain "$($sword.selector)"
python tools/gadb_read.py scratch/game.gamedb loot "$($sword.selector)"
python tools/gadb_read.py scratch/game.gamedb resolve "$($sword.reference)"
```

`chain` follows the item through its builder and equipped data to models and bundles. `loot` follows reverse references to gear records, lists, entries and tables. Shared lists can affect several rewards.

To find another donor:

```powershell
python tools/gadb_read.py scratch/game.gamedb find --category Inventory.Item --contains Sword --limit 10
```

## 3. Check its display name

```powershell
python tools/archive_read.py "$game" extract database/string/enus/string.strdb --output scratch/enus.strdb
python tools/strdb_read.py scratch/enus.strdb summary
```

Inspect the chosen `Inventory.EquippedItemData` record with `record`. Pass its `ItemName` value to:

```powershell
python tools/strdb_read.py scratch/enus.strdb lookup 'KEY_FROM_ItemName'
```

Replace the marked key with the returned value. The key is different from the displayed weapon name.

## 4. Plan the addition

| Clone | Change |
| --- | --- |
| `Inventory.Item` | Point `ItemBuilder` to the new builder. |
| `Inventory.ItemBuilder` | Substitute the new equipped-data reference in `WeaponData`; preserve other members. |
| `Inventory.EquippedItemData` | Set new `ItemName` and `ItemDesc` keys; keep native models and bundles. |
| `Faction.LootNemesisGear` | Point `Item` to the new item; align `NAME` and `Desc`. |

Append the new gear reference to the selected `Faction.LootNemesisGearList.Entries`. Preserve the donor's intended slot, rarity, affixes, tags and level behavior. Review `Combat.PredicateItem.Items` memberships that enumerate the donor.

For one reward only, clone shared lists/entries and rebind that table's `Items` member. For broader distribution, extend the intended shared list.

## 5. Write and validate

**A database writer is not included.** Implement [GADB record/list extension](GADB_FORMAT.md#extending-the-database): reserve stable ordinals, allocate atoms, copy descriptors when lists grow, update counts and enforce native name-hash order. The section supplies the exact structures and algorithm.

Add the two display keys using [SKDB v9](ARCHIVE_FORMAT.md#skdb-v9-string-tables). Reusing native art requires no new model or material serializer.

Once your writer has produced candidate files:

```powershell
python tools/gadb_read.py scratch/candidate/game.gamedb validate --all-fields
python tools/gadb_read.py scratch/candidate/game.gamedb chain 'Inventory.Item:YOUR_FINAL_NAME'
python tools/gadb_read.py scratch/candidate/game.gamedb loot 'Inventory.Item:YOUR_FINAL_NAME'
python tools/strdb_read.py scratch/candidate/enus.strdb lookup 'YOUR_NEW_NAME_KEY'
```

Use the final serialized name from your writer's name map. Compare unchanged records and strings against the source.

## 6. Package and test

Implement the [archive layout and patch list](ARCHIVE_FORMAT.md). Raw chunks avoid needing an Oodle encoder. Package the changed database, locale table and binary patch list, then read back:

```powershell
python tools/archive_read.py scratch/candidate/ExampleSword.arch06 list --limit 0
python tools/archive_read.py scratch/candidate/ExampleSword.arch06 extract database/game/game.gamedb --output scratch/readback.gamedb
python tools/gadb_read.py scratch/readback.gamedb validate --all-fields
Get-FileHash scratch/candidate/game.gamedb
Get-FileHash scratch/readback.gamedb
```

The hashes must match. Back up the mount configuration and a test save. Close the game, install the completed archive, and add its relative path to `x64/default.archcfg` at the intended priority; search order is bottom-up.

Check the effective database with `archive_read.py "$game" find database/game/game.gamedb`. Test a **newly generated drop**, equip/unequip, attacks and save/reload. A direct item grant does not prove natural loot eligibility.
