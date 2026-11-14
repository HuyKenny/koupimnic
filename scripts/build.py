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
    """Listing data for client-side sort/filter (first JSON_ITEMS by default order)."""
    items = items[:JSON_ITEMS]
    brands = [b for b, _ in Counter(p["brand"] for p in items if p["brand"]).most_common(80)]
    bidx = {b: i for i, b in enumerate(brands)}
    rows = []
    for p in items:
        d = S.item_data(p)
        rows.append([d["id"], d["n"], bidx.get(p["brand"], -1), d["p"], d["w"], d["i"], d["s"], d["g"]])
    out.write(f"data/l/{key}.json", json.dumps({"b": brands, "i": rows}, ensure_ascii=False, separators=(",", ":")))
    return f"/data/l/{key}.json"


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

    go_tpl, _ = GL.local_go(products)
    shop_meta = {s["id"]: {"name": s["name"], "color": s.get("color", "#888"), "domain": s["domain"]} for s in shops}
    present = sorted({o["shop"] for p in products for o in p["offers"]})
    stats = {"products": len(products), "shops": len(present), "updated": TODAY_CZ}

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
    S.ctx = {"by_cat": by_cat, "brands": brand_pages, "brand_name": brand_name}

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
    out.page("/kosik/", flow_page(S, "/kosik/", "Košík", "cart"), None, index=False)
    out.page("/pokladna/", flow_page(S, "/pokladna/", "Pokladna", "checkout"), None, index=False)
    out.page("/objednavka/", flow_page(S, "/objednavka/", "Tvoje objednávka", "order"), None, index=False)
    out.page("/moje-uspory/", flow_page(S, "/moje-uspory/", "Moje úspory", "savings"), None, index=False)
    out.page("/hledat/", flow_page(S, "/hledat/", "Hledat", "search"), None, index=False)
    out.page("/jak-to-funguje/", about_page(S, present), "pages")
    out.page("/kontakt/", contact_page(S), "pages")
    out.page("/ochrana-osobnich-udaju/", privacy_page(S), "pages")
    out.page("/", home_page(S, products, by_cat, by_dept), "pages")
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

def band(title, lead, icon=None, extra=""):
    ic = f'<img class="band__ic" src="/img/ic/{icon}.webp" alt="" width="72" height="72">' if icon else ""
    return f'<section class="band"><div class="wrap band__in">{ic}<div class="band__txt"><h1>{title}</h1><p class="lead">{lead}</p>{extra}</div></div></section>'


def listing(S, items, jsn, page, pages, path):
    """Server-rendered page of products + the toolbar that app.js wires to the listing JSON (sort, brand, price)."""
    chunk = items[(page - 1) * R.PER_PAGE: page * R.PER_PAGE]
    brands = [b for b, n in Counter(p["brand"] for p in items[:JSON_ITEMS] if p["brand"]).most_common(14) if n >= 2]
    bopts = "".join(f'<option value="{E(b)}">{E(b)}</option>' for b in brands)
    n = len(items)
    tools = (f'<div class="tools" data-list="{jsn}"><p class="tools__n"><b>{nb(n)}</b> {plural(n, "kousek", "kousky", "kousků")}</p>'
             '<label class="sel"><span class="sr">Řadit</span><select data-sort><option value="">Doporučené</option><option value="p">Nejlevnější</option>'
             '<option value="-p">Nejdražší</option><option value="d">Největší sleva</option></select></label>'
             + (f'<label class="sel"><span class="sr">Značka</span><select data-brand><option value="">Všechny značky</option>{bopts}</select></label>' if len(brands) > 1 else "")
             + '<label class="sel"><span class="sr">Cena</span><select data-price><option value="">Jakákoli cena</option><option value="0-1000">do 1 000 Kč</option>'
             '<option value="1000-5000">1 000–5 000 Kč</option><option value="5000-20000">5 000–20 000 Kč</option><option value="20000-">nad 20 000 Kč</option></select></label></div>')
    return tools + f'<div data-grid>{S.grid(chunk, first_eager=4 if page == 1 else 0)}</div>' + R.pager_html(path, page, pages)


