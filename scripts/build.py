#!/usr/bin/env python3
"""Build the static koupimnic.cz site into dist/ from data/raw/*.jsonl.gz.

    KNC_ENV=production python3 scripts/build.py      # indexable build (default: staging = noindex everywhere)
    KNC_MAX_PRODUCTS=20000 python3 scripts/build.py  # fewer products (staging on workers.dev must fit one Worker)

Plain files only: Workers static assets serve them for free. scripts/deploy.py moves /produkt/<x>… into shard Workers
when there are more files than one Worker version may hold. The cart, checkout and the "delivery" run in the browser
(static/assets/app.js, localStorage): nothing is sent anywhere, nothing is paid.
"""
import base64
import hashlib
import json
import os
import re
import shutil
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import catalog as C  # noqa: E402
import golinks as GL  # noqa: E402
import render as R  # noqa: E402
import taxonomy as X  # noqa: E402

APP = Path(__file__).resolve().parent.parent
DIST = APP / "dist"
BASE = os.environ.get("KNC_BASE", "https://koupimnic.cz")
ENV = os.environ.get("KNC_ENV", "staging")
GA4 = os.environ.get("GA4_ID", "")
INDEXNOW_KEY = os.environ.get("INDEXNOW_KEY", "")
MAX_PAGES = 50
JSON_ITEMS = 2400
MIN_CAT = 6
MIN_SUB = 4
MIN_BRAND_SUB = 12
E, kc, plural, SUFFIX = R.E, R.kc, R.plural, R.SUFFIX
TODAY = date.today()
TODAY_CZ = f"{TODAY.day}. {TODAY.month}. {TODAY.year}"
DAY = TODAY.toordinal()
HOME = ("KoupímNic", "/")


def log(m):
    print(m, file=sys.stderr, flush=True)


def nb(n):
    return f"{n:,}".replace(",", " ")


INLINE_SCRIPT = re.compile(rb'<script(?: type="speculationrules")?>(.*?)</script>', re.S)


class Out:
    def __init__(self, state):
        self.hashes = state.setdefault("hash", {})
        self.lastmod = state.setdefault("lastmod", {})
        self.changed, self.files, self.sitemap = [], 0, defaultdict(list)
        self.seen = set()
        self.script_hashes = set()      # CSP: inline scripts are allowed by hash, never 'unsafe-inline'

    def write(self, rel, content):
        p = DIST / rel.lstrip("/")
        p.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode() if isinstance(content, str) else content
        p.write_bytes(data)
        self.files += 1
        if rel.endswith(".html") and b"<script" in data:
            for m in INLINE_SCRIPT.finditer(data):
                self.script_hashes.add(base64.b64encode(hashlib.sha256(m.group(1)).digest()).decode())
        return data

    def page(self, path, html, group=None, index=True):
        if path in self.seen:
            raise SystemExit(f"duplicate page {path}")
        self.seen.add(path)
        data = self.write(path + "index.html", html)
        h = hashlib.md5(re.sub(rb"Aktualizov\xc3\xa1no [^<]+", b"", data)).hexdigest()[:12]
        if self.hashes.get(path) != h:
            self.hashes[path] = h
            self.lastmod[path] = TODAY.isoformat()
            if index:
                self.changed.append(path)
        if group and index:
            self.sitemap[group].append(path)


def pop_key(p):
    """Default order of listings: dream brands with a real photo and discount first, then the rest by desirability."""
    return (-C.quality(p), p["price"], p["id"])


def write_json(out, S, key, items):
    """Listing data for the client-side filters (first JSON_ITEMS by default order): brands, subcategories, shops, rows."""
    items = items[:JSON_ITEMS]
    brands = [b for b, _ in Counter(p["brand"] for p in items if p["brand"]).most_common(120)]
    subs = [k for k, _ in Counter(sub_key(p) for p in items if sub_key(p)).most_common()]
    shops = [k for k, _ in Counter(S.shop(p["offers"][0]["shop"])["name"] for p in items).most_common()]
    bidx, sidx, oidx = {b: i for i, b in enumerate(brands)}, {k: i for i, k in enumerate(subs)}, {k: i for i, k in enumerate(shops)}
    rows = []
    for p in items:
        d = S.item_data(p)
        rows.append([d["id"], d["n"], bidx.get(p["brand"], -1), d["p"], d["w"], d["i"], oidx[d["s"]], d["g"], sidx.get(sub_key(p), -1)])
    out.write(f"data/l/{key}.json", json.dumps({"b": brands, "o": shops, "s": [[k, X.sub_name(*k.split("/", 1)) if "/" in k else k] for k in subs], "i": rows},
                                               ensure_ascii=False, separators=(",", ":")))
    return f"/data/l/{key}.json"


def sub_key(p):
    return f"{p['cat']}/{p['sub']}" if p.get("sub") else ""


