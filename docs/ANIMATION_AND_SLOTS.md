# Animation, attachment and equipment slots

The source model's weapon label does not create a gameplay category in Shadow of War. Choose a native equipment route, fit the asset to it, and verify the animation, attachment and event contracts that route uses. A two-handed source sword can use the Sword inventory slot with a separately selected two-handed stance; its filename selects neither.

The simplest first import is a rigid weapon using an existing slot, rig and animation set. Preserve that behavior while validating the new appearance. Custom motion is a separate integration task.

## The contracts that must agree

| Contract | What it controls | What it does not prove |
| --- | --- | --- |
| Inventory/equipment slot | Storage, equip/unequip and the native item route. | A source family name does not establish a new visible UI category. |
| Player attachment | Placement relative to the character. | A correct rest pose does not prove a correct moving grip. |
| Weapon skeleton and weights | Movement within the weapon, such as a string or chain. | Player arms and the combat state machine are separate. |
| Player animation library | Body pose, local motion and supported root motion. | A decodable clip does not prove valid transitions or events. |
| Behavior graph and predicates | When the engine enters, remains in and exits a state. | Creating a state does not update every predicate testing the old state. |
| Attack, projectile and weapon events | Gameplay timing, firing and synchronized weapon animation. | A melee hit marker is not a projectile firing route. |

Keep the selected item, model, slot, stance, clip library and event route together in the integration record. This exposes mismatches before they become runtime symptoms.

## Native rig and index preservation

Native geometry uses Y-up centimetres and native quaternions use XYZW order. Blender may display WXYZ quaternions and a different up axis. Use the converter's defined transforms rather than copying displayed values between representations.

Preserve hierarchy, rest transforms, inverse binds and attachments. SKEL record order and the Havok index order used by mesh palettes are not interchangeable. The mesh publisher preserves HK metadata on imported bones; explicit maps must resolve to those actual target indices.

Retargeting requires more than renaming bones. Account for source and target rest poses, local versus global transforms, root motion and animation fallback behavior. Validate mapped channels and unanimated bones retaining bind fallback.

If a character skeleton already registers animation libraries from other mods, preserve them when adding yours. Deliver one composed final skeleton rather than competing replacements of the same resource. Adding a library path should not rewrite unrelated bone records.

## Choose the weapon route

| Source appearance | Route established by the inspected work | Additional work |
| --- | --- | --- |
| Rigid sword, axe, mace, polearm or similar melee weapon | Native Sword item and compatible rigid target; stance selection is separate. | Fit grip and blade/shaft direction; validate the selected melee family's contacts and transitions. |
| Dagger | Native Dagger item, dagger target and native synchronized stealth/execution behavior. | Fit the actual dagger frame. A short sword conversion is not equivalent. |
| Bow | Native Bow item, deforming bow rig and native ranged/projectile path. | Fit limbs, string and nock; check player motion and draw/hold/fire predicates. |
| Crossbow | Native ranged route with a compatible crossbow rig and firing event. The inspected import uses the Bow inventory route. | Qualify grip, string/bolt motion, player pose and graph behavior. This does not create a Crossbow UI slot. |
| Flail | Native Sword item plus an articulated weapon rig and synchronized body/weapon clips. | Preserve or author chain weights, supply paired motion and validate interruption/reset behavior. |
| Staff or wand | A qualified melee route can display and use the model as a melee weapon. | Casting, targeting, projectiles and spell effects require separate implemented mechanics. |
| Shield, focus, book or totem | Requires a qualified offhand item, attachment, storage and UI route. | An engine enum or NPC equipment path alone does not provide a working player category. |

These are compatibility routes, not promises that every model works without fitting. A source named `Crossbow2H`, for example, does not prove that a two-handed player animation has been qualified.

## Rigid swords and daggers

A rigid sword can bind to its native handle bone and reuse the native weapon skeleton. The established sword template has `root`, `sword_handle` and `sword_tip`. Preserve their transforms and choose the handle index from the actual target.

The inspected dagger target has `root1`, `dagger_handle` and `dagger_tip`. Its grip and orientation are derived from that target. Reusing sword transform constants can misplace a dagger even though both targets have three bones.

Keep a dagger in **Dagger** when the intended behavior is native stealth and synchronized executions. A source dagger motion set is not needed to import the appearance. Moving the asset to Sword changes its gameplay route and does not preserve those interactions.

For other rigid melee weapons, confirm the stance gate selects only intended equipped items. An existing gate on a shared list may also select items newly added to that list. Review existing and new membership together, including the fallback for other weapons.

## Bows: body pose and weapon deformation

A functional bow has two moving systems: the player's body and the bow itself. The inspected native rig includes `bow_handle`, `bow_draw`, lower limb bones and upper limb bones. Custom geometry must follow their correct transforms.

Check the weapon model:

1. Fit the grip to the native handle frame.
2. Identify the actual string geometry, including strings sharing vertices with the bow body.
3. Provide enough geometry near the nock to deform during draw.
4. Give string and limbs appropriate native weights.
5. Inspect relaxed, partial-draw and full-draw poses for finite data, shape and attachment continuity.

Do not bind the entire bow rigidly to its handle when string and limb motion is required. Adding a draw-bone weight also cannot create a central bend in a string with no central geometry.

