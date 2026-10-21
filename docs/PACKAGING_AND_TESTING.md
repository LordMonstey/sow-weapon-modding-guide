# Packaging and testing new weapons

A new weapon is complete when its new database identity can be selected by the intended loot route, load its own resources, equip correctly, and survive saving and loading. A mesh export, a valid database, and a successful archive installation establish different parts of that result.

This chapter specifies the build and verification contracts demonstrated by the reference implementation. It is not a command sequence for a toolkit included in this repository. See [Tooling and evidence](TOOLING_AND_EVIDENCE.md) for the public tools and the implementation roles still required.

## 1. Establish the effective baseline

For a clean experiment, pin a known game build and its extracted native database, strings, resource templates, and archive configuration. Keep that fixture separate from the working installation. A clean fixture provides a reproducible reference for native structure; it does not describe an installation that already contains other mods.

For an incremental update, start from the effective installed version of each resource. Record:

| Input | Record before building |
|---|---|
| `game.gamedb` | Source hash, parent package identity, existing record identities and names |
| Every changed locale's `string.strdb` | Source hash and existing key-to-text mapping |
| Shared skeletons and behavior graphs | Effective bytes, library registrations, and previous additions |
| Parent bundles | Effective EMBB payloads and BNDL dependency tables |
| Archives | Installed paths, resource membership, sizes, and hashes |
| `default.archcfg` | Exact contents and mount order |
| Loose overlays | Effective virtual path, content hash, and owning component |
| Optional runtime extensions | Version and the database or UI assumptions they depend on |

Rebuilding an existing modded database from a clean native database can remove earlier items, script bindings, loot edits, strings, or animations. A valid delta must name the exact parent hash it extends and fail if that parent differs.

Installation receipts and the latest completed operation take precedence over an older status heading. A reserved build number or a build in progress is not an installed baseline. The reference project's later coordination entries superseded its summary table, which illustrates why this distinction matters.

## 2. Compile the GADB change without changing old identities

The reference compiler assigns an appended record a typed reference using:

```text
reference = (category_index << 20) | record_ordinal
```

That identity is distinct from the record's byte offset in the rebuilt file. Adding shared atoms, descriptors, records, or longer lists can move subsequent serialized bytes. Preserve existing category indices and record ordinals while rebuilding the affected layout.

For a cloned record or a changed list, a compiler must:

1. Resolve references and clone labels against the declared source and the complete set of additions in the current build.
2. Preserve the existing shared atom table as a byte-exact prefix; append aligned strings or other supported atoms.
3. Preserve existing descriptor blocks. If a list changes length, clone its descriptor block, update that field's count and offset, and relocate the later affected fields within the record.
4. Recompute record value counts, descriptor indices, category counts, and database totals. Respect field widths and reject overflow or overlapping serialized fields.
5. Require expected old values for every deliberate edit of an existing record.
6. Reparse the output and prove that unrelated records, original ordinals, atom prefixes, and descriptor prefixes remain unchanged.

Raw byte offsets from the old database are not a durable interface. Even when old relative atom offsets remain unchanged, the enclosing tables can move. External consumers must resolve through the new database or verify the precise values and offsets on which they depend. Preserving existing UI records is particularly important if a separate UI extension reads them.

### Named lookup is a separate constraint

A database can parse successfully and still fail native lookup by record name. Named records in the reference format are searched by their native 32-bit name hash and must remain strictly ordered for the observed binary-search path. Appending arbitrary readable names does not establish that property.

Reordering all records to sort the names would change ordinal-based references. The reference implementation instead assigns names to newly appended project-owned records whose hashes extend the existing ordered tail. It keeps all old ordinals and typed references unchanged and records a mapping from the authoring label to the final serialized name.

This strategy requires sufficient hash space after the existing tail and a verified name-hash implementation. It is one implemented solution, not a requirement to use the same suffix generator. Any replacement must prove both native name lookup and stable record identity.

After finalizing names:

