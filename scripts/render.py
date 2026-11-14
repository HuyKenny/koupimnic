"""HTML pieces for koupimnic.cz: layout, cards, grids, small helpers. Plain f-strings, no template engine."""
import html
import json
import re
from urllib.parse import quote

import taxonomy as X

E = html.escape
SUFFIX = " | KoupímNic"
PER_PAGE = 48
OPERATOR = {"name": "Ha Duy Huy", "address": "Bartáková 36, 140 00 Praha", "ico": "07876823", "vat": "není plátce DPH",
            "email": "info@koupimnic.cz"}   # public business-register data (ARES), the site operator on legal pages
NAV = list(X.DEPTS)
SHORT = {"boty": "Boty", "doplnky": "Doplňky", "krasa": "Parfémy", "drogerie": "Drogerie", "domov": "Domov", "hracky": "Hračky a LEGO", "sport": "Sport"}


def kc(n):
    return f"{int(round(n)):,}".replace(",", " ") + " Kč"


def plural(n, one, few, many):
    return one if n == 1 else few if 1 < n < 5 else many


def shorten(text, limit):
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:-–—(") + "…"


def shorten_mid(text, limit):
    """Product names say what it is first and which variant last: cut the middle, keep both ends."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    words = text.split(" ")
    head, tail = [], []
    while words:
        w = words.pop(0)
        if len(" ".join(head + [w])) + 2 + len(" ".join(tail)) > limit:
            break
        head.append(w)
        if words:
            t = words.pop()
            if len(" ".join(head)) + 2 + len(" ".join([t] + tail)) > limit:
                break
            tail.insert(0, t)
    return (" ".join(head) + " … " + " ".join(tail)).strip()


# image hosts that refuse server-side fetches (wsrv.nl gets 403): hotlink the original from the visitor's browser
NO_PROXY = ("sportisimo", "answear", "notino", "allegroimg")


FILL_DEPTS = {"boty", "doplnky"}


def photo_bg(url, cat=None):
    """Answear shoots on a beige-grey studio wall whose shade differs photo to photo, so a fixed box colour still shows a
    rectangle. Product shots (shoes, bags, watches) fill the square instead (is-fill, the 2:3 photo loses only wall);
    model shots keep the whole photo on the average wall colour (is-gray)."""
    if "ans-media.com" not in (url or ""):
        return ""
    return " is-gray is-fill" if cat and X.CATS.get(cat, ("", ""))[1] in FILL_DEPTS else " is-gray"


def img_url(u, size="card"):
    """Smaller renditions via wsrv.nl (free image CDN, no CPU on our side); hosts that block it get the original.
    app.js (fixImg) falls back to the original when wsrv cannot deliver one."""
    if not u:
        return u
    if "cdn.myshoptet.com" in u and "/user/shop/orig/" in u:
        return u.replace("/user/shop/orig/", "/user/shop/detail/" if size == "card" else "/user/shop/big/")
    if any(h in u for h in NO_PROXY) or "wsrv.nl" in u or not u.startswith("https://"):
        return u
    return f"https://wsrv.nl/?url={quote(u, safe='')}&w={480 if size == 'card' else 1000}&we&output=webp&q=80"


def discount(p):
    return round(100 * (p["was"] - p["price"]) / p["was"]) if p.get("was") and p["was"] > p["price"] else 0


def icon(name, size=24):
    return f'<svg class="i" width="{size}" height="{size}" aria-hidden="true"><use href="/img/ui/icons.svg#{name}"/></svg>'


def pager_html(path, cur, pages):
    if pages <= 1:
        return ""
    url = lambda k: path if k == 1 else f"{path}strana-{k}/"
    show = sorted({1, pages, cur - 1, cur, cur + 1} & set(range(1, pages + 1)))
    out, last = [], 0
    for k in show:
        if k - last > 1:
            out.append('<span class="pg__gap">…</span>')
        out.append(f'<a href="{url(k)}"{" aria-current=page" if k == cur else ""}>{k}</a>')
        last = k
    prev = f'<a class="pg__nav" rel="prev" href="{url(cur - 1)}">← Předchozí</a>' if cur > 1 else ""
    nxt = f'<a class="pg__nav" rel="next" href="{url(cur + 1)}">Další →</a>' if cur < pages else ""
    return f'<nav class="pg" aria-label="Stránky">{prev}{"".join(out)}{nxt}</nav>'


class Site:
    def __init__(self, base, env, ga4, css, js, shops, stats):
        self.base, self.env, self.ga4, self.css, self.js = base, env, ga4, css, js
        self.shops, self.stats = shops, stats
        self.pg = None
        self.dept_ok, self.cat_ok = set(NAV), set(X.CATS)

    def url(self, path):
        return self.base + path

    def shop(self, sid):
        return self.shops.get(sid) or {"name": sid, "color": "#888"}

    # ------------------------------------------------------------ layout
    def layout(self, path, title, desc, body, crumbs=None, jsonld=None, noindex=False, og_img=None, preload_img=None, cls=""):
        robots = '<meta name="robots" content="noindex,follow">' if (noindex or self.env != "production" or (self.pg and self.pg[1] > 1)) else ""
        canon = path if not (self.pg and self.pg[1] > 1) else f"{self.pg[0]}strana-{self.pg[1]}/"
        ld = list(jsonld or [])
        if crumbs and len(crumbs) > 1:
            ld.append({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "name": n, "item": self.url(u)} for i, (n, u) in enumerate(crumbs)]})
        ldh = "".join('<script type="application/ld+json">' + json.dumps(x, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + "</script>" for x in ld if x)
        bc = ""
        if crumbs and len(crumbs) > 1:
            bc = '<nav class="bc wrap" aria-label="Drobečková navigace"><ol>' + "".join(
                f'<li><a href="{u}">{E(n)}</a></li>' if i < len(crumbs) - 1 else f'<li aria-current="page">{E(n)}</li>' for i, (n, u) in enumerate(crumbs)) + "</ol></nav>"
        og = og_img or self.url("/img/ui/og.png")
        pre = f'<link rel="preload" as="image" href="{E(preload_img)}" fetchpriority="high">' if preload_img else ""
        nav = "".join(f'<a href="/{d}/"{" aria-current=true" if path.startswith(f"/{d}/") else ""}>{E(SHORT.get(d, X.DEPTS[d][0]))}</a>' for d in NAV if d in self.dept_ok)
        ga = f' data-ga="{E(self.ga4)}"' if self.ga4 else ""
        return f"""<!doctype html><html lang="cs"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title><meta name="description" content="{E(desc)}">{robots}<link rel="canonical" href="{self.url(canon)}">
<meta property="og:type" content="website"><meta property="og:site_name" content="KoupímNic"><meta property="og:title" content="{E(title)}">
<meta property="og:description" content="{E(desc)}"><meta property="og:url" content="{self.url(canon)}"><meta property="og:image" content="{E(og)}">
<meta name="twitter:card" content="summary_large_image"><meta name="theme-color" content="#4B1D6B">
<link rel="icon" href="/favicon.ico" sizes="32x32"><link rel="icon" href="/favicon-192.png" type="image/png" sizes="192x192"><link rel="apple-touch-icon" href="/favicon-180.png">
<link rel="manifest" href="/site.webmanifest"><link rel="stylesheet" href="/assets/{self.css}">{pre}{ldh}
<script type="speculationrules">{{"prefetch":[{{"where":{{"and":[{{"href_matches":"/*"}},{{"not":{{"href_matches":"/go/*"}}}},{{"not":{{"href_matches":"/objednavka/*"}}}}]}},"eagerness":"moderate"}}]}}</script>
</head><body class="{cls}"{ga}>
<a class="skip" href="#main">Přeskočit na obsah</a>
<div class="sim">KoupímNic – nákupní galerie nanečisto. Ceny a produkty jsou skutečné, z českých e-shopů.</div>
<header class="hd"><div class="wrap hd__in">
<button class="hd__menu" type="button" data-drawer aria-label="Kategorie">{icon("menu", 22)}</button>
<a class="logo" href="/" aria-label="KoupímNic – úvod"><img src="/img/ui/logo.webp" alt="KoupímNic" width="137" height="36"></a>
<button class="hd__cats" type="button" data-mega aria-expanded="false" aria-controls="mega">{icon("menu", 20)}<span>Kategorie</span></button>
<form class="search" action="/hledat/" role="search"><label class="sr" for="q">Hledat</label><input id="q" name="q" type="search" placeholder="Hledat mezi {self.stats.get("products_fmt", "tisíci")} produkty" autocomplete="off" enterkeyhint="search">
<button type="submit" aria-label="Hledat">{icon("search", 20)}</button><div class="sugg" id="sugg" hidden></div></form>
<a class="hd__save" href="/moje-uspory/" title="Neutraceno – moje úspory" aria-label="Moje úspory" data-saved-pill hidden>{icon("piggy", 22)}<small>Neutraceno</small><span data-saved>0&nbsp;Kč</span></a>
<button class="hd__cart" type="button" data-open-cart aria-label="Košík">{icon("bag", 22)}<span class="hd__sum" data-sum>Košík</span><span class="badge" data-count hidden>0</span></button>
</div><nav class="dn wrap" aria-label="Oddělení">{nav}</nav>
<div class="mega" id="mega" hidden><div class="wrap mega__in" id="mega-in"></div></div></header>
<div class="perks-bar"><div class="wrap"><span>{icon("truck", 16)}Doprava zdarma</span><span>{icon("lock", 16)}Bez registrace</span><span>{icon("check", 16)}Platba až na konci objednávky</span><span>{icon("box", 16)}Doručení ještě dnes</span></div></div>
<div class="orderpill" id="orderpill" hidden></div>
{bc}<main id="main" class="{'' if 'wide' in cls else ''}">{body}</main>
<footer class="ft"><div class="wrap ft__in">
<div><img src="/img/ui/logo.webp" alt="KoupímNic" width="137" height="36" loading="lazy"><p>Nákupní galerie nanečisto. Skutečné produkty a ceny z českých e-shopů, nákup jako všude jinde. Jen na konci se nic nestrhne.</p></div>
<div><h2>Oddělení</h2><ul>{"".join(f'<li><a href="/{d}/">{E(X.DEPTS[d][0])}</a></li>' for d in NAV if d in self.dept_ok)}</ul></div>
<div><h2>KoupímNic</h2><ul><li><a href="/jak-to-funguje/">Jak to funguje</a></li><li><a href="/moje-uspory/">Moje úspory</a></li><li><a href="/znacky/">Značky</a></li>
<li><a href="/obchody/">Obchody</a></li><li><a href="/kontakt/">Kontakt</a></li><li><a href="/ochrana-osobnich-udaju/">Soukromí a cookies</a></li></ul></div>
<div><h2>Poctivě</h2><p>KoupímNic je nákup nanečisto: nic tu neprodáváme a z účtu se nic nestrhne. Odkazy „Koupit doopravdy“ vedou do e-shopů a jsou reklamní, když tam nakoupíš, můžeme dostat provizi.</p></div>
</div><div class="wrap ft__op"><p>Provozovatel: {OPERATOR["name"]}, {OPERATOR["address"]}, IČO {OPERATOR["ico"]}, {OPERATOR["vat"]}. <a href="mailto:{OPERATOR["email"]}">{OPERATOR["email"]}</a>.
Ceny a dostupnost přebíráme z e-shopů a mohou se změnit. Aktualizováno {self.stats.get("updated", "")}.</p></div></footer>
<div class="drawer" id="cart" hidden><div class="drawer__bg" data-close></div><aside class="drawer__panel" role="dialog" aria-modal="true" aria-labelledby="cart-h">
<div class="drawer__hd"><h2 id="cart-h">Košík</h2><button type="button" class="x" data-close aria-label="Zavřít">{icon("x", 22)}</button></div><div class="drawer__body" id="cart-body"></div></aside></div>
<div class="toast" id="toast" role="status" aria-live="polite" hidden></div>
<div class="consent" id="consent" role="dialog" aria-label="Cookies" hidden><p>Smíme anonymně měřit návštěvnost (Google Analytics)? Košík a úspory jsou jen v tvém prohlížeči, ty neměříme.</p>
<div class="row"><button class="btn btn--sm" data-consent="yes">Souhlasím</button><button class="btn btn--sm btn--ghost" data-consent="no">Nesouhlasím</button></div></div>
<script src="/assets/{self.js}" defer></script></body></html>"""

    # ------------------------------------------------------------ pieces
    def item_data(self, p):
        """What the cart needs about a product, embedded in the page (no API)."""
        o = p["offers"][0]
        return {"id": p["slug"], "n": p["name"], "b": p["brand"], "p": p["price"], "w": p.get("was") or 0, "i": img_url(p["img"], "card"),
                "s": self.shop(o["shop"])["name"], "g": o["go"], "u": f"/produkt/{p['slug']}/", "c": p["cat"]}

    def card(self, p, lazy=True, eager=False):
        d = discount(p)
        badge = f'<span class="card__off">−{d}&nbsp;%</span>' if d >= 5 else ""
        was = f'<s>{kc(p["was"])}</s>' if d >= 5 else ""
        img = img_url(p["img"], "card") or "/img/ui/placeholder.svg"
        data = E(json.dumps(self.item_data(p), ensure_ascii=False, separators=(",", ":")))
        return (f'<article class="card"><a class="card__a" href="/produkt/{p["slug"]}/"><span class="card__img{photo_bg(p["img"], p["cat"])}"><img src="{E(img)}" alt="" '
                f'{"loading=lazy " if lazy and not eager else ""}{"fetchpriority=high " if eager else ""}decoding="async" referrerpolicy="no-referrer" width="320" height="320" data-orig="{E(p["img"])}">{badge}</span>'
                f'<span class="card__b">{E(p["brand"]) if p["brand"] else "&nbsp;"}</span><span class="card__n">{E(shorten(p["name"], 90))}</span></a>'
                f'<div class="card__foot"><span class="card__p"><b>{kc(p["price"])}</b>{was}</span><span class="card__st">Skladem</span>'
                f'<button class="card__add" type="button" data-add="{data}">{icon("bag", 18)}<span>Do košíku</span></button></div></article>')

    def grid(self, items, first_eager=0):
        return '<div class="grid">' + "".join(self.card(p, eager=i < first_eager) for i, p in enumerate(items)) + "</div>"

    def tiles(self, rows):
        """rows: (href, name, count, icon)"""
        if not rows:
            return ""
        return '<div class="tiles">' + "".join(
            f'<a class="tile" href="{h}"><img src="/img/ic/{ic}.webp" alt="" width="56" height="56" loading="lazy"><span><b>{E(n)}</b><small>{c:,} {plural(c, "kousek", "kousky", "kousků")}</small></span></a>'.replace(",", " ")
            for h, n, c, ic in rows) + "</div>"

    def faq(self, qa):
        if not qa:
            return "", None
        html_ = '<section class="faq wrap"><h2>Časté otázky</h2>' + "".join(f"<details><summary>{E(q)}</summary><p>{a}</p></details>" for q, a in qa) + "</section>"
        ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": re.sub(r"<[^>]+>", "", a)}} for q, a in qa]}
        return html_, ld