def dept_page(S, d, items, jsn, page, pages):
    name, blurb, ic = X.DEPTS[d]
    lo, med, hi = price_range(items)
    cats = [(f"/{k}/", X.CATS[k][0], len(S.ctx["by_cat"][k]), X.CATS[k][3]) for k in X.CATS if X.CATS[k][1] == d and k in S.cat_ok]
    lead = f"{blurb}. {nb(len(items))} skutečných produktů z českých e-shopů, od {kc(lo)} do {kc(hi)}. Do košíku cokoli, zaplatíš 0 Kč."
    body = band(E(name), lead, ic) + f'<div class="wrap">{S.tiles(cats) if page == 1 else ""}{listing(S, items, jsn, page, pages, f"/{d}/")}</div>'
    return S.layout(f"/{d}/", f"{name} nanečisto – nakup si radost za 0 Kč" + SUFFIX,
                    f"{name}: {blurb.lower()}. Vyber si, dej do košíku a zaplať 0 Kč. Skutečné produkty a ceny z českých e-shopů.",
                    body, crumbs=[HOME, (name, f"/{d}/")])


CAT_LEAD = {
    "mobilni-telefony": "Nový telefon je nejrychlejší dopamin, jaký se dá koupit. Tady ho koupíš za nula korun a ten starý ti dál slouží.",
    "notebooky": "MacBook, herní stroj nebo tenký ultrabook. Vybírej specifikace, jako bys to myslel vážně.",
    "herni-konzole": "PS5, Xbox, Switch. Konzole přijede v krabici, ve které nic nebude, a ušetříš i za hry.",
    "tenisky": "Limitky, klasiky i běžecké boty. Velikost klidně o číslo větší, stejně nic nepřijde.",
    "damske-parfemy": "Vůně se přes obrazovku nepřenese. Proto je tohle nejbezpečnější místo, kde si ji koupit.",
    "kabelky": "Kabelka, kterou nikdy nebudeš hledat ve skříni. Protože ve skříni nebude.",
    "hodinky": "Čas na nákup? Vždycky. Čas na placení? Nikdy.",
    "chytre-hodinky": "Spočítají ti kroky, tep i spánek. Tyhle navíc spočítají, kolik jsi ušetřil.",
    "sluchatka": "Potlačení hluku funguje skvěle. Hlavně toho, který dělá tvůj účet.",
}


def cat_page(S, k, items, jsn, page, pages):
    name, d, h1, ic = X.CATS[k][0], X.CATS[k][1], X.CATS[k][2], X.CATS[k][3]
    lo, med, hi = price_range(items)
    n = len(items)
    shops = len({o["shop"] for p in items for o in p["offers"]})
    top = [b for b, _ in Counter(p["brand"] for p in items[:400] if p["brand"]).most_common(3)]
    lead = ((CAT_LEAD[k] + " ") if k in CAT_LEAD else "") + (
        f"{nb(n)} {plural(n, 'kousek', 'kousky', 'kousků')} z {shops} {plural(shops, 'obchodu', 'obchodů', 'obchodů')}, od {kc(lo)} do {kc(hi)}"
        + (f", nejčastěji {', '.join(E(b) for b in top)}" if top else "") + ".")
    sibs = [(f"/{c}/", X.CATS[c][0]) for c in X.CATS if X.CATS[c][1] == d and c != k and c in S.cat_ok]
    chips = '<nav class="chips" aria-label="Související">' + "".join(f'<a href="{h}">{E(nm)}</a>' for h, nm in sibs) + "</nav>" if sibs else ""
    body = band(E(h1), lead, ic, chips) + f'<div class="wrap">{listing(S, items, jsn, page, pages, f"/{k}/")}</div>'
    title = f"{h1} – kup si nanečisto, od {kc(lo)}" + SUFFIX
    if len(title) > 70:
        title = f"{h1} nanečisto za 0 Kč" + SUFFIX
    return S.layout(f"/{k}/", title, f"{h1}: {n} skutečných kousků z českých e-shopů. Dej do košíku, zaplať 0 Kč a ušetři. Kdo chce doopravdy, koupí přímo u obchodu.",
                    body, crumbs=[HOME, (X.DEPTS[d][0], f"/{d}/"), (name, f"/{k}/")], noindex=k not in S.cat_ok)


