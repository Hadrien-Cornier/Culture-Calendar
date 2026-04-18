(function () {
  "use strict";

  var CONFIG = {
    variant: "v12b",
    multiVenue: false,
    multiCategory: false,
    persistence: "url-only",
    storageKey: "v12b_filter",
    iconMode: "icon+text",
    collapseSheet: false,
    fused: true
  };

  var DATA_URL = "../../data.json";
  var CATEGORY_ICONS = {
    movie: "🎬", film: "🎬", concert: "🎵", book_club: "📖", opera: "🎭",
    dance: "💃", ballet: "💃", visual_arts: "🎨", other: "✨"
  };
  var CATEGORY_LABELS = {
    movie: "Film", film: "Film", concert: "Concert", book_club: "Book Club",
    opera: "Opera", dance: "Dance", ballet: "Ballet", visual_arts: "Visual Arts",
    other: "Other"
  };
  var MONTHS_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

  var picksList = document.getElementById("picks-list");
  var listingsEl = document.getElementById("listings");
  var loadingEl = document.getElementById("loading");
  var errorEl = document.getElementById("error");
  var fusedChipsEl = document.getElementById("fused-chips");

  var state = loadState();
  var allEvents = [];

  fetch(DATA_URL)
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(function (raw) {
      allEvents = Array.isArray(raw) ? raw : (raw.events || []);
      loadingEl.hidden = true;
      buildFilterBar();
      renderAll();
    })
    .catch(function (err) {
      loadingEl.hidden = true;
      errorEl.hidden = false;
      errorEl.textContent = "Error: " + err.message;
    });

  function loadState() {
    var params = new URLSearchParams(window.location.search);
    var s = { venues: [], categories: [] };
    var vm = params.get("venues"), vs = params.get("venue");
    var cm = params.get("categories"), cs = params.get("category");
    if (vm) s.venues = vm.split(",").filter(Boolean);
    else if (vs) s.venues = [vs];
    if (cm) s.categories = cm.split(",").filter(Boolean);
    else if (cs) s.categories = [cs];
    return s;
  }

  function saveState() {
    var params = new URLSearchParams(window.location.search);
    ["venue","venues","category","categories"].forEach(function (k) { params.delete(k); });
    if (state.venues.length > 0) {
      params.set(CONFIG.multiVenue ? "venues" : "venue",
        CONFIG.multiVenue ? state.venues.join(",") : state.venues[0]);
    }
    if (state.categories.length > 0) {
      params.set(CONFIG.multiCategory ? "categories" : "category",
        CONFIG.multiCategory ? state.categories.join(",") : state.categories[0]);
    }
    var qs = params.toString();
    try { history.replaceState(null, "", window.location.pathname + (qs ? "?" + qs : "") + window.location.hash); } catch (e) {}
  }

  function toggleFilter(group, value) {
    var arr = state[group];
    var multi = (group === "venues") ? CONFIG.multiVenue : CONFIG.multiCategory;
    var i = arr.indexOf(value);
    if (i >= 0) arr.splice(i, 1);
    else if (multi) arr.push(value);
    else state[group] = [value];
    saveState();
    buildFilterBar();
    renderAll();
  }

  function buildFilterBar() {
    var venueSet = {}, categorySet = {};
    allEvents.forEach(function (ev) {
      if (ev.venue) venueSet[ev.venue] = true;
      var c = (ev.type || ev.event_category || "other").toLowerCase();
      categorySet[c] = true;
    });
    var venues = Object.keys(venueSet).sort();
    var categories = Object.keys(categorySet).sort();

    fusedChipsEl.innerHTML = "";
    var anyActive = state.venues.length > 0 || state.categories.length > 0;

    var all = document.createElement("button");
    all.type = "button";
    all.className = "filter-chip" + (!anyActive ? " is-active" : "");
    all.setAttribute("aria-checked", !anyActive ? "true" : "false");
    all.setAttribute("role", "radio");
    all.textContent = "All";
    all.addEventListener("click", function () {
      state = { venues: [], categories: [] };
      saveState();
      buildFilterBar();
      renderAll();
    });
    fusedChipsEl.appendChild(all);

    categories.forEach(function (c) {
      addChip(fusedChipsEl, "categories", c, CATEGORY_LABELS[c] || c.replace(/_/g," "), CATEGORY_ICONS[c]);
    });
    var sep = document.createElement("span");
    sep.className = "filter-chip-sep"; sep.textContent = "|"; sep.setAttribute("aria-hidden","true");
    fusedChipsEl.appendChild(sep);
    venues.forEach(function (v) { addChip(fusedChipsEl, "venues", v, v, "📍"); });
  }

  function addChip(container, group, value, label, icon) {
    var btn = document.createElement("button");
    var selected = state[group].indexOf(value) >= 0;
    var multi = (group === "venues") ? CONFIG.multiVenue : CONFIG.multiCategory;
    btn.type = "button";
    btn.className = "filter-chip" + (selected ? " is-active" : "");
    btn.setAttribute(multi ? "aria-pressed" : "aria-checked", selected ? "true" : "false");
    btn.setAttribute("role", multi ? "button" : "radio");

    if (CONFIG.iconMode !== "text-only") {
      var i = document.createElement("span");
      i.className = "filter-chip-icon"; i.setAttribute("aria-hidden","true");
      i.textContent = icon || "•";
      btn.appendChild(i);
    }
    var lab = document.createElement("span");
    lab.className = "filter-chip-label";
    lab.textContent = label;
    btn.appendChild(lab);
    btn.addEventListener("click", function () { toggleFilter(group, value); });
    container.appendChild(btn);
  }

  function eventPassesFilter(ev) {
    if (state.venues.length > 0) {
      if (!ev.venue || state.venues.indexOf(ev.venue) < 0) return false;
    }
    if (state.categories.length > 0) {
      var c = (ev.type || ev.event_category || "other").toLowerCase();
      if (state.categories.indexOf(c) < 0) return false;
    }
    return true;
  }

  function groupEvents(events) {
    var byTitle = {}, order = [];
    events.forEach(function (ev) {
      if (!eventPassesFilter(ev)) return;
      var key = ev.title || "Untitled";
      if (!byTitle[key]) {
        byTitle[key] = {
          title: ev.title, rating: ev.rating || 0,
          type: (ev.type || ev.event_category || "other").toLowerCase(),
          venue: ev.venue || "", url: ev.url || "",
          description: ev.description || "", one_liner: ev.one_liner_summary || "",
          showings: []
        };
        order.push(key);
      }
      var entry = byTitle[key];
      var s = ev.screenings || [];
      if (s.length > 0) {
        s.forEach(function (x) { entry.showings.push({date:x.date,time:x.time||"",venue:x.venue||ev.venue||"",url:x.url||ev.url||""}); });
      } else {
        (ev.dates || []).forEach(function (d, i) {
          entry.showings.push({date:d,time:(ev.times||[])[i]||"",venue:ev.venue||"",url:ev.url||""});
        });
      }
    });
    var out = order.map(function (k) { return byTitle[k]; });
    out.forEach(function (ev) { ev.showings = dedupeShowings(ev.showings); });
    out.sort(function (a, b) { return b.rating - a.rating || a.title.localeCompare(b.title); });
    return out;
  }

  function dedupeShowings(list) {
    var seen = {}, out = [];
    list.forEach(function (s) { var k = s.date + "|" + s.time; if (!seen[k]) { seen[k]=true; out.push(s); } });
    out.sort(function (a, b) { return a.date < b.date ? -1 : a.date > b.date ? 1 : (a.time||"").localeCompare(b.time||""); });
    return out;
  }

  function ratingClass(r) { return r >= 8 ? "high" : r >= 5 ? "mid" : "low"; }
  function formatDate(str) { var p = str.split("-"); return MONTHS_SHORT[parseInt(p[1],10)-1] + " " + parseInt(p[2],10); }
  function formatTime(t) {
    if (!t) return ""; var m = t.match(/^(\d{1,2}):(\d{2})$/); if (!m) return t;
    var hh = parseInt(m[1],10), ampm = hh >= 12 ? "PM" : "AM", h12 = hh%12===0?12:hh%12;
    return h12 + ":" + m[2] + " " + ampm;
  }

  function renderAll() {
    var grouped = groupEvents(allEvents);
    renderPicks(grouped.slice(0, 10));
    renderListings(grouped);
  }

  function renderPicks(picks) {
    picksList.innerHTML = "";
    if (picks.length === 0) {
      var e = document.createElement("li"); e.className="empty-state"; e.textContent="No picks match your filters."; picksList.appendChild(e); return;
    }
    var frag = document.createDocumentFragment();
    picks.forEach(function (ev) {
      var li = document.createElement("li"); li.className="pick-item";
      var b = document.createElement("span");
      b.className = "pick-rating pick-rating--" + ratingClass(ev.rating);
      b.textContent = ev.rating > 0 ? ev.rating + " / 10" : "—";
      b.setAttribute("aria-label","rated " + ev.rating + " out of 10");
      li.appendChild(b);
      var t = document.createElement("span"); t.className="pick-title";
      if (ev.url) { var a = document.createElement("a"); a.href=ev.url; a.target="_blank"; a.rel="noopener"; a.textContent=ev.title; t.appendChild(a); }
      else t.textContent = ev.title;
      li.appendChild(t);
      var m = document.createElement("span"); m.className="pick-meta";
      var next = ev.showings[0], parts = [CATEGORY_LABELS[ev.type] || ev.type.replace(/_/g," ")];
      if (next) parts.push(formatDate(next.date) + (next.time ? " · " + formatTime(next.time) : ""));
      m.textContent = parts.join(" · ");
      li.appendChild(m);
      frag.appendChild(li);
    });
    picksList.appendChild(frag);
  }

  function renderListings(events) {
    listingsEl.innerHTML = "<h2 class=\"listings-heading\">COMPLETE EVENTS — BY MERIT</h2>";
    if (events.length === 0) {
      var e = document.createElement("p"); e.className="empty-state"; e.textContent="No events match your filters."; listingsEl.appendChild(e); return;
    }
    var frag = document.createDocumentFragment();
    events.forEach(function (ev) {
      var card = document.createElement("article"); card.className="event-card";
      var h = document.createElement("div"); h.className="event-header";
      var b = document.createElement("span");
      b.className = "event-rating-badge rating-" + ratingClass(ev.rating);
      b.textContent = ev.rating > 0 ? ev.rating + " / 10" : "—";
      b.setAttribute("aria-label","rated " + ev.rating + " out of 10");
      h.appendChild(b);
      var c = document.createElement("div"); c.className="event-title-col";
      var t = document.createElement("div"); t.className="event-title-text";
      if (ev.url) { var a=document.createElement("a"); a.href=ev.url; a.target="_blank"; a.rel="noopener"; a.className="event-title-link"; a.textContent=ev.title; a.addEventListener("click",function(e){e.stopPropagation();}); t.appendChild(a); }
      else t.textContent = ev.title;
      c.appendChild(t);
      var sub = document.createElement("div"); sub.className="event-subtitle";
      var sp = []; if (ev.venue) sp.push(ev.venue); sp.push(CATEGORY_LABELS[ev.type] || ev.type.replace(/_/g," "));
      sub.textContent = sp.join(" · "); c.appendChild(sub);
      h.appendChild(c);
      var ar = document.createElement("span"); ar.className="expand-indicator"; ar.textContent="▶"; ar.setAttribute("aria-hidden","true");
      h.appendChild(ar);
      card.appendChild(h);

      var panel = document.createElement("div"); panel.className="event-panel";
      if (ev.one_liner) { var ol=document.createElement("p"); ol.className="event-oneliner"; ol.textContent=ev.one_liner; panel.appendChild(ol); }
      var review = ev.description ? ev.description.replace(/<[^>]*>/g, "") : "";
      if (review && review !== ev.one_liner) { var p=document.createElement("p"); p.className="event-review-body"; p.textContent=review; panel.appendChild(p); }
      if (panel.childNodes.length > 0) card.appendChild(panel);

      h.setAttribute("role","button"); h.setAttribute("tabindex","0"); h.setAttribute("aria-expanded","false");
      h.addEventListener("click", function () { var exp = card.classList.toggle("is-expanded"); h.setAttribute("aria-expanded", exp?"true":"false"); });
      h.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); h.click(); }
        if (e.key === "Escape" && card.classList.contains("is-expanded")) { card.classList.remove("is-expanded"); h.setAttribute("aria-expanded","false"); }
      });
      frag.appendChild(card);
    });
    listingsEl.appendChild(frag);
  }
})();
