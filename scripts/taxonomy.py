"""Departments, categories and the classifier for koupimnic.cz.

The range is what people buy on impulse (Kenny 14. 11. 2026): phones, laptops, consoles, watches, headphones, fashion, sneakers,
bags, perfume. classify(rec, shop) reads the product title first (most reliable across shops), then the shop's own category
path; fashion needs a gender (feed field, path or title) because the pages are "dámské" / "pánské". Accessories (cases,
cables, spare parts) and children's goods are vetoed: nobody gets a dopamine hit from a phone case.
"""
import re
import unicodedata

I = re.I
T = lambda s: re.compile(s, I)

# ------------------------------------------------------------------ departments (nav) and categories
# department slug: (name, short blurb, icon)
DEPTS = {
    "elektronika": ("Elektronika", "Telefony, notebooky, konzole a všechno, co bliká", "mobily"),
    "damska-moda": ("Dámská móda", "Šaty, bundy, svetry a kabelky", "damska-moda"),
    "panska-moda": ("Pánská móda", "Bundy, mikiny, košile a džíny", "panska-moda"),
    "boty": ("Boty a tenisky", "Tenisky, kozačky, polobotky", "tenisky"),
    "doplnky": ("Doplňky a hodinky", "Kabelky, batohy, hodinky, šperky", "kabelky"),
    "krasa": ("Parfémy a kosmetika", "Vůně, make-up a péče", "parfemy"),
    "drogerie": ("Drogerie a zdraví", "Zubní péče, holení, vitamíny a zdravotní pomůcky", "drogerie"),
    "domov": ("Domov a spotřebiče", "Kávovary, vysavače, kuchyňské roboty", "kavovary"),
    "hracky": ("Hračky a LEGO", "LEGO, stavebnice, hry, panenky a RC modely", "hracky"),
    "sport": ("Sport a outdoor", "Kola, stany, lyže, fitness a sportovní oblečení", "sport"),
    "zvirata": ("Zvířata", "Pelíšky, hračky a vybavení pro psy a kočky", "zvirata"),
    "knihy": ("Knihy", "Romány, detektivky, fantasy, kuchařky a komiksy", "knihy"),
}
# category slug: (name, department, h1, icon, price floor in Kč, cap = max products on the site)
CATS = {
    "mobilni-telefony": ("Mobilní telefony", "elektronika", "Mobilní telefony", "mobily", 2500, 6000),
    "tablety": ("Tablety", "elektronika", "Tablety", "tablety", 2000, 2500),
    "notebooky": ("Notebooky", "elektronika", "Notebooky a MacBooky", "notebooky", 6000, 6000),
    "pocitace": ("Počítače", "elektronika", "Stolní a herní počítače", "pocitace", 6000, 2500),
    "monitory": ("Monitory", "elektronika", "Monitory", "pocitace", 2500, 2500),
    "herni-konzole": ("Herní konzole", "elektronika", "Herní konzole", "herni", 2500, 2500),
    "herni-prislusenstvi": ("Ovladače a herní vybavení", "elektronika", "Ovladače, herní sluchátka a VR", "herni", 900, 2500),
    "chytre-hodinky": ("Chytré hodinky", "elektronika", "Chytré hodinky a fitness náramky", "hodinky-chytre", 900, 3000),
    "sluchatka": ("Sluchátka", "elektronika", "Sluchátka", "sluchatka", 700, 3500),
    "reproduktory": ("Reproduktory", "elektronika", "Bluetooth a chytré reproduktory", "audio", 900, 2500),
    "televize": ("Televize", "elektronika", "Televize", "televize", 4000, 2500),
    "fotoaparaty": ("Fotoaparáty a kamery", "elektronika", "Fotoaparáty, objektivy a akční kamery", "foto", 3000, 2500),
    "drony": ("Drony", "elektronika", "Drony", "drony", 2500, 1500),
    "kavovary": ("Kávovary", "domov", "Kávovary a espresso", "kavovary", 2500, 2500),
    "vysavace": ("Vysavače", "domov", "Robotické a tyčové vysavače", "domacnost", 2500, 2500),
    "kuchynske-spotrebice": ("Kuchyňské spotřebiče", "domov", "Kuchyňské roboty, mixéry a fritézy", "domacnost", 1500, 2500),
    "pece-o-vlasy": ("Fény a kulmy", "domov", "Fény, kulmy a žehličky na vlasy", "domacnost", 900, 1500),
    "damske-saty-a-sukne": ("Šaty a sukně", "damska-moda", "Dámské šaty a sukně", "damska-moda", 400, 8000),
    "damske-bundy-a-kabaty": ("Dámské bundy a kabáty", "damska-moda", "Dámské bundy a kabáty", "damska-moda", 700, 8000),
    "damske-mikiny-a-svetry": ("Dámské mikiny a svetry", "damska-moda", "Dámské mikiny a svetry", "damska-moda", 400, 7000),
    "damska-tricka-a-topy": ("Dámská trička a topy", "damska-moda", "Dámská trička, topy a halenky", "damska-moda", 300, 7000),
    "damske-kalhoty-a-dziny": ("Dámské kalhoty a džíny", "damska-moda", "Dámské kalhoty, džíny a legíny", "damska-moda", 400, 6000),
    "damske-pradlo-a-plavky": ("Dámské prádlo a plavky", "damska-moda", "Dámské prádlo, pyžama a plavky", "pradlo", 300, 5000),
    "panske-bundy-a-kabaty": ("Pánské bundy a kabáty", "panska-moda", "Pánské bundy a kabáty", "panska-moda", 700, 7000),
    "panske-mikiny-a-svetry": ("Pánské mikiny a svetry", "panska-moda", "Pánské mikiny a svetry", "panska-moda", 400, 6000),
    "panska-tricka-a-kosile": ("Pánská trička a košile", "panska-moda", "Pánská trička, polokošile a košile", "panska-moda", 300, 6000),
    "panske-kalhoty-a-dziny": ("Pánské kalhoty a džíny", "panska-moda", "Pánské kalhoty, džíny a kraťasy", "panska-moda", 400, 5000),
    "panske-pradlo": ("Pánské prádlo", "panska-moda", "Pánské spodní prádlo a pyžama", "pradlo", 300, 2500),
    "obleky-a-saka": ("Saka a obleky", "panska-moda", "Pánská saka a obleky", "panska-moda", 1000, 2000),
    "tenisky": ("Tenisky", "boty", "Tenisky a sneakers", "tenisky", 700, 12000),
    "damske-boty": ("Dámské boty", "boty", "Dámské boty, kozačky a lodičky", "boty", 600, 8000),
    "panske-boty": ("Pánské boty", "boty", "Pánské boty a polobotky", "boty", 600, 5000),
    "kabelky": ("Kabelky", "doplnky", "Kabelky a tašky", "kabelky", 500, 6000),
    "batohy": ("Batohy", "doplnky", "Batohy", "batohy", 500, 3000),
    "penezenky": ("Peněženky", "doplnky", "Peněženky a pouzdra na karty", "kabelky", 400, 2500),
    "hodinky": ("Hodinky", "doplnky", "Hodinky", "hodinky", 1000, 6000),
    "sperky": ("Šperky", "doplnky", "Šperky a bižuterie", "sperky", 500, 5000),
    "slunecni-bryle": ("Sluneční brýle", "doplnky", "Sluneční brýle", "bryle", 600, 2500),
    "damske-parfemy": ("Dámské parfémy", "krasa", "Dámské parfémy", "parfemy", 500, 8000),
    "panske-parfemy": ("Pánské parfémy", "krasa", "Pánské parfémy", "parfemy", 500, 5000),
    "unisex-parfemy": ("Unisex parfémy", "krasa", "Unisex parfémy", "parfemy", 500, 2500),
    "kosmetika": ("Kosmetika", "krasa", "Make-up a péče o pleť", "kosmetika", 400, 6000),
    "zimni-sporty": ("Lyže a snowboard", "sport", "Lyže, snowboardy a lyžařské vybavení", "zimni-sporty", 1500, 3000),
    "sportovni-obleceni": ("Sportovní a outdoorové oblečení", "sport", "Sportovní a outdoorové oblečení", "sport", 600, 8000),
    "kola-a-kolobezky": ("Kola a koloběžky", "sport", "Kola, elektrokola a koloběžky", "kola", 3000, 2500),
    "fitness": ("Fitness", "sport", "Fitness stroje a vybavení", "fitness", 1500, 2000),
    "rc-modely": ("RC modely a drony na ovladač", "hracky", "RC auta, lodě, letadla a modely na dálkové ovládání", "rc-modely", 800, 4000),
    "hudebni-nastroje": ("Hudební nástroje", "sport", "Kytary, klávesy a hudební nástroje", "hudba", 2000, 3000),
    # --- sport a outdoor (Kenny 14. 11.: celý sport, ne jen oblečení)
    "stany": ("Stany", "sport", "Stany a přístřešky", "stany", 1200, 3000),
    "spacaky-a-karimatky": ("Spacáky a karimatky", "sport", "Spacáky, karimatky a nafukovací matrace", "stany", 700, 3000),
    "outdoorove-batohy": ("Outdoorové batohy", "sport", "Turistické a outdoorové batohy", "batohy", 900, 3000),
    "turistika": ("Turistika", "sport", "Turistické hole, čelovky a vybavení na cesty", "sport", 500, 3000),
    "cyklo-vybaveni": ("Cyklo vybavení", "sport", "Cyklistické helmy, oblečení a doplňky", "kola", 700, 3000),
    "brusle": ("Brusle", "sport", "Hokejové, krasobruslařské a inline brusle", "zimni-sporty", 1000, 2000),
    "micove-sporty": ("Míčové a raketové sporty", "sport", "Míče, rakety, hokejky a pálky", "micove-sporty", 500, 3000),
    "vodni-sporty": ("Vodní sporty", "sport", "Paddleboardy, neopreny a vybavení k vodě", "sport", 900, 2000),
    # --- drogerie a zdraví
    "zubni-pece": ("Zubní péče", "drogerie", "Elektrické zubní kartáčky a ústní sprchy", "zubni-pece", 700, 2500),
    "holeni-a-strihani": ("Holení a zastřihování", "drogerie", "Holicí strojky, zastřihovače a epilátory", "drogerie", 700, 2500),
    "pece-o-telo": ("Péče o tělo", "drogerie", "Péče o tělo a koupel", "drogerie", 300, 4000),
    "vlasova-kosmetika": ("Vlasová kosmetika", "drogerie", "Šampony, kondicionéry a péče o vlasy", "drogerie", 300, 3000),
    "vitaminy-a-doplnky": ("Vitamíny a doplňky stravy", "drogerie", "Vitamíny, minerály a doplňky stravy", "zdravi", 300, 4000),
    "zdravotni-pomucky": ("Zdravotní pomůcky", "drogerie", "Tlakoměry, teploměry, masážní přístroje a pomůcky", "zdravi", 500, 3000),
    # --- zvířata
    "pro-psy": ("Pro psy", "zvirata", "Pelíšky, hračky, postroje a vybavení pro psy", "zvirata", 300, 5000),
    "pro-kocky": ("Pro kočky", "zvirata", "Škrabadla, pelíšky a vybavení pro kočky", "zvirata", 300, 3000),
    "ostatni-zvirata": ("Ostatní zvířata", "zvirata", "Akvária, klece a vybavení pro malá zvířata", "zvirata", 300, 2000),
    # --- knihy (žánry z cest knihkupectví)
    "beletrie": ("Beletrie", "knihy", "Romány a beletrie", "knihy", 200, 6000),
    "detektivky-a-thrillery": ("Detektivky a thrillery", "knihy", "Detektivky, krimi a thrillery", "knihy", 200, 4000),
    "fantasy-a-sci-fi": ("Fantasy a sci-fi", "knihy", "Fantasy, sci-fi a horory", "knihy", 200, 4000),
    "romantika": ("Romantika", "knihy", "Romantické romány", "knihy", 200, 3000),
    "komiksy-a-manga": ("Komiksy a manga", "knihy", "Komiksy, manga a grafické romány", "knihy", 200, 3000),
    "knihy-pro-deti": ("Knihy pro děti a mládež", "knihy", "Knihy pro děti a young adult", "knihy", 200, 4000),
    "kucharky": ("Kuchařky", "knihy", "Kuchařky a knihy o jídle", "knihy", 200, 2000),
    "cestovani-a-pruvodce": ("Cestování", "knihy", "Cestopisy a průvodce", "knihy", 200, 2000),
    "biografie-a-historie": ("Biografie a historie", "knihy", "Biografie, paměti a historie", "knihy", 200, 3000),
    "seberozvoj-a-psychologie": ("Seberozvoj a psychologie", "knihy", "Psychologie, seberozvoj a byznys", "knihy", 200, 3000),
    "naucne-a-hobby": ("Naučné a hobby", "knihy", "Populárně naučné knihy, hobby a umění", "knihy", 200, 3000),
}
TREE = {**{k: (v[0], None, v[0]) for k, v in DEPTS.items()}, **{k: (v[0], v[1], v[2]) for k, v in CATS.items()}}
PRICE_FLOOR = {k: v[4] for k, v in CATS.items()}
CAP = {k: v[5] for k, v in CATS.items()}

