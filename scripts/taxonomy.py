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
    "domov": ("Domov a spotřebiče", "Kávovary, vysavače, kuchyňské roboty", "kavovary"),
    "sport": ("Sport a hobby", "Lyže, kola, RC modely a kytary", "sport"),
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
    "kola-a-kolobezky": ("Kola a koloběžky", "sport", "Kola, elektrokola a koloběžky", "sport", 3000, 2500),
    "fitness": ("Fitness", "sport", "Fitness stroje a vybavení", "sport", 1500, 2000),
    "rc-modely": ("RC modely", "sport", "RC auta, lodě a modely", "rc-modely", 1000, 2500),
    "hudebni-nastroje": ("Hudební nástroje", "sport", "Kytary, klávesy a hudební nástroje", "hudba", 2000, 3000),
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
               r"palmrest|matrice|displej\w* (pro|do|k)|lcd panel|základní desk\w*|ventilátor (pro|do)|pant\w* (pro|do)|touchpad|klávesnice (pro|do|k)|"
               r"battery|nástav\w*|součást\w*|kartáč\w*|tyč\w*|selfie|filtr\w*|kombo|kytarov\w* (kombo|zesilovač)|podomítkov\w*|"
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
