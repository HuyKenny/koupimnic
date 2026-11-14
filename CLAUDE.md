# koupimnic.cz — rules for agents

A "dopamine shop": a gallery of REAL products from affiliate feeds where visitors "buy" in a FAKE checkout (0 Kč), watch a
fictional delivery, open an empty box and get a receipt "neutraceno X Kč". Sister site of damenic.cz. Kenny's brief 14. 11. 2026.

## Product rules
- The simulation must be obvious on every page (strip `.sim` above the header) — never imply a real purchase happened.
- No payment gateway, no card/bank/personal-data fields, no accounts, no contact form. Checkout data are fixed fake values.
- Everything user-side lives in localStorage (`knc:*` keys in static/assets/app.js); nothing is sent to a server.
- Real purchase links ("Koupit doopravdy", "Fakt to chci") are ALWAYS marked `Reklama`, `rel="sponsored nofollow noopener"`,
  go through /go/<shop>/ (scripts/golinks.py) and are secondary: the primary CTA is always the fake cart.
- CJ website id 100709380 is shared with vpny.cz: every CJ link carries `sid=koupimnic` (fetch.py `with_sid`).
- No invented reviews, ratings or "most bought" numbers. Prices are the shops' real prices with the date.
- "Savings" copy stays honest: nothing was saved from the account, it was not spent.
- Tone (Czech, tykání): playful, dry, punchline at the end; no emoji, no exclamation walls, never mock people who overspend.
- Range: impulse buys (electronics, fashion, shoes, bags, watches, perfume, a few appliances/sport). No kids' goods, no
  accessories (cases, cables), no adult goods. Max 300 000 products (KNC_MAX_PRODUCTS), per-category caps in taxonomy.CATS.

## Tech
- Python stdlib generator (copied from apps/vian): fetch.py -> catalog.py -> build.py (+ render.py, taxonomy.py) -> dist/.
- Static Workers assets only, no Worker script, no D1/KV/R2 (deploy.py refuses) = 0 $. Shards for /produkt/<char>*.
- Build/deploy ONLY in GitHub Actions (public repo = free minutes); nothing heavy on the Raspberry Pi.
- Quick fix path: Actions -> build -> Run workflow with fetch=off, quick=on.
- Public repo: never print keys or feed URLs; verify_no_secrets.py runs before deploy.