# brands people dream about: they go first when a category has to be capped and they get hub pages
TOP_BRANDS = {
    "apple", "samsung", "xiaomi", "google", "sony", "nintendo", "microsoft", "dyson", "dji", "gopro", "garmin", "lenovo", "asus", "acer", "msi",
    "hp", "dell", "lg", "philips", "bose", "jbl", "marshall", "sonos", "canon", "nikon", "fujifilm", "delonghi", "de'longhi", "nespresso", "krups",
    "kitchenaid", "smeg", "roborock", "ecovacs", "irobot", "nike", "adidas", "puma", "new balance", "converse", "vans", "asics", "reebok",
    "the north face", "columbia", "calvin klein", "tommy hilfiger", "guess", "michael kors", "hugo boss", "boss", "lacoste", "ralph lauren",
    "polo ralph lauren", "levi's", "gant", "armani", "emporio armani", "armani exchange", "karl lagerfeld", "versace", "dior", "chanel",
    "yves saint laurent", "gucci", "prada", "carolina herrera", "lancome", "lancôme", "paco rabanne", "rabanne", "hugo", "casio", "g-shock",
    "seiko", "tissot", "fossil", "swarovski", "pandora", "ray-ban", "oakley", "salomon", "fjallraven", "fjällräven", "patagonia",
    "ugg", "timberland", "dr. martens", "birkenstock", "on", "hoka", "skechers", "veja", "steve madden", "furla", "coach", "lego",
}


def fold(s):
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"[®™©]", "", s or "")).strip()


def slugify(s):
    s = fold(clean(s).replace("&", " a "))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


# ------------------------------------------------------------------ vetoes
VETO_TITLE = T(r"\b(kryt|krytu|obal|obaly|pouzdr\w*|ochrann\w* (sklo|fóli\w*|folie|kryt)|tvrzen\w* sklo|fóli[ei]|folie|nabíječk\w*|nabijeck\w*|kabel|kabely|"
               r"adaptér\w*|redukce|držák\w*|stojan(?! na kola)\w*|řemín\w*|reminek|náhradní|náramek pro|pásek (pro|na) (apple|hodinky|watch)|"
               r"baterie|akumulátor (pro|do)|powerbank\w*|power bank|nálepk\w*|samolepk\w*|skin|dock|hub|"
               r"servis\w*|oprav\w*|repas\w*|renov\w*|refurb\w*|použit\w*|bazar\w*|rozbalen\w*|vystaven\w*|2\. jakost|"
               r"dětsk\w*|pro děti|chlapeck\w*|dívčí|kojen\w*|miminko|baby|junior|mini me|"
               r"dárkový poukaz|poukázk\w*|voucher|vzorek|tester|odstřik|"
               r"erotick\w*|vibrátor\w*|dildo|"
               r"náplň|kapsle|kávová zrna|zrnková káva|filtr do|sáčky do|sáček|mop|kartáč pro robot\w*|"
               r"ponožk\w*|pantofl\w*|papuč\w*|"
               r"palmrest|matrice|displej\w* (pro|do|k)|lcd displej\w*|originální lcd|výměna displej\w*|lcd panel|základní desk\w*|ventilátor (pro|do)|pant\w* (pro|do)|touchpad|klávesnice (pro|do|k)|"
               r"battery|nástav\w*|součást\w*|(náhradní|čisticí|čistící) kartáč\w*|kartáč\w* (pro|na|do) (robot|vysavač|filtr)\w*|náhradní hlavic\w*|tyč\w*|selfie|filtr\w*|kombo|kytarov\w* (kombo|zesilovač)|podomítkov\w*|"
               r"autorádio|rádio android|navigace|carplay|android auto|"
               r"kapodastr\w*|trsátk\w*|struny|popruh\w*|stojan\w*|ochrann\w* sad\w*|sklo na|safírov\w* sklo|podstav\w*|podložk\w*)\b|\bsada \d+ ks|\b\d+\s?ks\b|\b\d+-?pack\b")
