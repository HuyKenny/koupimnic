"""Offers -> products for koupimnic.cz, and the state that keeps them stable between runs.

1. Every offer gets a category (taxonomy.classify) or is dropped (accessories, kids, not our range, under the price floor).
2. Size variants of one model in one shop (same itemGroupId, or the same title at a marketplace) become ONE product with a
   list of sizes; the same item in several shops is joined by EAN.
3. select() keeps at most taxonomy.CAP[cat] products per category and KNC_MAX_PRODUCTS overall (Kenny 14. 11. 2026: max
   300 000), dream brands and good photos first, round-robin over shops so one big shop cannot fill a category.
Slugs, content hashes and a snapshot of products that went away live in data/state/state.json.gz (CI: encrypted release asset).
"""
import gzip
import json
import math
import os
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import taxonomy as X

APP = Path(__file__).resolve().parent.parent
RAW = APP / "data/raw"
WEEKLY = APP / "data/weekly"   # offers frozen by the last weekly (full) run: the product range changes only then
STATE = APP / "data/state"
TODAY = date.today()
DAY = TODAY.toordinal()
GONE_DAYS = 30
MAX_PRODUCTS = int(os.environ.get("KNC_MAX_PRODUCTS") or 0) or 300000   # 0 / unset = the default cap (Kenny: max 300 000)
STATS = {}


def norm_ean(e):
    d = re.sub(r"\D", "", str(e or ""))
    if len(d) in (8, 12, 13, 14) and set(d) != {"0"}:
        d = d.lstrip("0").zfill(13) if len(d) > 8 else d
        return d if len(d) <= 13 else ""
    return ""


def https(u):
    return "https://" + u[7:] if (u or "").startswith("http://") else (u or "")


def new_shops():
    if not WEEKLY.exists():
        return []
    return sorted(p.name.split(".")[0] for p in RAW.glob("*.jsonl.gz") if not (WEEKLY / p.name).exists())


def full_mode():
    """Full run = the range comes from the fresh feeds. Otherwise the range is the weekly snapshot and today's feeds only
    refresh price and link (pages do not appear and vanish every night)."""
    return os.environ.get("KNC_FULL") == "1" or not WEEKLY.exists() or bool(new_shops())


def todays_prices(path):
    over = {}
    if path.exists():
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                if float(r.get("p") or 0) > 0 and r.get("go"):
                    over[r["id"]] = (r["p"], r.get("was"), r["go"], r.get("url"))
    return over