def brand_page(S, b, items, jsn, page, pages):
    name = S.ctx["brand_name"][b]
    lo, _, hi = price_range(items)
    cats = Counter(p["cat"] for p in items)
    chips = '<nav class="chips">' + "".join(f'<a href="/{c}/">{E(X.CATS[c][0])}</a>' for c, _ in cats.most_common(8) if c in S.cat_ok) + "</nav>"
    lead = f"{nb(len(items))} {plural(len(items), 'produkt', 'produkty', 'produktů')} značky {E(name)} od {kc(lo)} do {kc(hi)}. Kup si cokoli z nich za 0 Kč."
    body = band(f"{E(name)} nanečisto", lead, None, chips) + f'<div class="wrap">{listing(S, items, jsn, page, pages, f"/znacky/{b}/")}</div>'
    return S.layout(f"/znacky/{b}/", f"{name} – nakup si nanečisto za 0 Kč" + SUFFIX,
                    f"{name}: {len(items)} skutečných produktů z českých e-shopů. Vyber, dej do košíku, zaplať 0 Kč.",
                    body, crumbs=[HOME, ("Značky", "/znacky/"), (name, f"/znacky/{b}/")], noindex=len(items) < 12)


def brands_index(S, brand_pages, brand_name):
    rows = sorted(brand_pages.items(), key=lambda x: X.fold(brand_name[x[0]]))
    groups = defaultdict(list)
    for b, ps in rows:
        ch = X.fold(brand_name[b])[:1].upper()
        groups[ch if ch.isalpha() else "#"].append(f'<li><a href="/znacky/{b}/">{E(brand_name[b])}</a> <small>{len(ps)}</small></li>')
    top = sorted(brand_pages, key=lambda b: (-(X.top_brand(brand_name[b])), -len(brand_pages[b])))[:24]
    body = (band("Značky", f"{len(brand_pages)} značek od Apple po Zaru. Vyber si tu, kterou sis vždycky chtěl koupit, a kup ji za nic.")
            + '<div class="wrap"><div class="brandtop">' + "".join(f'<a href="/znacky/{b}/">{E(brand_name[b])}</a>' for b in top) + "</div>"
            + '<div class="az">' + "".join(f'<section><h2>{ch}</h2><ul>{"".join(v)}</ul></section>' for ch, v in sorted(groups.items())) + "</div></div>")
    return S.layout("/znacky/", "Značky – Apple, Nike, Dior a další nanečisto" + SUFFIX, "Všechny značky v galerii KoupímNic: elektronika, móda, boty, parfémy.",
                    body, crumbs=[HOME, ("Značky", "/znacky/")])


def shop_page(S, s, items, jsn, page, pages):
    lead = (f"{nb(len(items))} produktů z e-shopu {E(s['name'])} ({E(s['domain'])}). U nás je koupíš nanečisto za 0 Kč. "
            f"Kdo chce doopravdy, najde u každého produktu odkaz do obchodu.")
    path = f"/obchody/{s['id']}/"
    body = band(E(s["name"]), lead) + f'<div class="wrap">{listing(S, items, jsn, page, pages, path)}</div>'
    return S.layout(path, f"{s['name']} – produkty nanečisto" + SUFFIX, f"Produkty z obchodu {s['name']} v galerii KoupímNic.",
                    body, crumbs=[HOME, ("Obchody", "/obchody/"), (s["name"], path)], noindex=len(items) < 12)


def shops_index(S, shops, by_shop):
    rows = "".join(f'<li><a href="/obchody/{s["id"]}/"><span class="dot" style="background:{s.get("color", "#888")}"></span>{E(s["name"])}</a>'
                   f'<small>{nb(len(by_shop[s["id"]]))} produktů</small></li>' for s in sorted(shops, key=lambda s: -len(by_shop.get(s["id"], []))) if by_shop.get(s["id"]))
    body = band("Obchody", "Odkud bereme produkty a ceny. Všechno jsou skutečné e-shopy. My jen ukazujeme, oni prodávají.") + f'<div class="wrap"><ul class="shoplist">{rows}</ul></div>'
    return S.layout("/obchody/", "Obchody, ze kterých bereme produkty" + SUFFIX, "Seznam e-shopů, jejichž produkty a ceny ukazujeme.", body, crumbs=[HOME, ("Obchody", "/obchody/")])