VETO_PATH = T(r"\b(Dítě|Děti|Dětsk\w*|Junior\w*|Kids|Chlapec|Chlapci|Dívka|Dívky|Kojen\w*|Batol\w*|Home|Bydlení|Náhradní díl\w*|"
              r"Doplňky výživy|Krmiv\w*|Zvířat\w*|Sexshop|Erotik\w*|Knihy|Elektroinstalační\w*|Nářadí a stavebniny|Osvětlení|Zahrad\w*|"
              r"Vzorky|Dárkové poukazy|Ponožky|Punčoch\w*|2\. jakost|Příslušenství pro|Příslušenství k|Doporučené příslušenství|Náhradní)\b")
# path words that are fine even when VETO_PATH hits (Notino "Doplňky" is not accessories of a phone)
PATH_OK = T(r"Ona > Doplňky|On > Doplňky|Ženy > Doplňky|Muži > Doplňky|Dámské doplňky|Pánské doplňky|Módní doplňky")

# ------------------------------------------------------------------ gender
FEMALE_PATH = T(r"(^|> |\b)(Ona|Ženy|Žena|Dámsk\w*|Women|Woman)\b")
MALE_PATH = T(r"(^|> |\b)(On|Muži|Muž|Pánsk\w*|Men|Man)\b")
FEMALE_TITLE = T(r"\b(dámsk\w*|pro ženy|women|woman)\b")
MALE_TITLE = T(r"\b(pánsk\w*|pro muže|men\b|man\b)")


def gender_of(rec):
    """f / m / u (unisex) / "" unknown. Feed field first, then the shop path, then the title."""
    sex = (rec.get("sex") or "").lower()
    if sex in ("female", "f", "žena", "ženy", "dámské", "dámská", "damske"):
        return "f"
    if sex in ("male", "m", "muž", "muži", "pánské", "pánská", "panske"):
        return "m"
    if sex in ("unisex", "u"):
        return "u"
    path, title = rec.get("cat") or "", rec.get("t") or ""
    f, m = bool(FEMALE_PATH.search(path)), bool(MALE_PATH.search(path))
    if f != m:
        return "f" if f else "m"
    f, m = bool(FEMALE_TITLE.search(title)), bool(MALE_TITLE.search(title))
    if f != m:
        return "f" if f else "m"
    if re.search(r"\bunisex\b", title + " " + path, I):
        return "u"
    return ""


