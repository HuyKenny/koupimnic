# koupimnic.cz

Nákupní galerie nanečisto: skutečné produkty z českých e-shopů, falešný košík a pokladna za 0 Kč, smyšlené doručení,
prázdná krabice a účtenka „neutraceno X Kč“. Statický web na Cloudflare Workers (static assets, 0 $), build v GitHub Actions.

## Jak to běží
- `scripts/fetch.py` stáhne nabídky (CJ GraphQL, XML feedy eHub/Dognet/AffiliatePort) do `data/raw/`.
- `scripts/build.py` z nich udělá katalog (max 300 000 produktů) a statické stránky do `dist/`.
- `scripts/deploy.py` nahraje `dist/` jako Workers static assets (hlavní Worker + shardy pro `/produkt/<znak>*`).
- Košík, objednávky, úspory a karanténa přání běží v prohlížeči (`static/assets/app.js`, localStorage).

## Secrets (GitHub environment `production`)
`CJ_API_KEY`, `CJ_CID`, `CJ_PID`, `FEEDS_JSON` (`{"<feed_key>": "<url>"}`), `STATE_KEY`, `CLOUDFLARE_API_TOKEN`,
`CLOUDFLARE_ACCOUNT_ID`, `INDEXNOW_KEY`. Repo variables: `KNC_ENV` (`staging`/`production`), `KNC_MAX_PRODUCTS`, `GA4_ID`.

## Lokálně (malý vzorek)
    FETCH_LIMIT=200 python3 scripts/fetch.py answear notino
    KNC_MAX_PRODUCTS=3000 python3 scripts/build.py && node scripts/serve.mjs 8765

Grafika: Canva (viz `static/img/ASSETS.md`), fonty Schibsted Grotesk, Bricolage Grotesque, Space Mono (SIL OFL).