- Check binary lookup for every named record, including inherited records.
- Preserve every already installed name exactly.
- Update exact string consumers of newly renamed records. Review scripts and other resources that refer to those names outside the database.
- Do not perform broad substring replacements inside scripts or unrelated text.
- Use the final mapping for diagnostics or a controlled acquisition test. An authoring label is not necessarily the name accepted by the game.

## 3. Extend STRDB tables without losing existing text

Weapon name and description fields refer to localization keys. Those keys must resolve in every locale the package claims to support.

The inspected `string.strdb` format is SKDB version 9: a 28-byte header, entries containing a 32-bit key hash and a UTF-16 code-unit offset, followed by UTF-16LE NUL-terminated strings. Entries are ordered by key hash. The text offset counts UTF-16 code units, not bytes or Unicode code points.

For each supported locale:

1. Read its effective installed table. Use an extracted native table only when that locale has no installed replacement or higher-priority overlay.
2. Allocate project-owned name and description keys and compute their native hashes.
3. Check the new keys against each other and against the available existing key catalog. An existing hash alone does not prove that the entry belongs to the same textual key, because the table stores hashes rather than the original key names.
4. Preserve an existing owned key when its text is identical. For an intentional text revision, append the new UTF-16 text and repoint only that key.
5. Sort entries by hash, update counts and text extents, then reparse.
6. Compare every unaffected key's decoded text with the baseline and resolve every requested key to its expected text.

Keep localization keys separate from internal GADB record names. The suffix chosen to satisfy named-record ordering does not require renaming the display key. Several components that change the same locale must be merged or chained through one table; independently packaging two tables at the same virtual path does not combine them.

## 4. Build the resource dependency closure

A new virtual path must resolve to actual bytes, and each resource must be reachable through the bundle used by the item. An archive containing a mesh is insufficient if the item's selected bundle never requests it.

| Form | Role | Required checks |
|---|---|---|
| `.embb`, magic `EMBB` | Embeds named resource payloads with individual lengths | Preserve untouched child bytes and order; rebuild changed lengths and appended name offsets; reparse every child |
| `.bndl`, magic `BNDL` | Names dependencies and carries size hints and bundle metadata | Preserve kind/version and unrelated entries; update hints for changed resources; add dependencies needed by the actual load route |

A BNDL can reference a resource that is not embedded in its paired EMBB. Native examples use external material, texture, or shader resources. Identical BNDL and EMBB membership is therefore not a general invariant. Resolve each dependency either to a matching embedded payload or to an available external resource under the effective mount configuration.

For newly written or changed resources, use the verified payload size where the template's hint contract calls for it. Preserve unrelated native BNDL hints, even when they differ from EMBB payload lengths. Blindly replacing every hint with the current file length changes data outside the intended edit.

Walk the complete item-local chain, including mesh, skeleton, material sets, materials, textures, shaders, and any referenced effects or animation libraries. Verify material/shader identity as well as path existence. If an embedded child also has a direct archive entry, compare their hashes; a fresh loose mesh does not repair an older copy embedded in the bundle actually loaded.

Shared textures can be deduplicated by content while each item still declares its own dependencies. Avoid preloading a whole catalog through an unrelated global bundle. The internal component format has an `item_local` preload option because an older package default attached native dependencies to an unrelated preload root. Public implementations should make the intended load root explicit.

## 5. Register new paths in native archives

The demonstrated packaging route uses LTAR `.arch06` archives and a native binary `archivepatchloosefiles.txt`. Despite its extension, that patch list is not a newline-separated text file.

The inspected patch list stores a version, a path-string table, and sorted pairs of native path hash and string-table offset. A new resource needs both an archive entry and the correct patch-list registration.

The native resource-path hash uses unsigned 32-bit arithmetic with multiplier `0x397` and the game's character map. The reference wrapper normalizes virtual paths to backslashes before hashing. The native byte routine itself distinguishes slash from backslash, so these must not be treated as interchangeable without normalization. The character map implements ASCII case equivalence; a general language or locale hash is not a substitute.

Before writing:

