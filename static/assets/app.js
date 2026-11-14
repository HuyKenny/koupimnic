/* KoupímNic — the whole shop runs here: cart, checkout, the "delivery", the receipt, savings and the wish quarantine.
   Everything stays in localStorage; nothing is sent anywhere and nothing is paid. No inline handlers (strict CSP). */
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
  var kc = function (n) { return Math.round(n || 0).toLocaleString("cs-CZ").replace(/\s/g, " ") + " Kč"; };
  var plural = function (n, a, b, c) { return n === 1 ? a : (n > 1 && n < 5 ? b : c); };
  var ICON = function (n, s) { s = s || 20; return '<svg class="i" width="' + s + '" height="' + s + '" aria-hidden="true"><use href="/img/ui/icons.svg#' + n + '"/></svg>'; };

  // ------------------------------------------------------------------ storage (versioned, survives blocked storage)
  var mem = {};
  function load(key, fb) {
    try { var v = localStorage.getItem("knc:" + key); return v ? JSON.parse(v) : fb; } catch (e) { return mem[key] !== undefined ? mem[key] : fb; }
  }
  function save(key, v) { mem[key] = v; try { localStorage.setItem("knc:" + key, JSON.stringify(v)); } catch (e) {} }
  var cart = load("cart:v1", []), orders = load("orders:v1", []), wants = load("wants:v1", []);
  if (!Array.isArray(cart)) cart = []; if (!Array.isArray(orders)) orders = []; if (!Array.isArray(wants)) wants = [];
  window.addEventListener("storage", function (e) {
    if (!e.key || e.key.indexOf("knc:") !== 0) return;
    cart = load("cart:v1", []); orders = load("orders:v1", []); wants = load("wants:v1", []);
    refreshHeader(); if ($("#cart") && !$("#cart").hidden) renderDrawer();
  });
  function setCart(c) { cart = c; save("cart:v1", c); refreshHeader(); }
  function setOrders(o) { orders = o.slice(0, 40); save("orders:v1", orders); refreshHeader(); }
  function setWants(w) { wants = w.slice(0, 60); save("wants:v1", wants); }

  var cartCount = function () { return cart.reduce(function (s, x) { return s + x.q; }, 0); };
  var cartSum = function (c) { return (c || cart).reduce(function (s, x) { return s + x.p * x.q; }, 0); };
  var savedTotal = function () { return orders.reduce(function (s, o) { return s + (o.cancelled ? 0 : o.total); }, 0); };

  // ------------------------------------------------------------------ header, toast
  function refreshHeader() {
    var n = cartCount();
    $$("[data-count]").forEach(function (b) { b.hidden = !n; if (b.textContent !== String(n)) { b.textContent = n; b.classList.remove("pop"); void b.offsetWidth; b.classList.add("pop"); } });
    $$("[data-saved]").forEach(function (s) { s.textContent = kc(savedTotal()); });
    var hero = $("[data-saved-hero]");
    if (hero && savedTotal() > 0) { hero.hidden = false; hero.textContent = "Zatím jsi tu neutratil " + kc(savedTotal()); }
    orderPill();
  }
  var toastT;
  function toast(html) {
    var t = $("#toast"); if (!t) return;
    t.innerHTML = html; t.hidden = false; clearTimeout(toastT);
    toastT = setTimeout(function () { t.hidden = true; }, 3200);
  }

  // ------------------------------------------------------------------ cart actions
  function addItem(d, size, quiet) {
    var key = d.id + "|" + (size || "");
    var c = cart.slice(), found = false;
    c.forEach(function (x) { if (x.k === key) { x.q = Math.min(9, x.q + 1); found = true; } });
    if (!found) c.unshift({ k: key, id: d.id, n: d.n, b: d.b, p: d.p, w: d.w, i: d.i, s: d.s, g: d.g, u: d.u, c: d.c, size: size || "", q: 1 });
    setCart(c.slice(0, 40));
    track("add_to_cart", { value: d.p });
    if (!quiet) toast(ICON("check") + "<span>V košíku. Zatím to stojí 0&nbsp;Kč.</span><a href=\"/kosik/\">Košík</a>");
  }
  document.addEventListener("click", function (e) {
    var a = e.target.closest("[data-add]");
    if (a) {
      e.preventDefault();
      try { addItem(JSON.parse(a.getAttribute("data-add"))); a.classList.add("ok"); a.innerHTML = ICON("check"); } catch (err) {}
      return;
    }
    var b = e.target.closest("[data-buy]");
    if (b) {
      var box = b.closest("[data-item]"); if (!box) return;
      var d = JSON.parse(box.getAttribute("data-item")), sz = $("input[name=size]:checked", box);
      addItem(d, sz ? sz.value : "", b.getAttribute("data-buy") === "now");
      if (b.getAttribute("data-buy") === "now") location.href = "/pokladna/"; else openCart();
      return;
    }
    if (e.target.closest("[data-open-cart]")) { openCart(); return; }
    if (e.target.closest("#cart [data-close]")) { closeCart(); return; }
    var q = e.target.closest("[data-q]");
    if (q) { changeQty(q.getAttribute("data-k"), +q.getAttribute("data-q")); return; }
    var t = e.target.closest("[data-thumb]") || e.target.closest(".thumbs button");
    if (t && $("#gmain")) { $("#gmain").src = t.getAttribute("data-src"); $$(".thumbs button").forEach(function (x) { x.classList.toggle("on", x === t); }); return; }
    var m = e.target.closest("[data-more]");
    if (m) { var el = document.getElementById(m.getAttribute("data-more")); if (el) el.classList.remove("clamp"); m.remove(); return; }
    var go = e.target.closest("a[data-go]");
    if (go) track("affiliate_click", { shop: go.getAttribute("data-go") });
  });
  function changeQty(k, dq) {
    var c = cart.map(function (x) { return x.k === k ? Object.assign({}, x, { q: dq === 0 ? 0 : Math.max(0, Math.min(9, x.q + dq)) }) : x; }).filter(function (x) { return x.q > 0; });
    setCart(c); renderDrawer(); if ($("[data-flow=cart]")) flowCart($("#flow")); if ($("[data-flow=checkout]")) flowCheckout($("#flow"));
  }

  // ------------------------------------------------------------------ drawer
  function linesHtml(c, editable) {
    return '<ul class="lines">' + c.map(function (x) {
      return '<li class="line"><img src="' + esc(x.i) + '" alt="" loading="lazy" referrerpolicy="no-referrer"><div><a class="line__n" href="' + esc(x.u) + '">' + esc(x.n) + '</a>'
        + '<div class="line__m">' + esc(x.s) + (x.size ? " · vel. " + esc(x.size) : "") + '</div>'
        + (editable ? '<div class="qty"><button type="button" data-q="-1" data-k="' + esc(x.k) + '" aria-label="Méně">' + ICON("minus", 14) + '</button><span>' + x.q + '</span>'
          + '<button type="button" data-q="1" data-k="' + esc(x.k) + '" aria-label="Více">' + ICON("plus", 14) + '</button> <button class="rm" type="button" data-q="0" data-k="' + esc(x.k) + '">Odebrat</button></div>' : (x.q > 1 ? '<div class="line__m">' + x.q + ' ks</div>' : ""))
        + '</div><div class="line__p">' + kc(x.p * x.q) + '</div></li>';
    }).join("") + "</ul>";
  }
  function totalsHtml(sum, extra) {
    return '<div class="totals"><p><span>Mezisoučet</span><span>' + kc(sum) + '</span></p>' + (extra || "")
      + '<p class="disc"><span>Sleva „Nic nekupuju“</span><span>−' + kc(sum) + '</span></p><p class="pay"><span>K úhradě</span><b>0 Kč</b></p></div>';
  }
  function emptyHtml() {
    return '<div class="empty"><img src="/img/ui/box-empty.webp" alt="" width="150" height="150"><p><b>Košík je prázdný.</b><br>Na rozdíl od krabice, která ti přijde, se to dá změnit.</p>'
      + '<p><a class="btn" href="/">Jdu vybírat</a></p></div>';
  }
  function renderDrawer() {
    var b = $("#cart-body"); if (!b) return;
    if (!cart.length) { b.innerHTML = emptyHtml(); return; }
    b.innerHTML = linesHtml(cart, true) + totalsHtml(cartSum()) + '<a class="btn btn--lg" style="width:100%" href="/pokladna/">K pokladně, platí se 0 Kč</a>'
      + '<p class="muted" style="font-size:13px;text-align:center;margin-top:10px">Ceny jsou skutečné ceny obchodů. Ty nezaplatíš nic.</p>';
  }
  var lastFocus;
  function openCart() { var d = $("#cart"); if (!d) return; lastFocus = document.activeElement; renderDrawer(); d.hidden = false; document.body.style.overflow = "hidden"; var x = $(".x", d); if (x) x.focus(); }
  function closeCart() { var d = $("#cart"); if (!d) return; d.hidden = true; document.body.style.overflow = ""; if (lastFocus) lastFocus.focus(); }
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && $("#cart") && !$("#cart").hidden) closeCart(); });

  // ------------------------------------------------------------------ images: wsrv.nl fallback to the shop's original
  document.addEventListener("error", function (e) {
    var im = e.target;
    if (im.tagName !== "IMG") return;
    var o = im.getAttribute("data-orig");
    if (o && im.src !== o) { im.setAttribute("data-orig", ""); im.src = o; }
    else if (im.src.indexOf("placeholder.svg") < 0) im.src = "/img/ui/placeholder.svg";
  }, true);

  // ------------------------------------------------------------------ listing: sort / filter from the listing JSON
  function cardHtml(r, brands) {
    var d = { id: r[0], n: r[1], b: r[2] >= 0 ? brands[r[2]] : "", p: r[3], w: r[4], i: r[5], s: r[6], g: r[7], u: "/produkt/" + r[0] + "/" };
    var off = d.w > d.p ? Math.round(100 * (d.w - d.p) / d.w) : 0;
    return '<article class="card"><a class="card__a" href="' + d.u + '"><span class="card__img"><img src="' + esc(d.i || "/img/ui/placeholder.svg") + '" alt="" loading="lazy" referrerpolicy="no-referrer" width="320" height="320">'
      + (off >= 5 ? '<span class="card__off">−' + off + ' %</span>' : "") + '</span><span class="card__b">' + (esc(d.b) || "&nbsp;") + '</span><span class="card__n">' + esc(d.n) + '</span>'
      + '<span class="card__p"><b>' + kc(d.p) + '</b>' + (off >= 5 ? "<s>" + kc(d.w) + "</s>" : "") + '</span></a>'
      + '<button class="card__add" type="button" data-add="' + esc(JSON.stringify(d)) + '" aria-label="Přidat do košíku">' + ICON("plus") + '</button></article>';
  }
  var tools = $(".tools[data-list]");
  if (tools) {
    var data = null, shown = 48, grid = $("[data-grid]"), pager = $(".pg");
    var apply = function () {
      var sort = ($("[data-sort]", tools) || {}).value || "", br = ($("[data-brand]", tools) || {}).value || "", pr = ($("[data-price]", tools) || {}).value || "";
      if (!sort && !br && !pr) { location.reload(); return; }
      var lo = 0, hi = 1e12;
      if (pr) { var a = pr.split("-"); lo = +a[0] || 0; hi = a[1] ? +a[1] : 1e12; }
      var bi = br ? data.b.indexOf(br) : -1;
      var rows = data.i.filter(function (r) { return (!br || r[2] === bi) && r[3] >= lo && r[3] <= hi; });
      if (sort === "p") rows.sort(function (a, b) { return a[3] - b[3]; });
      if (sort === "-p") rows.sort(function (a, b) { return b[3] - a[3]; });
      if (sort === "d") rows.sort(function (a, b) { return (b[4] > b[3] ? (b[4] - b[3]) / b[4] : 0) - (a[4] > a[3] ? (a[4] - a[3]) / a[4] : 0); });
      var html = rows.slice(0, shown).map(function (r) { return cardHtml(r, data.b); }).join("");
      grid.innerHTML = rows.length ? '<div class="grid">' + html + "</div>" + (rows.length > shown ? '<div class="more-wrap"><button class="btn btn--ghost" type="button" data-showmore>Ukázat další</button></div>' : "")
        : '<p class="empty">Nic takového tu není. Jako ve tvé krabici.</p>';
      if (pager) pager.hidden = true;
      var n = $(".tools__n b", tools); if (n) n.textContent = rows.length.toLocaleString("cs-CZ");
    };
    tools.addEventListener("change", function () {
      shown = 48;
      if (data) return apply();
      fetch(tools.getAttribute("data-list")).then(function (r) { return r.json(); }).then(function (j) { data = j; apply(); }).catch(function () {});
    });
    document.addEventListener("click", function (e) { if (e.target.closest("[data-showmore]")) { shown += 48; apply(); } });
  }

  // ------------------------------------------------------------------ search (static index: data/sug.json + data/s/<2 letters>.json)
  var fold = function (s) { return (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, ""); };
  var sugCache = {}, sugAll = null;
  function getJSON(u) { if (!sugCache[u]) sugCache[u] = fetch(u).then(function (r) { return r.ok ? r.json() : []; }).catch(function () { return []; }); return sugCache[u]; }
  function searchRows(q) {
    var words = fold(q).match(/[a-z0-9]+/g) || [];
    if (!words.length || words[0].length < 2) return Promise.resolve({ c: [], p: [] });
    return Promise.all([getJSON("/data/sug.json"), getJSON("/data/s/" + words[0].slice(0, 2) + ".json")]).then(function (res) {
      var hit = function (t) { var f = fold(t); return words.every(function (w) { return f.indexOf(w) >= 0; }); };
      return { c: res[0].filter(function (r) { return hit(r[0]); }).slice(0, 4), p: res[1].filter(function (r) { return hit(r[1] + " " + r[2]); }) };
    });
  }
  var qi = $("#q"), sg = $("#sugg");
  if (qi && sg) {
    var st;
    qi.addEventListener("input", function () {
      clearTimeout(st);
      st = setTimeout(function () {
        if (qi.value.trim().length < 2) { sg.hidden = true; return; }
        searchRows(qi.value).then(function (r) {
          var html = r.c.map(function (c) { return '<a href="' + c[1] + '"><span class="k">' + ({ k: "Kategorie", o: "Oddělení", z: "Značka" }[c[2]] || "") + '</span>' + esc(c[0]) + '</a>'; }).join("")
            + r.p.slice(0, 7).map(function (p) { return '<a href="/produkt/' + p[0] + '/"><img src="' + esc(p[4]) + '" alt="" referrerpolicy="no-referrer">' + esc(p[1]) + '<small>' + kc(p[3]) + '</small></a>'; }).join("");
          sg.innerHTML = html || '<p class="muted" style="padding:8px 10px;margin:0">Nic. Ale to tady umíme.</p>'; sg.hidden = false;
        });
      }, 160);
    });
    document.addEventListener("click", function (e) { if (!e.target.closest(".search")) sg.hidden = true; });
  }

  // ------------------------------------------------------------------ the "delivery"
  var STAGES = [
    { t: 0, n: "Objednávka přijata", notes: ["Systém zaznamenal tvoji objednávku. Taky zaznamenal, že jsi nic nezaplatil. Obojí je v pořádku."] },
    { t: 25, n: "Hledáme zboží ve skladu", notes: ["Skladník Ignác prochází regály. Zatím nic. To je dobrá zpráva.", "Čtečka čárových kódů pípá naprázdno."] },
    { t: 90, n: "Balíme", notes: ["Bublinková fólie se pečlivě omotává kolem ničeho.", "Krabice je zalepená. Váží přesně tolik co krabice."] },
    { t: 180, n: "Předáno kurýrovi", notes: ["Kurýr naložil balík a nedůvěřivě s ním zatřásl.", "Balík je na cestě. Nic v něm nedrnčí."] },
    { t: 360, n: "Kurýr je ve tvé ulici", notes: ["Hledá číslo popisné. Tvoje peníze mezitím zůstávají na účtu.", "Parkuje. Na chodníku, ale jen nanečisto."] },
    { t: 480, n: "Doručeno", notes: ["Crrr. Někdo zvoní."] }
  ];
  var COURIERS = ["Vavřinec Nikdo", "Prokop Prázdný", "Bohdana Bezobsahová", "Igor Ničeho", "Žofie Zbytečná", "Dalibor Doručil"];
  var SHIP = [["kuryr", "Kurýr Nikdo", "Doručí dnes, pokud vůbec"], ["zasilkovna", "Výdejní místo Nikde 0", "Otevřeno nonstop, nikdo tam není"], ["sklad", "Osobní odběr", "Z prázdného skladu v Prázdninové ulici"], ["dron", "Dron", "Přiletí s ničím, zato rychle"]];
  var PAY = [["nic", "Peněženka Nic", "Zůstatek 0 Kč, a stačí"], ["karta", "Karta 0000 •••• 0000", "Číslo nezadáváš, nemělo by kam"], ["faktura", "Na fakturu", "Kterou nikdo nepošle"], ["dobirka", "Dobírka 0 Kč", "Kurýrovi nic nedáváš, on tobě taky ne"]];
  var hash = function (s) { var h = 0; for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return Math.abs(h); };
  function stageOf(o, now) {
    if (o.opened) return STAGES.length;
    var el = ((now || Date.now()) - o.at) / 1000 + (o.skip || 0), k = 0;
    for (var i = 0; i < STAGES.length; i++) if (el >= STAGES[i].t) k = i;
    return k;
  }
  function orderPill() {
    var p = $("#orderpill"); if (!p) return;
    if ($("[data-flow=order]")) { p.hidden = true; return; }
    var o = orders.filter(function (x) { return !x.opened && !x.cancelled && Date.now() - x.at < 864e5; })[0];
    if (!o) { p.hidden = true; return; }
    var k = stageOf(o);
    p.outerHTML = '<a class="orderpill" id="orderpill" href="/objednavka/#' + o.id + '"><span class="dot"></span><span>' + (k >= 5 ? "<b>Kurýr zvoní.</b> Otevři dveře" : "Zásilka " + o.id + ": <b>" + STAGES[k].n + "</b>") + "</span></a>";
  }
  setInterval(function () { if (document.visibilityState === "visible") orderPill(); }, 15000);

  var actx;
  function ring() {
    try {
      actx = actx || new (window.AudioContext || window.webkitAudioContext)();
      [[659.3, 0], [523.3, .42]].forEach(function (f) {
        var o = actx.createOscillator(), g = actx.createGain(), t = actx.currentTime + f[1];
        o.type = "sine"; o.frequency.value = f[0]; o.connect(g); g.connect(actx.destination);
        g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.35, t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.9);
        o.start(t); o.stop(t + 1);
      });
      if (navigator.vibrate) navigator.vibrate([120, 80, 120]);
    } catch (e) {}
  }
  function confetti() {
    if (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    var c = document.createElement("div"), cols = ["#4B1D6B", "#C8F169", "#FF6B4A", "#7A3FA0", "#1A1423"];
    c.className = "confetti";
    for (var i = 0; i < 70; i++) {
      var s = document.createElement("i");
      s.style.left = Math.random() * 100 + "%"; s.style.background = cols[i % cols.length];
      s.style.animationDuration = (1.8 + Math.random() * 1.8) + "s"; s.style.animationDelay = (Math.random() * .4) + "s";
      c.appendChild(s);
    }
    document.body.appendChild(c); setTimeout(function () { c.remove(); }, 4200);
  }

  // ------------------------------------------------------------------ flow pages
  function flowCart(el) {
    if (!cart.length) { el.innerHTML = emptyHtml(); return; }
    el.innerHTML = linesHtml(cart, true) + totalsHtml(cartSum()) + '<p><a class="btn btn--lg" href="/pokladna/">Pokračovat k pokladně</a></p>';
  }
  function optsHtml(name, rows) {
    return '<div class="opts">' + rows.map(function (r, i) { return '<label class="opt"><input type="radio" name="' + name + '" value="' + r[0] + '"' + (i === 0 ? " checked" : "") + '><span><b>' + esc(r[1]) + '</b><small>' + esc(r[2]) + '</small></span></label>'; }).join("") + "</div>";
  }
  var newId = function () { return "KN-" + String(Date.now()).slice(-6) + String(Math.floor(Math.random() * 90 + 10)); };
  function flowCheckout(el) {
    if (!cart.length) { el.innerHTML = emptyHtml(); return; }
    var sum = cartSum();
    el.innerHTML = '<div class="steps-co">'
      + '<section class="co-sec"><h2><i>1</i>Doprava</h2>' + optsHtml("ship", SHIP) + '</section>'
      + '<section class="co-sec"><h2><i>2</i>Doručovací údaje</h2><div class="fake"><div><span>Jméno</span><b>Nikdo Nikdovič</b></div><div><span>Adresa</span><b>Prázdná 0, 000 00 Nikde</b></div>'
      + '<div><span>Telefon</span><b>nevyplňuješ, nikdo nezavolá</b></div></div><p class="muted" style="font-size:13px;margin:10px 0 0">Žádné osobní údaje nechceme. Tyhle jsou smyšlené a stejné pro všechny.</p></section>'
      + '<section class="co-sec"><h2><i>3</i>Platba</h2>' + optsHtml("pay", PAY) + '</section>'
      + '<section class="co-sec"><h2><i>4</i>Shrnutí</h2>' + linesHtml(cart, false) + totalsHtml(sum, '<p><span>Doprava</span><span>0 Kč</span></p>')
      + '<label class="agree"><input type="checkbox" id="agree"> <span>Beru na vědomí, že mi nic nepřijde a že je to přesně ono.</span></label>'
      + '<button class="btn btn--lg btn--lime" type="button" id="paybtn" disabled>Zaplatit 0 Kč</button><div id="paystate" aria-live="polite"></div></section></div>';
    var ag = $("#agree"), pb = $("#paybtn"), lock = false;
    ag.addEventListener("change", function () { pb.disabled = !ag.checked; });
    pb.addEventListener("click", function () {
      if (lock || !ag.checked) return; lock = true; pb.disabled = true;
      var msgs = ["Ověřujeme, že nic neplatíš…", "Banka nic nezaznamenala. Výborně.", "Hotovo."], i = 0;
      var ps = $("#paystate"); ps.innerHTML = '<p class="paying"><span class="spin"></span><span>' + msgs[0] + "</span></p>";
      var t = setInterval(function () { i++; if (i < msgs.length) $("span:last-child", ps).textContent = msgs[i]; }, 700);
      setTimeout(function () {
        clearInterval(t);
        var id = newId(), ship = ($("input[name=ship]:checked") || {}).value || "kuryr", pay = ($("input[name=pay]:checked") || {}).value || "nic";
        var o = { id: id, at: Date.now(), items: cart.map(function (x) { return { id: x.id, n: x.n, p: x.p, q: x.q, i: x.i, s: x.s, g: x.g, u: x.u, size: x.size }; }),
          total: cartSum(), ship: ship, pay: pay, courier: COURIERS[hash(id) % COURIERS.length], skip: 0 };
        setOrders([o].concat(orders)); setCart([]);
        track("purchase", { value: 0, items: o.items.length });
        location.href = "/objednavka/#" + id;
      }, 2200);
    });
  }
  var timer;
  function flowOrder(el) {
    var id = location.hash.slice(1), o = orders.filter(function (x) { return x.id === id; })[0] || orders[0];
    if (!o) { el.innerHTML = '<h1>Žádná objednávka</h1><p>Zatím sis nic nekoupil. Napravit se to dá během chvilky a za 0 Kč.</p><p><a class="btn" href="/">Jdu vybírat</a></p>'; return; }
    if (location.hash.slice(1) !== o.id) history.replaceState(null, "", "#" + o.id);
    clearInterval(timer);
    var draw = function () {
      var k = stageOf(o), total = STAGES[STAGES.length - 1].t, el2 = Math.min(total, (Date.now() - o.at) / 1000 + (o.skip || 0));
      if (o.opened) { receipt(el, o); clearInterval(timer); return; }
      var st = STAGES[Math.min(k, STAGES.length - 1)], note = st.notes[hash(o.id + k) % st.notes.length];
      var pos = 6 + 88 * Math.min(1, Math.max(0, (el2 - 180) / (total - 180)));
      var tl = STAGES.map(function (s, i) {
        var at = new Date(o.at + (s.t - (o.skip || 0)) * 1000);
        return '<li class="' + (i < k ? "done" : i === k ? "now" : "") + '"><span>' + s.n + '</span><small>' + (i <= k ? at.toLocaleTimeString("cs-CZ", { hour: "2-digit", minute: "2-digit" }) : "") + "</small></li>";
      }).join("");
      var left = Math.max(0, Math.ceil((total - el2) / 60));
      el.innerHTML = '<div class="ord__h"><h1>Objednávka je na cestě</h1><span class="ord__id">' + o.id + " · " + kc(o.total) + " → 0 Kč</span></div>"
        + '<section class="track"><div class="road"><span class="road__wh">' + ICON("box") + '</span><span class="road__home">' + ICON("bell") + '</span>'
        + '<span class="road__c" style="left:' + (k < 3 ? 12 : Math.max(12, pos)) + '%"><img src="/img/ui/courier.webp" alt="" width="104" height="75"></span></div>'
        + '<p class="stage">' + (k >= 5 ? "Kurýr zvoní" : st.n) + '</p><p class="stage__note">' + esc(note) + (k >= 3 && k < 5 ? " Kurýr: " + esc(o.courier) + "." : "") + "</p>"
        + '<div class="bar"><i style="width:' + Math.round(100 * el2 / total) + '%"></i></div>'
        + (k >= 5 ? '<div class="door"><p>Na rohožce stojí krabice. Podezřele lehká.</p><button class="btn btn--lg btn--lime" type="button" id="opendoor">' + ICON("box") + "Otevřít dveře a rozbalit</button></div>"
          : '<p class="muted" style="margin:10px 0 0">Doručení zhruba za ' + left + " " + plural(left, "minutu", "minuty", "minut") + ". Můžeš mezitím nakupovat dál, zazvoníme.</p>"
            + '<div class="ord__act"><button class="btn btn--sm btn--ghost" type="button" id="skip">Přeskočit čekání</button><a class="btn btn--sm btn--ghost" href="/">Nakupovat dál</a></div>')
        + '<ol class="tl">' + tl + "</ol></section>"
        + '<details class="co-sec"><summary><b>Co jsi objednal (' + o.items.length + ')</b></summary>' + linesHtml(o.items.map(function (x) { return Object.assign({ k: x.id }, x); }), false) + "</details>";
      var sk = $("#skip");
      if (sk) sk.addEventListener("click", function () { o.skip = total - (Date.now() - o.at) / 1000; persist(o); if (actx && actx.resume) actx.resume(); draw(); });
      var od = $("#opendoor");
      if (od) {
        try { if (!sessionStorage.getItem("knc:rang:" + o.id)) { ring(); sessionStorage.setItem("knc:rang:" + o.id, "1"); } } catch (e) { ring(); }
        od.addEventListener("click", function () { ring(); unbox(el, o); });
      }
    };
    draw();
    timer = setInterval(function () { if (document.visibilityState === "visible") draw(); }, 1000);
  }
  function persist(o) { setOrders(orders.map(function (x) { return x.id === o.id ? o : x; })); }
  function unbox(el, o) {
    clearInterval(timer);
    el.innerHTML = '<div class="unbox"><p class="unbox__t">Rozbal to</p><button class="box" type="button" id="box" aria-label="Otevřít krabici"><span class="box__note">nic :)</span>'
      + '<span class="box__l"></span><span class="box__r"></span><span class="box__tape"></span><span class="box__body"></span></button><p class="muted">Klepni na krabici.</p></div>';
    $("#box").addEventListener("click", function () {
      var b = this; if (b.classList.contains("open")) return;
      b.classList.add("open"); confetti();
      setTimeout(function () { o.opened = Date.now(); persist(o); receipt(el, o, true); }, 1800);
    }, { once: false });
  }
  var EQUIV = [[79, "káv v kavárně", "káva", "kávy"], [239, "pizz z rozvozu", "pizza", "pizzy"], [229, "lístků do kina", "lístek do kina", "lístky do kina"], [259, "měsíců streamování", "měsíc streamování", "měsíce streamování"]];
  function wage() { var w = +load("wage:v1", 35000); return w > 1000 ? w : 35000; }
  function equivHtml(sum) {
    var hours = sum / (wage() / 168);
    var rows = EQUIV.map(function (e) { var n = Math.floor(sum / e[0]); return n >= 1 ? '<div><b>' + n.toLocaleString("cs-CZ") + '</b><span>' + (n === 1 ? e[2] : n < 5 ? e[3] : e[1]) + '</span></div>' : ""; }).join("");
    return '<div class="equiv"><div><b>' + (hours >= 10 ? Math.round(hours) : hours.toFixed(1).replace(".", ",")) + ' h</b><span>tvojí práce, kterou nemusíš odpracovat</span></div>' + rows + "</div>"
      + '<p class="wage"><label for="wage">Počítáme s čistou mzdou</label><input id="wage" type="number" min="5000" step="1000" inputmode="numeric" value="' + wage() + '"> Kč měsíčně (168 h). Ostatní ceny jsou orientační.</p>';
  }
  function receipt(el, o, fresh) {
    var d = new Date(o.at), items = o.items.map(function (x) { return '<p class="r"><span>' + (x.q > 1 ? x.q + "× " : "") + esc(x.n) + '</span><span>' + kc(x.p * x.q) + "</span></p>"; }).join("");
    var real = o.items.map(function (x) {
      var w = wants.some(function (y) { return y.id === x.id; });
      return '<li class="want"><img src="' + esc(x.i) + '" alt="" loading="lazy" referrerpolicy="no-referrer"><div class="want__n"><b>' + esc(x.n) + '</b><br><span class="muted">' + kc(x.p) + " u obchodu " + esc(x.s) + "</span></div>"
        + '<div class="want__a"><button class="btn btn--sm btn--ghost" type="button" data-want="' + esc(x.id) + '"' + (w ? " disabled" : "") + ">" + ICON("clock", 16) + (w ? "V karanténě" : "Karanténa 72 h") + "</button>"
        + '<a class="btn btn--sm btn--ghost" href="' + esc(x.g) + '" rel="sponsored nofollow noopener" target="_blank" data-go="1">Fakt to chci ' + ICON("ext", 14) + '</a> <span class="tag-ad">Reklama</span></div></li>';
    }).join("");
    el.innerHTML = '<div class="ord__h"><h1>' + (fresh ? "Doručeno. Uvnitř nic." : "Účtenka") + '</h1><span class="ord__id">' + o.id + "</span></div>"
      + '<div class="receipt"><h2>KOUPÍMNIC.CZ</h2><p class="c">Nákupní galerie nanečisto</p><p class="c">' + d.toLocaleDateString("cs-CZ") + " " + d.toLocaleTimeString("cs-CZ", { hour: "2-digit", minute: "2-digit" }) + " · č. " + o.id + "</p><hr>"
      + items + '<hr><p class="r big"><span>CELKEM</span><span>' + kc(o.total) + '</span></p><p class="r"><span>Sleva za rozum</span><span>−' + kc(o.total) + '</span></p>'
      + '<p class="r big"><span>K ÚHRADĚ</span><span>0,00 Kč</span></p><hr><p class="saved">NEUTRACENO<b>' + kc(o.total) + "</b></p>"
      + '<p class="c">Doručil: ' + esc(o.courier) + '. Uvnitř: nic, přesně podle objednávky.</p><span class="stamp">ZAPLACENO<br>NIČÍM</span></div>'
      + "<h2>Za tyhle peníze by sis mohl dát</h2>" + equivHtml(o.total)
      + '<div class="piggy"><img src="/img/ui/piggy.webp" alt="" width="96" height="96"><div><span class="muted">Celkem jsi na KoupímNic neutratil</span><b>' + kc(savedTotal()) + "</b>"
      + '<button class="btn btn--sm btn--ghost" type="button" id="share">' + ICON("share", 16) + "Pochlubit se</button></div></div>"
      + "<h2>Pořád to chceš?</h2><p>Dej tomu tři dny v karanténě. Když tě to pak pořád bude lákat, koupíš to s čistým svědomím. Odkaz „Fakt to chci“ vede do obchodu a je reklamní.</p>"
      + '<ul class="wants">' + real + "</ul>"
      + '<p class="honestbox">Poctivě: z účtu ti nic neubylo, takže jsi nic „neušetřil“ v pravém smyslu. Jen ses nenechal unést. I to se počítá.</p>'
      + '<p class="ord__act"><a class="btn" href="/">Nakoupit znovu nanečisto</a><a class="btn btn--ghost" href="/moje-uspory/">Moje úspory</a></p>';
    bindReceipt(el);
  }
  function bindReceipt(el) {
    var w = $("#wage", el);
    if (w) w.addEventListener("change", function () { var v = Math.max(5000, +w.value || 35000); save("wage:v1", v); var f = $("#flow"); if ($("[data-flow=order]")) flowOrder(f); else flowSavings(f); });
    $$("[data-want]", el).forEach(function (b) {
      b.addEventListener("click", function () {
        var id = b.getAttribute("data-want"), it = null;
        orders.forEach(function (o) { o.items.forEach(function (x) { if (x.id === id) it = x; }); });
        if (!it || wants.some(function (y) { return y.id === id; })) return;
        setWants([Object.assign({ at: Date.now() }, it)].concat(wants));
        b.disabled = true; b.innerHTML = ICON("clock", 16) + "V karanténě";
        toast("Do karantény. Ozvi se za 72 hodin v <a href=\"/moje-uspory/\">Mých úsporách</a>.");
      });
    });
    var sh = $("#share", el);
    if (sh) sh.addEventListener("click", function () {
      var txt = "Na KoupímNic jsem si nakoupil za " + kc(savedTotal()) + " a nezaplatil ani korunu. https://koupimnic.cz";
      if (navigator.share) navigator.share({ text: txt }).catch(function () {});
      else if (navigator.clipboard) navigator.clipboard.writeText(txt).then(function () { toast("Zkopírováno. Teď už se jen pochlubit."); });
    });
  }
  function flowSavings(el) {
    var tot = savedTotal(), act = orders.filter(function (o) { return !o.cancelled; });
    var H = 72 * 36e5, now = Date.now();
    var wl = wants.map(function (x) {
      var left = x.at + H - now, ready = left <= 0, hrs = Math.ceil(left / 36e5);
      return '<li class="want"><img src="' + esc(x.i) + '" alt="" loading="lazy" referrerpolicy="no-referrer"><div class="want__n"><b>' + esc(x.n) + "</b><br>"
        + (ready ? '<span style="color:var(--green);font-weight:700">Tři dny uplynuly. Pořád to chceš?</span>' : '<span class="muted">V karanténě ještě ' + hrs + " " + plural(hrs, "hodinu", "hodiny", "hodin") + "</span>") + "</div>"
        + '<div class="want__a">' + (ready ? '<a class="btn btn--sm" href="' + esc(x.g) + '" rel="sponsored nofollow noopener" target="_blank" data-go="1">Ano, koupit u ' + esc(x.s) + "</a> " : "")
        + '<button class="btn btn--sm btn--ghost" type="button" data-unwant="' + esc(x.id) + '">' + (ready ? "Ne, pustit z hlavy" : "Už to nechci") + "</button>"
        + (ready ? ' <span class="tag-ad">Reklama</span>' : "") + "</div></li>";
    }).join("");
    el.innerHTML = '<div class="piggy"><img src="/img/ui/piggy.webp" alt="" width="96" height="96"><div><span class="muted">Celkem neutraceno</span><b>' + kc(tot) + "</b>"
      + '<span class="muted">' + act.length + " " + plural(act.length, "objednávka", "objednávky", "objednávek") + " nanečisto</span></div></div>"
      + (tot ? "<h2>To je</h2>" + equivHtml(tot) : '<p>Zatím nic. Prasátko čeká na první nákup, který nezaplatíš. <a class="lnk" href="/">Jdu vybírat</a></p>')
      + "<h2>Karanténa přání</h2>" + (wl ? '<ul class="wants">' + wl + "</ul>" : '<p class="muted">Prázdná. Věci sem dáš z účtenky po „doručení“.</p>')
      + (act.length ? "<h2>Historie</h2><ul class=\"hist\">" + act.map(function (o) {
        return '<li><a href="/objednavka/#' + o.id + '"><span><b>' + o.id + "</b> · " + o.items.length + " " + plural(o.items.length, "položka", "položky", "položek")
          + "<br><small>" + new Date(o.at).toLocaleDateString("cs-CZ") + "</small></span><span><b>" + kc(o.total) + "</b><br><small>" + (o.opened ? "rozbaleno" : "na cestě") + "</small></span></a></li>";
      }).join("") + "</ul>" : "")
      + '<p class="muted" style="margin-top:24px;font-size:14px">Všechno je uložené jen v tomhle prohlížeči. <button class="rm" type="button" id="wipe">Smazat moje data</button></p>';
    bindReceipt(el);
    $$("[data-unwant]", el).forEach(function (b) { b.addEventListener("click", function () { var id = b.getAttribute("data-unwant"); setWants(wants.filter(function (x) { return x.id !== id; })); flowSavings(el); }); });
    var wp = $("#wipe", el);
    if (wp) wp.addEventListener("click", function () { if (confirm("Smazat košík, objednávky, úspory i karanténu?")) { setCart([]); setOrders([]); setWants([]); flowSavings(el); } });
  }
  function flowSearch(el) {
    var q = new URLSearchParams(location.search).get("q") || "";
    if (qi) qi.value = q;
    if (q.trim().length < 2) { el.innerHTML = '<p class="muted">Napiš aspoň dvě písmena do vyhledávání nahoře.</p>'; return; }
    searchRows(q).then(function (r) {
      var cats = r.c.map(function (c) { return '<a href="' + c[1] + '">' + esc(c[0]) + "</a>"; }).join("");
      var rows = r.p.slice(0, 120).map(function (p) { return cardHtml([p[0], p[1], -1, p[3], 0, p[4], "", ""], []).replace('<span class="card__b">&nbsp;</span>', '<span class="card__b">' + esc(p[2]) + "</span>"); });
      el.innerHTML = '<p class="lead">„' + esc(q) + "“: " + (r.p.length ? r.p.length + (r.p.length >= 120 ? "+" : "") + " " + plural(r.p.length, "produkt", "produkty", "produktů") : "nic") + "</p>"
        + (cats ? '<nav class="chips">' + cats + "</nav>" : "") + (rows.length ? '<div class="grid" style="margin-top:18px">' + rows.join("") + "</div>" : '<p>Nic jsme nenašli. Zkus jiné slovo, třeba „iPhone“ nebo „tenisky“.</p>');
      $$(".card__add", el).forEach(function (b) { b.remove(); });
    });
  }

  // ------------------------------------------------------------------ consent + GA4 (only after consent)
  var ga = document.body.getAttribute("data-ga");
  function track(ev, params) { try { if (window.gtag) window.gtag("event", ev, params || {}); } catch (e) {} }
  function startGA() {
    if (!ga || window.gtag) return;
    var s = document.createElement("script"); s.async = true; s.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(ga); document.head.appendChild(s);
    window.dataLayer = window.dataLayer || []; window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag("js", new Date()); window.gtag("config", ga, { anonymize_ip: true });
  }
  if (ga) {
    var cs = load("consent:v1", null), cb = $("#consent");
    if (cs === "yes") startGA(); else if (cs === null && cb) cb.hidden = false;
    if (cb) cb.addEventListener("click", function (e) { var b = e.target.closest("[data-consent]"); if (!b) return; save("consent:v1", b.getAttribute("data-consent")); cb.hidden = true; if (b.getAttribute("data-consent") === "yes") startGA(); });
  }

  // ------------------------------------------------------------------ boot
  var flow = $("#flow");
  if (flow) ({ cart: flowCart, checkout: flowCheckout, order: flowOrder, savings: flowSavings, search: flowSearch }[flow.getAttribute("data-flow")] || function () {})(flow);
  window.addEventListener("hashchange", function () { if ($("[data-flow=order]")) flowOrder($("#flow")); });
  refreshHeader();
})();
