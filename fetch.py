"""Fetch prices, quotes and news for the watchlist with yfinance -> data/*.json"""
import json, math, os, sys, time
from datetime import datetime, timezone
import yfinance as yf
import urllib.request, urllib.parse, xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}

def rss(url, sym, n=10):
    out = []
    try:
        req = urllib.request.Request(url, headers=UA)
        root = ET.fromstring(urllib.request.urlopen(req, timeout=15).read())
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            if not title:
                continue
            src = it.find("source")
            pub = src.text if src is not None and src.text else None
            if pub and title.endswith(" - " + pub):
                title = title[: -len(pub) - 3]
            ts = it.findtext("pubDate")
            try:
                ts = parsedate_to_datetime(ts).astimezone(timezone.utc).isoformat()
            except Exception:
                pass
            out.append({"id": (it.findtext("guid") or title)[:120], "title": title, "summary": "",
                        "publisher": pub or ("Yahoo Finance" if "yahoo" in url else None), "url": it.findtext("link"),
                        "time": ts, "tickers": [sym]})
            if len(out) >= n:
                break
    except Exception as e:
        print("rss fail", sym, url[:60], e, file=sys.stderr)
    return out


OUT = "data"
DEBUG = set()
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
        raw = []
        try:
            raw = t.get_news(count=12) or []
        except Exception as e:
            print("get_news err", sym, e, file=sys.stderr)
            if sym in DEBUG:
                open(f"{OUT}/debug_err_{sym}.txt", "w").write(repr(e))
        if not raw:
            raw = t.news or []
        if sym in DEBUG:
            print("NEWSDEBUG", sym, len(raw), json.dumps(raw[:1], default=str)[:600])
            with open(f"{OUT}/debug_{sym}.txt", "w") as fh:
                fh.write(f"{yf.__version__} {len(raw)}\n" + json.dumps(raw[:2], default=str)[:3000])
        for n in raw[:12]:
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
    if not out:
        out = rss("https://feeds.finance.yahoo.com/rss/2.0/headline?" + urllib.parse.urlencode({"s": sym, "region": "US", "lang": "en-US"}), sym)
    if not out and NAMES.get(sym):
        q = NAMES[sym] + (" bourse" if sym.endswith((".PA",)) else " stock")
        hl = "fr" if sym.endswith(".PA") else "en-US"
        gl = "FR" if sym.endswith(".PA") else "US"
        out = rss("https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q + " when:7d", "hl": hl, "gl": gl, "ceid": f"{gl}:{hl.split('-')[0]}"}), sym, 8)
    if sym in DEBUG:
        open(f"{OUT}/debug_{sym}.txt", "a").write(f"\nfinal {len(out)}")
    return out

NAMES = {}

def main():
    wl = json.load(open("watchlist.json"))["tickers"]
    extra = sys.argv[1:]
    syms = list(dict.fromkeys(wl + extra))
    hist = yf.download(syms, period="5y", interval="1d", group_by="ticker", auto_adjust=True, progress=False, threads=True)
    intra = yf.download(syms, period="5d", interval="30m", group_by="ticker", auto_adjust=True, progress=False, threads=True)
    meta, news, failed = {}, {}, []
    for s in syms:
        try:
            df = hist[s].dropna(subset=["Close"]) if s in hist.columns.get_level_values(0) else None
            if df is None or df.empty:
                df = yf.download(s, period="5y", interval="1d", auto_adjust=True, progress=False, multi_level_index=False).dropna(subset=["Close"])
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
            m = {"symbol": s, "id": safe_id(s), "name": (info.get("shortName") or info.get("longName") or s).strip(),
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
            NAMES[s] = m["name"] if m["name"] != s else None
            for n in news_items(t, s):
                key = " ".join((n["title"] or "").lower().split())[:90]
                if key in news:
                    if s not in news[key]["tickers"]:
                        news[key]["tickers"].append(s)
                else:
                    news[key] = n
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
