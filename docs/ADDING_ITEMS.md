# Adding a new native weapon item

A new mesh becomes a new inventory weapon only when a dedicated native item record selects its own equipment and visual records. Replacing a donor mesh or material changes the appearance of its existing consumers. It does not create another collectible item, save identity, or loot result.

This workflow adds an `Inventory.Item` within an existing native equipment slot. An axe or hammer model can use the sword slot and its established behavior. Creating an additional gameplay weapon class, inventory category, or attack system is separate work. A different model and display name do not establish those systems.

The fields below are verified in the inspected named-field compiler and item generators. Source inspection and offline compilation do not establish that every resulting combination works in game. See [tooling and evidence](TOOLING_AND_EVIDENCE.md).

## Choose a donor that already behaves correctly

Start from the database used by your complete mod stack and record its hash. Select a native loot item of the intended slot and rarity, then follow its references. Do not assemble unrelated records merely because their names look similar.

The inspected armory generator finds epic donors through lists such as `Faction.LootNemesisGearList:NemGearList_4Epic_1Sword`. For legendary donors, it filters `NemGearList_5Lgnd_All` for the intended slot. The gear record leads to its `Item`, the item's `ItemBuilder`, and that builder's `WeaponData`. This supplies a consistent starting contract for slot, UI, affixes, and drop construction.

A story reward is not automatically a suitable random-drop donor. The earlier grant-oriented generator used a story sword with a complete affix picker and player-level override. The later loot generator changed those settings to match native drops. Copying the grant settings unchanged can produce the wrong level or duplicate affix selection.

Clone only records whose identity or values must differ. Keep suitable native combat data, rarity UI, world pickup data, and unchanged stats shared. Give authored records unique project-owned IDs. Preserve native donor records and resources for their existing consumers.

## Build the equipment reference graph

The exact weapon graph inspected in the generators is:

```text
Inventory.Item
  ItemBuilder -> Inventory.ItemBuilder
    WeaponData[] -> Inventory.EquippedItemData
      DynamicBundle[] -> DynamicResource.BundleDefinition
        Bundle -> resource path
      Model[] -> InventoryItemModel
        Models[] -> InventoryModel
          ModelRecord -> Model
            ModelFile -> .skel resource path [with matching .mesh]
            MaterialSets[] -> MaterialSet
          CompanionModelRecord -> Model [optional spectral representation]
      PreviewModel -> Model [where explicitly used]
```

`InventoryItemModel` and `InventoryModel` are native category names without an `Inventory.` prefix. `Inventory.Item.BaseWeaponData` selects combat data; `Inventory.ItemBuilder.WeaponData` selects equipped appearance data. These are different links.

| Record | Fields to review |
| --- | --- |
| `Inventory.Item` | `ItemBuilder`, `BaseWeaponData`, `UIItemData`, `WorldItemData`, `ItemSet`, `PairedItems`, quantity and save settings |
| `Inventory.ItemBuilder` | `WeaponData`, `AffixPicker`, `NemesisGearItem`, level overrides |
| `Inventory.EquippedItemData` | `ItemName`, `ItemDesc`, `Model`, `DynamicBundle`, `AddItemOnEquip`, `PreviewModel`, upgrade and UI overrides |
| `InventoryItemModel` | `Models`, `OverrideModels`, `MaterialOverrides`, active/inactive attachment nodes and animations |
| `InventoryModel` | `ModelRecord`, `CompanionModelRecord`, `MinMeshIndex`, `MaxMeshIndex` |
| `Model` / `MaterialSet` | `ModelFile`, `MaterialSets`, physical and spectral material arrays |

Use private copies of the changed chain so the new item can coexist with its donor. Multiple runtime inventory instances can share one item definition and visual graph. A dedicated definition does not require a duplicate mesh for every acquired instance.

Reset inherited overrides only when they conflict with the intended appearance. The inspected weapon builder clears model/material overrides and tint in its private chain, sets a private preview, and explicitly chooses its mesh range. Preserve a scabbard through `AddItemOnEquip` only when it fits the new weapon. Attachment nodes and sheathed placement remain part of the equipment contract.