# ------------------------------------------------------------------ title rules: (category, regex); first match wins.
# "@" categories are gendered: "@bundy" -> damske-bundy-a-kabaty / panske-bundy-a-kabaty
TITLE_RULES = [
    ("mobilni-telefony", T(r"\b(iphone \d|iphone se|iphone air|galaxy (s|a|z|m)\d|galaxy z (fold|flip)|pixel \d|redmi (note )?\d|xiaomi \d|xiaomi (redmi|poco|mi) ?\d|"
                           r"poco [fmx]\d|honor (magic|\d)|motorola (edge|moto g)|moto g\d|oneplus \d|nothing phone|realme \d|oppo (reno|find)|vivo (x|v)\d|"
                           r"mobilní telefon|smartphone|chytrý telefon)")),
    ("tablety", T(r"\b(ipad|galaxy tab|xiaomi pad|redmi pad|lenovo tab|tablet\b|surface pro)")),
    ("notebooky", T(r"\b(macbook|notebook|laptop|ultrabook|chromebook|thinkpad|zenbook|vivobook|ideapad|legion \d|rog (strix|zephyrus|flow)|tuf gaming f|"
                    r"aspire \d|nitro (v|\d)|predator helios|pavilion \d|omen (transcend|\d)|envy x?\d|elitebook|probook|latitude|inspiron|xps \d|"
                    r"surface laptop|galaxy book)")),
    ("pocitace", T(r"\b(imac|mac mini|mac studio|herní (počítač|pc|sestava)|stolní počítač|all-in-one (počítač|pc)|aio pc|počítačová sestava)")),
    ("monitory", T(r"\b(monitor)\b")),
    ("herni-prislusenstvi", T(r"\b(dualsense|dualshock|ovladač (pro|na) (ps|xbox|playstation|nintendo|switch)|xbox (wireless )?controller|"
                              r"playstation vr|meta quest|vr brýle|herní sluchátka|herní myš|herní klávesnice|herní křeslo|volant (pro|logitech|thrustmaster))")),
    ("herni-konzole", T(r"\b(playstation 5|ps5( slim| pro| digital)?\b(?!.*(ovladač|hra|controller))|xbox series [sx]|nintendo switch|steam deck|rog ally|legion go|"
                        r"herní konzole)")),
    ("chytre-hodinky", T(r"\b(apple watch|galaxy watch|galaxy fit|pixel watch|chytré hodinky|smartwatch|fitness náramek|chytrý náramek|garmin (fenix|forerunner|venu|vivoactive|instinct|epix)|"
                         r"amazfit|huawei watch|xiaomi (smart band|watch)|mi band|redmi watch|polar (vantage|grit|ignite|pacer)|suunto|coros)")),
    ("sluchatka", T(r"\b(airpods|sluchátka|headphones|earbuds|galaxy buds|pixel buds|sony wh-|sony wf-|bose quietcomfort|beats (studio|solo|fit|flex|powerbeats))")),
    ("reproduktory", T(r"\b(reproduktor|soundbar|bluetooth speaker|jbl (charge|flip|go|xtreme|partybox|boombox|clip)|marshall (emberton|stanmore|acton|woburn|kilburn|middleton)|"
                       r"sonos|homepod|echo dot|google nest audio)")),
    ("televize", T(r"\b(televiz\w*|smart tv|(oled|qled|led|uhd|4k) (tv|televize)|\btv\b.*\b(oled|qled|4k|uhd)\b|(oled|qled)\d{2}|bravia|\d{2}\" (lg|samsung|sony|philips|tcl|hisense))")),
    ("drony", T(r"\b(dron\b|drony\b|dji (mini|air|mavic|avata|neo|flip))")),
    ("fotoaparaty", T(r"\b(fotoaparát|bezzrcadlovk|zrcadlovk|objektiv|gopro|insta360|akční kamera|osmo (pocket|action|360)|dji pocket|instax|polaroid|"
                      r"canon eos|sony alpha|sony a7|nikon z|fujifilm x-)")),
    ("kavovary", T(r"\b(kávovar|espresso\b|espresovač|presovač|automatický kávovar|pákový kávovar|nespresso|dolce gusto|mlýnek na kávu)")),
    ("vysavace", T(r"\b(vysavač|robotický vysavač|dyson v\d|tyčový vysavač|mopovací robot|roborock|roomba)")),
    ("pece-o-vlasy", T(r"\b(fén\b|vysoušeč vlasů|kulma|žehlička na vlasy|airwrap|supersonic|horkovzdušná kartáč|multistyler)")),
    ("kuchynske-spotrebice", T(r"\b(kuchyňský robot|kitchenaid|thermomix|mixér|fritéza|horkovzdušná fritéza|airfryer|air fryer|toastovač|varná konvice|"
                               r"sodastream|zmrzlinovač|odšťavňovač|food processor|monsieur cuisine)")),
    ("zimni-sporty", T(r"\b(lyže\b|lyže |sjezdové lyže|snowboard|lyžařsk\w* (boty|helma|přilba|brýle)|skialp|běžky\b|běžecké lyže)")),
    ("zubni-pece", T(r"\b(zubní kartáč\w*|sonicare|oral-?b|ústní sprch\w*|irigátor\w*)")),
    ("holeni-a-strihani", T(r"\b(holicí strojek|holicí strojky|holicí strojek|zastřihovač\w*|epilátor\w*|oneblade|trimmer)")),
    ("zdravotni-pomucky", T(r"\b(tlakoměr\w*|oxymetr\w*|masážní (pistole|přístroj|polštář|podložk)\w*|bezdotykov\w* teploměr)")),
    ("stany", T(r"\b(stan|stany|stanu)\b")),
    ("spacaky-a-karimatky", T(r"\b(spacák\w*|karimatk\w*|samonafukovací\w*|nafukovací matrac\w*)")),
    ("brusle", T(r"\b(brusle|inline brusl\w*|kolečkov\w* brusl\w*)")),
    ("micove-sporty", T(r"\b(míč|míče|tenisov\w* raket\w*|badmintonov\w* raket\w*|padel\w*|florbalov\w* hůl|hokejk\w*|golfov\w* hol\w*)")),
    ("vodni-sporty", T(r"\b(paddleboard\w*|paddle board|neopren\w*|plavecké brýle|šnorchl\w*|kajak\w*)")),
    ("turistika", T(r"\b(trekov\w* hole|turistick\w* hole|nordic walking|čelovk\w*|vařič\w*)")),
    ("cyklo-vybaveni", T(r"\b(cyklistick\w* (helm|přilb|dres|kalhot|bot|brýl|rukavic)\w*|(helma|přilba) na kolo|cyklopočítač\w*)")),
    ("kola-a-kolobezky", T(r"\b(elektrokolo|horské kolo|silniční kolo|gravel|e-?bike|koloběžk|elektrokoloběžk|kolo \d{2}\")")),
    ("fitness", T(r"\b(běžecký pás|rotoped|eliptický trenažér|veslovací trenažér|posilovací (lavice|věž|stroj)|spinningové kolo|multifunkční posilovač)")),
    ("rc-modely", T(r"\b(rc (auto|auta|model|loď|lodě|truck|buggy|tank|bagr|crawler|vrtulník|letadlo)|na dálkové ovládání|\b1:(8|10|12|14|16|18)\b.*rc)")),
    ("hudebni-nastroje", T(r"\b(kytara|elektrická kytara|akustická kytara|baskytara|ukulele|klávesy|digitální piano|syntezátor|bicí souprava|elektronické bicí)")),
    ("unisex-parfemy", T(r"\bunisex\b.*\b(parfém|parfum|toaletní voda|eau de)|\b(parfém|parfum|toaletní voda|eau de)\b.*\bunisex\b")),
    ("@parfemy", T(r"\b(parfém|parfum|parfémovaná voda|toaletní voda|kolínská|eau de (parfum|toilette|cologne)|edp\b|edt\b)")),
    ("kosmetika", T(r"\b(make-?up|řasenk|rtěnk|oční stíny|paletka|tvářenk|bronzer|rozjasňovač|korektor|pudr\b|krém na (obličej|pleť|oči)|pleťov\w* (krém|sérum|maska)|sérum|"
                    r"denní krém|noční krém|hydratační krém|lak na nehty)")),
    ("hodinky", T(r"\b(hodinky|chronograf|watch\b)")),
    ("sperky", T(r"\b(náhrdelník|řetízek|náušnice|prsten|náramek|přívěsek|brož|šperk|piercing)")),
    ("slunecni-bryle", T(r"\b(sluneční brýle|brýle sluneční|ray-?ban|sunglasses)")),
    ("penezenky", T(r"\b(peněženk|pouzdro na karty|dokladovk|card holder|wallet)")),
    ("batohy", T(r"\b(batoh|batůžek|backpack|ruksak)")),
    ("kabelky", T(r"\b(kabelk|crossbody|shopper|kabela|psaníčko|ledvinka|taška přes rameno|taška do ruky|clutch|tote)")),
    ("tenisky", T(r"\b(tenisky|tenisk|sneakers?|botasky|air (max|force|jordan)|jordan \d|dunk (low|high)|samba|gazelle|campus 00|superstar|stan smith|"
                  r"chuck taylor|old skool|new balance \d{3}|gel-(kayano|nimbus|1130|lyte)|běžecké boty|běžecká obuv)")),
    ("@boty", T(r"\b(boty|obuv|kozačk|kotníkov|lodičk|baleríny|sandál|pantofl|polobotk|mokasín|espadrilk|žabky|holínky|sněhule|chelsea|farmářk|"
                r"loafers|mule|pumps|zimní obuv|trekov\w* (boty|obuv))")),
    ("obleky-a-saka", T(r"\b(oblek\b|obleky\b|sako\b|saka\b|smoking|vesta k obleku)")),
    ("@saty", T(r"\b(šaty|sukně|overal|kostým)")),
    ("@kalhoty", T(r"\b(kalhoty|džíny|jeans|rifle|legíny|tepláky|kraťasy|šortky|chinos|joggers|culottes)")),
    ("@bundy", T(r"\b(bunda|bundy|kabát|parka|vesta|péřov|softshell|větrovka|pláštěnka|trenčkot|bomber|blazer)")),
    ("@mikiny", T(r"\b(mikina|mikiny|svetr|svetry|rolák|cardigan|kardigan|pulovr|hoodie|fleece)")),
    ("@pradlo", T(r"\b(podprsenk|kalhotky|tanga|boxerky|slipy|trenýrky|trenky|spodní prádlo|pyžamo|župan|noční košile|plavky|bikiny|body\b|korzet)")),
    ("@tricka", T(r"\b(tričko|trička|triko|top\b|topy|tílko|halenka|košile|polokošile|t-shirt|tunika|crop top|body\b)")),
]
# shop category path -> category (title did not decide)
PATH_RULES = [
    ("mobilni-telefony", T(r"Mobilní telefony|Smartphony|Telefony > Smartphony|Mobily")),
    ("notebooky", T(r"Notebooky|Laptopy")),
    ("tablety", T(r"\bTablety\b")),
    ("herni-konzole", T(r"Konzole a herní automaty > Sony PlayStation 5 > Konzole|Herní konzole")),
    ("chytre-hodinky", T(r"Chytré hodinky|Fitness náramky|Sporttestery")),
    ("sluchatka", T(r"Sluchátka")),
    ("reproduktory", T(r"Reproduktory|Soundbary")),
    ("televize", T(r"Televize")),
    ("fotoaparaty", T(r"Fotoaparáty|Akční kamery|Objektivy")),
    ("drony", T(r"RC Drony|Drony")),
    ("rc-modely", T(r"RC Auta|RC Lodě|RC stroje|RC modely")),
    ("kola-a-kolobezky", T(r"e-KOLOBĚŽKY|Elektrokola|Koloběžky|Jízdní kola")),
    ("kavovary", T(r"Kávovary|Příprava kávy")),
    ("vysavace", T(r"Vysavače")),
    ("kuchynske-spotrebice", T(r"Kuchyňské roboty|Mixéry|Fritézy")),
    ("pece-o-vlasy", T(r"Fény na vlasy|Kulmy|Žehličky na vlasy|Vlasy > Elektronika")),
    ("zubni-pece", T(r"Zubní|Ústní hygien")),
    ("holeni-a-strihani", T(r"Holicí strojky|Zastřihovače|Epilátory")),
    ("pece-o-telo", T(r"Péče o tělo|> Tělo\b|^Tělo\b|Koupel")),
    ("vlasova-kosmetika", T(r"Šampony|Kondicionéry|Péče o vlasy|Vlasová kosmetika|^Vlasy > (?!Elektronika)")),
    ("stany", T(r"\bStany\b")),
    ("spacaky-a-karimatky", T(r"Spacáky|Karimatky")),
    ("brusle", T(r"Brusle")),
    ("fitness", T(r"Posilovací|Fitness stroje|Trenažéry|Činky")),
    ("hudebni-nastroje", T(r"Akustické kytary|Elektrické kytary|Baskytary|Ukulele|Klávesy|Digitální piana|Bicí")),
    ("zimni-sporty", T(r"Sjezdové lyžování > (Lyže|Lyžařské boty|Helmy|Brýle)|Snowboarding > (Snowboardy|Boty)|Skialp")),
    ("unisex-parfemy", T(r"Unisex parfémy")),
    ("damske-parfemy", T(r"Dámské parfémy|Dámské vůně")),
    ("panske-parfemy", T(r"Pánské parfémy|Pánské vůně")),
    ("kosmetika", T(r"^Pleť > Péče o pleť|^Líčení")),
    ("tenisky", T(r"Tenisky|Sneakers")),
    ("@boty", T(r"\bBoty\b|\bObuv\b")),
    ("hodinky", T(r"\bHodinky\b")),
    ("sperky", T(r"Šperky|Bižuterie")),
    ("slunecni-bryle", T(r"Sluneční brýle")),
    ("batohy", T(r"\bBatohy\b")),
    ("kabelky", T(r"Kabelky|Tašky")),
    ("penezenky", T(r"Peněženky")),
    ("@saty", T(r"Šaty|Sukně|Overaly")),
    ("@bundy", T(r"Bundy|Kabáty|Vesty")),
    ("@mikiny", T(r"Mikiny|Svetry")),
    ("@pradlo", T(r"Spodní prádlo|Podprsenky|Kalhotky|Boxerky|Trenky|Pyžama|Župany|Plavky")),
    ("@kalhoty", T(r"Kalhoty|Džíny|Legíny|Tepláky|Kraťasy|Šortky")),
    ("@tricka", T(r"Trička|Košile|Topy|Halenky|Polokošile")),
]
GENDERED = {
    "@parfemy": ("damske-parfemy", "panske-parfemy", "unisex-parfemy"),
    "@boty": ("damske-boty", "panske-boty", None),
    "@saty": ("damske-saty-a-sukne", None, None),
    "@bundy": ("damske-bundy-a-kabaty", "panske-bundy-a-kabaty", None),
    "@mikiny": ("damske-mikiny-a-svetry", "panske-mikiny-a-svetry", None),
    "@pradlo": ("damske-pradlo-a-plavky", "panske-pradlo", None),
    "@kalhoty": ("damske-kalhoty-a-dziny", "panske-kalhoty-a-dziny", None),
    "@tricka": ("damska-tricka-a-topy", "panska-tricka-a-kosile", None),
}
# clothes from sport/outdoor shops become "sportovní oblečení" when the shop says so
SPORT_PATH = T(r"(Sporty|Outdoor|Turistik|Běh\b|Lyžov|Lyžařsk|Cyklo|Fitness|Funkční|Termo|Treking|Trekov)")
FASHION_CATS = {c for v in GENDERED.values() for c in v if c} - {"damske-parfemy", "panske-parfemy", "unisex-parfemy", "damske-boty", "panske-boty"}