def sale_page(S, items, jsn, page, pages):
    body = band("Slevy, které ti nic nevezmou", f"{nb(len(items))} produktů se slevou aspoň 20 %. Sleva je skutečná, nákup nanečisto. Ušetříš celou cenu, ne jen slevu.") + \
        f'<div class="wrap">{listing(S, items, jsn, page, pages, "/slevy/")}</div>'
    return S.layout("/slevy/", "Slevy – kup si zlevněné zboží za 0 Kč" + SUFFIX, "Zlevněné produkty z českých e-shopů. U nás je koupíš nanečisto a ušetříš všechno.",
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
    gal = (f'<div class="gal"><div class="gal__main"><img id="gmain" src="{E(main)}" alt="{E(p["name"])}" referrerpolicy="no-referrer" width="720" height="720" '
           f'fetchpriority="high" data-orig="{E(imgs[0] if imgs else "")}">{off}</div><div class="thumbs">{thumbs}</div></div>')
    data = E(json.dumps(S.item_data(p), ensure_ascii=False, separators=(",", ":")))
    sizes = ""
    if p["sizes"] and p["sizes"] != ["univerzální"]:
        sizes = ('<fieldset class="sizes"><legend>Velikost <small>na velikosti nezáleží, nic nepřijde</small></legend><div>'
                 + "".join(f'<label><input type="radio" name="size" value="{E(s)}"{" checked" if i == 0 else ""}><span>{E(s)}</span></label>' for i, s in enumerate(p["sizes"][:24]))
                 + "</div></fieldset>")
    was = f'<s>{kc(p["was"])}</s><span class="off">−{disc}&nbsp;%</span>' if disc >= 5 else ""
    others = ""
    if len(p["offers"]) > 1:
        others = '<details class="others"><summary>Stejný produkt v dalších obchodech</summary><ul>' + "".join(
            f'<li><span>{E(S.shop(o["shop"])["name"])}</span><b>{kc(o["price"])}</b></li>' for o in p["offers"][1:6]) + "</ul></details>"
    buy = (f'<div class="buy" data-item="{data}"><div class="buy__price"><b>{kc(p["price"])}</b>{was}</div>'
           f'<p class="buy__real">Skutečná cena v obchodě {E(shop["name"])} ({TODAY_CZ}). U nás platíš <b>0&nbsp;Kč</b>.</p>{sizes}'
           f'<div class="buy__cta"><button class="btn btn--lg" type="button" data-buy="cart">{R.icon("bag", 20)}Přidat do košíku</button>'
           f'<button class="btn btn--lg btn--lime" type="button" data-buy="now">Koupit hned za 0&nbsp;Kč</button></div>'
           f'<ul class="perks"><li>{R.icon("truck", 18)}Doprava zdarma. Nikam.</li><li>{R.icon("undo", 18)}Vrácení do 0 dnů, není co vracet</li>'
           f'<li>{R.icon("lock", 18)}Žádná karta, žádné údaje, žádný účet</li></ul>{others}'
           f'<p class="real">Chceš to doopravdy? <a href="{E(o0["go"])}" rel="sponsored nofollow noopener" target="_blank" data-go="{E(o0["shop"])}">Koupit u {E(shop["name"])}</a> '
           f'<span class="tag-ad">Reklama</span></p></div>')
    meta = []
    bslug = X.slugify(p["brand"])
    if p["brand"] and bslug in S.ctx["brands"]:
        meta.append(f'<a href="/znacky/{bslug}/">{E(p["brand"])}</a>')
    elif p["brand"]:
        meta.append(f"<span>{E(p['brand'])}</span>")
    meta.append(f'<a href="/{k}/">{E(X.CATS[k][0])}</a>')
    spec = [("Značka", E(p["brand"]) or "neuvedena"), ("Kategorie", f'<a href="/{k}/">{E(X.CATS[k][0])}</a>'), ("Obchod", E(shop["name"]))]
    if p["color"]:
        spec.append(("Barva", E(p["color"])))
    if p["sizes"]:
        spec.append(("Velikosti", E(", ".join(p["sizes"][:24]))))
    if p["ean"]:
        spec.append(("EAN", p["ean"]))
    spec_html = "".join(f"<tr><th>{a}</th><td>{b}</td></tr>" for a, b in spec)
    desc = (f'<h2>Popis od obchodu</h2><div class="desc clamp" id="desc">{E(p["desc"])}</div><button class="more" type="button" data-more="desc">Celý popis</button>'
            if len(p["desc"]) > 40 else "")
    sim = [q for q in S.ctx["by_cat"].get(k, []) if q is not p][:400]
    sim = sorted(sim, key=lambda q: (abs(q["price"] - p["price"]) / max(p["price"], 1) - (0.3 if q["brand"] == p["brand"] else 0), q["id"]))[:8]
    sim_html = f'<section class="sec"><div class="sec__h"><h2>Mohlo by se ti líbit (a nic stát)</h2><a href="/{k}/">Celá kategorie</a></div>{S.grid(sim)}</section>' if sim else ""
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
    tail = f" za 0 Kč místo {kc(p['price'])}"
    uniq = (f" ({p['color']})" if p["color"] and len(p["color"]) <= 18 else f" ({p['slug'][-6:]})") if p.get("dup") else ""
    nm = R.shorten_mid(p["name"], max(24, 74 - len(tail) - len(uniq) - len(SUFFIX)))
    title = nm + uniq + tail + SUFFIX
    desc_meta = f"{R.shorten(p['name'], 70)}: v obchodě {shop['name']} stojí {kc(p['price'])}, u nás nanečisto za 0 Kč. Přidej do košíku a ušetři celou cenu."
    return S.layout(f"/produkt/{p['slug']}/", title, desc_meta, body, jsonld=[ld], noindex=not p["index"], og_img=imgs[0] if imgs else None,
                    preload_img=main if imgs else None,
                    crumbs=[HOME, (X.DEPTS[d][0], f"/{d}/"), (X.CATS[k][0], f"/{k}/"), (R.shorten(p["name"], 50), f"/produkt/{p['slug']}/")])


def gone_page(S, g):
    k = g["cat"] if g["cat"] in X.CATS else "mobilni-telefony"
    sim = sorted(S.ctx["by_cat"].get(k, []), key=lambda q: abs(q["price"] - g["price"]))[:8]
    img = R.img_url(g["img"], "main") or "/img/ui/placeholder.svg"
    body = (f'<div class="wrap"><div class="prod"><div class="gal"><div class="gal__main"><img src="{E(img)}" alt="{E(g["name"])}" width="720" height="720"></div></div>'
            f'<div class="prod__info"><h1>{E(g["name"])}</h1><div class="gone"><b>Vyprodáno.</b> Obchod tenhle kousek už nenabízí, takže ho teď nekoupíš ani nanečisto. '
            f'Naposledy stál {kc(g["price"])}.</div><p><a class="btn" href="/{k}/">{E(X.CATS[k][0])}</a></p></div></div>'
            f'<section class="sec"><h2>Podobné, které ještě jdou nekoupit</h2>{S.grid(sim)}</section></div>')
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
    return S.layout(path, title + SUFFIX, "Nákup nanečisto na KoupímNic.", f'<div class="wrap flow">{shells[kind]}</div>', noindex=True, cls="is-" + kind)


def home_page(S, products, by_cat, by_dept):
    want = [("mobilni-telefony", r"iphone 1[67]"), ("notebooky", r"macbook"), ("herni-konzole", r"playstation 5|ps5|switch 2"), ("sluchatka", r"airpods|wh-1000"),
            ("chytre-hodinky", r"apple watch|galaxy watch"), ("tenisky", r"nike|adidas|new balance"), ("vysavace", r"dyson"), ("damske-parfemy", r"dior|chanel|lanc"),
            ("kabelky", r"michael kors|guess|coach|furla"), ("drony", r"dji"), ("hodinky", r"tissot|casio|seiko|guess"), ("kavovary", r"delonghi|de.longhi|nespresso")]
    picks, used = [], set()
    for k, rx in want:
        for p in by_cat.get(k, []):
            if p["id"] not in used and re.search(rx, X.fold(p["name"] + " " + p["brand"])):
                picks.append(p)
                used.add(p["id"])
                break
    picks += [p for p in products if p["id"] not in used and X.top_brand(p["brand"])][:max(0, 12 - len(picks))]
    depts = [(f"/{d}/", X.DEPTS[d][0], len(by_dept[d]), X.DEPTS[d][2]) for d in X.DEPTS if d in S.dept_ok]
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
        rows += f'<section class="sec"><div class="sec__h"><h2>{E(X.DEPTS[d][0])}</h2><a href="/{d}/">Celé oddělení</a></div>{S.grid(pick)}</section>'
    hero = ('<section class="hero"><div class="wrap hero__in"><div class="hero__txt"><p class="eyebrow">Nákupní galerie nanečisto</p>'
            '<h1>Nakup si radost.<br><span>Zaplať nic.</span></h1>'
            f'<p class="lead">{nb(len(products))} skutečných produktů z českých e-shopů: iPhony, tenisky, parfémy, konzole. Dej do košíku, zaplať 0 Kč, sleduj kurýra '
            'a rozbal krabici. Je prázdná. Peníze zůstaly na účtu.</p>'
            '<p class="hero__cta"><a class="btn btn--lg" href="#vyber">Jdu nakupovat</a><a class="btn btn--lg btn--ghost" href="/jak-to-funguje/">Jak to funguje</a></p>'
            '<p class="hero__saved" data-saved-hero hidden></p></div>'
            '<div class="hero__art"><img src="/img/ui/hero.webp" alt="" width="560" height="480" fetchpriority="high"></div></div></section>')
    steps = ('<section class="steps wrap" aria-label="Jak to funguje"><ol>'
             '<li><b>Vyber</b><span>Skutečné produkty, skutečné ceny. Klidně ten nejdražší.</span></li>'
             '<li><b>Zaplať 0 Kč</b><span>Žádná karta, žádný účet, žádné údaje. Jen tlačítko.</span></li>'
             '<li><b>Sleduj zásilku</b><span>Balíme, vezeme, zvoníme. Kurýr je smyšlený, napětí skutečné.</span></li>'
             '<li><b>Rozbal nic</b><span>Na účtence uvidíš, kolik jsi právě neutratil.</span></li></ol></section>')
    body = (hero + steps + f'<div class="wrap"><section class="sec" id="vyber"><div class="sec__h"><h2>Největší lákadla</h2><a href="/slevy/">Slevy</a></div>'
            f'{S.grid(picks[:12], first_eager=4)}</section><section class="sec"><h2>Oddělení</h2>{S.tiles(depts)}</section>{rows}'
            '<section class="honest"><h2>Proč to funguje</h2><p>Radost z nákupu přichází hlavně při vybírání a čekání, ne až s krabicí doma. '
            'KoupímNic ti dá to vybírání, košík, potvrzení i zvonek kurýra, jen bez placení. Když tě věc za tři dny pořád láká, nejspíš ji opravdu chceš. '
            'Pak ji koupíš v obchodě. Když ne, ušetřil jsi.</p><p class="muted">Nic tu neprodáváme. Odkazy do obchodů jsou označené jako reklama.</p></section></div>')
    ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": "KoupímNic", "url": BASE + "/",
           "potentialAction": {"@type": "SearchAction", "target": BASE + "/hledat/?q={q}", "query-input": "required name=q"}},
          {"@context": "https://schema.org", "@type": "Organization", "name": "KoupímNic", "url": BASE + "/", "logo": BASE + "/favicon-512.png"}]
    return S.layout("/", "KoupímNic – nakup si radost, zaplať nic", "Nákupní galerie nanečisto: skutečné iPhony, tenisky a parfémy z českých e-shopů. "
                    "Dej do košíku, zaplať 0 Kč a ušetři. Dopamin bez výpisu z účtu.", body, jsonld=ld, cls="home")


def about_page(S, present):
    shops = ", ".join(S.shop(s)["name"] for s in present[:20])
    body = band("Jak to funguje", "Nakupuješ jako obvykle, jen na konci nezaplatíš a nic nepřijde.") + f"""<div class="wrap prose">
<h2>Proč nákup nanečisto</h2><p>Část radosti z nakupování přichází dřív, než věc vůbec držíš v ruce: při vybírání, vkládání do košíku a čekání na kurýra.
KoupímNic ti nechá právě tuhle část. Produkty jsou skutečné, ceny taky, jen se nikde neplatí.</p>
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
