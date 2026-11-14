# koupimnic.cz — rules for agents

A "dopamine shop": a gallery of REAL products from affiliate feeds where visitors "buy" in a FAKE checkout (0 Kč), watch a
fictional delivery, open an empty box and get a receipt "neutraceno X Kč". Sister site of damenic.cz. Kenny's brief 14. 11. 2026.

## Product rules
- Kenny 14. 11. (v2): the site must FEEL like a real big e-shop: real prices everywhere (cards, cart, checkout, "Zaplatit 24 549 Kč");
  the 0 Kč reveal comes only after clicking "Zaplatit". The thin strip `.sim` stays on every page ("nákupní galerie nanečisto"),
  without mentioning 0 Kč; /jak-to-funguje/ and the footer explain it.
- No payment gateway, never card/bank fields. Address fields in checkout are optional, kept only in a JS variable while the page
  is open (`co.addr`), never written to localStorage, never sent; cleared after "payment". No accounts, no contact form.
- Cart/orders/savings live in localStorage (`knc:*` keys in static/assets/app.js); nothing is sent to a server.
- Real purchase links ("Koupit doopravdy", "Fakt to chci") are ALWAYS marked `Reklama`, `rel="sponsored nofollow noopener"`,
  go through /go/<shop>/ (scripts/golinks.py) and are secondary: the primary CTA is always the fake cart.
- CJ website id 100709380 is shared with vpny.cz: every CJ link carries `sid=koupimnic` (fetch.py `with_sid`).
- No invented reviews, ratings or "most bought" numbers. Prices are the shops' real prices with the date.
- "Savings" copy stays honest: nothing was saved from the account, it was not spent.
- Tone (Czech, tykání): playful, dry, punchline at the end; no emoji, no exclamation walls, never mock people who overspend.
- Range (v2): 12 departments — electronics, fashion, shoes, accessories, perfume, drugstore & health, home appliances,
  toys & LEGO (hrackarium taxonomy vendored as scripts/tax_toys.py, shops `hr-*`), sport & outdoor, pets, books.
  No accessories/spare parts (cases, cables, LCD panels), no used goods, no adult goods, no medicines. Max 300 000 products,
  per-category caps in taxonomy.CATS; subcategories = taxonomy.SUBS + toy tree + category x brand (>= 12 products).

## Tech
- Python stdlib generator (copied from apps/vian): fetch.py -> catalog.py -> build.py (+ render.py, taxonomy.py) -> dist/.
- Static Workers assets only, no Worker script, no D1/KV/R2 (deploy.py refuses) = 0 $. Shards for /produkt/<char>*.
- Build/deploy ONLY in GitHub Actions (public repo = free minutes); nothing heavy on the Raspberry Pi.
- Quick fix path: Actions -> build -> Run workflow with fetch=off, quick=on.
- Public repo: never print keys or feed URLs; verify_no_secrets.py runs before deploy.