# shop-level knowledge: what a shop sells decides ambiguous titles ("Watch" at a watch shop is a watch)
ELECTRONICS_ONLY = {"mobilni-telefony", "tablety", "notebooky", "pocitace", "monitory", "herni-konzole", "herni-prislusenstvi", "televize", "drony"}


def resolve(slug, g):
    if not slug or not slug.startswith("@"):
        return slug
    f, m, u = GENDERED[slug]
    if g == "f":
        return f
    if g == "m":
        return m
    if g == "u":
        return u or f or m
    return f if slug in ("@saty",) else None


def classify(rec, shop):
    """Category slug or None (vetoed / not our range)."""
    title, path = clean(rec.get("t")), clean(rec.get("cat"))
    if VETO_TITLE.search(title):
        return None
    if VETO_PATH.search(path) and not PATH_OK.search(path):
        return None
    allowed = set(shop.get("cats") or []) or None          # e.g. a fashion shop never sells phones (its "iPhone" is a case)
    g = gender_of(rec)
    hit, slug = None, ""
    for slug, rx in TITLE_RULES:
        if rx.search(title):
            hit = resolve(slug, g)
            break
    else:
        slug = ""
        for slug, rx in PATH_RULES:
            if rx.search(path):
                hit = resolve(slug, g)
                break
        else:
            slug = ""
    if hit is None and slug.startswith("@") and slug not in ("@parfemy", "@boty") and (shop.get("sport") or SPORT_PATH.search(path)):
        hit = "sportovni-obleceni"           # outdoor shops: most jackets and fleeces are unisex
    if not hit:
        return None
    if hit in FASHION_CATS and (shop.get("sport") or SPORT_PATH.search(path)) and not shop.get("fashion"):
        hit = "sportovni-obleceni"
    if hit == "batohy" and (shop.get("sport") or SPORT_PATH.search(path)):
        hit = "outdoorove-batohy"
    if allowed and hit not in allowed and not any(hit.startswith(a) for a in allowed):
        return None
    return hit


# ------------------------------------------------------------------ brands
BRAND_ALIAS = {"de'longhi": "De'Longhi", "delonghi": "De'Longhi", "the north face": "The North Face", "levi's": "Levi's", "levis": "Levi's",
               "hugo boss": "BOSS", "boss": "BOSS", "polo ralph lauren": "Polo Ralph Lauren", "calvin klein jeans": "Calvin Klein",
               "tommy jeans": "Tommy Hilfiger", "armani exchange": "Armani Exchange", "emporio armani": "Emporio Armani", "dji": "DJI",
               "msi": "MSI", "hp": "HP", "lg": "LG", "jbl": "JBL", "gopro": "GoPro", "ugg": "UGG", "asics": "ASICS", "fjällräven": "Fjällräven",
               "fjallraven": "Fjällräven", "new balance": "New Balance", "apple": "Apple", "samsung": "Samsung", "xiaomi": "Xiaomi"}
BAD_BRANDS = {"", "none", "null", "neuvedeno", "ostatní", "ostatni", "nezařazeno", "bez značky", "noname", "no name", "-", "n/a", "generic", "oem"}
TITLE_BRANDS = [("Apple", r"\b(iphone|ipad|macbook|imac|mac mini|airpods|apple watch|homepod)\b"), ("Samsung", r"\bgalaxy\b"),
                ("Sony", r"\b(playstation|ps5|dualsense)\b"), ("Nintendo", r"\bnintendo\b"), ("Microsoft", r"\bxbox\b"), ("Dyson", r"\bdyson\b"),
                ("Google", r"\bpixel \d"), ("Xiaomi", r"\b(redmi|poco)\b")]


def brand_of(rec):
    b = clean(rec.get("b"))
    k = b.lower()
    if k in BAD_BRANDS:
        b, k = "", ""
    if k in BRAND_ALIAS:
        return BRAND_ALIAS[k]
    t = rec.get("t") or ""
    for name, rx in TITLE_BRANDS:
        if re.search(rx, t, I) and (not b or b.lower() in ("apple", "samsung", "sony", "nintendo", "microsoft", "dyson", "google", "xiaomi")):
            return name
    if b.isupper() and len(b) > 4:
        b = b.title()
    return b[:40]


def top_brand(brand):
    return fold(brand) in TOP_BRANDS


# ------------------------------------------------------------------ sizes (EU only, fashion and shoes)
SIZE_ORDER = ["XXXS", "XXS", "XS", "S", "M", "L", "XL", "XXL", "2XL", "XXXL", "3XL", "4XL", "5XL"]


def size_key(s):
    u = s.upper().strip()
    if u in SIZE_ORDER:
        return (0, SIZE_ORDER.index(u), u)
    m = re.match(r"^(\d+(?:[.,]\d)?)", u)
    if m:
        return (1, float(m.group(1).replace(",", ".")), u)
    return (2, 0, u)


def clean_size(s):
    s = clean(s)
    if not s or len(s) > 12 or s.upper() in ("ONE SIZE", "UNI", "UNIVERZÁLNÍ", "OS"):
        return "" if not s or len(s) > 12 else "univerzální"
    if re.match(r"^(UK|US)\b", s, I):
        return ""
    return s.replace("EU ", "").replace("EUR ", "")


COLOR_WORDS = ["černá", "bílá", "šedá", "modrá", "tmavě modrá", "zelená", "červená", "růžová", "béžová", "hnědá", "žlutá", "oranžová", "fialová",
               "stříbrná", "zlatá", "vícebarevná"]


def nice_name(t):
    """Shop titles: drop double spaces, shouting words and trailing size/colour codes."""
    t = clean(t)
    t = re.sub(r"\s+-\s+(Pánské|Dámské|Unisex|Dětské|Wmns)\s+-\s+.*$", "", t, flags=I)       # The Streets: "… - Dámské - Tenisky Nike - Zelené - CODE"
    t = re.sub(r"\s*[,/|-]\s*(velikost|vel\.)(\s*\S+)?$", "", t, flags=I)

    def fix(m):
        w = m.group(0)
        return w if len(w) <= 4 else w[:1] + w[1:].lower()
    t = re.sub(r"\b[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]{5,}\b", fix, t)
    return t[:1].upper() + t[1:]


# ================================================================== toys (Hračky a LEGO): the hrackarium.cz taxonomy, vendored as tax_toys.py
import tax_toys as TY  # noqa: E402

TOY_CAT = {"elektronika": "interaktivni-hracky", "drevene": "drevene-hracky", "hudebni": "hudebni-hracky", "venku": "hracky-na-ven",
           "kreativni": "kreativni-hracky", "naucne": "naucne-hracky", "figurky-a-zviratka": "figurky", "auta-a-vlacky": "auta-a-vlacky"}
