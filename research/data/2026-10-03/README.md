# Private research snapshot — 2026-10-03

This snapshot contains participant information and recorded results, included in
the private `strikerdlm/MATB` repository under the owner's explicit instruction
on 2026-10-03. Participant records have not been anonymized. The archive contains
both research/practice recordings and retained diagnostic runs; inclusion does
not establish that a recording is suitable for scientific analysis.

Inventory: 1,307 files, 5.17 GiB uncompressed, 439.90 MiB compressed in 13 parts.
The primary station database contains 5 participant rows and 35 visit rows;
the second database is retained with the exported station dataset.

The four archive groups preserve repository-relative paths:

- `participant-database`: an online SQLite backup of
  `webui/backend/matb_webui.db`, including participant, visit, study, questionnaire,
  physiology, native-session and evidence records.
- `exports`: the accessible saved export tree, including OpenMATB recordings,
  Polar H10 RR/ECG/ACC artifacts and result exports, simulation results, and
  retained station datasets.
- `native-sessions`: the saved standalone `openmatb/sessions` tree.
- `diagnostic-results`: retained native audio and startup verification artifacts,
  Polar connection artifacts and station job responses.

`manifest.json` lists every archived file, its byte count and SHA-256, archive
part checksums, database table row counts, capture timestamps and exclusions.
All database files use SQLite's online backup API and pass `PRAGMA
integrity_check`. Original files are preserved byte-for-byte except SQLite files,
which are consistent online backups. Each non-database file was checked for
size/mtime changes during its copy; the complete multi-file snapshot is not a
single atomic capture across database and filesystem.

SQLite sidecars and session claim locks are omitted. Application credentials,
dependency/build caches and pytest temporary fixtures are outside the snapshot.
Any unreadable export directories are listed explicitly in the manifest.
Historical absolute paths and runtime state in the database remain historical;
the archive is for recovery and analysis and is not activated automatically.

Each ZIP is split into ordered parts of at most 40 MiB to stay below GitHub's
individual-file limit. Keep every part together with the manifest and script.
Python 3.10+ is sufficient; no additional packages are needed.

Verify all archive parts, decompress all members, and check their hashes:

```powershell
python research/data/2026-10-03/restore.py --verify-only
```

Restore to a **new** destination directory:

```powershell
python research/data/2026-10-03/restore.py --destination E:/MATB-restored-20261003
```

The script refuses an existing destination. It does not overwrite or start a
live station. Restored files retain their repository-relative directory layout.

Delivery validation from an isolated checkout of current `origin/main` plus the
pending changes:

- OpenMATB native suite: 958 passed.
- Scenario builder, manifests and SAGAT emission: 109 passed.
- Study preparation and physiology runtime: 25 passed.
- Focused frontend tests: 21 passed across 4 files.
- TypeScript and focused ESLint: passed.
- Six added native scenario files match their canonical scenario counterparts.
- Full restoration: all 1,307 members and all 13 parts verified against SHA-256.

These are software checks. Physical speaker intelligibility, H10 radio reliability
and participant identity matching were not revalidated by this delivery.
