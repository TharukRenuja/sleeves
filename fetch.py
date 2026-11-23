#!/usr/bin/env python3
"""Fetch top albums from Apple's public charts (no auth) and download hi-res covers.

Writes ./covers/<id>.jpg and ./covers.json. Exits non-zero on failure so CI keeps
yesterday's deployment.
"""
import argparse, json, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

FEED = "https://rss.applemarketingtools.com/api/v2/{cc}/music/{chart}/{n}/{kind}.json"
UA = {"User-Agent": "sleeves/1.0"}


def get(url, tries=2, binary=False, timeout=10):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                data = r.read()
            return data if binary else json.loads(data)
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(1)


def hires(url, size):
    # artworkUrl100 ends in .../100x100bb.jpg -> the CDN resizes on request
    return re.sub(r"/\d+x\d+(bb)?\.(jpg|png|webp)$", f"/{size}x{size}bb.jpg", url)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default="us,gb,jp,br,in,de,fr,mx,kr,au,ca,es")
    ap.add_argument("--chart", default="most-played", help="most-played | top")
    ap.add_argument("--kind", default="albums", help="albums | songs")
    ap.add_argument("--per-country", type=int, default=50)
    ap.add_argument("--max", type=int, default=160)
    ap.add_argument("--size", type=int, default=1000)
    ap.add_argument("--out", default="covers")
    ap.add_argument("--json", default="covers.json")
    a = ap.parse_args()

    def feed(cc):
        cc = cc.strip().lower()
        try:
            res = get(FEED.format(cc=cc, chart=a.chart, n=a.per_country, kind=a.kind))["feed"]["results"]
            print(f"{cc}: {len(res)} items")
            return [(cc, i + 1, x) for i, x in enumerate(res)]
        except Exception as e:
            print(f"{cc}: skipped ({e})", file=sys.stderr)
            return []

    with ThreadPoolExecutor(8) as ex:
        lists = [l for l in ex.map(feed, a.countries.split(",")) if l]

    # round-robin by rank so every country contributes its top items first; dedupe by id
    items, seen = [], set()
    for rank in range(a.per_country):
        for lst in lists:
            if rank < len(lst):
                cc, r, x = lst[rank]
                if x["id"] in seen or not x.get("artworkUrl100"):
                    continue
                seen.add(x["id"])
                items.append({
                    "id": x["id"], "title": x["name"], "artist": x["artistName"],
                    "country": cc, "rank": r, "link": x.get("url"),
                    "art": hires(x["artworkUrl100"], a.size),
                })
    items = items[: a.max]
    if len(items) < 12:
        sys.exit(f"only {len(items)} covers found, aborting")

    os.makedirs(a.out, exist_ok=True)
    for f in os.listdir(a.out):
        os.remove(os.path.join(a.out, f))

    def dl(it):
        path = os.path.join(a.out, f"{it['id']}.jpg")
        try:
            with open(path, "wb") as fh:
                fh.write(get(it["art"], binary=True))
            return it
        except Exception as e:
            print(f"cover {it['id']} failed: {e}", file=sys.stderr)
            return None

    with ThreadPoolExecutor(8) as ex:
        ok = [x for x in ex.map(dl, items) if x]
    if len(ok) < 12:
        sys.exit(f"only {len(ok)} covers downloaded, aborting")

    with open(a.json, "w") as fh:
        json.dump({"updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "source": "Apple Music charts", "items": ok}, fh, ensure_ascii=False, indent=1)
    print(f"{len(ok)} covers -> {a.out}/, {a.json}")


if __name__ == "__main__":
    main()