In the inspected weapon route, `ModelFile` points to the model's `.skel`, with its matching `.mesh` alongside it. The bundle must make that qualified pair, materials, textures, and required shaders available through the loading route. A valid database reference cannot compensate for a missing resource. Spectral appearance also needs a deliberate companion model/material choice. See [asset pipeline](ASSET_PIPELINE.md).

## Give it native inventory and drop semantics

For repeatable native drops, the inspected implementation uses this field summary:

| Record | Field | Value |
| --- | --- | --- |
| Item | `MaxQuantity` | `0` |
| Item | `CanSaveThisItem` | `true` |
| Item | `TriggerPlayerSave` | `true` |
| Builder | `NemesisGearItem` | `null` |
| Builder | `OverrideILvl` | `0` |
| Builder | `OverrideILvlMatchPlayerLevel` | `false` |

In this drop path, `MaxQuantity: 0` permits repeated instances. The level settings preserve the level supplied by the native drop constructor; they do not mean every item is level zero. A one-time grant can intentionally use different settings, but that is another acquisition policy.

For the demonstrated loot design, the builder's affix picker supplies the base damage group. The `Faction.LootNemesisGear` record supplies the nemesis affix, challenge, and upgrade behavior. Inspect both before reusing a complete grant-oriented picker. Clearing `ItemSet` is appropriate for an independent item that should not inherit the donor's set bonus. Keeping a set requires an intentional compatible design.

`ItemName` and `ItemDesc` contain localization keys. Add those keys to the required string tables while preserving existing keys and payloads. The loot gear record also has name/description fields, written as `NAME` and `Desc` by the inspected generator. Keep both presentation paths consistent. Rarity presentation comes from native UI/world records and affix configuration, not the display name.

## Make equipment predicates recognize it

A new item identity is not automatically a member of native combat predicates. The inspected generators scan `Combat.PredicateItem.Items` for the actual donor and add the new item to relevant native lists. Observed sword examples include `PC_Sword`, `PC_SwordOrDagger`, and equipment activation lists.

Review each membership's purpose. A list name such as `PC_LegendaryGear` does not establish that every new sword belongs there. The generalized armory generator follows the actual slot/rarity donor and excludes private project-owned gates from automatic expansion. A private stance gate must retain its explicit owner and intended membership.

Write each changed list as its complete final value: preserve foreign members in their original order, remove only your own previous entries, then add your intended entries once. Regenerate against the current parent database. Blind appends accumulate duplicates on persistent rebuilds; a list copied from an older parent can erase another component's additions.

## Resolve names and compile the complete stack

The verified authoring syntax uses `clones`, `patches`, `set`, and `lists`. New references use `{"clone":"Monstey_DemoSword"}`. Existing references use `{"record":"Category:FinalName"}` or a reference resolved from the exact source database. The [annotated example](../examples/weapon-records.annotated.json) uses these actual forms with unresolved donor placeholders. It is an intermediate teaching example, not a runnable package.

Compile dependent components together. Once a clone exists in the source, resolve its final identity and emit a patch. Resolve references to other components' records too: a stale `clone` reference is not valid merely because a previous build created that record.

Named records must remain sorted by the native name hash. Typed references can pass while name-based lookup fails. The inspected `Monstey_GadbNamedOrder` step assigns names while preserving ordinals. Propagate its rename map to exact string consumers, including scripts. Do not guess final suffixes or reuse another build's ordinal references.

## Validate acquisition, equip, and persistence separately

Offline checks should establish unique identities, valid reference types, complete visual dependencies, correct predicate membership, consistent localization, and no unintended donor changes. Compile the actual combined stack without warnings and reapply it to test idempotence. Inspect the final database after name repair, not only an intermediate spec.

Then test the packaged build in game: acquire the item, inspect its name and rarity, equip and sheath it, attack, enter spectral mode where applicable, obtain a second instance, and save/reload. Test upgrades to ensure donor art does not return. Record the exact package hash and observed results.

Random acquisition requires the additional [loot-pool graph](LOOT_POOLS.md). A successful inventory grant proves neither natural drop eligibility nor the distribution of future drops.
