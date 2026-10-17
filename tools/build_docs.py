"""Turn data/ (written by fetch.py) into artifact-db documents + batch plan.
usage: python tools/build_docs.py <repo_dir> <out_dir> [versions.json]
versions.json = {"series/AAPL": 3, "market/quotes": 5, ...} (current db versions; needed to overwrite existing docs)
out_dir/docs/<collection>__<doc_id>.json and out_dir/plan.json (list of batches)."""
import json, os, sys, glob
repo, out = sys.argv[1], sys.argv[2]
os.makedirs(f"{out}/docs", exist_ok=True)
vers = json.load(open(sys.argv[3])) if len(sys.argv) > 3 else {}
docs = []
quotes = json.load(open(f"{repo}/data/quotes.json"))
for f in sorted(glob.glob(f"{repo}/data/prices/*.json")):
    r = json.load(open(f)); sid = os.path.basename(f)[:-5]
    k = 260  # OHLC only for the last ~year, closes/volume for 5y
    doc = {"symbol": r["symbol"], "d": r["d"], "c": r["c"], "v": r["v"],
           "o": r["o"][-k:], "h": r["h"][-k:], "l": r["l"][-k:], "it": r.get("it", []), "ic": r.get("ic", [])}
    q = quotes["quotes"].get(r["symbol"])
    if q and r["c"] and r["c"][0]:
        q["p5y"] = round((r["c"][-1] / r["c"][0] - 1) * 100, 2)
    docs.append(("series", sid, doc))
docs.append(("market", "quotes", quotes))
news = json.load(open(f"{repo}/data/news.json"))
for n in news["items"]:
    n["summary"] = (n.get("summary") or "")[:240]
docs.append(("market", "news", news))
plan, cur, size = [], [], 0
for col, did, d in docs:
    p = f"{out}/docs/{col}__{did}.json"
    s = json.dumps(d, separators=(",", ":")); open(p, "w").write(s)
    if len(s) > 250_000: print("WARN too big", did, len(s))
    if cur and (size + len(s) > 900_000 or len(cur) >= 45):
        plan.append(cur); cur, size = [], 0
    w = {"op": "set", "collection": col, "doc_id": did, "file_path": p}
    if f"{col}/{did}" in vers: w["if_version"] = vers[f"{col}/{did}"]
    cur.append(w); size += len(s)
if cur: plan.append(cur)
json.dump(plan, open(f"{out}/plan.json", "w"), indent=1)
print(f"{len(docs)} docs in {len(plan)} batches; quotes updated {quotes.get('updated')}")