The player route must preserve ranged timing, camera/aim behavior, projectile data and ammo behavior. Ground, mounted, rail, aerial, slide and no-ammo contexts are distinct. A qualified ground draw does not qualify the others.

### A documented bow regression

An earlier custom route demonstrates two independent failure modes:

- Retargeted draw/fire clips changed right-arm solutions abruptly. Dense sampling found roughly 104 to 117 degrees of movement over 10 ms. Replacing the nine directional draw/hold/fire motions with native ranged motion and native markers addressed that discontinuity.
- The bow still alternated between drawing and lowering. Its private cloned behavior nodes were absent from `Predicate.ActiveNode` checks. Native transition predicates therefore read the drawing weapon as not drawing and forced it out of the state. Reusing native draw, hold and fire behavior nodes corrected this state identity problem and was confirmed in an in-game test.

The animation-only change was insufficient. The corrected reference combines compatible native motion with the native behavior-state route. The earlier private bow clone route and frame-by-frame hand-to-nock retarget are not a proven recipe to reproduce.

If you author new states, inspect every transition and active-state predicate depending on the original states. Include new identities coherently and test sustained input and interruption. A node can exist, reference a valid clip and pass database validation while remaining invisible to state predicates.

## Crossbows

The inspected native crossbow donor has six bones: `root`, `base`, `Bow_R`, `Bow_L`, `String` and `Bolt`. Its stock and moving parts cannot all use one rigid sword binding. The geometry work distinguishes grip, limbs, string and nock, then fits motion to the native firing stroke.

Review the source pose first. A relaxed string may need explicit preparation for a loaded pose; record that conversion assumption. Do not pull a nearby latch or stock component with the string merely because it lies near the nock.

The native weapon firing clip in the inspected route is `BRXbow_Fire`, started through the ranged weapon event path. Player and weapon clips must be synchronized with the attack producing the projectile. A sword attack event cannot replace that connection.

The inspected player motion used a right-handed one-hand crossbow source. A shared left-hand contact pose for the two-handed source was not qualified. Clips passed a continuity review, but a later graph inspection found the same missing active-state references as the bow clones. That graph risk remains separate from clip quality and must not be described as resolved by the bow's in-game test.

Test draw/reload, sustained hold, firing, aim directions, interruption and return to idle. Confirm projectile origin and direction independently from visual bolt and string motion.

## Flails

A flail needs relative motion between handle, chain and head. A static imported mesh supplies its silhouette, not articulation or physics.

The inspected implementation preserves authored chain weights, extends the weapon rig with private chain bones and retains the native sword root/handle/tip attachment contract. Source palette entries map explicitly to target HK indices. Account for source rest-skin transforms before claiming that extracted positions already represent the final bind surface.

Body attacks select matching weapon clips through `SourceAnimationWeapon`. The reviewed route contains 19 paired body/weapon clips and returns the weapon to a dedicated Ready action while preserving existing stop actions. These are synchronized authored trajectories, not the source game's flail physics.

Inspect each complete pair: start, contact, follow-through and stop. Check transitions to Ready, interrupted attacks and equip/unequip. A correct chain pose in a still frame does not validate the sequence.

## Animation tools and their boundaries

The public [Shadow of War ANIX format repository](https://github.com/LordMonstey/sow-anix-format) documents ANIX v44 and provides a reference reader, rotation/translation codecs and synthetic tests. It explains libraries, channels, descriptors, segment alignment, time tables and event data. It is not a source-game extractor, complete retargeter, combat-graph author or installer.

Libraries are selected through skeleton registrations and clip identities. Channel mappings, bind fallback, durations, root motion, event markers and footer/directory metadata must remain coherent. Writing a library successfully does not make an attack reference it.

Decoding a native clip for pose inspection does not reproduce runtime IK, motion controllers, cloth, gameplay events or state-machine behavior. A Blender Action is a pose preview, not an in-game combat test. Mesh Publisher v0.1.1 does not include a native animation preview panel or an arbitrary animation export path.

The private retargeting and graph-building tools behind the inspected examples are not included here. Their existence does not imply a public command converting any FBX animation into a working attack.

## Validate an animation change

| Layer | Useful checks |
| --- | --- |
| Serialization | Re-read the final library; verify extents, timing, channels, identities, events and finite reconstructed values. |
| Target rig | Verify hierarchy, bind fallback, exact mapping and old skeleton registrations. |
| Temporal behavior | Sample full clips densely enough to expose discontinuities; check joint excursions, root motion and transition endpoints. |
| Item selection | Confirm the equipped-item predicate selects the intended family and preserves the complement for other items. |
| Behavior state | Trace entry, hold and exit predicates, active-state identities and interrupted input. |
| Weapon synchronization | Check body/weapon pairs, firing/contact events and return-to-ready behavior. |
| In game | Test equip/unequip, repeated actions, hold/release, interruption, relevant movement contexts, save/load and unrelated native items. |

State results at their actual level: structurally valid, pose-reviewed, graph-reviewed or tested in game. Clean decoding and unchanged native records do not establish runtime aiming, grip or transitions.

See [Asset pipeline](ASSET_PIPELINE.md) for geometry and resources, [Adding items](../docs/ADDING_ITEMS.md) for the inventory identity and slot, and [Loot pools](LOOT_POOLS.md) for drop eligibility.