- Canonicalize paths consistently, reject duplicate normalized paths, and reject drive-qualified, absolute, or parent-traversal paths.
- Verify the hash implementation against native reference entries.
- Check different paths for hash collisions across the complete logical package, known inherited resources, and the native reference catalog available to the build. A group-local check alone can miss a collision in another archive.
- If two new paths collide, choose a different owned path and update all consumers, including bundle and material references. Do not silently overwrite an entry or change a native path's known hash.
- Register the patch list itself according to the demonstrated archive contract.

The collision guarantee is limited by the catalog checked. A check against a small native reference list does not prove uniqueness across every resource in the game.

Reopen the written archive with an independent reader. Validate the LTAR tree, index, declared sizes, chunk boundaries, padding, resource payload hashes, and binary patch list. A whole-archive SHA-256 proves that bytes have not changed since hashing; it does not prove they form a valid archive.

## 6. Keep a full logical package, write only changed groups

An incremental package still describes the complete resulting virtual file set. It retains every inherited resource unless an explicit, reviewed change replaces it. The database proof must point to the same parent database as the parent package.

Split archives reduce rebuilding and copying. Partition resources into disjoint groups, for example database and strings, geometry and textures, and animation libraries. Apply specific grouping rules before generic fallback rules, then pin the resulting membership in the split manifest.

Each physical group needs its own patch list. The union of group resources, excluding those per-group patch lists, must equal the logical package exactly. The same virtual resource must not accidentally belong to two groups.

Use a content identity based on normalized virtual paths and resource hashes to find changed groups. Keep that identity distinct from the SHA-256 of the archive file. The reference implementation additionally hashes the complete logical list of `(path, sha256, bytes)` tuples.

An unchanged group may reuse retained staging or the exact installed archive verified against its recorded size and hash. Missing old staging is acceptable only if an exact backing copy remains. Present but corrupted staging must fail validation. Keep the parent manifests, database sources, proofs, and receipts needed to validate later deltas; deleting those because an archive is installed can break the next build.

## 7. Verify mount precedence and loose overlays

In the observed `default.archcfg` archive ordering, the last line is searched first. Mount position therefore matters whenever another archive provides the same virtual path. Preserve unrelated mount entries and change only the block owned by the package.

The reference installation also uses a loose mount named `Monstey_Live` with priority over packaged resources. This is an internal development convention, not a universal directory supplied by the game or by this guide.

Two failures are possible:

- A stale loose resource wins over a correct new archive, so the game tests old bytes.
- Reconciliation removes a newer intended development resource and exposes an older inherited archive copy underneath it.

The inspected reconciliation code compares content hashes and modification times. A differing live file older than the build can be retired, while a file pushed after the build is retained. That heuristic does not decide which implementation is correct. Record the intended winning bytes explicitly and verify them after installation.

This occurred with an inventory UI resource: a newer live version had to be preserved while the inherited archive still contained older bytes. The same issue applies to animation libraries and their BNDL size hints. Preserve or package the verified effective version, then confirm the mounted result, not only the build manifest.

## 8. Install and roll back as one transaction

Close the game before changing its archives or mount configuration. Install only after the complete package and its physical archives pass validation.

A transactional installer should:

1. Verify the installed baseline and produce a plan of changed, unchanged, added, and removed managed archives.
2. Save the mount configuration, installed-state metadata, and hashes of replaced files. Retain a separate save backup for runtime testing.
3. Copy changed archives to temporary destinations and verify their size and hash before publishing them.
4. Retain previous managed archives, publish the new files, and commit the configuration, installed state, and receipt consistently.
5. Read back the committed files and metadata. Verify effective loose overlays separately.
6. On failure, restore renamed archives, configuration, and state, including failure after a partial publish or partial backup move. Remove only newly created transaction files.

The internal implementation can retain previous archives through same-volume renames, avoiding a second copy of large files. This is an implementation optimization, not a requirement to use a particular backup directory.

