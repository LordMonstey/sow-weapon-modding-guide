# Validation

## Reproduce

```powershell
python -m unittest discover -s tests -v
python tools/gadb_read.py YOUR_GAME_GAMEDB validate --all-fields
```

Tests construct their fixtures from Python code. The GADB specification's 165-byte hex example is compared byte-for-byte with its fixture.

## Real-file checks

The readers were checked on local PC game files on 21 October 2026. Only counts and digests were retained; no native data is distributed.

| Check | Result |
| --- | --- |
| Shipped GADB | 2,742 categories; 694,632 records; 11,413,092 decoded fields |
| Independent parser comparison | All category headers, record metadata and value words matched |
| Shipped typed references | 5,203,999 reference words checked |
| Shipped named lookup | 278,865 binary lookups checked |
| Extended GADB | 12,556,612 fields and 5,856,156 reference words checked |
| Archive indexes | 77 archives; 488,763 entries |
| Binary patch lists | 38 lists; 73,049 path hashes matched |
| English and French SKDB | 68,547 rows each; offsets, UTF-16 and ordering checked |
| Archive decompression | Native database and both locale hashes matched trusted local reads |

Using the public readers, archive decoding in memory plus sword discovery took **7.14 seconds** on the test machine: 26 model-chain nodes and 23 reachable loot tables. This is a measured run, not a hardware-independent timing guarantee.

The native database fingerprint was `404ba14571bf0856c28c4d45580fea5fe1a11963fc451430ad97bf257ba63ee7` (56,759,100 bytes). It is evidence of the tested input, not a required input hash.

These checks qualify reading and format interpretation. They do not claim that an arbitrary edited item will load or drop correctly in game.
