# Sync procedure (run by the scheduled Claude task)
Artifact: https://claude.ai/artifact/3KfjaqFTgYDTcJNmmXdoAz (Desk Terminal)

1. Handle ADD requests: ArtifactData `list` collection `requests`. For each doc, add its `symbols` (Yahoo symbols, uppercase) to `watchlist.json` if missing. If any were added: commit + push, then delete those request docs (pin `if_version`).
2. If the latest workflow run is older than ~50 min OR symbols were just added: `gh workflow run fetch.yml -R davidprzzzzz/terminal-data --ref main`, wait for it (`gh run watch`), then `git pull`.
3. Versions: ArtifactData `list` on `series` (limit 100, `out_dir` /tmp/v) and on `market` (out_dir) -> write `versions.json` mapping "series/<id>": version, "market/quotes": v, "market/news": v.
4. `python tools/build_docs.py . /tmp/sync-out versions.json` -> `/tmp/sync-out/plan.json` = list of batches; send each batch with ArtifactData `batch` (entries already carry op/if_version/file_path).
5. If a batch fails on a version conflict, re-list that collection and rebuild once. Report: number of tickers, quotes `updated` timestamp, any `failed` tickers.
