# Contributing

For a format correction, include the affected offset or field, a synthetic regression test, and the checks performed against your own game files.

Do not commit extracted resources, databases, archives, executable files, credentials or local paths. Keep working outputs in `scratch/`.

Run:

```powershell
python -m unittest discover -s tests -v
```

Separate verified byte layout from inferred meaning. Preserve unknown fields and state unsupported format variants explicitly.