A rollback receipt should identify the original error and any restoration error separately. An incomplete rollback must remain visible. Restoring archive files does not undo game progress saved during a later runtime test. Retain the matching test-save backup rather than assuming a save containing new item identities is compatible with a package that no longer defines them.

## 9. Run static and runtime acceptance separately

### Offline acceptance

| Area | Pass condition |
|---|---|
| Identity | Existing ordinals and names are unchanged; all new typed references resolve |
| Native name lookup | Every named record is recovered at its intended ordinal through the native ordering contract |
| Loot route | Intended tables reach the new items; eligibility, tags, tiers, and appearance overrides have been checked |
| Localization | New keys resolve in supported locales; unrelated existing texts remain identical |
| Visual closure | Every referenced dependency resolves; embedded and direct copies agree where both exist |
| Animation | Libraries and clips resolve; decoded samples are finite; event requirements and graph predicates are satisfied |
| Packaging | No duplicate paths or known hash collisions; each archive reparses and reproduces expected payload hashes |
| Preservation | Every inherited change outside the declared edit set remains intact |
| Installation | Actual installed files, configuration, receipt, and effective overlays match the intended result |
| Failure handling | Partial copy, partial publish, state-write failure, and backup failure restore the preceding installation in a fixture |

Synthetic fixtures are useful for serializer and installer failure tests. They do not replace validation of a real database. The internal split-archive tests use real tiny LTAR archives but an explicitly substituted GADB proof for their miniature payload; that suite alone is not evidence of game database compatibility.

### In-game acceptance

Test a deliberately small catalog first, then expand coverage. Record the game build, installed package identity, effective overlay hashes, locale, test save, acquisition source, item identity, and result.

| Scenario | Evidence to capture |
|---|---|
| Start and load | The game starts and an existing test save loads with the package active |
| Fresh native drop | A newly generated eligible encounter produces the added item through the intended loot route |
| Inventory | The new item has its own identity, correct name, description, icon, rarity, level, and intended slot |
| Equip and unequip | Correct model and attachments appear; another item can be equipped; no stale model remains |
| Normal use | Attacks, hit events, sheathing, locomotion, transitions, and relevant effects behave correctly |
| Ranged use | Draw, hold, cancel, release, projectile, ammunition, and aim transitions work repeatedly |
| Persistence | Save, fully exit, restart, and reload; verify the acquired item's identity and intended equipment state |
| Return visit | Travel or reload the region, then reacquire another eligible drop and retest equip behavior |
| Baseline regression | Existing native equipment and earlier added items still load and function |
| Rollback | Restore the previous package and its matching test save, then confirm the baseline starts and loads |

A controlled grant can isolate inventory or equipment problems, but it does not prove natural loot selection. Seeing a drop icon does not prove equip behavior or persistence. A weighted random pool does not promise a particular item on the next kill; record eligibility and enough trials to interpret the result.

A new save is not automatically required to add loot records. Begin with a backed-up existing test save and newly generated loot. Previously acquired or already generated drops retain their recorded instance choices; changing a loot table does not reroll them. Shared resource or definition changes may still affect how an old instance is displayed. Use a clean save as an additional diagnostic when the test requires fresh campaign state, and report that condition explicitly.

### A recent bow regression and what it proves

The reference project documented a bow that repeatedly returned from a drawn state while the input remained held. Replacing its animation clips with native motion did not fully fix it. Native `Predicate.ActiveNode` checks still referred to native behavior nodes, while the private cloned states were absent from those checks. A transition therefore treated the bow as no longer drawing and interrupted it.

The targeted correction routed the affected animation records through the native behavior states. That change was tested in game and recorded as successful; the generator's state mapping was updated for subsequent builds. This supports the narrower lesson that state predicates and transition topology are part of weapon correctness. It does not establish that every ranged variant or the entire equipment catalog has passed runtime testing.

The reviewed bulk v154 installation has extensive offline and installed-file evidence, but its receipt explicitly records `runtime_verified=false`. Later successful targeted tests must be recorded as their own coverage, not used to upgrade that whole batch to runtime-verified status.
