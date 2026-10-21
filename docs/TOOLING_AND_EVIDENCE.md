# Tooling and evidence

This repository documents a native method for adding new weapons and loot to Shadow of War. It does not ship the reference project's complete database compiler, resource packager, installer, or game assets. A reader can use the public tools below for specific stages; completing the integration still requires the remaining roles described here.

## Public tools

| Project | Available capability | Boundary |
|---|---|---|
| [Monstey Mesh Publisher](https://github.com/LordMonstey/Monstey-Mesh-Publisher) | Blender import and export of MMSH v17 models; native skeleton and material associations; native editing and custom geometry export against a native template; JSON reports | Exports model resources. It does not create inventory records, compile loot tables, build archives, or install a weapon |
| [sow-anix-format](https://github.com/LordMonstey/sow-anix-format) | ANIX v44 specification, reference reader and codecs, packed-quaternion and UATR encoders, synthetic codec tests | Provides animation format knowledge and reference code. It is not a complete animation retargeter, combat-graph editor, weapon builder, or game installer |

Mesh Publisher's native editing path preserves an unedited import byte-for-byte. Its custom geometry workflow still requires a suitable native template, correct binding, and pose review. Blender preview materials do not replace native material and shader authoring.

Use the selected [public release](https://github.com/LordMonstey/Monstey-Mesh-Publisher/releases/latest) and its documented features as the capability contract. This guide relies on Mesh Publisher's mesh workflow and the separate ANIX reference project. See the [Blender guide](https://github.com/LordMonstey/Monstey-Mesh-Publisher/blob/master/docs/BLENDER.md) for native model editing, custom export, and binding limits.

The ANIX reference project reports checks against 1,017 native libraries and in-game playback of libraries written from its specification. That evidence concerns the animation format and playback. It does not validate the database, loot, materials, or installation of a new weapon assembled with it.

Neither public project includes the game's source resources. Extracted templates, proprietary meshes, textures, animation clips, and binary game data are not distributed in this guide.

## Required implementation roles

The following table describes the capabilities a complete implementation needs. Internal module names are evidence references, not download links or commands that can be run from this repository.

| Role | Required behavior | Reference implementation inspected |
|---|---|---|
| Resource extractor and inspector | Read the relevant game build's archives and native resource templates; retain provenance | `Monstey_ExtractSowAssets.py`, `Monstey_Index` |
| GADB reader and compiler | Resolve typed records, clone records, extend lists, preserve existing ordinals and shared data, and reparse the result | `Monstey_GadbInspect.py`, `Monstey_Gadb`; `Monstey_GadbEdit.py`, `Monstey_EditGadb` |
| Named-record finalizer | Satisfy native name-hash ordering without renumbering installed records; emit the final name map | `Monstey_GadbNamedOrder.py`, `Monstey_Repair`, `Monstey_NameHash`, `Monstey_Search` |
| Weapon and loot authoring | Build the complete item chain and the intended acquisition route against the current source database | `weapon_items.py`; project-specific equipment and loot generators |
| Localization writer | Add owned keys to effective locale tables, preserve existing text, and verify readback | `weapon_strings.py`, `parse`, `add_keys`, `main` |
| Native material and texture authoring | Produce resources compatible with the selected native shader and retain correct paths and channel meanings | Project-specific conversion tools; not supplied by Mesh Publisher's Blender material preview |
| Bundle writer | Rebuild changed EMBB children and BNDL dependencies without changing unrelated contents | `Monstey_SowBundleWriter.py`, `Monstey_RebuildEmbb`, `Monstey_RebuildBndl`, `Monstey_ValidateMaterialShader` |
| Path registration | Reproduce native resource hashes and build sorted binary patch lists with collision checks | `Monstey_SowPathHash.py`, `Monstey_PathHash`; `Monstey_SowPatchList.py`, `Monstey_BuildPatchList` |
| Package builder and validator | Preserve the full inherited logical resource set, verify the parent database, write native archives, and read back payloads | `Monstey_CrimsonRetinueBuild.py`, `Monstey_Merge`, `Monstey_Build`, `Monstey_ValidateContents`; `Monstey_PackageMounts.py`, `Monstey_WriteArchive`, `Monstey_VerifyArchive` |
| Optional split storage | Partition the logical package into disjoint physical groups and reuse unchanged verified archives | `Monstey_SplitArchives.py`, `partition`, `build`, `Monstey_ValidateSplit` |
| Installer and rollback | Verify the baseline, publish staged archives, preserve mount order, commit receipts, and recover from partial failure | `Monstey_InstallSplit.py`, `new_config`, `main`, `Monstey_MoveBackups` |
| Optional development overlay | Track the resource that actually wins over an archive and reconcile it without losing intended work | `Monstey_LiveMount.py`, `Monstey_Reconcile` |

These internal tools have project-specific directory constraints, native baseline assumptions, schemas, and dependencies. Copying their filenames into a command line does not create a portable pipeline. The public guide describes their contracts so another implementation can reproduce the behavior without inheriting private configuration or assets.

## Evidence levels

Use a specific evidence level for each claim and each tested item family.

| Level | What it establishes | What remains unproven |
|---|---|---|
| Format or code inspection | An observed structure, lookup rule, or execution route | Whether a particular generated package satisfies it |
| Synthetic fixture | Writer/readback behavior or a failure path under controlled inputs | Compatibility with all real native resources |
| Offline native validation | The tested real resources satisfy the implemented structural and preservation checks | Actual loading, rendering, combat behavior, and persistence |
| Installed-file verification | The intended bytes and configuration reached the installation | Whether the game selected and used those bytes as intended |
| Targeted runtime verification | A named scenario worked for a recorded build, item, and save | Untested variants, scenarios, or later changes |

Passing one level does not silently promote another. A successful acquisition test does not prove natural drop probability, and a successful equip test does not prove persistence after restarting.

## Evidence ledger

The guide was prepared from implementation source, validation reports, and integration notes reviewed on 21 October 2026. Internal sources named below are not included in this public repository. They identify where the conclusions came from; they are not presented as independently downloadable evidence.

| Claim in this guide | Source basename and symbol or record | Evidence and limit |
|---|---|---|
| New equipment can have a native identity separate from existing weapons | `import-armes-et-stance-katana.md`, sections 1 and 9; `weapon_items.py` | Earlier addition and acquisition were recorded, including a successful grant log. The later native loot route is documented separately; the first grant is not a natural-drop test |
| Existing ordinal references can be preserved while serialized layout grows | `Monstey_GadbEdit.py`, `Monstey_EditGadb` | Compiler reconstructs records and descriptor blocks, then compares original records, atom prefix, and descriptor prefix |
| Appended readable names alone are insufficient for native name lookup | `Monstey_GadbNamedOrder.py`, `Monstey_Repair`, `Monstey_Search` | Strict hash ordering and lookup are checked for every named record; typed references remain unchanged |
| Installed private names are stable across incremental builds | `Monstey_CrimsonRetinueBuild.py`, `Monstey_Merge` | Merge rejects a changed name belonging to the source database |
| Existing localization text is preserved when new keys are added | `weapon_strings.py`, `add_keys`, `main` | Uses the installed locale table when present; compares every unaffected decoded text and resolves new keys. Hash ownership still requires a key catalog |
| BNDL dependencies need not all be embedded in the paired EMBB | `Monstey_SowBundleWriter.py`, readers/writers; armory integration `README.md`, assembly notes | Native external dependencies were inspected. Closure must be checked against the actual load route |
| Patch-list registration uses a native hash and sorted binary entries | `Monstey_SowPathHash.py`, `Monstey_PathHash`; `Monstey_SowPatchList.py`, `Monstey_BuildPatchList` | Hashes are compared with supplied native reference entries. Collision coverage is limited to the catalog tested |
| A delta preserves undeclared inherited resources | `Monstey_CrimsonRetinueBuild.py`, `Monstey_ValidateContents` | Recomputes the full resource set and checks parent-source hashes and unchanged inherited payloads |
| Split storage preserves the logical package | `Monstey_SplitArchives.py`, `Monstey_ValidateSplit`; `Monstey_TestSplitOnly.py`; associated `validation.json` | 18 recorded checks include real tiny archives, chunk boundaries, corruption, and reuse. The miniature GADB fixture explicitly substitutes its database proof |
| Installer failure paths can restore prior files and state | `Monstey_InstallSplit.py`, `main`; `Monstey_TestInstallSplitBackup.py`; associated `validation.json` | 19 recorded fixture checks include partial copy, publish, state commit, and backup failures. Tests used a fake game directory |
| Loose overlays can hide a packaged update or be retired incorrectly for the intended workflow | `Monstey_LiveMount.py`, `Monstey_Reconcile`; `COORDINATION.md`, later installation notes | Source confirms hash/mtime behavior; integration notes record the effective UI version being preserved after reconciliation |
| The large v154 equipment batch was installed and extensively validated offline | `install-result-v154.json`; armory integration `README.md`; `post-install-validation-v154.json` | Installation and preservation checks are recorded. The install result explicitly has `runtime_verified=false`; do not claim all items were verified in game |
| A targeted bow fix needed native behavior-state wiring in addition to native clips | `COORDINATION.md`, 21 October 2026 bow correction entries; `graph-result.json`, `state_map` | The earlier clip-only correction was insufficient. The later native-state change was tested live and recorded as successful; corresponding build work was in progress at the reviewed snapshot |

The inspected bulk integration reports preservation of 272 previously added weapons and installation of 1,208 new weapons within a larger equipment batch. Those counts describe the recorded batch; they are not a claim that all variants passed rendering, combat, drop, and persistence tests. The public examples should be treated as small authoring examples rather than a distribution of that catalog.

## Record evidence for a reproducible release

A release record should include:

- The target game build, tool versions, source-resource provenance, and hashes of the source database and effective locale tables.
- The authoring plan, final record-name map, typed reference map, and declared edits to existing records.
- The complete virtual file manifest, per-resource hashes, dependency closure results, and known path-hash collision checks.
- The written archives, archive hashes, native readback results, and mount configuration change.
- The install receipt and the actual effective overlay hashes.
- A test matrix separating offline validation, installed-file checks, fresh native acquisition, equip behavior, and save/reload results.
- Remaining gaps, excluded item families, and the package and save backups used for rollback.

See [Packaging and testing](PACKAGING_AND_TESTING.md) for the checks behind those records. Preserve a failing case and its exact inputs when a later revision regresses; a newer version number by itself does not demonstrate an improvement.
