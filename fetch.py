"""Fetch prices, quotes and news for the watchlist with yfinance -> data/*.json"""
import json, math, os, sys, time
from datetime import datetime, timezone
import yfinance as yf

OUT = "data"
os.makedirs(f"{OUT}/prices", exist_ok=True)

def safe_id(sym):  # filename / db doc id
    return sym.replace("^", "~").replace("=", "+")

def num(x, nd=6):
    try:
        x = float(x)
        return None if math.isnan(x) or math.isinf(x) else round(x, nd)
    except Exception:
        return None

def news_items(t, sym):
    out = []
    try:
        for n in (t.news or [])[:12]:
            c = n.get("content", n)
            title = c.get("title")
            if not title:
                continue
            link = (c.get("canonicalUrl") or {}).get("url") or (c.get("clickThroughUrl") or {}).get("url") or c.get("link")
            pub = (c.get("provider") or {}).get("displayName") or c.get("publisher")
            ts = c.get("pubDate") or c.get("displayTime")
            if not ts and c.get("providerPublishTime"):
                ts = datetime.fromtimestamp(c["providerPublishTime"], timezone.utc).isoformat()
            out.append({"id": n.get("id") or c.get("uuid") or title[:40], "title": title, "summary": (c.get("summary") or "")[:400],
                        "publisher": pub, "url": link, "time": ts, "tickers": [sym]})
    except Exception as e:
        print("news fail", sym, e, file=sys.stderr)
    return out

def main():
    wl = json.load(open("watchlist.json"))["tickers"]
    extra = sys.argv[1:]
    syms = list(dict.fromkeys(wl + extra))
    hist = yf.download(syms, period="5y", interval="1d", group_by="ticker", auto_adjust=True, progress=False, threads=True)
    intra = yf.download(syms, period="5d", interval="30m", group_by="ticker", auto_adjust=True, progress=False, threads=True)
    meta, news, failed = {}, {}, []
    for s in syms:
        try:
            df = hist[s].dropna(subset=["Close"])
            if df.empty:
                failed.append(s); continue
            rec = {"symbol": s, "d": [d.strftime("%Y-%m-%d") for d in df.index],
                   "o": [num(v, 4) for v in df["Open"]], "h": [num(v, 4) for v in df["High"]],
                   "l": [num(v, 4) for v in df["Low"]], "c": [num(v, 4) for v in df["Close"]],
                   "v": [int(v) if num(v) is not None else 0 for v in df["Volume"]]}
            try:
                di = intra[s].dropna(subset=["Close"])
                rec["it"] = [d.strftime("%Y-%m-%dT%H:%M") for d in di.index.tz_convert("UTC")]
                rec["ic"] = [num(v, 4) for v in di["Close"]]
            except Exception:
                rec["it"], rec["ic"] = [], []
            t = yf.Ticker(s)
            info = {}
            try:
                info = t.info or {}
            except Exception:
                pass
            last = rec["c"][-1]; prev = rec["c"][-2] if len(rec["c"]) > 1 else last
            if rec["ic"]:
                last = rec["ic"][-1]
            m = {"symbol": s, "id": safe_id(s), "name": info.get("shortName") or info.get("longName") or s,
                 "type": info.get("quoteType"), "currency": info.get("currency"), "exchange": info.get("exchange"),
                 "sector": info.get("sector"), "industry": info.get("industry"),
                 "mktCap": num(info.get("marketCap"), 0), "pe": num(info.get("trailingPE"), 2), "fpe": num(info.get("forwardPE"), 2),
                 "divYield": num(info.get("dividendYield"), 4), "beta": num(info.get("beta"), 3),
                 "hi52": num(info.get("fiftyTwoWeekHigh"), 4), "lo52": num(info.get("fiftyTwoWeekLow"), 4),
                 "last": last, "prevClose": prev, "chg": num(last - prev, 4), "chgPct": num((last / prev - 1) * 100, 3) if prev else None,
                 "asOf": (rec["it"][-1] if rec["it"] else rec["d"][-1])}
            rec["meta"] = m
            json.dump(rec, open(f"{OUT}/prices/{safe_id(s)}.json", "w"), separators=(",", ":"))
            meta[s] = m
            for n in news_items(t, s):
                if n["id"] in news:
                    news[n["id"]]["tickers"].append(s)
                else:
                    news[n["id"]] = n
            time.sleep(0.2)
        except Exception as e:
            print("fail", s, e, file=sys.stderr); failed.append(s)
    items = sorted(news.values(), key=lambda n: n.get("time") or "", reverse=True)[:200]
    json.dump({"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "quotes": meta, "failed": failed},
              open(f"{OUT}/quotes.json", "w"), separators=(",", ":"))
    json.dump({"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "items": items},
              open(f"{OUT}/news.json", "w"), separators=(",", ":"))
    print(f"ok {len(meta)} tickers, {len(items)} news, failed={failed}")

if __name__ == "__main__":
    main()
