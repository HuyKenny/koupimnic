/* KoupímNic — the whole shop runs here: menu, filters, cart, checkout, the "delivery", the receipt, savings, wish quarantine.
   Prices are real everywhere; only after "Zaplatit" the visitor learns that nothing was charged (Kenny 14. 11. 2026).
   Cart/orders live in localStorage; checkout address fields are NEVER stored or sent. No inline handlers (strict CSP). */
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
  var NB = " ";
  var kc = function (n) { return Math.round(n || 0).toLocaleString("cs-CZ").replace(/\s/g, NB) + NB + "Kč"; };
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
    $$("[data-sum]").forEach(function (s) { s.textContent = n ? kc(cartSum()) : "Košík"; });
    $$("[data-saved]").forEach(function (s) { s.textContent = kc(savedTotal()); });
    $$("[data-saved-pill]").forEach(function (s) { s.hidden = !savedTotal(); });
    orderPill();
  }
  var toastT;
  function toast(html) {
    var t = $("#toast"); if (!t) return;
    t.innerHTML = html; t.hidden = false; clearTimeout(toastT);
    toastT = setTimeout(function () { t.hidden = true; }, 3200);
  }

  // ------------------------------------------------------------------ cart actions
  function addItem(d, size, quiet, qty) {
    var key = d.id + "|" + (size || ""), add = Math.max(1, Math.min(9, qty || 1));
    var c = cart.slice(), found = false;
    c.forEach(function (x) { if (x.k === key) { x.q = Math.min(9, x.q + add); found = true; } });
    if (!found) c.unshift({ k: key, id: d.id, n: d.n, b: d.b, p: d.p, w: d.w, i: d.i, s: d.s, g: d.g, u: d.u, c: d.c, size: size || "", q: add });
    setCart(c.slice(0, 40));
    track("add_to_cart", { value: d.p * add, currency: "CZK" });
    if (!quiet) toast(ICON("check") + "<span>Přidáno do košíku</span><a href=\"/kosik/\">Zobrazit košík</a>");
  }
  document.addEventListener("click", function (e) {
    var a = e.target.closest("[data-add]");
    if (a) {
      e.preventDefault();
      try { addItem(JSON.parse(a.getAttribute("data-add"))); a.classList.add("ok"); a.innerHTML = ICON("check", 18) + "<span>V košíku</span>"; } catch (err) {}
      return;
    }
    var b = e.target.closest("[data-buy]");
    if (b) {
      var box = b.closest("[data-item]"); if (!box) return;
      var d = JSON.parse(box.getAttribute("data-item")), sz = $(".buy input[name=size]:checked"), qi2 = $(".buy [data-qty] input");
      var now = b.getAttribute("data-buy") === "now";
      addItem(d, sz ? sz.value : "", now, qi2 ? +qi2.value : 1);
      if (now) location.href = "/pokladna/"; else openCart();
      return;
    }
    var qd = e.target.closest("[data-qd]");
    if (qd) { var inp = $("input", qd.closest("[data-qty]")); inp.value = Math.max(1, Math.min(9, (+inp.value || 1) + (+qd.getAttribute("data-qd")))); return; }
    if (e.target.closest("[data-open-cart]")) { openCart(); return; }
    if (e.target.closest("#cart [data-close]")) { closeCart(); return; }
    if (e.target.closest("[data-mega]")) { toggleMega(); return; }
    if (e.target.closest("[data-drawer]")) { openDrawer(); return; }
    var dd = e.target.closest("[data-drw-d]");
    if (dd) { drawDrawer(+dd.getAttribute("data-drw-d")); return; }
    if (e.target.closest("[data-drw-back]")) { drawDrawer(null); return; }
    if (e.target.closest("[data-drw-x]")) { closeDrawer(); return; }
    if (e.target.closest("[data-pill-x]")) { try { sessionStorage.setItem("knc:pillx", e.target.closest("[data-pill-x]").getAttribute("data-pill-x")); } catch (x) {} var op = $("#orderpill"); if (op) op.hidden = true; return; }
    if ($("#mega") && !$("#mega").hidden && !e.target.closest("#mega")) toggleMega(false);
    if (e.target.closest("[data-open-filters]")) { document.body.classList.add("filters-open"); return; }
    if (e.target.closest("[data-close-filters]")) { document.body.classList.remove("filters-open"); return; }
    var q = e.target.closest("[data-q]");
    if (q) { changeQty(q.getAttribute("data-k"), +q.getAttribute("data-q")); return; }
    var t = e.target.closest(".thumbs button");
    if (t && $("#gmain")) { $("#gmain").src = t.getAttribute("data-src"); $$(".thumbs button").forEach(function (x) { x.classList.toggle("on", x === t); }); return; }
    var m = e.target.closest("[data-more]");
    if (m) { var el = document.getElementById(m.getAttribute("data-more")); if (el) el.classList.remove("clamp"); m.remove(); return; }
    var go = e.target.closest("a[data-go]");
    if (go) track("affiliate_click", { shop: go.getAttribute("data-go") });
  });
  function changeQty(k, dq) {
    var c = cart.map(function (x) { return x.k === k ? Object.assign({}, x, { q: dq === 0 ? 0 : Math.max(0, Math.min(9, x.q + dq)) }) : x; }).filter(function (x) { return x.q > 0; });
    setCart(c); renderDrawer(); if ($("[data-flow=cart]")) flowCart($("#flow")); if ($("[data-flow=checkout]")) coRender();
  }

  // ------------------------------------------------------------------ mega menu (data/menu.json, loaded on first open)
  var menu = null, menuDept = 0;
  function toggleMega(force) {
    var m = $("#mega"), btn = $("[data-mega]"); if (!m) return;
    var open = force === undefined ? m.hidden : force;
    m.hidden = !open; if (btn) btn.setAttribute("aria-expanded", open ? "true" : "false");
    document.body.classList.toggle("mega-open", open);
    if (open && !menu) fetch("/data/menu.json").then(function (r) { return r.json(); }).then(function (j) { menu = j; drawMega(); }).catch(function () {});
    else if (open) drawMega();
  }
  function drawMega() {
    var box = $("#mega-in"); if (!box || !menu) return;
    var d = menu[menuDept] || menu[0];
    box.innerHTML = '<ul class="mega__depts">' + menu.map(function (x, i) {
      return '<li><button type="button" data-dept="' + i + '"' + (i === menuDept ? ' class="on"' : "") + '><img src="/img/ic/' + x[2] + '.webp" alt="" width="28" height="28">' + esc(x[1]) + ICON("chev", 16) + "</button></li>";
    }).join("") + '</ul><div class="mega__cats"><a class="mega__all" href="/' + d[0] + '/">Vše z oddělení ' + esc(d[1]) + ICON("arrow", 16) + "</a><div class=\"mega__grid\">" + d[3].map(function (c) {
      return '<div><a class="mega__cat" href="/' + c[0] + '/"><img src="/img/ic/' + c[3] + '.webp" alt="" width="36" height="36" loading="lazy">' + esc(c[1]) + "</a><ul>"
        + c[4].slice(0, 7).map(function (s) { return '<li><a href="/' + c[0] + "/" + s[0] + '/">' + esc(s[1]) + "</a></li>"; }).join("") + "</ul></div>";
    }).join("") + "</div></div>";
    $$("[data-dept]", box).forEach(function (b) {
      var pick = function () { menuDept = +b.getAttribute("data-dept"); drawMega(); };
      b.addEventListener("click", pick);
      if (window.matchMedia("(hover: hover)").matches) b.addEventListener("mouseenter", pick);
    });
  }

  // ------------------------------------------------------------------ phone menu: departments -> categories with subcategories (same menu.json)
  function withMenu(cb) {
    if (menu) return cb();
    fetch("/data/menu.json").then(function (r) { return r.json(); }).then(function (j) { menu = j; cb(); }).catch(function () {});
  }
  function openDrawer() {
    var d = $("#drw");
    if (!d) {
      d = document.createElement("div"); d.id = "drw"; d.className = "drw";
      d.setAttribute("role", "dialog"); d.setAttribute("aria-modal", "true"); d.setAttribute("aria-label", "Kategorie");
      document.body.appendChild(d);
    }
    d.hidden = false; document.body.classList.add("drw-open");
    d.innerHTML = '<div class="drw__h"><b>Kategorie</b><button type="button" data-drw-x aria-label="Zavřít">' + ICON("x", 20) + '</button></div><div class="drw__b"><p class="muted">Načítám…</p></div>';
    withMenu(function () { drawDrawer(null); });
  }
  function closeDrawer() { var d = $("#drw"); if (d) d.hidden = true; document.body.classList.remove("drw-open"); }
  function drawDrawer(i) {
    var d = $("#drw"); if (!d || !menu) return;
    var x = '<button type="button" data-drw-x aria-label="Zavřít">' + ICON("x", 20) + "</button>";
    if (i === null) {
      d.innerHTML = '<div class="drw__h"><b>Kategorie</b>' + x + '</div><div class="drw__b"><ul>' + menu.map(function (m, k) {
        return '<li><button class="drw__row" type="button" data-drw-d="' + k + '"><img src="/img/ic/' + m[2] + '.webp" alt="" width="36" height="36">' + esc(m[1]) + ICON("chev", 18) + "</button></li>";
      }).join("") + "</ul></div>";
    } else {
      var m = menu[i];
      d.innerHTML = '<div class="drw__h"><button type="button" data-drw-back aria-label="Zpět">' + '<svg class="i" width="20" height="20" aria-hidden="true" style="transform:scaleX(-1)"><use href="/img/ui/icons.svg#chev"/></svg>' + "</button><b>" + esc(m[1]) + "</b>" + x + '</div><div class="drw__b">'
        + '<a class="drw__all" href="/' + m[0] + '/">Vše z oddělení ' + esc(m[1]) + ICON("arrow", 16) + "</a><ul>" + m[3].map(function (c) {
          return '<li><a class="drw__row" href="/' + c[0] + '/"><img src="/img/ic/' + c[3] + '.webp" alt="" width="36" height="36" loading="lazy">' + esc(c[1]) + "</a>"
            + (c[4].length ? '<div class="drw__subs">' + c[4].slice(0, 8).map(function (s) { return '<a href="/' + c[0] + "/" + s[0] + '/">' + esc(s[1]) + "</a>"; }).join("") + "</div>" : "") + "</li>";
        }).join("") + "</ul></div>";
    }
    var b = $(".drw__b", d); if (b) b.scrollTop = 0;
  }

  // ------------------------------------------------------------------ drawer
  function linesHtml(c, editable) {
    return '<ul class="lines">' + c.map(function (x) {
      return '<li class="line"><img src="' + esc(x.i) + '" alt="" loading="lazy" referrerpolicy="no-referrer"><div><a class="line__n" href="' + esc(x.u) + '">' + esc(x.n) + '</a>'
        + '<div class="line__m">Skladem' + (x.size ? " · velikost " + esc(x.size) : "") + '</div>'
        + (editable ? '<div class="qty"><button type="button" data-q="-1" data-k="' + esc(x.k) + '" aria-label="Méně">' + ICON("minus", 14) + '</button><span>' + x.q + '</span>'
          + '<button type="button" data-q="1" data-k="' + esc(x.k) + '" aria-label="Více">' + ICON("plus", 14) + '</button><button class="rm" type="button" data-q="0" data-k="' + esc(x.k) + '">Odebrat</button></div>'
          : (x.q > 1 ? '<div class="line__m">' + x.q + ' ks</div>' : ""))
        + '</div><div class="line__p">' + kc(x.p * x.q) + '</div></li>';
    }).join("") + "</ul>";
  }
  function totalsHtml(sum) {
    return '<div class="totals"><p><span>Mezisoučet</span><span>' + kc(sum) + '</span></p><p><span>Doprava</span><span class="free">zdarma</span></p>'
      + '<p class="pay"><span>Celkem k úhradě</span><b>' + kc(sum) + '</b></p><p class="vat">včetně DPH</p></div>';
  }
  function emptyHtml() {
    return '<div class="empty"><img src="/img/ui/box-empty.webp" alt="" width="150" height="150"><p><b>Košík je prázdný.</b><br>Vyber si z tisíců produktů.</p>'
      + '<p><a class="btn" href="/">Nakupovat</a></p></div>';
  }
  function renderDrawer() {
    var b = $("#cart-body"); if (!b) return;
    if (!cart.length) { b.innerHTML = emptyHtml(); return; }
    b.innerHTML = linesHtml(cart, true) + totalsHtml(cartSum()) + '<a class="btn btn--lg btn--full" href="/pokladna/">Pokračovat k pokladně</a>'
      + '<a class="btn btn--ghost btn--full" href="/kosik/">Zobrazit košík</a>';
  }
  var lastFocus;
  function openCart() { var d = $("#cart"); if (!d) return; lastFocus = document.activeElement; renderDrawer(); d.hidden = false; document.body.style.overflow = "hidden"; var x = $(".x", d); if (x) x.focus(); }
  function closeCart() { var d = $("#cart"); if (!d) return; d.hidden = true; document.body.style.overflow = ""; if (lastFocus) lastFocus.focus(); }
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    if ($("#cart") && !$("#cart").hidden) closeCart();
    if ($("#mega") && !$("#mega").hidden) toggleMega(false);
    if ($("#drw") && !$("#drw").hidden) closeDrawer();
    document.body.classList.remove("filters-open");
  });

  // ------------------------------------------------------------------ images: wsrv.nl fallback to the shop's original
  document.addEventListener("error", function (e) {
    var im = e.target;
    if (im.tagName !== "IMG") return;
    var o = im.getAttribute("data-orig");
    if (o && im.src !== o) { im.setAttribute("data-orig", ""); im.src = o; }
    else if (im.getAttribute("data-ic")) { im.src = im.getAttribute("data-ic"); im.removeAttribute("data-ic"); im.classList.add("is-ic"); }
    else if (im.src.indexOf("placeholder.svg") < 0) im.src = "/img/ui/placeholder.svg";
  }, true);

  // ------------------------------------------------------------------ listing filters (sidebar) on the listing JSON
  function cardHtml(d) {
    var off = d.w > d.p ? Math.round(100 * (d.w - d.p) / d.w) : 0;
    return '<article class="card"><a class="card__a" href="' + d.u + '"><span class="card__img' + (/ans-media\.com/.test(d.i || "") ? " is-gray" + ($("[data-grid][data-fill]") ? " is-fill" : "") : "") + '"><img src="' + esc(d.i || "/img/ui/placeholder.svg") + '" alt="" loading="lazy" referrerpolicy="no-referrer" width="320" height="320">'
      + (off >= 5 ? '<span class="card__off">−' + off + NB + '%</span>' : "") + '</span><span class="card__b">' + (esc(d.b) || "&nbsp;") + '</span><span class="card__n">' + esc(d.n) + '</span></a>'
      + '<div class="card__foot"><span class="card__p"><b>' + kc(d.p) + '</b>' + (off >= 5 ? "<s>" + kc(d.w) + "</s>" : "") + '</span><span class="card__st">Skladem</span>'
      + '<button class="card__add" type="button" data-add="' + esc(JSON.stringify(d)) + '">' + ICON("bag", 18) + '<span>Do košíku</span></button></div></article>';
  }
  var side = $("#filters");
  if (side) {
    var data = null, shown = 48, sort = "", grid = $("[data-grid]"), pager = $(".pg");
    var rowData = function (r) { return { id: r[0], n: r[1], b: r[2] >= 0 ? data.b[r[2]] : "", p: r[3], w: r[4], i: r[5], s: data.o[r[6]], g: r[7], u: "/produkt/" + r[0] + "/" }; };
    var state = function () {
      var vals = function (f) { return $$('[data-f="' + f + '"] input:checked', side).map(function (x) { return x.value; }); };
      return { brands: vals("brand"), shops: vals("shop"), min: +($('[data-f="min"]', side).value || 0), max: +($('[data-f="max"]', side).value || 0), sale: $('[data-f="sale"]', side).checked };
    };
    var apply = function () {
      var st = state(), any = st.brands.length || st.shops.length || st.min || st.max || st.sale || sort;
      if (!any) { if (grid.getAttribute("data-orig")) { grid.innerHTML = grid.getAttribute("data-orig"); if (pager) pager.hidden = false; } setN(null); chips(st); return; }
      if (!grid.getAttribute("data-orig")) grid.setAttribute("data-orig", grid.innerHTML);
      var rows = data.i.filter(function (r) {
        return (!st.brands.length || (r[2] >= 0 && st.brands.indexOf(data.b[r[2]]) >= 0)) && (!st.shops.length || st.shops.indexOf(data.o[r[6]]) >= 0)
          && (!st.min || r[3] >= st.min) && (!st.max || r[3] <= st.max) && (!st.sale || r[4] > r[3] * 1.05);
      });
      if (sort === "p") rows.sort(function (a, b) { return a[3] - b[3]; });
      if (sort === "-p") rows.sort(function (a, b) { return b[3] - a[3]; });
      if (sort === "d") rows.sort(function (a, b) { return (b[4] > b[3] ? (b[4] - b[3]) / b[4] : 0) - (a[4] > a[3] ? (a[4] - a[3]) / a[4] : 0); });
      grid.innerHTML = rows.length ? '<div class="grid">' + rows.slice(0, shown).map(function (r) { return cardHtml(rowData(r)); }).join("") + "</div>"
        + (rows.length > shown ? '<div class="more-wrap"><button class="btn btn--ghost" type="button" data-showmore>Načíst další (' + (rows.length - shown) + ")</button></div>" : "")
        : '<div class="empty"><p><b>Tomu nic neodpovídá.</b><br>Zkus uvolnit filtry.</p></div>';
      if (pager) pager.hidden = true;
      setN(rows.length); chips(st);
    };
    var setN = function (n) { var el = $("[data-n]"); if (!el) return; if (!el.getAttribute("data-orig")) el.setAttribute("data-orig", el.textContent); el.textContent = n === null ? el.getAttribute("data-orig") : n.toLocaleString("cs-CZ"); };
    var chips = function (st) {
      var box = $("[data-active]"); if (!box) return;
      var c = st.brands.concat(st.shops).map(function (v) { return '<button type="button" data-unf="' + esc(v) + '">' + esc(v) + ICON("x", 14) + "</button>"; });
      if (st.min || st.max) c.push('<button type="button" data-unf="price">' + (st.min ? "od " + kc(st.min) + " " : "") + (st.max ? "do " + kc(st.max) : "") + ICON("x", 14) + "</button>");
      if (st.sale) c.push('<button type="button" data-unf="sale">Ve slevě' + ICON("x", 14) + "</button>");
      box.innerHTML = c.join("") + (c.length ? '<button type="button" class="chips-on__clear" data-unf="all">Zrušit filtry</button>' : "");
      box.hidden = !c.length;
    };
    var run = function () { shown = 48; if (data) return apply(); fetch(side.getAttribute("data-list")).then(function (r) { return r.json(); }).then(function (j) { data = j; apply(); }).catch(function () {}); };
    side.addEventListener("change", run);
    var tm; side.addEventListener("input", function (e) { if (e.target.type === "number") { clearTimeout(tm); tm = setTimeout(run, 400); } });
    $$("[data-sort]").forEach(function (b) { b.addEventListener("click", function () { sort = b.getAttribute("data-sort"); $$("[data-sort]").forEach(function (x) { x.classList.toggle("on", x === b); }); run(); }); });
    document.addEventListener("click", function (e) {
      if (e.target.closest("[data-showmore]")) { shown += 48; apply(); return; }
      var u = e.target.closest("[data-unf]"); if (!u) return;
      var v = u.getAttribute("data-unf");
      if (v === "all") { $$("input[type=checkbox]", side).forEach(function (x) { x.checked = false; }); $$("input[type=number]", side).forEach(function (x) { x.value = ""; }); }
      else if (v === "price") $$("input[type=number]", side).forEach(function (x) { x.value = ""; });
      else if (v === "sale") $('[data-f="sale"]', side).checked = false;
      else $$("input[type=checkbox]", side).forEach(function (x) { if (x.value === v) x.checked = false; });
      run();
    });
  }

  // ------------------------------------------------------------------ search (static index: data/sug.json + data/s/<2 letters>.json)
  var fold = function (s) { return (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, ""); };
  var sugCache = {};
  function getJSON(u) { if (!sugCache[u]) sugCache[u] = fetch(u).then(function (r) { return r.ok ? r.json() : []; }).catch(function () { return []; }); return sugCache[u]; }
  function searchRows(q) {
    var words = fold(q).match(/[a-z0-9]+/g) || [];
    if (!words.length || words[0].length < 2) return Promise.resolve({ c: [], p: [] });
    return Promise.all([getJSON("/data/sug.json"), getJSON("/data/s/" + words[0].slice(0, 2) + ".json")]).then(function (res) {
      var hit = function (t) { var f = fold(t); return words.every(function (w) { return f.indexOf(w) >= 0; }); };
      return { c: res[0].filter(function (r) { return hit(r[0]); }).slice(0, 5), p: res[1].filter(function (r) { return hit(r[1] + " " + r[2]); }) };
    });
  }
  var qi = $("#q"), sg = $("#sugg");
  if (qi && sg) {
    var st2;
    qi.addEventListener("input", function () {
      clearTimeout(st2);
      st2 = setTimeout(function () {
        if (qi.value.trim().length < 2) { sg.hidden = true; return; }
        searchRows(qi.value).then(function (r) {
          var html = r.c.map(function (c) { return '<a href="' + c[1] + '"><span class="k">' + ({ k: "Kategorie", o: "Oddělení", z: "Značka", p: "Podkategorie" }[c[2]] || "") + '</span>' + esc(c[0]) + '</a>'; }).join("")
            + r.p.slice(0, 7).map(function (p) { return '<a href="/produkt/' + p[0] + '/"><img src="' + esc(p[4]) + '" alt="" referrerpolicy="no-referrer">' + esc(p[1]) + '<small>' + kc(p[3]) + '</small></a>'; }).join("")
            + (r.p.length > 7 ? '<a class="sugg__all" href="/hledat/?q=' + encodeURIComponent(qi.value) + '">Všechny výsledky (' + r.p.length + ")</a>" : "");
          sg.innerHTML = html || '<p class="muted" style="padding:8px 10px;margin:0">Nic jsme nenašli. Zkus jiné slovo.</p>'; sg.hidden = false;
        });
      }, 160);
    });
    document.addEventListener("click", function (e) { if (!e.target.closest(".search")) sg.hidden = true; });
  }

  // ------------------------------------------------------------------ the "delivery"
  var STAGES = [
    { t: 0, n: "Objednávka přijata", notes: ["Objednávku jsme přijali. Platba: 0 Kč. Nic se nestrhlo a nic se nestrhne."] },
    { t: 25, n: "Hledáme zboží ve skladu", notes: ["Skladník Ignác prochází regály. Zatím nic. To je dobrá zpráva.", "Čtečka čárových kódů pípá naprázdno."] },
    { t: 90, n: "Balíme", notes: ["Bublinková fólie se pečlivě omotává kolem ničeho.", "Krabice je zalepená. Váží přesně tolik co krabice."] },
    { t: 180, n: "Předáno kurýrovi", notes: ["Kurýr naložil balík a nedůvěřivě s ním zatřásl.", "Balík je na cestě. Nic v něm nedrnčí."] },
    { t: 360, n: "Kurýr je ve tvé ulici", notes: ["Hledá číslo popisné. Tvoje peníze mezitím zůstávají na účtu.", "Parkuje. Na chodníku, ale jen nanečisto."] },
    { t: 480, n: "Doručeno", notes: ["Crrr. Někdo zvoní."] }
  ];
  var COURIERS = ["Vavřinec Nikdo", "Prokop Prázdný", "Bohdana Bezobsahová", "Igor Ničeho", "Žofie Zbytečná", "Dalibor Doručil"];
  var SHIP = [["kuryr", "Kurýr na adresu", "Doručení ještě dnes", "zdarma"], ["vydejni", "Výdejní místo", "Vyzvednutí do 24 hodin", "zdarma"],
    ["osobne", "Osobní odběr", "Na prodejně, ihned", "zdarma"], ["expres", "Expresní doručení", "Do 2 hodin", "zdarma"]];
  var PAY = [["karta", "Platební karta", "Visa, Mastercard"], ["wallet", "Apple Pay / Google Pay", "Rychlá platba telefonem"],
    ["prevod", "Bankovní převod", "Platba předem"], ["dobirka", "Dobírka", "Platba při převzetí"]];
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
    var k = stageOf(o), key = o.id + ":" + k, gone = "";
    try { gone = sessionStorage.getItem("knc:pillx") || ""; } catch (x) {}
    if (gone === key) { p.hidden = true; return; }      // hidden until the next stage
    p.outerHTML = '<div class="orderpill" id="orderpill"><a href="/objednavka/#' + o.id + '"><span class="dot"></span><span>' + (k >= 5 ? "<b>Kurýr zvoní.</b> Otevři dveře" : "Zásilka " + o.id + ": <b>" + STAGES[k].n + "</b>") + "</span></a>"
      + '<button class="orderpill__x" type="button" data-pill-x="' + key + '" aria-label="Skrýt">' + ICON("x", 16) + "</button></div>";
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

  // ------------------------------------------------------------------ cart page + checkout
  function stepper(k) {
    return '<ol class="stepper">' + ["Košík", "Doprava a platba", "Dodací údaje", "Shrnutí"].map(function (n, i) {
      return '<li class="' + (i + 1 < k ? "done" : i + 1 === k ? "now" : "") + '"><span>' + (i + 1 < k ? ICON("check", 14) : i + 1) + "</span>" + n + "</li>";
    }).join("") + "</ol>";
  }
  function flowCart(el) {
    if (!cart.length) { el.innerHTML = emptyHtml(); return; }
    el.innerHTML = stepper(1) + '<div class="co-grid"><div>' + linesHtml(cart, true) + '</div><div class="co-side">' + totalsHtml(cartSum())
      + '<a class="btn btn--lg btn--full" href="/pokladna/">Pokračovat k pokladně</a><p class="muted co-note">Doprava zdarma · Bez registrace</p></div></div>';
  }
  function optsHtml(name, rows, sel) {
    return '<div class="opts">' + rows.map(function (r) {
      return '<label class="opt"><input type="radio" name="' + name + '" value="' + r[0] + '"' + (r[0] === sel ? " checked" : "") + '><span><b>' + esc(r[1]) + (r[3] ? '<em>' + esc(r[3]) + "</em>" : "")
        + '</b><small>' + esc(r[2]) + '</small></span></label>';
    }).join("") + "</div>";
  }
  var newId = function () { return "KN-" + String(Date.now()).slice(-6) + String(Math.floor(Math.random() * 90 + 10)); };
  // the address lives ONLY in this object while the page is open: never written to localStorage, never sent anywhere
  var co = { step: 2, ship: "kuryr", pay: "karta", addr: {} };
  var FIELDS = [["name", "Jméno a příjmení", "text", "name"], ["street", "Ulice a číslo", "text", "street-address"], ["city", "Město", "text", "address-level2"],
    ["zip", "PSČ", "text", "postal-code"], ["email", "E-mail", "email", "email"], ["phone", "Telefon", "tel", "tel"]];
  function coRender() {
    var el = $("#flow"); if (!el) return;
    if (!cart.length) { el.innerHTML = emptyHtml(); return; }
    var sum = cartSum(), body = "";
    if (co.step === 2) {
      body = '<section class="co-sec"><h2>Doprava</h2>' + optsHtml("ship", SHIP, co.ship) + '</section><section class="co-sec"><h2>Platba</h2>' + optsHtml("pay", PAY, co.pay)
        + '</section><div class="co-nav"><a class="btn btn--ghost" href="/kosik/">Zpět do košíku</a><button class="btn btn--lg" type="button" data-co="3">Pokračovat</button></div>';
    } else if (co.step === 3) {
      body = '<section class="co-sec"><h2>Dodací údaje</h2><div class="form">' + FIELDS.map(function (f) {
        return '<label class="fld' + (f[0] === "street" || f[0] === "name" ? " fld--w" : "") + '"><span>' + f[1] + '</span><input name="' + f[0] + '" type="' + f[2] + '" autocomplete="off" value="' + esc(co.addr[f[0]] || "") + '"></label>';
      }).join("") + '</div><p class="muted co-note">Údaje nejsou povinné. Nikam je neposíláme ani neukládáme a po dokončení objednávky se zahodí.</p></section>'
        + '<div class="co-nav"><button class="btn btn--ghost" type="button" data-co="2">Zpět</button><button class="btn btn--lg" type="button" data-co="4">Pokračovat ke shrnutí</button></div>';
    } else {
      var s = SHIP.filter(function (x) { return x[0] === co.ship; })[0], p = PAY.filter(function (x) { return x[0] === co.pay; })[0];
      var who = [co.addr.name, co.addr.street, co.addr.city].filter(Boolean).map(esc).join(", ");
      body = '<section class="co-sec"><h2>Shrnutí objednávky</h2>' + linesHtml(cart, false)
        + '<div class="fake"><div><span>Doprava</span><b>' + esc(s[1]) + ' · zdarma</b></div><div><span>Platba</span><b>' + esc(p[1]) + '</b></div>'
        + (who ? '<div><span>Doručit na</span><b>' + who + '</b></div>' : "") + '</div></section>'
        + '<div class="co-nav"><button class="btn btn--ghost" type="button" data-co="3">Zpět</button><button class="btn btn--lg btn--pay" type="button" id="paybtn">' + ICON("lock", 18) + 'Zaplatit ' + kc(sum) + '</button></div>'
        + '<p class="muted co-note">Kliknutím na „Zaplatit“ dokončíš objednávku.</p>';
    }
    el.innerHTML = stepper(co.step) + '<div class="co-grid"><div>' + body + '</div><div class="co-side">' + totalsHtml(sum) + '</div></div>';
    $$("input[name=ship]", el).forEach(function (x) { x.addEventListener("change", function () { co.ship = x.value; }); });
    $$("input[name=pay]", el).forEach(function (x) { x.addEventListener("change", function () { co.pay = x.value; }); });
    $$(".form input", el).forEach(function (x) { x.addEventListener("input", function () { co.addr[x.name] = x.value; }); });
    $$("[data-co]", el).forEach(function (b) { b.addEventListener("click", function () { co.step = +b.getAttribute("data-co"); coRender(); window.scrollTo(0, 0); }); });
    var pb = $("#paybtn", el);
    if (pb) pb.addEventListener("click", function () { pay(el, sum); }, { once: true });
  }
  function pay(el, sum) {
    var ov = document.createElement("div");
    ov.className = "payov";
    ov.innerHTML = '<div class="payov__box" role="dialog" aria-modal="true" aria-live="polite"><div class="spin"></div><p class="payov__t">Zpracováváme platbu…</p><p class="payov__sum">' + kc(sum) + "</p></div>";
    document.body.appendChild(ov);
    var box = $(".payov__box", ov);
    setTimeout(function () { $(".payov__t", box).textContent = "Ověřujeme platbu…"; }, 1200);
    setTimeout(function () {
      var id = newId();
      var o = { id: id, at: Date.now(), items: cart.map(function (x) { return { id: x.id, n: x.n, p: x.p, q: x.q, i: x.i, s: x.s, g: x.g, u: x.u, size: x.size }; }),
        total: sum, ship: co.ship, pay: co.pay, courier: COURIERS[hash(id) % COURIERS.length], skip: 0 };
      co.addr = {};                                         // the address is gone: it was never stored
      setOrders([o].concat(orders)); setCart([]);
      track("purchase", { value: 0, currency: "CZK", items: o.items.length });
      box.innerHTML = '<p class="payov__t">Platba dokončena</p><p class="payov__sum"><s>' + kc(sum) + '</s></p><p class="payov__zero">0' + NB + 'Kč</p>'
        + '<p class="payov__msg">Z účtu se nestrhlo nic. Nikdy. Tohle je KoupímNic: nákup se vším všudy, jen bez placení.<br>Objednávka ' + id + " je i tak na cestě.</p>"
        + '<a class="btn btn--lg btn--lime" href="/objednavka/#' + id + '">Sledovat zásilku</a>';
      confetti();
    }, 2600);
  }
  function flowCheckout(el) { co.step = 2; coRender(); }

  // ------------------------------------------------------------------ order tracking, unboxing, receipt
  var timer;
  function flowOrder(el) {
    var id = location.hash.slice(1), o = orders.filter(function (x) { return x.id === id; })[0] || orders[0];
    if (!o) { el.innerHTML = '<h1>Žádná objednávka</h1><p>Zatím jsi nic neobjednal.</p><p><a class="btn" href="/">Nakupovat</a></p>'; return; }
    if (location.hash.slice(1) !== o.id) history.replaceState(null, "", "#" + o.id);
    clearInterval(timer);
    var draw = function () {
      var k = stageOf(o), total = STAGES[STAGES.length - 1].t, el2 = Math.min(total, (Date.now() - o.at) / 1000 + (o.skip || 0));
      if (o.opened) { receipt(el, o); clearInterval(timer); return; }
      var st = STAGES[Math.min(k, STAGES.length - 1)], note = st.notes[hash(o.id + k) % st.notes.length];
      var pos = 6 + 76 * Math.min(1, Math.max(0, (el2 - 180) / (total - 180)));
      var tl = STAGES.map(function (s, i) {
        var at = new Date(o.at + (s.t - (o.skip || 0)) * 1000);
        return '<li class="' + (i < k ? "done" : i === k ? "now" : "") + '"><span>' + s.n + '</span><small>' + (i <= k ? at.toLocaleTimeString("cs-CZ", { hour: "2-digit", minute: "2-digit" }) : "") + "</small></li>";
      }).join("");
      var left = Math.max(0, Math.ceil((total - el2) / 60));
      el.innerHTML = '<div class="ord__h"><h1>Objednávka je na cestě</h1><span class="ord__id">' + o.id + " · zaplaceno 0" + NB + "Kč</span></div>"
        + '<section class="track"><div class="road"><span class="road__wh">' + ICON("box") + '</span><span class="road__home">' + ICON("bell") + '</span>'
        + '<span class="road__c" style="left:' + (k < 3 ? 12 : Math.max(12, pos)) + '%"><img src="/img/ui/courier.webp" alt="" width="104" height="75"></span></div>'
        + '<p class="stage">' + (k >= 5 ? "Kurýr zvoní" : st.n) + '</p><p class="stage__note">' + esc(note) + (k >= 3 && k < 5 ? " Kurýr: " + esc(o.courier) + "." : "") + "</p>"
        + '<div class="bar"><i style="width:' + Math.round(100 * el2 / total) + '%"></i></div>'
        + (k >= 5 ? '<div class="door"><p>Na rohožce stojí krabice. Podezřele lehká.</p><button class="btn btn--lg btn--lime" type="button" id="opendoor">' + ICON("box") + "Otevřít dveře a rozbalit</button></div>"
          : '<p class="muted" style="margin:10px 0 0">Doručení zhruba za ' + left + " " + plural(left, "minutu", "minuty", "minut") + ". Můžeš mezitím nakupovat dál, zazvoníme.</p>"
            + '<div class="ord__act"><button class="btn btn--sm btn--ghost" type="button" id="skip">Přeskočit čekání</button><a class="btn btn--sm btn--ghost" href="/">Nakupovat dál</a></div>')
        + '<ol class="tl">' + tl + "</ol></section>"
        + '<details class="co-sec"><summary><b>Obsah objednávky (' + o.items.length + ')</b></summary>' + linesHtml(o.items.map(function (x) { return Object.assign({ k: x.id }, x); }), false) + "</details>";
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
    });
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
        + '<a class="btn btn--sm btn--ghost" href="' + esc(x.g) + '" rel="sponsored nofollow noopener" target="_blank" data-go="1">Fakt to chci ' + ICON("ext", 14) + '</a><span class="tag-ad">Reklama</span></div></li>';
    }).join("");
    el.innerHTML = '<div class="ord__h"><h1>' + (fresh ? "Doručeno. Uvnitř nic." : "Účtenka") + '</h1><span class="ord__id">' + o.id + "</span></div>"
      + '<div class="receipt"><span class="stamp">ZAPLACENO<br>NIČÍM</span><h2>KOUPÍMNIC.CZ</h2><p class="c">Nákupní galerie nanečisto</p><p class="c">' + d.toLocaleDateString("cs-CZ") + " " + d.toLocaleTimeString("cs-CZ", { hour: "2-digit", minute: "2-digit" }) + " · č. " + o.id + "</p><hr>"
      + items + '<hr><p class="r big"><span>CELKEM</span><span>' + kc(o.total) + '</span></p><p class="r"><span>Sleva za rozum</span><span>−' + kc(o.total) + '</span></p>'
      + '<p class="r big"><span>ZAPLACENO</span><span>0,00' + NB + 'Kč</span></p><hr><p class="saved">NEUTRACENO<b>' + kc(o.total) + "</b></p>"
      + '<p class="c">Doručil: ' + esc(o.courier) + '. Uvnitř: nic, přesně podle objednávky.</p></div>'
      + "<h2>Za tyhle peníze by šlo mít</h2>" + equivHtml(o.total)
      + '<div class="piggy"><img src="/img/ui/piggy.webp" alt="" width="96" height="96"><div><span class="muted">Celkem jsi na KoupímNic neutratil</span><b>' + kc(savedTotal()) + "</b>"
      + '<button class="btn btn--sm btn--ghost" type="button" id="share">' + ICON("share", 16) + "Pochlubit se</button></div></div>"
      + "<h2>Pořád to chceš?</h2><p>Dej tomu tři dny v karanténě. Když tě to pak pořád bude lákat, koupíš to s čistým svědomím. Odkaz „Fakt to chci“ vede do obchodu a je reklamní.</p>"
      + '<ul class="wants">' + real + "</ul>"
      + '<p class="honestbox">Poctivě: z účtu ti nic neubylo, takže jsi nic „neušetřil“ v pravém smyslu. Jen ses nenechal unést. I to se počítá.</p>'
      + '<p class="ord__act"><a class="btn" href="/">Nakupovat dál</a><a class="btn btn--ghost" href="/moje-uspory/">Moje úspory</a></p>';
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
        + '<div class="want__a">' + (ready ? '<a class="btn btn--sm" href="' + esc(x.g) + '" rel="sponsored nofollow noopener" target="_blank" data-go="1">Ano, koupit u ' + esc(x.s) + "</a>" : "")
        + '<button class="btn btn--sm btn--ghost" type="button" data-unwant="' + esc(x.id) + '">' + (ready ? "Ne, pustit z hlavy" : "Už to nechci") + "</button>"
        + (ready ? '<span class="tag-ad">Reklama</span>' : "") + "</div></li>";
    }).join("");
    el.innerHTML = '<div class="piggy"><img src="/img/ui/piggy.webp" alt="" width="96" height="96"><div><span class="muted">Celkem neutraceno</span><b>' + kc(tot) + "</b>"
      + '<span class="muted">' + act.length + " " + plural(act.length, "objednávka", "objednávky", "objednávek") + "</span></div></div>"
      + (tot ? "<h2>To je</h2>" + equivHtml(tot) : '<p>Zatím nic. <a class="lnk" href="/">Jdi nakupovat</a></p>')
      + "<h2>Karanténa přání</h2>" + (wl ? '<ul class="wants">' + wl + "</ul>" : '<p class="muted">Prázdná. Věci sem dáš z účtenky po doručení.</p>')
      + (act.length ? "<h2>Historie objednávek</h2><ul class=\"hist\">" + act.map(function (o) {
        return '<li><a href="/objednavka/#' + o.id + '"><span><b>' + o.id + "</b> · " + o.items.length + " " + plural(o.items.length, "položka", "položky", "položek")
          + "<br><small>" + new Date(o.at).toLocaleDateString("cs-CZ") + "</small></span><span><b>" + kc(o.total) + "</b><br><small>" + (o.opened ? "doručeno" : "na cestě") + "</small></span></a></li>";
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
      var rows = r.p.slice(0, 120).map(function (p) { return cardHtml({ id: p[0], n: p[1], b: p[2], p: p[3], w: 0, i: p[4], s: "", g: "", u: "/produkt/" + p[0] + "/" }); });
      el.innerHTML = '<p class="lead">„' + esc(q) + "“: " + (r.p.length ? r.p.length + (r.p.length >= 120 ? "+" : "") + " " + plural(r.p.length, "produkt", "produkty", "produktů") : "nic") + "</p>"
        + (cats ? '<nav class="chips">' + cats + "</nav>" : "") + (rows.length ? '<div class="grid" style="margin-top:18px">' + rows.join("") + "</div>" : "<p>Nic jsme nenašli. Zkus jiné slovo, třeba „iPhone“ nebo „LEGO“.</p>");
      $$(".card__add", el).forEach(function (b) {     // search rows carry no shop: the button opens the product instead
        var a = b.closest(".card").querySelector(".card__a");
        b.outerHTML = '<a class="card__add" href="' + a.getAttribute("href") + '"><span>Zobrazit</span></a>';
      });
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