TOY_ICON = {"lego": "lego", "stavebnice": "stavebnice", "panenky": "panenky", "spolecenske-hry": "deskove-hry", "puzzle": "puzzle",
            "plysaci": "plysaci", "rc-modely": "rc-modely"}
for _top in TY.TOP:
    _slug = TOY_CAT.get(_top, _top)
    if _slug in CATS:                      # rc-modely: one category in the toy department
        continue
    _n, _, _h1, _ = TY.TREE[_top]
    CATS[_slug] = (_n, "hracky", _h1, TOY_ICON.get(_top, "hracky"), 150, 8000 if _top == "lego" else 4000)
TREE.update({k: (v[0], v[1], v[2]) for k, v in CATS.items() if k not in TREE})
PRICE_FLOOR.update({k: v[4] for k, v in CATS.items()})
CAP.update({k: v[5] for k, v in CATS.items()})


def classify_toy(rec, shop):
    """(category, subcategory) for toy shops; None when hrackarium's own veto says it is not a toy."""
    t = TY.classify(rec) or shop.get("fallback_cat")
    if not t:
        return None, ""
    top, _, child = t.partition("/")
    cat = TOY_CAT.get(top, top)
    if cat == "lego":
        s = TY.lego_series(rec.get("t") or "")
        return cat, ("" if s == "ostatni" else s)
    return cat, ("" if child == "ostatni" else child)


TOY_SUB_NAMES = {}
for _k, _v in TY.TREE.items():
    if "/" in _k:
        _top, _, _child = _k.partition("/")
        TOY_SUB_NAMES[(TOY_CAT.get(_top, _top), _child)] = _v[0]
for _s, _n, _rx in TY.LEGO_SERIES:
    TOY_SUB_NAMES[("lego", _s)] = _n


# ================================================================== books, pets, pharmacies: decided by the shop's category path
BOOK_RULES = [
    ("komiksy-a-manga", T(r"komiks|manga|grafick\w* román")), ("knihy-pro-deti", T(r"pro děti|dětsk|mládež|young adult|leporel|pohádk")),
    ("detektivky-a-thrillery", T(r"detektiv|krimi|thriller|napětí")), ("fantasy-a-sci-fi", T(r"fantasy|sci-?fi|science fiction|horor")),
    ("romantika", T(r"romantick|romance|červená knihovna|pro ženy")), ("kucharky", T(r"kuchař|vaření|gastronom|recept")),
    ("cestovani-a-pruvodce", T(r"cestopis|průvodc|cestování|mapy|atlas")), ("biografie-a-historie", T(r"biografi|memoár|paměti|životopis|histori|válk")),
    ("seberozvoj-a-psychologie", T(r"psycholog|seberozvoj|osobní rozvoj|motivac|ekonomi|business|byznys|management|marketing|finance")),
    ("naucne-a-hobby", T(r"naučn|věda|příroda|hobby|umění|fotograf|zdraví|sport|zahrad|technik|počítač|jazyk")),
    ("beletrie", T(r"beletri|román|próza|česká literatura|světová literatura|povídk|poezie")),
]
BOOK_VETO = T(r"cizojazyčn|english literature|ve slovenštině|^ebook|> ebook|hračky|blu-?ray|\bdvd\b|\bcd\b|\blp\b|vinyl|film z kategorie|e-?kniha|e-?book|audiokniha|audiobook|mp3|učebnic|pracovní sešit|diář|kalendář|zápisník|omalovánk|puzzle|plakát|školní")
PET_RULES = [("pro-kocky", T(r"kočk|koček|kočičí|cat\b|škrabad")), ("pro-psy", T(r"\bpes\b|\bpsi\b|psů|psí|pro psy|dog\b|štěn")),
             ("ostatni-zvirata", T(r"akvári|teráři|hlodav|králík|ptác|ptáci|rybičk|morč|křeč|fretk"))]
PET_VETO = T(r"krmivo|granule|konzerv|kapsičk|pamlsk|pochoutk|steliv|antiparazit|léčiv|veterinár|vzorek|\b\d+\s?(kg|g)\b")
HEALTH_RULES = [
    ("zubni-pece", T(r"zubní kartáč|sonicare|oral-?b|ústní sprch|irigátor|zubní hygien")),
    ("zdravotni-pomucky", T(r"tlakoměr|teploměr|oxymetr|inhalátor|masážní|glukometr|zdravotní pomůck|ortéz|bandáž|kompresní")),
    ("vitaminy-a-doplnky", T(r"vitamín|vitamin|doplňk\w* stravy|minerál|probiotik|kolagen|omega|hořčík|zinek")),
    ("pece-o-telo", T(r"tělov|sprchov|koupel|deodorant|mýdl|krém na ruce|tělové mléko")),
    ("vlasova-kosmetika", T(r"šampon|kondicionér|vlasov|maska na vlasy")),
    ("kosmetika", T(r"pleť|make-?up|řasenk|rtěnk|sérum|krém na obličej")),
]
HEALTH_VETO = T(r"lék\b|léky|léčiv|na předpis|homeopat|kapky do|sirup|tablety proti|antikoncep|těhotensk|test\b|náplast|obvaz|kondom|lubrikač")


def classify_path(rec, shop):
    """Shops whose own category path decides (bookshops, pet shops, pharmacies)."""
    kind, title, path = shop.get("tax"), clean(rec.get("t")), clean(rec.get("cat"))
    text = path + " | " + title
    if kind == "books":
        if BOOK_VETO.search(text):
            return None
        hit = next((c for c, rx in BOOK_RULES if rx.search(path)), None)
        if hit or path.strip().lower() not in ("knihy", "kniha"):
            return hit
        desc = (rec.get("d") or "")[:500]                      # Dobrovský files most titles just under "Knihy": the blurb tells the genre
        return next((c for c, rx in BOOK_RULES[:-1] if rx.search(title + " " + desc)), "beletrie")
    if kind == "pets":
        if PET_VETO.search(text):
            return None
        return next((c for c, rx in PET_RULES if rx.search(text)), None)
    if kind == "health":
        if HEALTH_VETO.search(text):
            return None
        return next((c for c, rx in HEALTH_RULES if rx.search(text)), None)
    return None


