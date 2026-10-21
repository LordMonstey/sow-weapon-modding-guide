# Adding weapons to native loot pools

New inventory definitions do not enter random loot automatically. A natural gear drop must reach the new item through a native loot table, an offered gear list, and an eligible nemesis gear record. Additive integration can preserve every native item. An imported-only policy is optional and changes the distribution deliberately.

This page describes inspected compiler/generator contracts and documented native selection logic. Offline reachability, simulated odds, and observed drops are separate evidence. See [tooling and evidence](TOOLING_AND_EVIDENCE.md).

## The exact native route

```text
Faction.LootTable
  Items[] -> FactionLootEntry
    NemesisGearList[] -> Faction.LootNemesisGearList
      LootTypeWeight -> Faction.LootType [or null]
      Entries[] -> Faction.LootNemesisGear
        Tags[] -> Faction.LootTag
        Item -> Inventory.Item
        NemesisAffix -> Inventory.ItemAffix
        UpgradeTiers[] -> Faction.LootNemesisGearUpgradeTier
```

`FactionLootEntry` has no dot between `Faction` and `LootEntry`. “Gear lists” or “GearLists” is descriptive shorthand here; the inspected entry field is `NemesisGearList`, not `GearLists`. `Entries` belongs to the gear list, while the owner table uses `Items`. A scripted `ItemList` or fixed quest reward is another acquisition route.

The demonstrated route uses the gear record's direct `Item` field. The schema also contains additional rarity/affix-related fields. Preserve a qualified donor's behavior instead of assuming all native gear records have an identical minimal layout.

## Create a drop-ready item and gear record

Complete [the inventory item](ADDING_ITEMS.md), using a donor of the same slot and intended rarity. The demonstrated item permits repeat drops, retains the drop-supplied level, and uses a base-only affix picker. The nemesis gear layer contributes further drop behavior.

Clone a corresponding `Faction.LootNemesisGear`. Set `Item` to the new item and update `NAME`/`Desc` to its localization keys. Review `DescriptionOverride`, `IsPreorderItem`, `NemesisAffix`, challenges, and upgrade tiers. The inspected generators clear a donor description override and preorder status for ordinary custom loot.

Inspect `UpgradeTiers[].ArtOverride`. An inherited override can restore native art at acquisition or upgrade even when the inventory item points at a custom model. Clone affected tiers and clear `ArtOverride` on those clones; retain unaffected tiers. Do not edit a shared native tier to fix one new weapon.

Eligibility is essential. The documented native selection requires a matching tag in the captain's context, ranks/scores candidates, and chooses uniformly among ties. An empty `Tags` list does not mean unrestricted eligibility in this path. A nonempty list alone also does not prove suitability for every captain.

The broad admission implementation collects tags from the `LootTags`/`AddLootTags` fields of `Faction.Tribe` and `Faction.TraitMarker`, following `Faction.LootTagWeight.Tag` references. Giving the same coverage to all custom candidates makes their tag-related eligibility comparable. A thematic or tribe-specific item should use the intended tags and be checked against eligible and ineligible contexts. Do not advertise uniform item selection unless the final candidates actually tie.

## Create or extend a reachable gear list

Two additive designs have different probability effects:

| Design | Native edit | Consequence |
| --- | --- | --- |
| Extend an existing list | Add gear to `Faction.LootNemesisGearList.Entries` | Shares that list's route and type weight; changes competition inside the list |
| Add a private list | Clone a list, optionally clone its type, append the list to selected entries | Adds another weighted choice at the list-selection stage |

For a private list, `Entries` references gear records, not inventory items. `LootTypeWeight` references a `Faction.LootType`; it is not itself a numeric weight. Clone a compatible list/type and edit their named fields.

The inspected additive generator creates private epic lists by slot and a legendary group. It appends a private list to entries already offering specified compatible native lists. For example, an epic sword route can match `NemGearList_4Epic_1Sword`, `NemGearList_4Epic_All`, or `NemGearList_4Epic_NoRing`. Legendary matching uses the corresponding `5Lgnd` lists. These are the generator's attachment rules, not universal engine requirements.

Preserve each affected `NemesisGearList` array's foreign members and order. Replace only previously owned entries before adding your current lists. Reject duplicates and unreachable private lists. When components modify the same complete array, compose their changes against one parent. Applying independent full-list patches sequentially can discard an earlier component.