def paged(out, S, path, items, render, group="listings", index=True):
    pages = max(1, min(-(-len(items) // R.PER_PAGE), MAX_PAGES))
    for k in range(1, pages + 1):
        S.pg = (path, k, pages)
        out.page(path if k == 1 else f"{path}strana-{k}/", render(k, pages), group if k == 1 else None, index=index if k == 1 else False)
    S.pg = None


def price_range(items):
    ps = sorted(p["price"] for p in items)
    return (ps[0], ps[len(ps) // 2], ps[-1]) if ps else (0, 0, 0)


def main():
    import faulthandler
    faulthandler.dump_traceback_later(int(os.environ.get("KNC_BUILD_WATCHDOG", "8100")), exit=True)
    t0 = time.time()
    shops = [s for s in json.load(open(APP / "data/shops.json"))["shops"] if s.get("enabled", True)]
    rank = {s["id"]: i for i, s in enumerate(shops)}
    state = C.load_state()
    log("full run: range from fresh feeds" if C.full_mode() else "price run: range frozen at the last weekly run, prices refreshed")
    offers, dropped = C.load_offers(shops)
    if not offers:
        sys.exit("no offers — refusing to build an empty site")
    log(f"{len(offers)} offers; dropped: {dict(dropped.most_common(30))}")
    products = C.cluster(offers, rank)
    n_all = len(products)
    products = C.select(products)
    new = C.assign_slugs(products, state)
    gone = C.gone_products(products, state)
    log(f"{n_all} products -> {len(products)} after caps ({C.STATS.get('capped')}), {new} new slugs, {len(gone)} gone pages")
    products.sort(key=pop_key)
    names = Counter(X.fold(p["name"]) for p in products)
    for p in products:
        p["index"] = len(p["desc"]) >= 120 or len(p["offers"]) > 1
        p["dup"] = names[X.fold(p["name"])] > 1
        p["sub"] = X.sub_of(p)

    go_tpl, _ = GL.local_go(products)
    shop_meta = {s["id"]: {"name": s["name"], "color": s.get("color", "#888"), "domain": s["domain"]} for s in shops}
    present = sorted({o["shop"] for p in products for o in p["offers"]})
    stats = {"products": len(products), "shops": len(present), "updated": TODAY_CZ, "products_fmt": nb(len(products))}

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    out = Out(state)
    for f in (APP / "static").rglob("*"):
        if f.is_file() and f.name not in ("site.css", "app.js") and not f.name.endswith(".md") and "-src." not in f.name:
            out.write(f.relative_to(APP / "static").as_posix(), f.read_bytes())
    css = (APP / "static/assets/site.css").read_bytes()
    js = (APP / "static/assets/app.js").read_bytes()
    css_name = f"site.{hashlib.md5(css).hexdigest()[:8]}.css"
    js_name = f"app.{hashlib.md5(js).hexdigest()[:8]}.js"
    out.write("assets/" + css_name, css)
    out.write("assets/" + js_name, js)
    keep = state.setdefault("assets", {})     # earlier CSS/JS stay online: cached HTML keeps its styles after a deploy
    for name, data in ((css_name, css), (js_name, js)):
        keep.setdefault(name, {"day": DAY, "b64": base64.b64encode(data).decode()})
    for kind in ("site.", "app."):
        for n in sorted((n for n in keep if n.startswith(kind)), key=lambda n: keep[n]["day"])[:-4]:
            keep.pop(n)
    for name, rec in keep.items():
        if not (DIST / "assets" / name).exists():
            out.write("assets/" + name, base64.b64decode(rec["b64"]))
    S = R.Site(BASE, ENV, GA4, css_name, js_name, shop_meta, stats)
    GL.write_go(out, go_tpl, shop_meta)

    # one spelling per brand ("LEGO" / "Lego" -> the most common one)
    spell = defaultdict(Counter)
    for p in products:
        if p["brand"]:
            spell[X.slugify(p["brand"])][p["brand"]] += 1
    for p in products:
        if p["brand"]:
            p["brand"] = spell[X.slugify(p["brand"])].most_common(1)[0][0]
    by_cat, by_dept, by_brand, by_shop = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    for p in products:
        by_cat[p["cat"]].append(p)
        by_dept[X.CATS[p["cat"]][1]].append(p)
        if p["brand"]:
            by_brand[X.slugify(p["brand"])].append(p)
        for sid in {o["shop"] for o in p["offers"]}:
            by_shop[sid].append(p)
    S.cat_ok = {k for k, ps in by_cat.items() if len(ps) >= MIN_CAT}
    S.dept_ok = {X.CATS[k][1] for k in S.cat_ok}
    brand_name = {b: Counter(p["brand"] for p in ps).most_common(1)[0][0] for b, ps in by_brand.items()}
    brand_pages = {b: ps for b, ps in by_brand.items() if len(ps) >= 8 and b and b not in X.TREE}
    # subcategories: hand-written / toy ones (>= MIN_SUB products) + category x brand (>= MIN_BRAND_SUB) where no hand-written one has that name
    by_sub = defaultdict(list)
    for p in products:
        if p["sub"]:
            by_sub[(p["cat"], p["sub"])].append(p)
    subs = {k: v for k, v in by_sub.items() if len(v) >= MIN_SUB and k[0] in S.cat_ok}
    for p in products:
        if p["sub"] and (p["cat"], p["sub"]) not in subs:
            p["sub"] = ""
    taken = defaultdict(set)
    for (c, sl) in subs:
        taken[c].add(sl)
        taken[c].add(X.slugify(X.sub_name(c, sl)))
    brand_subs, sub_redirects = {}, {}
    for c, ps in by_cat.items():
        if c not in S.cat_ok:
            continue
        for b, n in Counter(p["brand"] for p in ps if p["brand"]).most_common(24):
            bs = X.slugify(b)
            if n >= MIN_BRAND_SUB and bs and bs not in taken[c] and bs not in X.TREE:
                bps = [p for p in ps if p["brand"] == b]
                # skip "Apple" next to "iPhone": a hand-written sub already holds most of the brand
                top_sub = Counter(p["sub"] for p in bps if p["sub"]).most_common(1)
                if top_sub and top_sub[0][1] >= 0.6 * len(bps):
                    if (c, top_sub[0][0]) in subs:
                        sub_redirects[f"/{c}/{bs}/"] = f"/{c}/{top_sub[0][0]}/"
                    continue
                brand_subs[(c, bs)] = (b, bps)
    S.subs = {k: X.sub_name(*k) for k in subs}
    S.brand_subs = {k: v[0] for k, v in brand_subs.items()}
    S.sub_redirects = {a: b for a, b in sub_redirects.items() if a not in out.seen}
    S.ctx = {"by_cat": by_cat, "brands": brand_pages, "brand_name": brand_name, "by_sub": subs}
    write_menu(out, S, by_cat, subs, brand_subs)

    # ---------------- products
    for p in products:
        out.page(f"/produkt/{p['slug']}/", product_page(S, p), "products", index=p["index"])
    for g in gone.values():
        path = f"/produkt/{g['slug']}/"
        if path not in out.seen:
            out.page(path, gone_page(S, g), None, index=False)
    log(f"product pages done ({time.time() - t0:.0f}s)")

    # ---------------- departments, categories, brands, shops, sale
    for d in X.DEPTS:
        items = sorted(by_dept.get(d, []), key=pop_key)
        if d not in S.dept_ok:
            continue
        j = write_json(out, S, d, items)
        paged(out, S, f"/{d}/", items, lambda k, n: dept_page(S, d, items, j, k, n))
    for k in X.CATS:
        ps = sorted(by_cat.get(k, []), key=pop_key)
        if not ps:
            continue
        j = write_json(out, S, k, ps)
        paged(out, S, f"/{k}/", ps, lambda pg, n: cat_page(S, k, ps, j, pg, n), index=k in S.cat_ok)
    for (c, sl), ps in subs.items():
        ps = sorted(ps, key=pop_key)
        j = write_json(out, S, f"{c}--{sl}", ps)
        paged(out, S, f"/{c}/{sl}/", ps, lambda pg, n: sub_page(S, c, sl, S.subs[(c, sl)], ps, j, pg, n), index=len(ps) >= 8)
    for (c, bs), (b, ps) in brand_subs.items():
        ps = sorted(ps, key=pop_key)
        j = write_json(out, S, f"{c}--{bs}", ps)
        paged(out, S, f"/{c}/{bs}/", ps, lambda pg, n: sub_page(S, c, bs, f"{X.CATS[c][0]} {b}", ps, j, pg, n), index=True)
    log(f"subcategories: {len(subs)} hand-written/toys, {len(brand_subs)} by brand")
    for b, ps in brand_pages.items():
        ps = sorted(ps, key=pop_key)
        j = write_json(out, S, f"z-{b}", ps)
        paged(out, S, f"/znacky/{b}/", ps, lambda pg, n: brand_page(S, b, ps, j, pg, n), index=len(ps) >= 12)
    out.page("/znacky/", brands_index(S, brand_pages, brand_name), "pages")
    for s in shops:
        ps = sorted(by_shop.get(s["id"], []), key=pop_key)
        if ps:
            j = write_json(out, S, f"o-{s['id']}", ps)
            paged(out, S, f"/obchody/{s['id']}/", ps, lambda pg, n: shop_page(S, s, ps, j, pg, n), index=len(ps) >= 12)
    out.page("/obchody/", shops_index(S, shops, by_shop), "pages")
    sale = sorted([p for p in products if R.discount(p) >= 20], key=lambda p: (-R.discount(p) - (30 if X.top_brand(p["brand"]) else 0), p["id"]))
    if sale:
        j = write_json(out, S, "slevy", sale)
        paged(out, S, "/slevy/", sale, lambda pg, n: sale_page(S, sale, j, pg, n), "pages")

    # ---------------- the shop flow (filled by app.js) and static pages
    out.page("/kategorie/", categories_index(S, by_cat, subs, brand_subs), "pages")
    out.page("/kosik/", flow_page(S, "/kosik/", "Košík", "cart"), None, index=False)
    out.page("/pokladna/", flow_page(S, "/pokladna/", "Pokladna", "checkout"), None, index=False)
    out.page("/objednavka/", flow_page(S, "/objednavka/", "Tvoje objednávka", "order"), None, index=False)
    out.page("/moje-uspory/", flow_page(S, "/moje-uspory/", "Moje úspory", "savings"), None, index=False)
    out.page("/hledat/", flow_page(S, "/hledat/", "Hledat", "search"), None, index=False)
    out.page("/jak-to-funguje/", about_page(S, present), "pages")
    out.page("/dopaminove-nakupovani/", dopamine_page(S), "pages")
    out.page("/kontakt/", contact_page(S), "pages")
    out.page("/ochrana-osobnich-udaju/", privacy_page(S), "pages")
    out.page("/", home_page(S, products, by_cat, by_dept, subs), "pages")
    out.write("404.html", S.layout("/404/", "Stránka nenalezena" + SUFFIX, "Tahle stránka neexistuje.",
                                   '<section class="e404 wrap"><img src="/img/ui/box-empty.webp" alt="" width="240" height="240"><div><p class="eyebrow">404</p>'
                                   '<h1>Tady je prázdno. A ne tím dobrým způsobem.</h1><p class="lead">Produkt mohl zmizet z nabídky obchodu, nebo vedla stará adresa. '
                                   'Zkus ho najít nahoře ve vyhledávání.</p><p><a class="btn" href="/">Zpět do galerie</a></p></div></section>', noindex=True))
    write_search(out, S, products, brand_pages, brand_name)

    # ---------------- sitemaps, robots, headers
    sm = []
    pic = {f"/produkt/{p['slug']}/": p["img"] for p in products if p.get("img", "").startswith("https://")}
    for group, paths in out.sitemap.items():
        for i in range(0, len(paths), 40000):
            name = f"sitemap-{group}-{i // 40000 + 1}.xml"
            body = "".join(f"<url><loc>{BASE}{p}</loc><lastmod>{state['lastmod'].get(p, TODAY.isoformat())}</lastmod>"
                           + (f"<image:image><image:loc>{E(pic[p])}</image:loc></image:image>" if p in pic else "") + "</url>" for p in paths[i:i + 40000])
            out.write(name, '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
                            f'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">{body}</urlset>')
            sm.append(name)
    out.write("sitemap_index.xml", '<?xml version="1.0" encoding="UTF-8"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
              + "".join(f"<sitemap><loc>{BASE}/{n}</loc><lastmod>{TODAY.isoformat()}</lastmod></sitemap>" for n in sm) + "</sitemapindex>")
    if ENV == "production":
        out.write("robots.txt", f"User-agent: *\nDisallow: /data/\nDisallow: /hledat/\nDisallow: /go/\nDisallow: /kosik/\nDisallow: /pokladna/\n"
                                f"Disallow: /objednavka/\n\nSitemap: {BASE}/sitemap_index.xml\n")
    else:
        out.write("robots.txt", "User-agent: *\nDisallow: /\n")
    out.write(".well-known/security.txt", f"Contact: mailto:{R.OPERATOR['email']}\nExpires: {TODAY.year + 1}-12-31T00:00:00.000Z\nPreferred-Languages: cs, en\n"
                                          f"Canonical: {BASE}/.well-known/security.txt\n")
    noidx = "" if ENV == "production" else "  X-Robots-Tag: noindex\n"
    sec = ("  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n"
           "  Strict-Transport-Security: max-age=63072000; includeSubDomains; preload\n  X-Frame-Options: DENY\n"
           "  Cross-Origin-Opener-Policy: same-origin\n  X-Permitted-Cross-Domain-Policies: none\n"
           "  Permissions-Policy: accelerometer=(), camera=(), display-capture=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), "
           "midi=(), payment=(), usb=(), xr-spatial-tracking=(), interest-cohort=()\n")
    csp = ("  Content-Security-Policy: default-src 'none'; img-src 'self' https: data:; "
           "script-src 'self' 'inline-speculation-rules' https://www.googletagmanager.com " + " ".join(f"'sha256-{h}'" for h in sorted(out.script_hashes)) + "; "
           "connect-src 'self' https://*.googletagmanager.com https://*.google-analytics.com https://*.analytics.google.com; style-src 'self' 'unsafe-inline'; "
           "font-src 'self'; manifest-src 'self'; media-src 'self'; object-src 'none'; frame-src 'none'; worker-src 'none'; frame-ancestors 'none'; "
           "base-uri 'none'; form-action 'self'; upgrade-insecure-requests\n")
    preload = (f"  Link: </assets/{css_name}>; rel=preload; as=style, </fonts/body.woff2>; rel=preload; as=font; type=font/woff2; crossorigin, "
               f"</fonts/display.woff2>; rel=preload; as=font; type=font/woff2; crossorigin\n")
    html_cache = "  Cache-Control: public, max-age=300, stale-while-revalidate=3600\n"
    # brand subcategories folded into a hand-written one (Apple -> iPhone) keep their links; Workers allow 2 000 static rules
    out.write("_redirects", "".join(f"{a} {b} 301\n" for a, b in sorted(S.sub_redirects.items())[:2000]))
    out.write("_headers", "/assets/*\n  Cache-Control: public, max-age=31536000, immutable\n/fonts/*\n  Cache-Control: public, max-age=31536000, immutable\n"
              "/data/*\n  Cache-Control: public, max-age=3600\n  X-Robots-Tag: noindex\n"
              "/img/*\n  Cache-Control: public, max-age=604800, stale-while-revalidate=2592000\n"
              "/*.xml\n  Cache-Control: public, max-age=3600\n/go/*\n  X-Robots-Tag: noindex, nofollow\n"
              "/\n" + html_cache + preload + "/*/\n" + html_cache + preload + "/*\n" + sec + csp + noidx)
    if INDEXNOW_KEY:
        out.write(f"{INDEXNOW_KEY}.txt", INDEXNOW_KEY)
    for k in list(out.hashes):
        if k not in out.seen:
            out.hashes.pop(k, None)
            out.lastmod.pop(k, None)
    C.save_state(state)
    (APP / "data/state/changed.txt").write_text("\n".join(out.changed))
    report = {"at": time.strftime("%Y-%m-%d %H:%M"), "env": ENV, "files": out.files, "offers": len(offers), "products": len(products),
              "multi_shop": sum(1 for p in products if len(p["offers"]) > 1), "with_sizes": sum(1 for p in products if p["sizes"]),
              "indexable_products": sum(1 for p in products if p["index"]), "gone_pages": len(gone), "brands": len(brand_pages),
              "public_categories": len(S.cat_ok), "per_cat": dict(Counter(p["cat"] for p in products).most_common()),
              "per_shop": dict(Counter(o["shop"] for p in products for o in p["offers"]).most_common()), "dropped": dict(dropped),
              "capped": C.STATS.get("capped"), "changed": len(out.changed)}
    json.dump(report, open(APP / "data/state/build-report.json", "w"), indent=1, ensure_ascii=False)
    log(json.dumps({k: v for k, v in report.items() if k not in ("per_cat", "per_shop", "dropped")}, ensure_ascii=False))
    log(f"built {out.files} files in {time.time() - t0:.0f}s")


# ======================================================================= search

def write_search(out, S, products, brand_pages, brand_name):
    """Suggestions without a server: data/sug.json (categories, brands) + data/s/<2 letters>.json (best products per word prefix)."""
    sug = [[X.CATS[k][0], f"/{k}/", "k"] for k in X.CATS if k in S.cat_ok]
    sug += [[X.DEPTS[d][0], f"/{d}/", "o"] for d in X.DEPTS if d in S.dept_ok]
    sug += [[brand_name[b], f"/znacky/{b}/", "z"] for b, ps in sorted(brand_pages.items(), key=lambda x: -len(x[1]))]
    bf = {X.fold(v) for v in brand_name.values()}      # a subcategory called "Nike" reads "Tenisky Nike" next to the brand "Nike"
    sug += [[f"{X.CATS[c][0]} {n}" if X.fold(n) in bf else n, f"/{c}/{sl}/", "p"] for (c, sl), n in S.subs.items()]
    sug += [[f"{X.CATS[c][0]} {b}", f"/{c}/{bs}/", "p"] for (c, bs), b in S.brand_subs.items()]
    out.write("data/sug.json", json.dumps(sug, ensure_ascii=False, separators=(",", ":")))
    buckets = defaultdict(list)
    for p in products:          # products are sorted by desirability: the first ones per bucket are the best
        words = {w for w in re.findall(r"[a-z0-9]+", X.fold(p["name"] + " " + p["brand"])) if len(w) >= 2}
        for k in {w[:2] for w in words}:
            if len(buckets[k]) < 600:
                buckets[k].append([p["slug"], p["name"], p["brand"], p["price"], R.img_url(p["img"], "card")])
    for k, rows in buckets.items():
        out.write(f"data/s/{k}.json", json.dumps(rows, ensure_ascii=False, separators=(",", ":")))


# ======================================================================= pages

def write_menu(out, S, by_cat, subs, brand_subs):
    """The mega menu is loaded on demand from /data/menu.json (not repeated in 300 000 pages)."""
    sub_of_cat = defaultdict(list)
    for (c, sl), ps in sorted(subs.items(), key=lambda x: -len(x[1])):
        sub_of_cat[c].append([sl, S.subs[(c, sl)]])
    for (c, bs), (b, ps) in sorted(brand_subs.items(), key=lambda x: -len(x[1][1])):
        sub_of_cat[c].append([bs, b])
    menu = []
    for d, (dn, _, dic) in X.DEPTS.items():
        if d not in S.dept_ok:
            continue
        cats = [[k, X.CATS[k][0], len(by_cat[k]), X.CATS[k][3], sub_of_cat[k][:12]] for k in X.CATS if X.CATS[k][1] == d and k in S.cat_ok]
        cats.sort(key=lambda c: -c[2])
        menu.append([d, dn, dic, cats])
    out.write("data/menu.json", json.dumps(menu, ensure_ascii=False, separators=(",", ":")))


def band(title, lead, icon=None, extra=""):
    ic = f'<img class="band__ic" src="/img/ic/{icon}.webp" alt="" width="64" height="64">' if icon else ""
    return f'<section class="band"><div class="wrap band__in">{ic}<div class="band__txt"><h1>{title}</h1><p class="lead">{lead}</p>{extra}</div></div></section>'


def full_rows(rows, per=7, most=14):
    """Photo tiles fill whole rows of 7 on desktop: 1-7 stay, more are cut to 7 or 14 (the rest is in the sidebar)."""
    return rows if len(rows) <= per else rows[:min(most, len(rows) // per * per)]


def img_tiles(S, rows, cls=""):
    """Subcategory / category tiles with the photo of their best product: rows = (href, name, count, product).
    Square photo boxes like the product cards; a dead photo falls back to the category icon (app.js, data-ic)."""
    if not rows:
        return ""
    return f'<div class="ptiles{" " + cls if cls else ""}">' + "".join(
        f'<a class="ptile" href="{h}"><span class="ptile__img{R.photo_bg(p["img"], p["cat"])}"><img src="{E(R.img_url(p["img"], "card"))}" alt="" loading="lazy" referrerpolicy="no-referrer" width="160" height="160" data-orig="{E(p["img"])}" data-ic="/img/ic/{X.CATS[p["cat"]][3]}.webp"></span>'
        f'<span class="ptile__t"><b>{E(n)}</b><small>{nb(c)} {plural(c, "produkt", "produkty", "produktů")}</small></span></a>' for h, n, c, p in rows) + "</div>"


def listing(S, items, jsn, page, pages, path, side_links=None):
    """Sidebar filters (wired to the listing JSON by app.js) + sort tabs + server-rendered page of products + pager."""
    fill = " data-fill" if items and X.CATS[items[0]["cat"]][1] in R.FILL_DEPTS else ""     # Answear shoe/bag shots fill the box
    chunk = items[(page - 1) * R.PER_PAGE: page * R.PER_PAGE]
    top = items[:JSON_ITEMS]
    brands = [(b, n) for b, n in Counter(p["brand"] for p in top if p["brand"]).most_common(30) if n >= 2]
    shops = Counter(S.shop(p["offers"][0]["shop"])["name"] for p in top).most_common(12)
    lo, _, hi = price_range(items)
    n = len(items)
    links = ""
    if side_links:
        links = '<div class="fbox"><h3>Kategorie</h3><ul class="flinks">' + "".join(
            f'<li><a href="{h}"{" aria-current=page" if h == path else ""}>{E(t)}<small>{nb(c)}</small></a></li>' for h, t, c in side_links) + "</ul></div>"
    bbox = ('<div class="fbox"><h3>Značka</h3><div class="fchecks" data-f="brand">' + "".join(
        f'<label><input type="checkbox" value="{E(b)}"><span>{E(b)}</span><small>{c}</small></label>' for b, c in brands) + "</div></div>") if len(brands) > 1 else ""
    sbox = ('<div class="fbox"><h3>Obchod</h3><div class="fchecks" data-f="shop">' + "".join(
        f'<label><input type="checkbox" value="{E(o)}"><span>{E(o)}</span><small>{c}</small></label>' for o, c in shops) + "</div></div>") if len(shops) > 1 else ""
    side = (f'<aside class="side" id="filters" data-list="{jsn}"><div class="side__hd"><b>Filtry</b><button type="button" class="x" data-close-filters aria-label="Zavřít filtry">{R.icon("x", 20)}</button></div>'
            f'{links}<div class="fbox"><h3>Cena</h3><div class="frange"><label><span class="sr">Cena od</span><input type="number" inputmode="numeric" data-f="min" placeholder="{lo}"></label>'
            f'<span>–</span><label><span class="sr">Cena do</span><input type="number" inputmode="numeric" data-f="max" placeholder="{hi}"></label><span>Kč</span></div>'
            f'<label class="fsale"><input type="checkbox" data-f="sale"><span>Jen ve slevě</span></label></div>{bbox}{sbox}'
            f'<button type="button" class="btn btn--sm side__go" data-close-filters>Zobrazit produkty</button></aside>')
    tabs = ('<div class="sorts" role="tablist" aria-label="Řazení"><button type="button" class="on" data-sort="">Doporučujeme</button><button type="button" data-sort="p">Nejlevnější</button>'
            '<button type="button" data-sort="-p">Nejdražší</button><button type="button" data-sort="d">Největší sleva</button></div>')
    head = (f'<div class="lhead"><p class="lhead__n"><b data-n>{nb(n)}</b> {plural(n, "produkt", "produkty", "produktů")}</p>{tabs}'
            f'<button type="button" class="btn btn--sm btn--ghost lhead__f" data-open-filters>{R.icon("sliders", 18)}Filtry</button></div>')
    return (f'<div class="shop">{side}<div class="shop__main">{head}<div class="chips-on" data-active hidden></div>'
            f'<div data-grid{fill}>{S.grid(chunk, first_eager=4 if page == 1 else 0)}</div>{R.pager_html(path, page, pages)}</div></div>')


def dept_page(S, d, items, jsn, page, pages):
    name, blurb, ic = X.DEPTS[d]
    lo, med, hi = price_range(items)
    cats = [(f"/{k}/", X.CATS[k][0], len(S.ctx["by_cat"][k]), S.ctx["by_cat"][k][0]) for k in X.CATS if X.CATS[k][1] == d and k in S.cat_ok]
    cats.sort(key=lambda x: -x[2])
    lead = f"{blurb}. {nb(len(items))} produktů od {kc(lo)}."
    side = [(h, t, c) for h, t, c, _ in cats]
    body = band(E(name), lead, ic) + f'<div class="wrap">{img_tiles(S, cats) if page == 1 else ""}{listing(S, items, jsn, page, pages, f"/{d}/", side)}</div>'
    return S.layout(f"/{d}/", f"{name} – {nb(len(items))} produktů od {kc(lo)}" + SUFFIX, f"{name}: {blurb.lower()}. {len(items)} produktů z českých e-shopů, ceny od {kc(lo)}.",
                    body, crumbs=[HOME, (name, f"/{d}/")])


def cat_subs(S, k):
    rows = [(f"/{k}/{sl}/", S.subs[(k, sl)], len(ps), sorted(ps, key=pop_key)[0]) for (c, sl), ps in S.ctx["by_sub"].items() if c == k]
    rows.sort(key=lambda x: -x[2])
    brows = [(f"/{k}/{bs}/", b, len(S.ctx["by_cat"][k]) and sum(1 for p in S.ctx["by_cat"][k] if p["brand"] == b), None) for (c, bs), b in S.brand_subs.items() if c == k]
    brows = [(h, t, n, next(p for p in S.ctx["by_cat"][k] if p["brand"] == t)) for h, t, n, _ in brows]
    brows.sort(key=lambda x: -x[2])
    return rows, brows


def cat_page(S, k, items, jsn, page, pages):
    name, d, h1, ic = X.CATS[k][0], X.CATS[k][1], X.CATS[k][2], X.CATS[k][3]
    lo, med, hi = price_range(items)
    n = len(items)
    top = [b for b, _ in Counter(p["brand"] for p in items[:400] if p["brand"]).most_common(3)]
    lead = f"{nb(n)} {plural(n, 'produkt', 'produkty', 'produktů')} od {kc(lo)} do {kc(hi)}" + (f", nejvíc {', '.join(E(b) for b in top)}" if top else "") + "."
    rows, brows = cat_subs(S, k)
    tiles = img_tiles(S, full_rows(rows)) if page == 1 else ""
    bchips = ('<div class="bchips"><span>Značky:</span>' + "".join(f'<a href="{h}">{E(t)}</a>' for h, t, _, _ in brows[:16]) + "</div>") if brows and page == 1 else ""
    side = [(h, t, c) for h, t, c, _ in rows] + [(h, t, c) for h, t, c, _ in brows]
    body = band(E(h1), lead, ic) + f'<div class="wrap">{tiles}{bchips}{listing(S, items, jsn, page, pages, f"/{k}/", side)}</div>'
    title = f"{h1} – {nb(n)} produktů od {kc(lo)}" + SUFFIX
    return S.layout(f"/{k}/", title, f"{h1}: {n} produktů z českých e-shopů od {kc(lo)}. Vyber podle značky, ceny a obchodu.",
                    body, crumbs=[HOME, (X.DEPTS[d][0], f"/{d}/"), (name, f"/{k}/")], noindex=k not in S.cat_ok)


def sub_page(S, k, sl, sname, items, jsn, page, pages):
    d = X.CATS[k][1]
    lo, _, hi = price_range(items)
    n = len(items)
    rows, brows = cat_subs(S, k)
    side = [(h, t, c) for h, t, c, _ in rows] + [(h, t, c) for h, t, c, _ in brows]
    lead = f"{nb(n)} {plural(n, 'produkt', 'produkty', 'produktů')} od {kc(lo)} do {kc(hi)}."
    body = band(E(sname), lead, X.CATS[k][3]) + f'<div class="wrap">{listing(S, items, jsn, page, pages, f"/{k}/{sl}/", side)}</div>'
    return S.layout(f"/{k}/{sl}/", f"{sname} – {nb(n)} produktů od {kc(lo)}" + SUFFIX, f"{sname}: {n} produktů z českých e-shopů od {kc(lo)}.",
                    body, crumbs=[HOME, (X.DEPTS[d][0], f"/{d}/"), (X.CATS[k][0], f"/{k}/"), (sname, f"/{k}/{sl}/")], noindex=n < 8)


def categories_index(S, by_cat, subs, brand_subs):
    parts = []
    for d, (dn, _, dic) in X.DEPTS.items():
        if d not in S.dept_ok:
            continue
        cols = []
        for k in X.CATS:
            if X.CATS[k][1] != d or k not in S.cat_ok:
                continue
            sl = [(f"/{k}/{s}/", S.subs[(k, s)]) for (c, s) in subs if c == k][:10]
            cols.append(f'<div><h3><a href="/{k}/">{E(X.CATS[k][0])}</a></h3><ul>' + "".join(f'<li><a href="{h}">{E(t)}</a></li>' for h, t in sl) + "</ul></div>")
        parts.append(f'<section class="catidx"><h2><img src="/img/ic/{dic}.webp" alt="" width="40" height="40"><a href="/{d}/">{E(dn)}</a></h2><div class="catidx__cols">{"".join(cols)}</div></section>')
    body = band("Všechny kategorie", f"{len(S.cat_ok)} kategorií a {len(subs) + len(brand_subs)} podkategorií.") + f'<div class="wrap">{"".join(parts)}</div>'
    return S.layout("/kategorie/", "Všechny kategorie" + SUFFIX, "Přehled všech kategorií a podkategorií KoupímNic.", body, crumbs=[HOME, ("Kategorie", "/kategorie/")])


def brand_page(S, b, items, jsn, page, pages):
    name = S.ctx["brand_name"][b]
    lo, _, hi = price_range(items)
    cats = Counter(p["cat"] for p in items)
    chips = '<nav class="chips">' + "".join(f'<a href="/{c}/">{E(X.CATS[c][0])}</a>' for c, _ in cats.most_common(8) if c in S.cat_ok) + "</nav>"
    lead = f"{nb(len(items))} {plural(len(items), 'produkt', 'produkty', 'produktů')} značky {E(name)} od {kc(lo)} do {kc(hi)}."
    body = band(E(name), lead, None, chips) + f'<div class="wrap">{listing(S, items, jsn, page, pages, f"/znacky/{b}/")}</div>'
    return S.layout(f"/znacky/{b}/", f"{name} – {nb(len(items))} produktů od {kc(lo)}" + SUFFIX,
                    f"{name}: {len(items)} produktů z českých e-shopů od {kc(lo)}.",
                    body, crumbs=[HOME, ("Značky", "/znacky/"), (name, f"/znacky/{b}/")], noindex=len(items) < 12)


def brands_index(S, brand_pages, brand_name):
    rows = sorted(brand_pages.items(), key=lambda x: X.fold(brand_name[x[0]]))
    groups = defaultdict(list)
    for b, ps in rows:
        ch = X.fold(brand_name[b])[:1].upper()
        groups[ch if ch.isalpha() else "#"].append(f'<li><a href="/znacky/{b}/">{E(brand_name[b])}</a> <small>{len(ps)}</small></li>')
    top = sorted(brand_pages, key=lambda b: (-(X.top_brand(brand_name[b])), -len(brand_pages[b])))[:24]
    body = (band("Značky", f"{len(brand_pages)} značek od Apple po Zaru.")
            + '<div class="wrap"><div class="brandtop">' + "".join(f'<a href="/znacky/{b}/">{E(brand_name[b])}</a>' for b in top) + "</div>"
            + '<div class="az">' + "".join(f'<section><h2>{ch}</h2><ul>{"".join(v)}</ul></section>' for ch, v in sorted(groups.items())) + "</div></div>")
    return S.layout("/znacky/", "Značky – Apple, Nike, LEGO, Dior a další" + SUFFIX, "Všechny značky v galerii KoupímNic: elektronika, móda, boty, parfémy.",
                    body, crumbs=[HOME, ("Značky", "/znacky/")])


def shop_page(S, s, items, jsn, page, pages):
    lead = f"{nb(len(items))} produktů z e-shopu {E(s['name'])} ({E(s['domain'])})."
    path = f"/obchody/{s['id']}/"
    body = band(E(s["name"]), lead) + f'<div class="wrap">{listing(S, items, jsn, page, pages, path)}</div>'
    return S.layout(path, f"{s['name']} – {nb(len(items))} produktů" + SUFFIX, f"Produkty z obchodu {s['name']} v galerii KoupímNic.",
                    body, crumbs=[HOME, ("Obchody", "/obchody/"), (s["name"], path)], noindex=len(items) < 12)


def shops_index(S, shops, by_shop):
    rows = "".join(f'<li><a href="/obchody/{s["id"]}/"><span class="dot" style="background:{s.get("color", "#888")}"></span>{E(s["name"])}</a>'
                   f'<small>{nb(len(by_shop[s["id"]]))} produktů</small></li>' for s in sorted(shops, key=lambda s: -len(by_shop.get(s["id"], []))) if by_shop.get(s["id"]))
    body = band("Obchody", "Odkud bereme produkty a ceny. Všechno jsou skutečné e-shopy. My jen ukazujeme, oni prodávají.") + f'<div class="wrap"><ul class="shoplist">{rows}</ul></div>'
    return S.layout("/obchody/", "Obchody, ze kterých bereme produkty" + SUFFIX, "Seznam e-shopů, jejichž produkty a ceny ukazujeme.", body, crumbs=[HOME, ("Obchody", "/obchody/")])


def sale_page(S, items, jsn, page, pages):
    body = band("Slevy", f"{nb(len(items))} produktů se slevou aspoň 20 %.") + \
        f'<div class="wrap">{listing(S, items, jsn, page, pages, "/slevy/")}</div>'
    return S.layout("/slevy/", "Slevy až −70 % – elektronika, móda, boty" + SUFFIX, "Zlevněné produkty z českých e-shopů se slevou aspoň 20 %.",
                    body, crumbs=[HOME, ("Slevy", "/slevy/")])


def product_page(S, p):
    k = p["cat"]
    d = X.CATS[k][1]
    o0 = p["offers"][0]
    shop = S.shop(o0["shop"])
    disc = R.discount(p)
    imgs = [u for u in [p["img"]] + p["imgs"] if u][:7]
    main = R.img_url(imgs[0], "main") if imgs else "/img/ui/placeholder.svg"
    thumbs = "".join(f'<button type="button" data-src="{E(R.img_url(u, "main"))}"{" class=on" if i == 0 else ""} aria-label="Obrázek {i + 1}">'
                     f'<img src="{E(R.img_url(u, "card"))}" alt="" loading="lazy" referrerpolicy="no-referrer" width="72" height="72" data-orig="{E(u)}"></button>'
                     for i, u in enumerate(imgs)) if len(imgs) > 1 else ""
    off = f"<span class=card__off>−{disc}&nbsp;%</span>" if disc >= 5 else ""
    gal = (f'<div class="gal"><div class="gal__main{R.photo_bg(p["img"])}"><img id="gmain" src="{E(main)}" alt="{E(p["name"])}" referrerpolicy="no-referrer" width="720" height="720" '
           f'fetchpriority="high" data-orig="{E(imgs[0] if imgs else "")}">{off}</div><div class="thumbs">{thumbs}</div></div>')
    data = E(json.dumps(S.item_data(p), ensure_ascii=False, separators=(",", ":")))
    sizes = ""
    if p["sizes"] and p["sizes"] != ["univerzální"]:
        sizes = ('<fieldset class="sizes"><legend>Velikost</legend><div>'
                 + "".join(f'<label><input type="radio" name="size" value="{E(s)}"{" checked" if i == 0 else ""}><span>{E(s)}</span></label>' for i, s in enumerate(p["sizes"][:24]))
                 + "</div></fieldset>")
    was = f'<s>{kc(p["was"])}</s><span class="off">−{disc}&nbsp;%</span>' if disc >= 5 else ""
    others = ""
    if len(p["offers"]) > 1:
        others = '<details class="others"><summary>Cena v dalších obchodech</summary><ul>' + "".join(
            f'<li><span>{E(S.shop(o["shop"])["name"])}</span><b>{kc(o["price"])}</b></li>' for o in p["offers"][1:6]) + "</ul></details>"
    buy = (f'<div class="buy" data-item="{data}"><div class="buy__price"><b>{kc(p["price"])}</b>{was}</div>'
           f'<p class="buy__stock"><span class="dot-ok"></span><b>Skladem</b> · doručíme ještě dnes</p>{sizes}'
           f'<div class="buy__cta"><div class="qty qty--lg" data-qty><button type="button" data-qd="-1" aria-label="Méně">{R.icon("minus", 16)}</button>'
           f'<input type="number" min="1" max="9" value="1" inputmode="numeric" aria-label="Počet kusů"><button type="button" data-qd="1" aria-label="Více">{R.icon("plus", 16)}</button></div>'
           f'<button class="btn btn--lg buy__add" type="button" data-buy="cart">{R.icon("bag", 20)}Do košíku</button></div>'
           f'<button class="btn btn--lg btn--lime buy__now" type="button" data-buy="now">Koupit hned</button>'
           f'<ul class="perks"><li>{R.icon("truck", 18)}Doprava zdarma</li><li>{R.icon("lock", 18)}Platíš nanečisto. Cena je skutečná, platba ne.</li>'
           f'<li>{R.icon("undo", 18)}Cena z obchodu {E(shop["name"])}, aktualizováno {TODAY_CZ}</li></ul>{others}'
           f'<p class="real">Chceš to doopravdy? <a href="{E(o0["go"])}" rel="sponsored nofollow noopener" target="_blank" data-go="{E(o0["shop"])}">Koupit u {E(shop["name"])}</a> '
           f'<span class="tag-ad">Reklama</span></p></div>'
           f'<div class="sticky-buy" data-item="{data}"><div><b>{kc(p["price"])}</b><small>Skladem</small></div>'
           f'<button class="btn" type="button" data-buy="cart">{R.icon("bag", 18)}Do košíku</button></div>')
    meta = []
    bslug = X.slugify(p["brand"])
    if p["brand"] and bslug in S.ctx["brands"]:
        meta.append(f'<a href="/znacky/{bslug}/">{E(p["brand"])}</a>')
    elif p["brand"]:
        meta.append(f"<span>{E(p['brand'])}</span>")
    meta.append(f'<a href="/{k}/">{E(X.CATS[k][0])}</a>')
    if p.get("sub") and (k, p["sub"]) in S.subs and X.fold(S.subs[(k, p["sub"])]) != X.fold(p["brand"]):
        meta.append(f'<a href="/{k}/{p["sub"]}/">{E(S.subs[(k, p["sub"])])}</a>')
    spec = [("Značka", E(p["brand"]) or "neuvedena"), ("Kategorie", f'<a href="/{k}/">{E(X.CATS[k][0])}</a>'), ("Obchod", E(shop["name"]))]
    if p["color"]:
        spec.append(("Barva", E(p["color"])))
    if p["sizes"]:
        spec.append(("Velikosti", E(", ".join(p["sizes"][:24]))))
    if p["ean"]:
        spec.append(("EAN", p["ean"]))
    spec_html = "".join(f"<tr><th>{a}</th><td>{b}</td></tr>" for a, b in spec)
    desc = (f'<h2>Popis</h2><div class="desc clamp" id="desc">{E(p["desc"])}</div><button class="more" type="button" data-more="desc">Celý popis</button>'
            if len(p["desc"]) > 40 else "")
    pool = S.ctx["by_sub"].get((k, p["sub"])) if p.get("sub") else None
    sim = [q for q in (pool or S.ctx["by_cat"].get(k, [])) if q is not p][:400]
    sim = sorted(sim, key=lambda q: (abs(q["price"] - p["price"]) / max(p["price"], 1) - (0.3 if q["brand"] == p["brand"] else 0), q["id"]))[:8]
    sim_html = f'<section class="sec"><div class="sec__h"><h2>Podobné produkty</h2><a href="/{k}/">Celá kategorie</a></div>{S.grid(sim)}</section>' if sim else ""
    body = (f'<div class="wrap"><div class="prod">{gal}<div class="prod__info"><div class="meta">{"".join(meta)}</div><h1>{E(p["name"])}</h1>{buy}</div></div>'
            f'<div class="prod__more"><div><h2>Parametry</h2><table class="spec">{spec_html}</table></div><div>{desc}</div></div>{sim_html}</div>')
    ld = {"@context": "https://schema.org", "@type": "Product", "name": p["name"], "image": imgs[:3] or None, "url": S.url(f"/produkt/{p['slug']}/"),
          "description": (p["desc"][:300] or p["name"]), "category": X.CATS[k][0],
          "offers": {"@type": "AggregateOffer", "priceCurrency": "CZK", "lowPrice": p["price"], "highPrice": max(o["price"] for o in p["offers"]),
                     "offerCount": len(p["offers"]), "availability": "https://schema.org/InStock"}}
    if p["brand"]:
        ld["brand"] = {"@type": "Brand", "name": p["brand"]}
    if p["ean"] and len(p["ean"]) == 13:
        ld["gtin13"] = p["ean"]
    ld = {a: b for a, b in ld.items() if b}
    tail = f" – {kc(p['price'])}"
    uniq = (f" ({p['color']})" if p["color"] and len(p["color"]) <= 18 else f" ({p['slug'][-6:]})") if p.get("dup") else ""
    nm = R.shorten_mid(p["name"], max(24, 74 - len(tail) - len(uniq) - len(SUFFIX)))
    title = nm + uniq + tail + SUFFIX
    desc_meta = f"{R.shorten(p['name'], 70)} za {kc(p['price'])}. Kup si to nanečisto, cena z obchodu {shop['name']}."
    if p["desc"] and 155 - len(desc_meta) > 30:
        desc_meta += " " + R.shorten(p["desc"], 154 - len(desc_meta))
    return S.layout(f"/produkt/{p['slug']}/", title, desc_meta, body, jsonld=[ld], noindex=not p["index"], og_img=imgs[0] if imgs else None,
                    preload_img=main if imgs else None,
                    crumbs=[HOME, (X.DEPTS[d][0], f"/{d}/"), (X.CATS[k][0], f"/{k}/")]
                    + ([(S.subs[(k, p["sub"])], f"/{k}/{p['sub']}/")] if p.get("sub") and (k, p["sub"]) in S.subs else [])
                    + [(R.shorten(p["name"], 50), f"/produkt/{p['slug']}/")], cls="is-prod")


def gone_page(S, g):
    k = g["cat"] if g["cat"] in X.CATS else "mobilni-telefony"
    sim = sorted(S.ctx["by_cat"].get(k, []), key=lambda q: abs(q["price"] - g["price"]))[:8]
    img = R.img_url(g["img"], "main") or "/img/ui/placeholder.svg"
    body = (f'<div class="wrap"><div class="prod"><div class="gal"><div class="gal__main"><img src="{E(img)}" alt="{E(g["name"])}" width="720" height="720"></div></div>'
            f'<div class="prod__info"><h1>{E(g["name"])}</h1><div class="gone"><b>Vyprodáno.</b> Tenhle produkt už není v nabídce. '
            f'Naposledy stál {kc(g["price"])}.</div><p><a class="btn" href="/{k}/">{E(X.CATS[k][0])}</a></p></div></div>'
            f'<section class="sec"><h2>Podobné produkty skladem</h2>{S.grid(sim)}</section></div>')
    return S.layout(f"/produkt/{g['slug']}/", f"{g['name']} – vyprodáno" + SUFFIX, f"{g['name']} už obchod nenabízí. Podobné produkty.", body, noindex=True)


def flow_page(S, path, title, kind):
    """Cart, checkout, order tracking, savings and search are rendered by app.js from localStorage."""
    shells = {
        "cart": '<h1>Košík</h1><div id="flow" data-flow="cart"><p class="muted">Načítám košík…</p></div>',
        "checkout": '<h1>Pokladna</h1><div id="flow" data-flow="checkout"><p class="muted">Načítám pokladnu…</p></div>',
        "order": '<div id="flow" data-flow="order"><p class="muted">Načítám objednávku…</p></div>',
        "savings": '<h1>Moje úspory</h1><div id="flow" data-flow="savings"><p class="muted">Počítám, co jsi neutratil…</p></div>',
        "search": '<h1>Hledat</h1><div id="flow" data-flow="search"><p class="muted">Hledám…</p></div>',
    }
    wide = " flow--wide" if kind == "search" else ""      # results use the full width like every listing
    return S.layout(path, title + SUFFIX, "Nákup nanečisto na KoupímNic.", f'<div class="wrap flow{wide}">{shells[kind]}</div>', noindex=True, cls="is-" + kind)


HOME_DESC = ("Dopaminové nakupování: {n} skutečných produktů z českých e-shopů za skutečné ceny. "
             "Košík, pokladna i kurýr jako doopravdy, jen se nic neplatí.")
DEPT_NOTE = {
    "elektronika": "Nejnovější technika bez splátek na dva roky.",
    "damska-moda": "Šatník se nafoukne, skříň zůstane stejná.",
    "panska-moda": "Bundy, mikiny a košile. Žehlit se nic nemusí.",
    "boty": "Krabice od bot bez bot. Klasika.",
    "doplnky": "Kabelka za průměrný plat. Nosí se nanečisto.",
    "krasa": "Vůně drahá, flakon prázdný.",
    "drogerie": "Nákup, na který se jinak nikdo netěší.",
    "domov": "Kávovar, robot, vysavač. Kuchyňská linka zůstane volná.",
    "hracky": "Dětská radost za dospělé ceny. Platí se jen ta radost.",
    "sport": "Kolo, stan, lyže. Pohyb ti nezajistíme, nákup ano.",
    "zvirata": "Pelíšek, do kterého si pes stejně nelehne.",
    "knihy": "Knihy, které si nekoupíš, aspoň nebudou vyčítavě stát v knihovně.",
}


def sec_h(title, note, href, label):
    note = f"<p>{note}</p>" if note else ""
    return f'<div class="sec__h"><div><h2>{E(title)}</h2>{note}</div><a href="{href}">{E(label)}</a></div>'


def home_page(S, products, by_cat, by_dept, subs):
    want = [("mobilni-telefony", r"iphone 1[67]"), ("notebooky", r"macbook"), ("herni-konzole", r"playstation 5|ps5|switch 2"), ("sluchatka", r"airpods|wh-1000"),
            ("lego", r"lego"), ("chytre-hodinky", r"apple watch|galaxy watch"), ("tenisky", r"nike|adidas|new balance"), ("vysavace", r"dyson"),
            ("damske-parfemy", r"dior|chanel|lanc"), ("kabelky", r"michael kors|guess|coach|furla"), ("drony", r"dji"), ("kavovary", r"delonghi|de.longhi|nespresso")]
    picks, used = [], set()
    for k, rx in want:
        for p in by_cat.get(k, []):
            if p["id"] not in used and re.search(rx, X.fold(p["name"] + " " + p["brand"])):
                picks.append(p)
                used.add(p["id"])
                break
    picks += [p for p in products if p["id"] not in used and X.top_brand(p["brand"])][:max(0, 12 - len(picks))]
    depts = [(f"/{d}/", X.DEPTS[d][0], len(by_dept[d]), X.DEPTS[d][2]) for d in X.DEPTS if d in S.dept_ok]
    pop = [("mobilni-telefony", "iphone"), ("notebooky", "macbook-air"), ("herni-konzole", "playstation-5"), ("sluchatka", "airpods"), ("lego", "technic"),
           ("tenisky", "nike"), ("chytre-hodinky", "apple-watch"), ("televize", "oled-televize"), ("vysavace", "roboticke-vysavace"), ("damske-parfemy", "parfemovane-vody"),
           ("kavovary", "automaticke-kavovary"), ("tenisky", "new-balance"), ("tablety", "ipad"), ("drony", "dji-mini"),
           ("kabelky", "crossbody"), ("damske-parfemy", ""), ("lego", ""), ("notebooky", "herni-notebooky"), ("televize", ""), ("sluchatka", "")]
    prow = []
    for c, sl in pop:
        ps = subs.get((c, sl)) if sl else by_cat.get(c)
        if len(prow) < 14 and ps and (c, sl) not in {(r[4], r[5]) for r in prow}:
            best = sorted(ps, key=pop_key)[0]
            prow.append((f"/{c}/{sl}/" if sl else f"/{c}/", S.subs[(c, sl)] if sl else X.CATS[c][0], len(ps), best, c, sl))
    prow = [r[:4] for r in prow]
    rows = ""
    for d in X.DEPTS:
        if d not in S.dept_ok:
            continue
        seen_b, pick = Counter(), []
        for p in by_dept[d][:300]:          # variety: at most two products of one brand per row
            if p["img"] and seen_b[p["brand"]] < 2:
                pick.append(p)
                seen_b[p["brand"]] += 1
            if len(pick) == 8:
                break
        rows += f'<section class="sec">{sec_h(X.DEPTS[d][0], DEPT_NOTE.get(d, ""), f"/{d}/", "Vše z oddělení")}{S.grid(pick)}</section>'
    n_fmt = nb(len(products))
    top_off = max((R.discount(p) for p in products), default=0)
    top_off = min(70, top_off // 10 * 10)
    hero = ('<section class="hero"><div class="wrap hero__in"><div class="hero__txt"><p class="sticker">Dopaminové nakupování</p>'
            '<h1>Plný košík.<br><span>Plný účet.</span></h1>'
            f'<p class="lead">{n_fmt} skutečných produktů z {S.stats["shops"]} českých e-shopů za skutečné ceny. Vybereš, zaplatíš nanečisto, kurýr zazvoní. '
            'Radost z nákupu dorazí, peníze zůstanou doma.</p>'
            '<p class="hero__cta"><a class="btn btn--lg" href="#vyber">Nakupovat</a><a class="btn btn--lg btn--ghost" href="/kategorie/">Všechny kategorie</a></p>'
            '<p class="hero__saved" data-saved-hero hidden></p></div>'
            '<div class="hero__art"><img src="/img/ui/hero.webp" alt="" width="560" height="480" fetchpriority="high"></div></div></section>')
    how = ('<section class="sec">' + sec_h("Co se stane v hlavě, když nakupuješ", "Nejlepší část nákupu je ta před ním. Tady ji máš bez účtenky.",
                                          "/dopaminove-nakupovani/", "Dopaminové nakupování")
           + '<ol class="how">'
           f'<li><h3>Vybereš</h3><p>{n_fmt} produktů. Vybírat se dá donekonečna.</p></li>'
           '<li><h3>Naplníš košík</h3><p>Hodnota roste, výpis z účtu se nehne.</p></li>'
           '<li><h3>Zaplatíš nanečisto</h3><p>Pokladna jako všude. Kartu nechceme.</p></li>'
           '<li><h3>Zazvoní kurýr</h3><p>Rozbalíš krabici. Dopamin dorazil, zboží ne.</p></li></ol></section>')
    banners = ('<section class="banners" aria-label="Výhody">'
               f'<a class="banner banner--plum" href="/kategorie/"><span><strong>Doprava zdarma</strong> u všech {n_fmt} produktů. Taky proto, že nic nevezeme.</span>'
               '<img src="/img/ui/courier.webp" alt="" width="120" height="120" loading="lazy"></a>'
               + (f'<a class="banner banner--lime" href="/slevy/"><span><strong>Slevy až −{top_off}&nbsp;%</strong> na věci, které si stejně nekoupíš.</span>'
                  f'<b class="banner__big" aria-hidden="true">−{top_off}%</b></a>' if top_off >= 20 else "")
               + '<a class="banner banner--soft" href="/moje-uspory/"><span><strong>Počítadlo neutracených peněz.</strong> Roste s každým nákupem, který neproběhl.</span>'
               '<img src="/img/ui/piggy.webp" alt="" width="120" height="120" loading="lazy"></a></section>')
    body = (hero + f'<div class="wrap">{how}<section class="sec"><h2>Oddělení</h2>{S.tiles(depts)}</section>{banners}'
            f'<section class="sec">{sec_h("Oblíbené kategorie", "Kam se chodí pro radost.", "/kategorie/", "Všechny kategorie")}{img_tiles(S, prow, "ptiles--scroll")}</section>'
            f'<section class="sec" id="vyber">{sec_h("Doporučujeme", "Nejlepší věci, které si dnes nekoupíš.", "/slevy/", "Slevy")}{S.grid(picks[:12], first_eager=4)}</section>{rows}</div>')
    ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": "KoupímNic", "url": BASE + "/",
           "potentialAction": {"@type": "SearchAction", "target": BASE + "/hledat/?q={q}", "query-input": "required name=q"}},
          {"@context": "https://schema.org", "@type": "Organization", "name": "KoupímNic", "url": BASE + "/", "logo": BASE + "/favicon-512.png",
           "slogan": "Dopaminové nakupování nanečisto", "description": HOME_DESC.format(n=n_fmt)}]
    return S.layout("/", "KoupímNic – dopaminové nakupování nanečisto", HOME_DESC.format(n=n_fmt), body, jsonld=ld, cls="home")


def about_page(S, present):
    shops = ", ".join(S.shop(s)["name"] for s in present[:20])
    body = band("Jak to funguje", "Dopaminové nakupování: nakupuješ jako obvykle, jen na konci nezaplatíš a nic nepřijde.") + f"""<div class="wrap prose">
<h2>Proč nákup nanečisto</h2><p>Část radosti z nakupování přichází dřív, než věc vůbec držíš v ruce: při vybírání, vkládání do košíku a čekání na kurýra.
KoupímNic ti nechá právě tuhle část. Produkty jsou skutečné, ceny taky, jen se nikde neplatí.</p>
<p>Proč to funguje a kde jsou hranice, rozebíráme na stránce <a href="/dopaminove-nakupovani/">Dopaminové nakupování</a>.</p>
<h2>Co se děje s tvými daty</h2><p>Nic. Košík, objednávky i počítadlo úspor jsou uložené jen v tvém prohlížeči (localStorage). Nemáme účty, nechceme e-mail, adresu ani kartu.
Když vymažeš data prohlížeče, zmizí i tvoje historie nákupů nanečisto.</p>
<h2>Odkud jsou produkty</h2><p>Z partnerských e-shopů: {E(shops)} a dalších. Ceny se aktualizují každý den a mezitím se můžou změnit. Obrázky a popisy jsou od obchodů.</p>
<h2>Jak na tom vyděláváme</h2><p>U každého produktu je nenápadný odkaz „Koupit doopravdy“. Vede do e-shopu a je reklamní (affiliate): když tam nakoupíš,
můžeme dostat provizi. Tebe to nestojí nic navíc. Do skutečného nákupu tě nikdy nebudeme tlačit.</p>
<h2>Karanténa přání</h2><p>Když tě nějaká věc nepustí, dej ji na 72 hodin do karantény. Pokud ji po třech dnech pořád chceš, je to nejspíš skutečná potřeba, ne chvilkový impulz.</p>
<h2>Kolik jsem „ušetřil“?</h2><p>Počítadlo sčítá ceny věcí, které sis koupil nanečisto. Je to hra, ne účetnictví: peníze jsi neušetřil, jen jsi je neutratil. I tak je to dobrý pocit.</p>
<h2>Když nakupování přestává být zábava</h2><p>Pokud máš pocit, že nakupování nemáš pod kontrolou, nejsi v tom sám. Poradit se dá anonymně a zdarma, třeba v
<a href="https://www.mpsv.cz/web/cz/dluhove-poradenstvi" rel="noopener">dluhových poradnách</a> nebo u svého lékaře.</p></div>"""
    return S.layout("/jak-to-funguje/", "Jak funguje nákup nanečisto" + SUFFIX, "Co je KoupímNic, proč nákup nanečisto, co se děje s daty a jak web vydělává.",
                    body, crumbs=[HOME, ("Jak to funguje", "/jak-to-funguje/")])


DOPA_FAQ = [
    ("Je KoupímNic skutečný e-shop?", "Není. Produkty, fotky a ceny jsou skutečné a přebíráme je z českých e-shopů, ale u nás se nic neprodává, "
     "nic se neplatí a nic se nedoručí. Košík, pokladna i kurýr jsou hra."),
    ("Zaplatím na konci opravdu nic?", "Opravdu. Pokladna se neptá na kartu ani na účet a žádnou platební bránu nemáme. "
     "Jak vypadá konec nákupu, uvidíš, až klikneš na Zaplatit."),
    ("Proč mě baví nakupovat, i když nic nepřijde?", "Velká část radosti z nákupu přichází při vybírání a čekání, ne až když věc držíš v ruce. "
     "Tuhle část si tu můžeš užít celou."),
    ("Co když něco chci doopravdy?", "U produktu je odkaz do obchodu, označený jako reklama. Doporučujeme ale nejdřív karanténu přání: "
     "dej věc na 72 hodin stranou a pak se rozhodni."),
    ("Pomůže to při závislosti na nakupování?", "KoupímNic je hra, ne léčba. Když nakupování nemáš pod kontrolou nebo kvůli němu máš dluhy, "
     "obrať se na odborníka: praktického lékaře, psychologa, adiktologa nebo dluhovou poradnu."),
]


def dopamine_page(S):
    n = S.stats.get("products_fmt", "")
    faq = "".join(f"<h3>{E(q)}</h3><p>{E(a)}</p>" for q, a in DOPA_FAQ)
    body = band("Dopaminové nakupování", "Vybírání, košík, pokladna a kurýr se vším všudy. Jen bez placení a bez balíku.") + f"""<div class="wrap prose">
<h2>Co je dopaminové nakupování</h2><p>Nakupování, ze kterého si necháš jen tu příjemnou část. Prohlížíš skutečné produkty za skutečné ceny,
vkládáš je do košíku, projdeš pokladnou a sleduješ kurýra. Na KoupímNic je {E(n)} produktů z českých e-shopů, takže vybírat se dá dlouho.
Rozdíl je jediný: z účtu nic neodejde a domů nic nepřijde.</p>
<h2>Smyčka v pěti krocích</h2><ol>
<li><b>Vybírání.</b> Filtry, značky, slevy. Mozek si začne představovat, jak ti ta věc bude slušet.</li>
<li><b>Košík.</b> Hodnota roste. Tady je očekávání nejsilnější.</li>
<li><b>Pokladna.</b> Doprava, platba, shrnutí. Pocit „už to skoro mám“.</li>
<li><b>Čekání na kurýra.</b> Sledování zásilky je samo o sobě malá zábava.</li>
<li><b>Rozbalení.</b> Krabice je prázdná. Účtenka ukáže, kolik jsi neutratil a co by se za to dalo mít.</li></ol>
<h2>Co o tom říká věda (stručně a opatrně)</h2><p>Dopamin není „hormon štěstí“. Souvisí hlavně s očekáváním odměny a s chutí ji získat.
Proto bývá nejsilnější chvíle před koupí, ne po ní. KoupímNic na tom staví: dává ti očekávání bez výdaje.
Nejsme lékaři a nic neléčíme. Je to hra, která může ukojit chvilkovou chuť nakupovat.</p>
<h2>Kdy to hra není: závislost na nakupování</h2><p>Když nakupování nejde zastavit, kupuješ věci, které nepotřebuješ, a máš kvůli tomu dluhy nebo výčitky,
nepomůže prázdná krabice, ale odborník. Začít se dá u praktického lékaře, psychologa nebo adiktologa.
S dluhy pomohou <a href="https://www.mpsv.cz/web/cz/dluhove-poradenstvi" rel="noopener">bezplatné dluhové poradny</a>.</p>
<h2>Časté otázky</h2>{faq}
<p><a class="btn" href="/">Jít nakupovat nanečisto</a></p></div>"""
    ld = [{"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in DOPA_FAQ]}]
    return S.layout("/dopaminove-nakupovani/", "Dopaminové nakupování nanečisto" + SUFFIX,
                    "Dopaminové nakupování: vybírání, košík, pokladna i kurýr jako doopravdy, jen bez placení. Proč to baví a kdy to už hra není.",
                    body, jsonld=ld, crumbs=[HOME, ("Dopaminové nakupování", "/dopaminove-nakupovani/")])


def contact_page(S):
    o = R.OPERATOR
    body = band("Kontakt", "Napiš nám, i kdyby ses chtěl jen pochlubit, kolik jsi neutratil.") + f"""<div class="wrap prose">
<p>E-mail: <a href="mailto:{o["email"]}">{o["email"]}</a></p>
<p>Provozovatel: {o["name"]}, {o["address"]}, IČO {o["ico"]}, {o["vat"]}.</p>
<p>Objednávky tu nevyřizujeme, protože žádné nejsou. Reklamace skutečných nákupů řeš prosím s obchodem, kde jsi nakupoval.</p></div>"""
    return S.layout("/kontakt/", "Kontakt" + SUFFIX, "Kontakt na provozovatele KoupímNic: e-mail, IČO a adresa. Objednávky nevyřizujeme, protože žádné nejsou.", body, crumbs=[HOME, ("Kontakt", "/kontakt/")])


def privacy_page(S):
    o = R.OPERATOR
    body = band("Soukromí a cookies", "Krátce: nic o tobě nevíme a nechceme vědět.") + f"""<div class="wrap prose">
<h2>Data v prohlížeči</h2><p>Košík, objednávky nanečisto, karanténa přání a počítadlo úspor se ukládají jen do localStorage tvého prohlížeče. Na náš server se nic neposílá.</p>
<h2>Měření návštěvnosti</h2><p>Google Analytics spouštíme jen po tvém souhlasu v liště. Bez souhlasu se nic neměří. Souhlas změníš smazáním dat webu v prohlížeči.</p>
<h2>Odkazy do obchodů</h2><p>Když klikneš na „Koupit doopravdy“, přejdeš na web obchodu přes affiliate síť (například CJ). Ta si uloží cookie, aby obchod věděl, odkud jsi přišel.
Za to, co se děje na webu obchodu, odpovídá obchod.</p>
<h2>Správce</h2><p>{o["name"]}, IČO {o["ico"]}, {o["address"]}, <a href="mailto:{o["email"]}">{o["email"]}</a>.</p></div>"""
    return S.layout("/ochrana-osobnich-udaju/", "Soukromí a cookies" + SUFFIX, "Jak KoupímNic zachází s daty: nijak, všechno zůstává v tvém prohlížeči.",
                    body, crumbs=[HOME, ("Soukromí", "/ochrana-osobnich-udaju/")])


if __name__ == "__main__":
    main()