def read_shop(s, full):
    p = (RAW if full else WEEKLY) / f"{s['id']}.jsonl.gz"
    if not p.exists():
        return
    over = {} if full else todays_prices(RAW / f"{s['id']}.jsonl.gz")
    with gzip.open(p, "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if over:
                o = over.get(r["id"])
                if not o:
                    continue                      # sold out today: gone from the range until it is back
                r["p"], r["was"], r["go"] = o[0], o[1], o[2]
                r["url"] = o[3] or r.get("url")
            yield r


def load_offers(shops):
    out, dropped, per_cat = [], Counter(), Counter()
    full = full_mode()
    for s in shops:
        n0 = len(out)
        for r in read_shop(s, full):
            cat = X.classify(r, s)
            if not cat:
                dropped[s["id"] + ":range"] += 1
                continue
            price = float(r.get("p") or 0)
            if price <= 0 or not r.get("go") or not r.get("img"):
                dropped[s["id"] + ":incomplete"] += 1
                continue
            if price < X.PRICE_FLOOR.get(cat, 0):
                dropped[s["id"] + ":cheap"] += 1
                continue
            desc = X.clean(re.sub(r"<[^>]+>", " ", r.get("d") or ""))
            out.append({
                "shop": s["id"], "oid": str(r["id"]), "g": str(r.get("g") or ""), "title": X.clean(r["t"]), "desc": desc[:1200],
                "brand": X.brand_of(r) or s.get("brand", ""), "ean": norm_ean(r.get("ean")), "img": https(r.get("img")),
                "imgs": [https(u) for u in r.get("imgs") or [] if u][:4], "price": round(price), "was": round(float(r.get("was") or 0)),
                "url": r.get("url") or "", "go": r["go"], "cat": cat, "size": X.clean_size(r.get("size") or ""), "col": X.clean(r.get("col") or "")[:30],
                "market": bool(s.get("marketplace")),
            })
            per_cat[cat] += 1
        STATS.setdefault("offers_per_shop", {})[s["id"]] = len(out) - n0
    STATS["offers_per_cat"] = dict(per_cat.most_common())
    return out, dropped


class DSU:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


RX_SIZE_TAIL = re.compile(r"[\s,/-]+(vel(ikost|\.)?\s*)?(XXXS|XXS|XS|S|M|L|XL|XXL|XXXL|[2-5]XL|\d{2}(\.5|,5)?|\d{2}/\d{2}|W\d{2}\s*L\d{2})$", re.I)


def model_title(t):
    """Title without a trailing size ("… tričko, XL") so sizes of one model share a name."""
    prev = None
    while prev != t:
        prev, t = t, RX_SIZE_TAIL.sub("", t).strip(" ,-/")
    return t


def cluster(offers, shop_rank):
    dsu = DSU()
    first = {}
    for i, o in enumerate(offers):
        dsu.find(i)
        keys = []
        if o["g"]:
            keys.append(f"g:{o['shop']}:{o['g']}")                                  # one model, many sizes
        elif o["market"]:
            keys.append(f"t:{o['shop']}:{X.fold(model_title(o['title']))}")         # marketplace: same title = same thing
        if o["ean"]:
            keys.append("e:" + o["ean"])                                             # the same item in another shop
        for k in keys:
            if k in first:
                dsu.union(first[k], i)
            else:
                first[k] = i
    groups = defaultdict(list)
    for i, o in enumerate(offers):
        groups[dsu.find(i)].append(o)

    products = []
    for allo in groups.values():
        cats = Counter(o["cat"] for o in allo)
        best = {}
        for o in sorted(allo, key=lambda o: o["price"]):
            best.setdefault(o["shop"], o)
        offs = sorted(best.values(), key=lambda o: (o["price"], shop_rank.get(o["shop"], 99)))
        rep = sorted(allo, key=lambda o: (shop_rank.get(o["shop"], 99), -len(o["desc"]), o["price"]))[0]
        eans = sorted({o["ean"] for o in allo if o["ean"]})
        g0 = next((o for o in allo if o["g"]), None)
        pid = f"g:{g0['shop']}:{g0['g']}" if g0 else ("e:" + eans[0] if eans else f"o:{rep['shop']}:{rep['oid']}")
        sizes = sorted({o["size"] for o in allo if o["size"]}, key=X.size_key)
        img = next((o["img"] for o in sorted(allo, key=lambda o: o["price"]) if o["img"]), "")
        imgs = []
        for o in allo:
            for u in [o["img"]] + o["imgs"]:
                if u and u != img and u not in imgs:
                    imgs.append(u)
        brands = Counter(o["brand"] for o in allo if o["brand"])
        products.append({
            "id": pid, "name": X.nice_name(model_title(rep["title"])), "brand": brands.most_common(1)[0][0] if brands else "",
            "cat": cats.most_common(1)[0][0], "desc": max((o["desc"] for o in allo), key=len), "img": img, "imgs": imgs[:6],
            "offers": [{"shop": o["shop"], "price": o["price"], "was": o["was"], "go": o["go"], "url": o["url"]} for o in offs],
            "price": offs[0]["price"], "was": offs[0]["was"], "sizes": sizes[:30], "color": rep["col"], "ean": eans[0] if eans else "",
        })
    return products


def discount(p):
    return round(100 * (p["was"] - p["price"]) / p["was"]) if p.get("was") and p["was"] > p["price"] else 0


def quality(p):
    """What makes a product worth its place: sold in several shops, a dream brand, a real photo and description, a real
    discount, and a bit of price (a 30 000 Kč MacBook is more of a dopamine hit than a 300 Kč T-shirt)."""
    return (100 * (len(p["offers"]) - 1) + (40 if X.top_brand(p["brand"]) else 0) + (10 if p["brand"] else 0) + (5 if p["imgs"] else 0)
            + (8 if discount(p) >= 15 else 0) + (5 if len(p["desc"]) >= 120 else 0) + min(15, 3 * math.log10(max(p["price"], 10))))


def select(products):
    """Per-category caps, then the global cap. Deterministic (ties by id): the same feeds give the same pages every night."""
    by_cat = defaultdict(list)
    for p in products:
        by_cat[p["cat"]].append(p)
    keep, capped = [], {}
    for k, ps in by_cat.items():
        cap = X.CAP.get(k, 3000)
        ps.sort(key=lambda p: (-quality(p), p["id"]))
        if len(ps) <= cap:
            keep += ps
            continue
        multi = [p for p in ps if len(p["offers"]) > 1][:cap]
        queues = defaultdict(list)
        for p in ps:
            if len(p["offers"]) == 1:
                queues[p["offers"][0]["shop"]].append(p)
        order = sorted(queues, key=lambda sid: (-quality(queues[sid][0]), sid))
        picked = list(multi)
        while len(picked) < cap and any(queues.values()):
            for sid in order:
                if queues[sid] and len(picked) < cap:
                    picked.append(queues[sid].pop(0))
        keep += picked
        capped[k] = len(ps) - len(picked)
    if len(keep) > MAX_PRODUCTS:
        keep.sort(key=lambda p: (-quality(p), p["id"]))
        capped["_total"] = len(keep) - MAX_PRODUCTS
        keep = keep[:MAX_PRODUCTS]
    STATS["capped"] = capped
    return keep


# ---------------------------------------------------------------- slugs, gone products, state

def product_slug(p):
    s = X.slugify(p["name"])
    b = X.slugify(p["brand"])
    if b and not s.startswith(b) and b not in s:
        s = b + "-" + s
    return s[:80].rsplit("-", 1)[0] if len(s) > 80 else s


def assign_slugs(products, state):
    slugs = state.setdefault("slugs", {})
    used = set(slugs.values())
    new = 0
    for p in products:
        if p["id"] in slugs:
            continue
        base = product_slug(p) or "produkt"
        s, i = base, 2
        while s in used:
            s, i = f"{base}-{i}", i + 1
        slugs[p["id"]] = s
        used.add(s)
        new += 1
    for p in products:
        p["slug"] = slugs[p["id"]]
    return new


def gone_products(products, state):
    """A product that went away keeps a "vyprodáno" page for GONE_DAYS (links and search engines keep working), then 404."""
    gone = state.setdefault("gone", {})
    live = {p["id"] for p in products}
    for pid, snap in state.get("snap", {}).items():
        if pid not in live and pid not in gone:
            gone[pid] = dict(snap, day=DAY)
    for pid in list(gone):
        if pid in live or gone[pid]["day"] < DAY - GONE_DAYS:
            gone.pop(pid)
    state["snap"] = {p["id"]: {"slug": p["slug"], "name": p["name"], "cat": p["cat"], "img": p["img"], "price": p["price"]} for p in products}
    slugs = state.get("slugs", {})
    keep = live | set(gone)
    for pid in [k for k in slugs if k not in keep]:       # slugs of products long gone are released
        slugs.pop(pid)
    return gone


def load_state():
    p = STATE / "state.json.gz"
    if p.exists():
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    STATE.mkdir(parents=True, exist_ok=True)
    with gzip.open(STATE / "state.json.gz", "wt", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, separators=(",", ":"))