# ================================================================== subcategories (Kenny 14. 11.: "mobily -> iPhone, Samsung…, televize, podkategorie celkově")
S_ = lambda *rows: [(slug, name, T(rx)) for slug, name, rx in rows]
SUBS = {
    "mobilni-telefony": S_(("iphone", "iPhone", r"\biphone\b"), ("skladaci-telefony", "Skládací telefony", r"\b(fold|flip)\b|skládací"),
                           ("samsung-galaxy", "Samsung Galaxy", r"\bgalaxy\b|samsung"), ("xiaomi-redmi-poco", "Xiaomi, Redmi a POCO", r"xiaomi|redmi|\bpoco\b"),
                           ("google-pixel", "Google Pixel", r"\bpixel\b"), ("motorola", "Motorola", r"motorola|\bmoto\b"), ("honor", "Honor", r"\bhonor\b"),
                           ("odolne-telefony", "Odolné telefony", r"odoln|rugged|cat s\d|doogee|ulefone|blackview")),
    "tablety": S_(("ipad", "iPad", r"\bipad\b"), ("samsung-galaxy-tab", "Samsung Galaxy Tab", r"galaxy tab"), ("xiaomi-tablety", "Xiaomi a Redmi Pad", r"xiaomi|redmi pad"),
                  ("lenovo-tablety", "Lenovo Tab", r"lenovo"), ("e-ctecky", "E-čtečky", r"kindle|pocketbook|e-?čtečk")),
    "notebooky": S_(("macbook-air", "MacBook Air", r"macbook air"), ("macbook-pro", "MacBook Pro", r"macbook pro"), ("macbook", "MacBook", r"macbook"),
                    ("herni-notebooky", "Herní notebooky", r"herní|gaming|\brog\b|legion|\btuf\b|nitro|predator|omen|victus|\bmsi\b|alienware|rtx"),
                    ("pracovni-notebooky", "Pracovní notebooky", r"thinkpad|elitebook|probook|latitude|vostro|expertbook|travelmate"),
                    ("ultrabooky", "Ultrabooky", r"zenbook|yoga|swift|xps|spectre|envy|gram|surface|galaxy book|ultrabook"),
                    ("chromebooky", "Chromebooky", r"chromebook")),
    "pocitace": S_(("mac", "Mac mini, iMac a Mac Studio", r"\bmac\b|imac"), ("herni-pocitace", "Herní počítače", r"herní|gaming|rtx")),
    "monitory": S_(("herni-monitory", "Herní monitory", r"herní|gaming|\b1[4-9]\dhz|\b2\d\dhz|\b[3-5]\d\dhz"), ("oled-monitory", "OLED monitory", r"oled"),
                   ("4k-monitory", "4K monitory", r"\b4k\b|3840")),
    "herni-konzole": S_(("playstation-5", "PlayStation 5", r"playstation|ps5"), ("xbox", "Xbox", r"xbox"), ("nintendo-switch", "Nintendo Switch", r"nintendo|switch"),
                        ("handheldy", "Herní handheldy", r"steam deck|rog ally|legion go|msi claw")),
    "herni-prislusenstvi": S_(("ovladace", "Ovladače", r"ovladač|controller|dualsense|gamepad"), ("vr-bryle", "VR brýle", r"\bvr\b|quest"),
                              ("herni-sluchatka", "Herní sluchátka", r"sluchátk|headset"), ("volanty", "Volanty", r"volant"), ("herni-kresla", "Herní křesla", r"křesl")),
    "chytre-hodinky": S_(("apple-watch", "Apple Watch", r"apple watch"), ("garmin", "Garmin", r"garmin"), ("samsung-galaxy-watch", "Samsung Galaxy Watch", r"galaxy watch"),
                         ("fitness-naramky", "Fitness náramky", r"náramek|band\b|\bfit\b"), ("chytre-prsteny", "Chytré prsteny", r"prsten|ring\b"),
                         ("amazfit", "Amazfit", r"amazfit"), ("huawei-a-xiaomi", "Huawei a Xiaomi", r"huawei|xiaomi|redmi")),
    "sluchatka": S_(("airpods", "AirPods", r"airpods"), ("pres-hlavu", "Sluchátka přes hlavu", r"přes (hlavu|uši)|over-?ear|wh-|quietcomfort|airpods max|studio pro|\bmax\b"),
                    ("do-usi", "Bezdrátová do uší", r"do uší|true wireless|\btws\b|buds|earbuds|wf-|pecky"), ("herni-sluchatka-audio", "Herní sluchátka", r"herní|gaming")),
    "reproduktory": S_(("prenosne-reproduktory", "Přenosné reproduktory", r"přenosn|bluetooth|jbl (charge|flip|go|clip|xtreme)|emberton|boombox"),
                       ("party-reproduktory", "Party reproduktory", r"party"), ("soundbary", "Soundbary", r"soundbar"),
                       ("chytre-reproduktory", "Chytré reproduktory", r"sonos|homepod|echo|nest|chytr")),
    "televize": S_(("oled-televize", "OLED televize", r"oled"), ("qled-televize", "QLED a Mini LED televize", r"qled|mini ?led|neo qled"),
                   ("televize-75-a-vice", "Televize 75\" a větší", r"\b(7[5-9]|8\d|9\d|100)\s?(\"|''|”|palc)"), ("televize-65", "Televize 65\"", r"\b6[5-9]\s?(\"|''|”|palc)"),
                   ("televize-55", "Televize 55\"", r"\b5[5-9]\s?(\"|''|”|palc)"), ("televize-do-50", "Televize do 50\"", r"\b([2-4]\d|50)\s?(\"|''|”|palc)"),
                   ("projektory", "Projektory", r"projektor|projector")),
    "fotoaparaty": S_(("akcni-kamery", "Akční kamery", r"gopro|insta360|akční|osmo action|osmo 360"), ("gimbaly-a-pocket", "Kapesní kamery a gimbaly", r"pocket|gimbal|osmo mobile"),
                      ("bezzrcadlovky", "Bezzrcadlovky", r"bezzrcadl|alpha|a7|eos r|nikon z|fujifilm x|lumix"), ("instantni-fotoaparaty", "Instantní fotoaparáty", r"instax|polaroid|instantn"),
                      ("objektivy", "Objektivy", r"objektiv")),
    "drony": S_(("dji-mini", "DJI Mini", r"dji mini"), ("dji-air-a-mavic", "DJI Air a Mavic", r"dji (air|mavic)"), ("fpv-drony", "FPV drony", r"fpv|avata"),
                ("drony-pro-zacatecniky", "Drony pro začátečníky", r"dji neo|dji flip|syma|začátečn")),
    "kavovary": S_(("automaticke-kavovary", "Automatické kávovary", r"automatick|magnifica|dinamica|eletta|primadonna|philips (ep|\d{4})"),
                   ("pakove-kavovary", "Pákové kávovary", r"pákov|espresso|lelit|sage|gaggia classic"), ("kapslove-kavovary", "Kapslové kávovary", r"nespresso|dolce gusto|vertuo|kapsl"),
                   ("mlynky-na-kavu", "Mlýnky na kávu", r"mlýnek")),
    "vysavace": S_(("roboticke-vysavace", "Robotické vysavače", r"robot|roborock|roomba|ecovacs|deebot|dreame (l|x)"), ("tycove-vysavace", "Tyčové vysavače", r"tyčov|dyson v\d|dyson gen|stick"),
                   ("mokre-vysavace", "Mopy a mokré vysavače", r"mop|mokr|wet|tineco|k[aä]rcher fc"), ("klasicke-vysavace", "Klasické vysavače", r"vysavač")),
    "kuchynske-spotrebice": S_(("kuchynske-roboty", "Kuchyňské roboty", r"kuchyňsk\w* robot|kitchenaid|thermomix|monsieur cuisine|kenwood"),
                               ("fritezy", "Horkovzdušné fritézy", r"fritéz|air ?fryer"), ("mixery", "Mixéry", r"mixér|blender"), ("rychlovarne-konvice", "Konvice", r"konvic"),
                               ("odstavovace", "Odšťavňovače", r"odšťav")),
    "pece-o-vlasy": S_(("dyson-airwrap-a-supersonic", "Dyson Airwrap a Supersonic", r"dyson"), ("feny", "Fény", r"fén|vysoušeč"), ("kulmy", "Kulmy", r"kulm"),
                       ("zehlicky-na-vlasy", "Žehličky na vlasy", r"žehličk|airstrait")),
    "tenisky": S_(("nike", "Nike", r"\bnike\b|jordan"), ("adidas", "adidas", r"adidas"), ("new-balance", "New Balance", r"new balance"), ("puma", "Puma", r"\bpuma\b"),
                  ("vans-a-converse", "Vans a Converse", r"\bvans\b|converse"), ("asics", "ASICS", r"asics"), ("bezecke-boty", "Běžecké boty", r"běžeck|running|\brun\b"),
                  ("onitsuka-tiger", "Onitsuka Tiger", r"onitsuka"), ("veja-a-ekologicke", "Veja", r"\bveja\b")),
    "damske-boty": S_(("kozacky", "Kozačky", r"kozačk|vysoké boty"), ("kotnikove-boty", "Kotníkové boty", r"kotníkov|chelsea|bot[ky]* do kotník"),
                      ("lodicky", "Lodičky", r"lodičk|pumps"), ("baleriny-a-mokasiny", "Baleríny a mokasíny", r"balerín|mokasín|loafer"),
                      ("sandaly-a-pantofle", "Sandály a pantofle", r"sandál|pantofl|žabk|mule"), ("trekove-boty", "Trekové a zimní boty", r"trekov|zimní|sněhul|outdoor")),
    "panske-boty": S_(("polobotky", "Polobotky", r"polobot|oxford|derby|společensk"), ("kotnikove-boty-panske", "Kotníkové boty", r"kotníkov|chelsea|farmářk"),
                      ("trekove-a-zimni", "Trekové a zimní boty", r"trekov|zimní|outdoor|turistick"), ("sandaly-panske", "Sandály a pantofle", r"sandál|pantofl|žabk"),
                      ("mokasiny", "Mokasíny", r"mokasín|loafer")),
    "damske-saty-a-sukne": S_(("sukne", "Sukně", r"sukně"), ("overaly", "Overaly", r"overal"), ("koktejlove-saty", "Koktejlové a večerní šaty", r"koktejl|večerní|společensk|plesov"),
                              ("maxi-saty", "Maxi šaty", r"maxi|dlouhé"), ("letni-saty", "Letní a plážové šaty", r"letní|plážov"), ("pletene-saty", "Pletené šaty", r"pleten|svetrov")),
    "damske-bundy-a-kabaty": S_(("kabaty", "Kabáty", r"kabát|trenčkot"), ("zimni-bundy", "Zimní bundy", r"zimní|péřov|prošívan|parka"), ("kozene-bundy", "Kožené bundy", r"kožen|ekokůž"),
                                ("vesty", "Vesty", r"vesta"), ("saka-damska", "Saka a blejzry", r"sako|blazer|blejzr"), ("prechodne-bundy", "Přechodné bundy", r"bunda|bomber|softshell")),
    "panske-bundy-a-kabaty": S_(("kabaty-panske", "Kabáty", r"kabát"), ("zimni-bundy-panske", "Zimní bundy", r"zimní|péřov|prošívan|parka"),
                                ("kozene-bundy-panske", "Kožené bundy", r"kožen"), ("vesty-panske", "Vesty", r"vesta"), ("prechodne-bundy-panske", "Přechodné bundy", r"bunda|bomber|softshell")),
    "damske-mikiny-a-svetry": S_(("mikiny", "Mikiny", r"mikin|hoodie"), ("svetry", "Svetry", r"svetr|pulovr|rolák"), ("kardigany", "Kardigany", r"kardigan|cardigan")),
    "panske-mikiny-a-svetry": S_(("mikiny-panske", "Mikiny", r"mikin|hoodie"), ("svetry-panske", "Svetry", r"svetr|pulovr|rolák"), ("kardigany-panske", "Kardigany", r"kardigan|cardigan")),
    "damska-tricka-a-topy": S_(("halenky-a-kosile", "Halenky a košile", r"halenk|košil"), ("tricka", "Trička", r"trič|triko|t-shirt"), ("topy-a-tilka", "Topy a tílka", r"top\b|topy|tílk|body")),
    "panska-tricka-a-kosile": S_(("kosile", "Košile", r"košil"), ("polokosile", "Polokošile", r"polokošil|polo\b"), ("tricka-panska", "Trička", r"trič|triko|t-shirt|tílk")),
    "damske-kalhoty-a-dziny": S_(("dziny", "Džíny", r"džín|jeans|rifl"), ("leginy", "Legíny", r"legín"), ("teplaky", "Tepláky", r"teplák|jogger"), ("sortky", "Šortky", r"šort|kraťas")),
    "panske-kalhoty-a-dziny": S_(("dziny-panske", "Džíny", r"džín|jeans|rifl"), ("chino", "Chino kalhoty", r"chino"), ("teplaky-panske", "Tepláky", r"teplák|jogger"),
                                 ("sortky-panske", "Šortky a kraťasy", r"šort|kraťas")),
    "damske-pradlo-a-plavky": S_(("podprsenky", "Podprsenky", r"podprsenk"), ("plavky", "Plavky", r"plavk|bikin"), ("pyzama", "Pyžama a župany", r"pyžam|župan|noční")),
    "kabelky": S_(("crossbody", "Crossbody kabelky", r"crossbody|přes rameno"), ("shopper", "Shopper a tote tašky", r"shopper|tote"), ("kozene-kabelky", "Kožené kabelky", r"kožen"),
                  ("psanicka", "Psaníčka", r"psaníčk|clutch"), ("ledvinky", "Ledvinky", r"ledvink")),
    "hodinky": S_(("damske-hodinky", "Dámské hodinky", r"dámsk|women|lady"), ("panske-hodinky", "Pánské hodinky", r"pánsk|\bmen\b|gent"),
                  ("chronografy", "Chronografy", r"chronograf"), ("casio-a-g-shock", "Casio a G-Shock", r"casio|g-shock")),
    "sperky": S_(("nahrdelniky", "Náhrdelníky a přívěsky", r"náhrdelník|řetízek|přívěs"), ("nausnice", "Náušnice", r"náušnic"), ("prsteny", "Prsteny", r"prsten"),
                 ("naramky", "Náramky", r"náram"), ("pandora-a-swarovski", "Pandora a Swarovski", r"pandora|swarovski")),
    "damske-parfemy": S_(("parfemovane-vody", "Parfémované vody (EDP)", r"parfémovan|eau de parfum|\bedp\b|parfum\b"), ("toaletni-vody", "Toaletní vody (EDT)", r"toaletní|eau de toilette|\bedt\b"),
                         ("darkove-sady", "Dárkové sady", r"dárkov|sada|set\b")),
    "panske-parfemy": S_(("parfemovane-vody-panske", "Parfémované vody (EDP)", r"parfémovan|eau de parfum|\bedp\b|parfum\b"),
                         ("toaletni-vody-panske", "Toaletní vody (EDT)", r"toaletní|eau de toilette|\bedt\b"), ("darkove-sady-panske", "Dárkové sady", r"dárkov|sada|set\b")),
    "kosmetika": S_(("make-up", "Make-up a líčení", r"make-?up|řasenk|rtěnk|stín|tvářenk|pudr|korektor|lesk na rty|bronzer"),
                    ("pletova-sera", "Pleťová séra", r"sérum|serum"), ("pletove-kremy", "Pleťové krémy", r"krém|cream")),
    "kola-a-kolobezky": S_(("elektrokola", "Elektrokola", r"elektrokol|e-?bike"), ("horska-kola", "Horská kola", r"horsk|mtb"), ("silnicni-a-gravel", "Silniční a gravel kola", r"silniční|gravel"),
                           ("elektrokolobezky", "Elektrokoloběžky", r"elektrokoloběž|e-?koloběž|elektrick\w* koloběž"), ("kolobezky", "Koloběžky", r"koloběž")),
    "zimni-sporty": S_(("lyze", "Lyže", r"lyže\b|sjezdov"), ("snowboardy", "Snowboardy", r"snowboard"), ("lyzarske-boty", "Lyžařské boty", r"lyžařsk\w* bot|bot\w* lyžař"),
                       ("helmy-a-bryle", "Helmy a brýle", r"helm|přilb|brýle"), ("bezky", "Běžky", r"běžk|běžeck\w* lyž"), ("skialpy", "Skialpy", r"skialp")),
    "fitness": S_(("bezecke-pasy", "Běžecké pásy", r"běžeck\w* pás"), ("rotopedy-a-spinning", "Rotopedy a spinningová kola", r"rotoped|spinning|cyklotrenažér"),
                  ("posilovani", "Posilování", r"čink|kettlebell|posilov|lavice|závaží"), ("trenazery", "Trenažéry", r"trenažér|veslov|eliptic")),
    "stany": S_(("turisticke-stany", "Turistické stany", r"turistick|trekov|ultralehk"), ("rodinne-stany", "Rodinné stany", r"rodinn|kemp|\b[4-8]\s?(os|místn)")),
    "hudebni-nastroje": S_(("elektricke-kytary", "Elektrické kytary", r"elektrick\w* kytar|stratocaster|telecaster|les paul"), ("akusticke-kytary", "Akustické kytary", r"akustick|klasick\w* kytar|kytar"),
                           ("baskytary", "Baskytary", r"baskytar"), ("klavesy-a-piana", "Klávesy a digitální piana", r"kláves|piano|syntezátor"), ("ukulele", "Ukulele", r"ukulele"),
                           ("bici", "Bicí", r"bicí|činel")),
}


def sub_of(p):
    """First matching hand-written subcategory (by name + brand)."""
    if p.get("sub"):
        return p["sub"]
    text = (p.get("name") or "") + " " + (p.get("brand") or "")
    for slug, _, rx in SUBS.get(p["cat"], []):
        if rx.search(text):
            return slug
    return ""


def sub_name(cat, slug):
    for s, n, _ in SUBS.get(cat, []):
        if s == slug:
            return n
    return TOY_SUB_NAMES.get((cat, slug), slug.replace("-", " ").capitalize())


SPORT_CATS = ["zimni-sporty", "kola-a-kolobezky", "fitness", "stany", "spacaky-a-karimatky", "outdoorove-batohy", "turistika", "cyklo-vybaveni", "brusle",
              "micove-sporty", "vodni-sporty", "sportovni-obleceni", "chytre-hodinky"]


def classify_any(rec, shop):
    """(category, subcategory) for any shop: toy shops use the hrackarium taxonomy, bookshops/pet shops/pharmacies their path."""
    tax = shop.get("tax")
    if tax == "toys":
        return classify_toy(rec, shop)
    if tax in ("books", "pets", "health"):
        return classify_path(rec, shop), ""
    return classify(rec, shop), ""
