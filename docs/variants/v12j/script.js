(function () {
  "use strict";

  var CONFIG = {
    variant: "v12j",
    multiVenue: true,
    multiCategory: true,
    persistence: "url+session",
    storageKey: "v12j_filter",
    iconMode: "icon+text",
    collapseSheet: false
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
  var venueChipsEl = document.getElementById("venue-chips");
  var categoryChipsEl = document.getElementById("category-chips");

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
    var vm = params.get("venues");
    var vs = params.get("venue");
    var cm = params.get("categories");
    var cs = params.get("category");
    if (vm) s.venues = vm.split(",").filter(Boolean);
    else if (vs) s.venues = [vs];
    if (cm) s.categories = cm.split(",").filter(Boolean);
    else if (cs) s.categories = [cs];

    if (s.venues.length === 0 && s.categories.length === 0 && CONFIG.persistence !== "url-only") {
      try {
        var store = CONFIG.persistence === "url+local" ? localStorage : sessionStorage;
        var saved = JSON.parse(store.getItem(CONFIG.storageKey) || "null");
        if (saved) { s.venues = saved.venues || []; s.categories = saved.categories || []; }
      } catch (e) {}
    }
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
    var newUrl = window.location.pathname + (qs ? "?" + qs : "") + window.location.hash;
    try { history.replaceState(null, "", newUrl); } catch (e) {}
    try {
      var store = CONFIG.persistence === "url+local" ? localStorage
                : CONFIG.persistence === "url+session" ? sessionStorage : null;
      if (store) store.setItem(CONFIG.storageKey, JSON.stringify(state));
    } catch (e) {}
  }

  function toggleFilter(group, value) {
    var arr = state[group];
    var multi = (group === "venues") ? CONFIG.multiVenue : CONFIG.multiCategory;
    var i = arr.indexOf(value);
    if (i >= 0) {
      arr.splice(i, 1);
    } else if (multi) {
      arr.push(value);
    } else {
      state[group] = [value];
    }
    saveState();
    buildFilterBar();
    renderAll();
  }

  function clearFilters() {
    state = { venues: [], categories: [] };
    saveState();
    buildFilterBar();
    renderAll();
  }

  function buildFilterBar() {
    var venueSet = {};
    var categorySet = {};
    allEvents.forEach(function (ev) {
      if (ev.venue) venueSet[ev.venue] = true;
      var c = (ev.type || ev.event_category || "other").toLowerCase();
      categorySet[c] = true;
    });
    var venues = Object.keys(venueSet).sort();
    var categories = Object.keys(categorySet).sort();

    if (venueChipsEl) renderChips(venueChipsEl, venues, "venues");
    if (categoryChipsEl) renderChips(categoryChipsEl, categories, "categories");
  }

  function renderChips(container, values, group) {
    container.innerHTML = "";
    var active = state[group];
    var multi = (group === "venues") ? CONFIG.multiVenue : CONFIG.multiCategory;

    var allBtn = document.createElement("button");
    allBtn.type = "button";
    allBtn.className = "filter-chip" + (active.length === 0 ? " is-active" : "");
    allBtn.setAttribute(multi ? "aria-pressed" : "aria-checked", active.length === 0 ? "true" : "false");
    allBtn.setAttribute("role", multi ? "button" : "radio");
    allBtn.textContent = "All";
    allBtn.addEventListener("click", function () {
      state[group] = [];
      saveState();
      buildFilterBar();
      renderAll();
    });
    container.appendChild(allBtn);

    values.forEach(function (v) {
      var btn = document.createElement("button");
      btn.type = "button";
      var selected = active.indexOf(v) >= 0;
      btn.className = "filter-chip" + (selected ? " is-active" : "");
      btn.setAttribute(multi ? "aria-pressed" : "aria-checked", selected ? "true" : "false");
      btn.setAttribute("role", multi ? "button" : "radio");
      btn.dataset.value = v;

      if (group === "categories" && CONFIG.iconMode !== "text-only") {
        var icon = document.createElement("span");
        icon.className = "filter-chip-icon";
        icon.setAttribute("aria-hidden", "true");
        icon.textContent = CATEGORY_ICONS[v] || "•";
        btn.appendChild(icon);
      }
      var label = document.createElement("span");
      label.className = "filter-chip-label";
      label.textContent = group === "categories"
        ? (CATEGORY_LABELS[v] || v.replace(/_/g, " "))
        : v;
      btn.appendChild(label);

      btn.addEventListener("click", function () { toggleFilter(group, v); });
      btn.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          toggleFilter(group, v);
        }
      });
      container.appendChild(btn);
    });

    if (active.length > 0) {
      var clear = document.createElement("button");
      clear.type = "button";
      clear.className = "filter-chip filter-chip--clear";
      clear.textContent = "Clear";
      clear.addEventListener("click", function () {
        state[group] = [];
        saveState();
        buildFilterBar();
        renderAll();
      });
      container.appendChild(clear);
    }
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
    var byTitle = {};
    var order = [];
    events.forEach(function (ev) {
      if (!eventPassesFilter(ev)) return;
      var key = ev.title || "Untitled";
      if (!byTitle[key]) {
        byTitle[key] = {
          title: ev.title,
          rating: ev.rating || 0,
          type: (ev.type || ev.event_category || "other").toLowerCase(),
          venue: ev.venue || "",
          url: ev.url || "",
          description: ev.description || "",
          one_liner: ev.one_liner_summary || "",
          showings: []
        };
        order.push(key);
      }
      var entry = byTitle[key];
      var screenings = ev.screenings || [];
      if (screenings.length > 0) {
        screenings.forEach(function (s) {
          entry.showings.push({ date: s.date, time: s.time || "", venue: s.venue || ev.venue || "", url: s.url || ev.url || "" });
        });
      } else {
        var dates = ev.dates || [];
        var times = ev.times || [];
        dates.forEach(function (d, i) {
          entry.showings.push({ date: d, time: times[i] || "", venue: ev.venue || "", url: ev.url || "" });
        });
      }
    });
    var result = order.map(function (k) { return byTitle[k]; });
    result.forEach(function (ev) { ev.showings = dedupeShowings(ev.showings); });
    result.sort(function (a, b) { return b.rating - a.rating || a.title.localeCompare(b.title); });
    return result;
  }

  function dedupeShowings(list) {
    var seen = {}, out = [];
    list.forEach(function (s) {
      var k = s.date + "|" + s.time;
      if (!seen[k]) { seen[k] = true; out.push(s); }
    });
    out.sort(function (a, b) { return a.date < b.date ? -1 : a.date > b.date ? 1 : (a.time || "").localeCompare(b.time || ""); });
    return out;
  }

  function ratingClass(r) { return r >= 8 ? "high" : r >= 5 ? "mid" : "low"; }

  function formatDate(str) {
    var p = str.split("-");
    return MONTHS_SHORT[parseInt(p[1], 10) - 1] + " " + parseInt(p[2], 10);
  }

  function formatTime(t) {
    if (!t) return "";
    var m = t.match(/^(\d{1,2}):(\d{2})$/);
    if (!m) return t;
    var hh = parseInt(m[1], 10);
    var ampm = hh >= 12 ? "PM" : "AM";
    var h12 = hh % 12 === 0 ? 12 : hh % 12;
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
      var empty = document.createElement("li");
      empty.className = "empty-state";
      empty.textContent = "No picks match your filters.";
      picksList.appendChild(empty);
      return;
    }
    var frag = document.createDocumentFragment();
    picks.forEach(function (ev) {
      var li = document.createElement("li");
      li.className = "pick-item";
      var badge = document.createElement("span");
      badge.className = "pick-rating pick-rating--" + ratingClass(ev.rating);
      badge.textContent = ev.rating > 0 ? ev.rating + " / 10" : "—";
      badge.setAttribute("aria-label", "rated " + ev.rating + " out of 10");
      li.appendChild(badge);

      var title = document.createElement("span");
      title.className = "pick-title";
      if (ev.url) {
        var a = document.createElement("a");
        a.href = ev.url; a.target = "_blank"; a.rel = "noopener";
        a.textContent = ev.title; title.appendChild(a);
      } else { title.textContent = ev.title; }
      li.appendChild(title);

      var meta = document.createElement("span");
      meta.className = "pick-meta";
      var next = ev.showings[0];
      var parts = [CATEGORY_LABELS[ev.type] || ev.type.replace(/_/g, " ")];
      if (next) parts.push(formatDate(next.date) + (next.time ? " · " + formatTime(next.time) : ""));
      meta.textContent = parts.join(" · ");
      li.appendChild(meta);
      frag.appendChild(li);
    });
    picksList.appendChild(frag);
  }

  function renderListings(events) {
    listingsEl.innerHTML = "<h2 class=\"listings-heading\">COMPLETE EVENTS — BY MERIT</h2>";
    if (events.length === 0) {
      var empty = document.createElement("p");
      empty.className = "empty-state";
      empty.textContent = "No events match your filters. Try widening them.";
      listingsEl.appendChild(empty);
      return;
    }
    var frag = document.createDocumentFragment();
    events.forEach(function (ev) {
      var card = document.createElement("article");
      card.className = "event-card";
      var header = document.createElement("div");
      header.className = "event-header";
      var badge = document.createElement("span");
      badge.className = "event-rating-badge rating-" + ratingClass(ev.rating);
      badge.textContent = ev.rating > 0 ? ev.rating + " / 10" : "—";
      badge.setAttribute("aria-label", "rated " + ev.rating + " out of 10");
      header.appendChild(badge);

      var col = document.createElement("div");
      col.className = "event-title-col";
      var title = document.createElement("div");
      title.className = "event-title-text";
      if (ev.url) {
        var a = document.createElement("a");
        a.href = ev.url; a.target = "_blank"; a.rel = "noopener";
        a.className = "event-title-link";
        a.textContent = ev.title;
        a.addEventListener("click", function (e) { e.stopPropagation(); });
        title.appendChild(a);
      } else { title.textContent = ev.title; }
      col.appendChild(title);

      var sub = document.createElement("div");
      sub.className = "event-subtitle";
      var sp = [];
      if (ev.venue) sp.push(ev.venue);
      sp.push(CATEGORY_LABELS[ev.type] || ev.type.replace(/_/g, " "));
      sub.textContent = sp.join(" · ");
      col.appendChild(sub);
      header.appendChild(col);

      var arrow = document.createElement("span");
      arrow.className = "expand-indicator";
      arrow.textContent = "▶";
      arrow.setAttribute("aria-hidden", "true");
      header.appendChild(arrow);
      card.appendChild(header);

      var panel = document.createElement("div");
      panel.className = "event-panel";
      if (ev.one_liner) {
        var ol = document.createElement("p");
        ol.className = "event-oneliner";
        ol.textContent = ev.one_liner;
        panel.appendChild(ol);
      }
      var review = ev.description ? ev.description.replace(/<[^>]*>/g, "") : "";
      if (review && review !== ev.one_liner) {
        var p = document.createElement("p");
        p.className = "event-review-body";
        p.textContent = review;
        panel.appendChild(p);
      }
      if (panel.childNodes.length > 0) card.appendChild(panel);

      header.setAttribute("role", "button");
      header.setAttribute("tabindex", "0");
      header.setAttribute("aria-expanded", "false");
      header.addEventListener("click", function () {
        var exp = card.classList.toggle("is-expanded");
        header.setAttribute("aria-expanded", exp ? "true" : "false");
      });
      header.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); header.click(); }
        if (e.key === "Escape" && card.classList.contains("is-expanded")) {
          card.classList.remove("is-expanded");
          header.setAttribute("aria-expanded", "false");
        }
      });
      frag.appendChild(card);
    });
    listingsEl.appendChild(frag);
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      var sheet = document.querySelector(".filter-sheet.is-open");
      if (sheet) sheet.classList.remove("is-open");
    }
  });
})();