## Decide how broad the route should be

Find every `Faction.LootTable.Items` reference to each entry being patched. Entries and lists may be shared. Matching every entry that offers a native sword list can affect captain drops, revenge/death-threat routes, and chests. That is broad integration even when the patch changes only one record category.

For a scoped reward, inspect the owner graph first. If the selected table shares an entry, clone that entry and rebind only the intended table's `Items` member. If the gear list is shared and needs different contents, clone that list too. Preserve all unrelated members and other fields. This authoring strategy follows the reference graph; the particular route still needs compilation and runtime acceptance.

Do not infer a table's actual trigger solely from its name. Trace its callers or establish the trigger in game. Fixed quest grants and scripted `ItemList` rewards require separate review if they are within scope.

## Calculate conditional odds at each stage

For a selected entry and a snapshot of its candidate weights, a list's first-draw probability is:

```text
P(list L | entry E, state S) = weight(L, S) / sum(candidate weights)
```

For equally eligible, equally ranked candidates in that list:

```text
P(item X | E, S) = P(L | E, S) / number of tied candidates in L
```

With multiple paths to an item, sum their contributions. For nested weighted pools, multiply conditional probabilities along each path, then sum paths ending at that item. Include outer event/table/entry probabilities before claiming an unconditional drop rate.

For example, a custom branch of weight 2 competing with a native branch of weight 8 has a 20% share of that draw. With ten equal custom candidates, each has a 2% share. If an outer event reaches this draw only 25% of the time, each item's overall share in this simplified example is 0.5%.

The [illustrative pool file](../examples/loot-pools.json) and [odds utility](../tools/loot_odds.py) explain this arithmetic. Their weighted-mixture model is not a native engine simulator or GADB compiler.

Native type weights can change over time. The inspected logic uses `InitialWeight`, `OnDropOtherAdjustment`, `OnDropOtherAdjustmentScalar`, and `OnDropThisReturnToValue`. A tracked selected type returns to its configured value; other tracked types update as:

```text
next = clamp((current + adjustment) * scalar, 0.1, 10000)
```

A null type contributes weight 1 in the documented selection path and does not trigger the same tracker update. Types can be updated by draws where their list is absent. Copying native rotation parameters onto a new type therefore does not guarantee a stable share.

The inspected two-pool experiment used constant custom weights of 30 for epic and 1/6 for legendary. Its Monte Carlo results depended on the proportion of draws exposing each list and the number of competing native types. A legendary branch at 1/6 against one constant branch at 1 yields 1/7, about 14.3%, under those assumptions. Weight 30 is not “30%.” These experimental settings are not universal defaults.

The documented runtime path removes a drawn list with no valid/buildable gear and retries remaining candidates. That changes effective probabilities. If all candidates fail, the retry rule alone cannot establish a successful drop. Distinguish fresh tracker initialization from a tracker restored from an older save; the inspected offline simulation does not establish save migration behavior.

## Optional policy: imported gear only

The later local policy replaced the `Entries` of selected native weapon/armor lists with imported gear of the same slot. It mapped rare draws to imported epic gear because that catalogue had no rare items. This is an explicit rarity policy, not a prerequisite for adding weapons.

The policy retained dedicated ring lists, kept rings in a mixed legendary list, and left a documented mission list and fixed scripted rewards outside its scope. It did not modify entry, table, or type records. Its verifier established those preservation checks and graph reachability on an offline merge.

Preserving ring records, membership, and type weights is narrower evidence than proving identical observed ring probabilities in every context. Eligibility and retry behavior still matter. Document which pools change, which remain, and which rarity substitutions are intentional. Do not include this removal policy in an ordinary additive weapon package by default.

## Validate the actual final database and gameplay

Walk affected tables through entry, list, gear, and item in the final database. Record owner tables, new reachable items, removed items, empty lists, duplicate entries, tag coverage, type parameters, and retained foreign members. Resolve names after final ordering. Test regeneration against the current parent and reapplication without duplicate clones or list growth.

Compilation and a graph walk prove offline structure. The inspected latest composition and imported-only dry run do not by themselves confirm runtime behavior of that build. Test natural acquisition from intended routes, different captain contexts, repeat drops, rarity and level, upgrade appearance, equip behavior, and save/reload. Attach observations to the exact package rather than transferring a previous build's runtime status to a new one.
