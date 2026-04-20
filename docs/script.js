/**
 * Culture-Calendar frontend.
 *
 * Single IIFE renders the static GitHub Pages site. No framework, no
 * bundler — everything runs directly in the browser from this file.
 * All data comes from ``docs/data.json`` (written by
 * ``update_website_data.py`` server-side).
 *
 * Module layout (by line number):
 *
 *   11-55   Constants, DOM refs, state.
 *   60-165  Data loading, occurrence expansion, merge-across-venues.
 *   166-215 Grouping (groupEvents, dedupeShowings).
 *   217-245 Rating + review parsing helpers.
 *   247-285 Date/time formatters.
 *   287-336 Search + filter (getSearchQuery, matchesQuery, filterEvents).
 *   338-449 Search UI (suggestions dropdown + autocomplete).
 *   451-584 Top-picks renderer (buildPickCard, renderPicks).
 *   585-705 Merit-listings renderer (buildListingCard, renderListings).
 *   706-735 "Pending more research" bucket for low-confidence reviews.
 *   740+    Read-aloud (Web Speech API) handlers + bootstrap.
 *
 * Feature inventory: every CSS selector this module depends on must
 * be mirrored in ``.overnight/feature-inventory.json`` so the
 * continuity-user persona catches silent regressions. See
 * ``CLAUDE.md §Feature Inventory`` and ``AGENTS.md §Invariants``.
 *
 * When changing UX here:
 * - Update or add an inventory entry in the same commit.
 * - Run ``scripts/check_live_site.py`` against the updated site for
 *   selector-level regression checks.
 * - For architectural changes, tag the commit ``[persona-gate]`` so
 *   the pre-push hook runs the LLM council (see ``.githooks/pre-push``).
 */
(function () {
  "use strict";

  var DATA_URL = (window.location && window.location.hostname || "").indexOf("github.io") !== -1
    ? "/Culture-Calendar/data.json"
    : "data.json";
  var CATEGORY_LABELS = {
    movie: "Film", film: "Film", concert: "Concert", book_club: "Book Club",
    opera: "Opera", dance: "Dance", ballet: "Ballet", visual_arts: "Visual Arts",
    other: "Other"
  };
  var MONTHS_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  var WEEKDAY_SHORT = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];

  var picksList = document.getElementById("picks-list");
  var listingsEl = document.getElementById("listings");
  var loadingEl = document.getElementById("loading");
  var errorEl = document.getElementById("error");
  var searchInput = document.getElementById("event-search");
  var searchSuggestions = document.getElementById("search-suggestions");

  var allEvents = [];
  var searchDebounceTimer = null;
  var SEARCH_DEBOUNCE_MS = 150;
  var MAX_SUGGESTIONS_PER_GROUP = 20;

  /* task-T1.5: Web Speech API read-aloud button.
     Supported cross-browser (desktop + mobile). Second click on an active
     button cancels. Sentence-chunked so Safari does not truncate long text. */
  var tts = (function () {
    var supported = typeof window !== "undefined"
      && typeof window.speechSynthesis !== "undefined"
      && typeof window.SpeechSynthesisUtterance !== "undefined";
    var voices = [];
    var activeBtn = null;

    function refreshVoices() {
      try { voices = window.speechSynthesis.getVoices() || []; }
      catch (e) { voices = []; }
    }
    if (supported) {
      refreshVoices();
      if (typeof window.speechSynthesis.addEventListener === "function") {
        window.speechSynthesis.addEventListener("voiceschanged", refreshVoices);
      } else {
        window.speechSynthesis.onvoiceschanged = refreshVoices;
      }
    }

    function pickVoice() {
      if (!voices.length) return null;
      for (var i = 0; i < voices.length; i++) {
        var v = voices[i];
        if (v && v.lang && v.lang.toLowerCase().indexOf("en") === 0 && v.localService) return v;
      }
      for (var j = 0; j < voices.length; j++) {
        var w = voices[j];
        if (w && w.lang && w.lang.toLowerCase().indexOf("en") === 0) return w;
      }
      return voices[0] || null;
    }

    function stripHtml(s) {
      if (!s) return "";
      return String(s).replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
    }

    function splitSentences(text) {
      if (!text) return [];
      var raw = text.match(/[^.!?]+[.!?]+(\s|$)|[^.!?]+$/g) || [text];
      var out = [];
      for (var i = 0; i < raw.length; i++) {
        var s = raw[i].trim();
        if (s) out.push(s);
      }
      return out;
    }

    function cancel() {
      if (!supported) return;
      try { window.speechSynthesis.cancel(); } catch (e) { /* noop */ }
    }

    function resetButton(btn) {
      if (!btn) return;
      btn.classList.remove("is-playing");
      btn.textContent = "\u25B6 Read aloud";
      btn.setAttribute("aria-label", "Read aloud");
    }

    function clearActive() {
      if (activeBtn) resetButton(activeBtn);
      activeBtn = null;
    }

    function buildText(ev) {
      var parts = [];
      if (ev.one_liner) parts.push(String(ev.one_liner).trim());
      var body = stripHtml(ev.description);
      if (body) parts.push(body);
      return parts.filter(Boolean).join(" ").trim();
    }

    function speakNow(btn, text) {
      cancel();
      clearActive();
      var chunks = splitSentences(text);
      if (!chunks.length) return;
      var voice = pickVoice();
      activeBtn = btn;
      btn.classList.add("is-playing");
      btn.textContent = "\u25A0 Stop";
      btn.setAttribute("aria-label", "Stop read aloud");
      var idx = 0;
      function next() {
        if (activeBtn !== btn) return;
        if (idx >= chunks.length) { clearActive(); return; }
        var u = new window.SpeechSynthesisUtterance(chunks[idx]);
        u.rate = 0.95;
        u.pitch = 1.0;
        u.volume = 1.0;
        if (voice) { u.voice = voice; u.lang = voice.lang; }
        u.onend = function () { if (activeBtn !== btn) return; idx++; next(); };
        u.onerror = function () { if (activeBtn === btn) clearActive(); };
        try { window.speechSynthesis.speak(u); }
        catch (e) { clearActive(); }
      }
      next();
    }

    function createButton(ev) {
      if (!supported) return null;
      var text = buildText(ev);
      if (!text) return null;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "tts-button";
      btn.textContent = "\u25B6 Read aloud";
      btn.setAttribute("aria-label", "Read aloud");
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        if (activeBtn === btn) { cancel(); clearActive(); return; }
        speakNow(btn, text);
      });
      return btn;
    }

    return { supported: supported, createButton: createButton };
  })();

  fetch(DATA_URL)
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(function (raw) {
      allEvents = Array.isArray(raw) ? raw : (raw.events || []);
      loadingEl.hidden = true;
      renderAll();
    })
    .catch(function (err) {
      loadingEl.hidden = true;
      errorEl.hidden = false;
      errorEl.textContent = "Error: " + err.message;
    });

  initSearch();

  function groupEvents(events) {
    var byTitle = {};
    var order = [];
    events.forEach(function (ev) {
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
          review_confidence: (ev.review_confidence || "unknown").toLowerCase(),
          showings: []
        };
        order.push(key);
      } else if ((ev.review_confidence || "").toLowerCase() === "low") {
        byTitle[key].review_confidence = "low";
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

  /* task-T2.1: JSON-LD Event schema injection.
     Runs the first time a card opens. Injects a
     <script type="application/ld+json"> tag so search engines and
     SERP-style previews can read Event metadata per
     https://schema.org/Event. Injected once per card. */
  function buildEventJsonLd(ev) {
    var first = ev.showings && ev.showings[0];
    var data = {
      "@context": "https://schema.org",
      "@type": "Event",
      "name": ev.title || "Untitled event"
    };
    if (first && first.date) {
      data.startDate = first.time ? (first.date + "T" + first.time) : first.date;
    }
    var venueName = (first && first.venue) || ev.venue;
    if (venueName) {
      data.location = { "@type": "Place", "name": venueName };
    }
    if (ev.description) {
      var flat = String(ev.description).replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
      if (flat) data.description = flat;
    }
    var offerUrl = (first && first.url) || ev.url;
    if (offerUrl) {
      data.offers = { "@type": "Offer", "url": offerUrl };
    }
    return data;
  }

  function injectEventJsonLd(card, ev) {
    if (!card || card.dataset.jsonLdInjected === "1") return;
    try {
      var script = document.createElement("script");
      script.type = "application/ld+json";
      script.textContent = JSON.stringify(buildEventJsonLd(ev));
      card.appendChild(script);
      card.dataset.jsonLdInjected = "1";
    } catch (e) { /* noop */ }
  }

  /* task-T2.3: Dynamic Open Graph / Twitter meta tags for deep-linked
     events. Static fallback lives in index.html <head>. When the URL
     carries #event=<id>, we rewrite the meta tags so social-card
     scrapers (Twitter, LinkedIn, Slack, iMessage) see an event-
     specific title, description, and SVG card image generated by
     scripts/build_og_cards.py (docs/og/<slug>.svg). T2.4 adds the
     hashchange handler that wires this up; exposing updateOGMetaForEvent
     here keeps that task a small one-liner. */
  var OG_SITE_ORIGIN = "https://hadrien-cornier.github.io/Culture-Calendar";
  var OG_DEFAULT_TITLE = "Culture Calendar — Austin cultural events, AI-curated";
  var OG_DEFAULT_DESCRIPTION = "Austin cultural events, AI-curated. Films, concerts, opera, ballet, and literary events — sorted by merit, not marketing.";
  var OG_DEFAULT_URL = OG_SITE_ORIGIN + "/";
  var OG_DEFAULT_IMAGE = OG_SITE_ORIGIN + "/og/site-default.svg";

  function ogCardSlug(eventId) {
    if (!eventId) return "";
    var lowered = String(eventId).toLowerCase();
    var safe = lowered.replace(/[^a-z0-9._-]+/g, "-");
    safe = safe.replace(/^[-.]+|[-.]+$/g, "");
    safe = safe.replace(/-{2,}/g, "-");
    return safe;
  }

  function setMetaContent(selector, content) {
    var el = document.head.querySelector(selector);
    if (!el) return;
    el.setAttribute("content", content);
  }

  function flattenText(html) {
    if (!html) return "";
    return String(html).replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
  }

  function resetOGMetaToDefault() {
    setMetaContent('meta[property="og:title"]', OG_DEFAULT_TITLE);
    setMetaContent('meta[property="og:description"]', OG_DEFAULT_DESCRIPTION);
    setMetaContent('meta[property="og:url"]', OG_DEFAULT_URL);
    setMetaContent('meta[property="og:image"]', OG_DEFAULT_IMAGE);
    setMetaContent('meta[property="og:type"]', "website");
    setMetaContent('meta[name="twitter:title"]', OG_DEFAULT_TITLE);
    setMetaContent('meta[name="twitter:description"]', OG_DEFAULT_DESCRIPTION);
    setMetaContent('meta[name="twitter:image"]', OG_DEFAULT_IMAGE);
  }

  function updateOGMetaForEvent(ev) {
    if (!ev) { resetOGMetaToDefault(); return; }
    var eventId = ev.id || ev.event_id || ev.title || "";
    var slug = ogCardSlug(eventId);
    var imgUrl = slug ? (OG_SITE_ORIGIN + "/og/" + slug + ".svg") : OG_DEFAULT_IMAGE;
    var title = ev.title ? (ev.title + " — Culture Calendar") : OG_DEFAULT_TITLE;
    var one = (ev.one_liner_summary || ev.one_liner || "").trim();
    var flat = one || flattenText(ev.description) || OG_DEFAULT_DESCRIPTION;
    if (flat.length > 280) flat = flat.slice(0, 277) + "…";
    var hashId = ev.id || ev.event_id || "";
    var pageUrl = hashId ? (OG_DEFAULT_URL + "#event=" + encodeURIComponent(hashId)) : OG_DEFAULT_URL;
    setMetaContent('meta[property="og:type"]', "article");
    setMetaContent('meta[property="og:title"]', title);
    setMetaContent('meta[property="og:description"]', flat);
    setMetaContent('meta[property="og:url"]', pageUrl);
    setMetaContent('meta[property="og:image"]', imgUrl);
    setMetaContent('meta[name="twitter:title"]', title);
    setMetaContent('meta[name="twitter:description"]', flat);
    setMetaContent('meta[name="twitter:image"]', imgUrl);
  }

  window.cultureCalendar = window.cultureCalendar || {};
  window.cultureCalendar.updateOGMetaForEvent = updateOGMetaForEvent;
  window.cultureCalendar.resetOGMetaToDefault = resetOGMetaToDefault;

  function parseReview(html) {
    if (!html) return { rating: "", sections: [], flat: "" };
    var doc = new DOMParser().parseFromString("<div>" + html + "</div>", "text/html");
    var ps = doc.querySelectorAll("p");
    var rating = "";
    var sections = [];
    ps.forEach(function (p) {
      var text = (p.textContent || "").trim();
      if (!text) return;
      var rMatch = text.match(/^★\s*Rating:\s*(\d+(?:\.\d+)?)\s*\/\s*10/i);
      if (rMatch) { rating = rMatch[1]; return; }
      var strong = p.querySelector("strong");
      var label = "", body = text;
      if (strong) {
        label = (strong.textContent || "").trim();
        var after = text.indexOf(label);
        if (after >= 0) {
          body = text.slice(after + label.length).replace(/^[\s–—\-:]+/, "").trim();
        }
      }
      var leading = text.match(/^([\p{Extended_Pictographic}\p{Emoji}]+)/u);
      var emoji = leading ? leading[1] : "";
      if (label || body) sections.push({ emoji: emoji, label: label, body: body });
    });
    var flat = sections.map(function (s) { return s.body; }).join("\n\n");
    return { rating: rating, sections: sections, flat: flat };
  }

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

  function formatTimeShort(t) {
    if (!t) return "";
    var m = t.match(/^(\d{1,2}):(\d{2})$/);
    if (!m) return t;
    var hh = parseInt(m[1], 10);
    var ampm = hh >= 12 ? "pm" : "am";
    var h12 = hh % 12 === 0 ? 12 : hh % 12;
    var mm = m[2];
    return h12 + (mm === "00" ? "" : ":" + mm) + ampm;
  }

  function formatWhen(dateStr, timeStr) {
    if (!dateStr) return "";
    var p = dateStr.split("-");
    if (p.length !== 3) return dateStr + (timeStr ? " \u00b7 " + formatTimeShort(timeStr) : "");
    var y = parseInt(p[0], 10);
    var mo = parseInt(p[1], 10) - 1;
    var d = parseInt(p[2], 10);
    var dt = new Date(y, mo, d);
    var wd = isNaN(dt.getTime()) ? "" : WEEKDAY_SHORT[dt.getDay()];
    var datePart = (wd ? wd + ", " : "") + MONTHS_SHORT[mo] + " " + d;
    var timePart = formatTimeShort(timeStr);
    return timePart ? datePart + " \u00b7 " + timePart : datePart;
  }

  function getSearchQuery() {
    return (searchInput && searchInput.value || "").trim().toLowerCase();
  }

  function categoryLabel(type) {
    var key = (type || "").toLowerCase();
    return CATEGORY_LABELS[key] || key.replace(/_/g, " ");
  }

  function matchesQuery(ev, q) {
    if (!q) return true;
    var title = (ev.title || "").toLowerCase();
    var venue = (ev.venue || "").toLowerCase();
    var type = (ev.type || ev.event_category || "").toLowerCase();
    var label = categoryLabel(type).toLowerCase();
    return title.indexOf(q) !== -1
      || venue.indexOf(q) !== -1
      || type.indexOf(q) !== -1
      || label.indexOf(q) !== -1;
  }

  function filterEvents(events) {
    var q = getSearchQuery();
    if (!q) return events;
    return events.filter(function (ev) { return matchesQuery(ev, q); });
  }

  function renderAll() {
    var filtered = filterEvents(allEvents);
    var grouped = groupEvents(filtered);
    var needsResearch = [];
    var merit = [];
    grouped.forEach(function (ev) {
      if (ev.review_confidence === "low") needsResearch.push(ev);
      else merit.push(ev);
    });
    var now = new Date();
    now.setHours(0, 0, 0, 0);
    var cap = new Date(now);
    cap.setDate(cap.getDate() + 7);
    var thisWeek = merit.filter(function (ev) {
      if (!ev.showings || !ev.showings[0]) return false;
      var p = ev.showings[0].date.split("-");
      var d = new Date(parseInt(p[0], 10), parseInt(p[1], 10) - 1, parseInt(p[2], 10));
      return d >= now && d < cap;
    });
    renderPicks(thisWeek.slice(0, 10));
    renderListings(merit);
    renderNeedsResearch(needsResearch);
  }

  function initSearch() {
    if (!searchInput || !searchSuggestions) return;
    searchInput.addEventListener("input", function () {
      if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
      searchDebounceTimer = setTimeout(applySearch, SEARCH_DEBOUNCE_MS);
    });
    searchInput.addEventListener("focus", function () {
      showSuggestions();
    });
    searchInput.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        searchInput.value = "";
        applySearch();
        hideSuggestions();
        searchInput.blur();
      }
    });
    searchSuggestions.addEventListener("mousedown", function (e) {
      var li = e.target && e.target.closest ? e.target.closest(".suggestion") : null;
      if (!li) return;
      e.preventDefault();
      var val = li.getAttribute("data-value") || "";
      searchInput.value = val;
      applySearch();
      hideSuggestions();
    });
    document.addEventListener("click", function (e) {
      if (!searchSuggestions || searchSuggestions.hidden) return;
      var t = e.target;
      if (t === searchInput || (searchSuggestions.contains && searchSuggestions.contains(t))) return;
      hideSuggestions();
    });
  }

  function applySearch() {
    renderSuggestions();
    renderAll();
  }

  function showSuggestions() {
    if (!searchSuggestions) return;
    searchSuggestions.hidden = false;
    if (searchInput) searchInput.setAttribute("aria-expanded", "true");
    renderSuggestions();
  }

  function hideSuggestions() {
    if (!searchSuggestions) return;
    searchSuggestions.hidden = true;
    if (searchInput) searchInput.setAttribute("aria-expanded", "false");
  }

  function collectSuggestions(q) {
    var venues = {};
    var titles = {};
    var cats = {};
    allEvents.forEach(function (ev) {
      var venue = ev.venue || "";
      var title = ev.title || "";
      var type = (ev.type || ev.event_category || "").toLowerCase();
      var label = categoryLabel(type);
      if (venue && venue.toLowerCase().indexOf(q) !== -1) venues[venue] = true;
      if (title && title.toLowerCase().indexOf(q) !== -1) titles[title] = true;
      if (label && label.toLowerCase().indexOf(q) !== -1) cats[label] = true;
    });
    return {
      venues: Object.keys(venues).sort(),
      titles: Object.keys(titles).sort(),
      categories: Object.keys(cats).sort()
    };
  }

  function renderSuggestions() {
    if (!searchSuggestions) return;
    var q = getSearchQuery();
    var grouped = collectSuggestions(q);
    searchSuggestions.innerHTML = "";
    var frag = document.createDocumentFragment();
    var total = appendSuggestionGroup(frag, "Venues", grouped.venues, "venue")
      + appendSuggestionGroup(frag, "Titles", grouped.titles, "title")
      + appendSuggestionGroup(frag, "Categories", grouped.categories, "category");
    if (total === 0) {
      var empty = document.createElement("li");
      empty.className = "suggestion-empty";
      empty.textContent = q ? "No matches for “" + searchInput.value.trim() + "”" : "No events yet";
      frag.appendChild(empty);
    }
    searchSuggestions.appendChild(frag);
  }

  function appendSuggestionGroup(frag, label, values, type) {
    if (!values || values.length === 0) return 0;
    var header = document.createElement("li");
    header.className = "suggestion-group";
    header.setAttribute("role", "presentation");
    header.textContent = label;
    frag.appendChild(header);
    var limited = values.slice(0, MAX_SUGGESTIONS_PER_GROUP);
    limited.forEach(function (value) {
      var li = document.createElement("li");
      li.className = "suggestion";
      li.setAttribute("role", "option");
      li.setAttribute("data-type", type);
      li.setAttribute("data-value", value);
      var span = document.createElement("span");
      span.className = "suggestion-label";
      span.textContent = value;
      li.appendChild(span);
      frag.appendChild(li);
    });
    return limited.length;
  }

  function renderPicks(picks) {
    picksList.innerHTML = "";
    picksList.classList.add("top-picks");
    if (picks.length === 0) {
      var empty = document.createElement("li");
      empty.className = "empty-state";
      empty.textContent = "No picks match your filters.";
      picksList.appendChild(empty);
      return;
    }
    var frag = document.createDocumentFragment();
    picks.forEach(function (ev) {
      frag.appendChild(buildPickCard(ev));
    });
    picksList.appendChild(frag);
  }

  function buildPickCard(ev) {
    var card = document.createElement("li");
    card.className = "event-card pick-card";
    if (ev.showings && ev.showings[0]) {
      card.dataset.firstDate = ev.showings[0].date;
    }

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
    var next = ev.showings && ev.showings[0];
    var sp = [CATEGORY_LABELS[ev.type] || (ev.type || "").replace(/_/g, " ")];
    if (ev.venue) sp.unshift(ev.venue);
    if (next) sp.push(formatDate(next.date) + (next.time ? " · " + formatTime(next.time) : ""));
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
    var parsed = parseReview(ev.description);
    if (parsed.sections.length > 0) {
      var reviewWrap = document.createElement("div");
      reviewWrap.className = "event-review";
      parsed.sections.forEach(function (sec, idx) {
        var sectionEl = document.createElement("section");
        sectionEl.className = idx === 0
          ? "event-review-section event-review-first"
          : "event-review-section";
        if (sec.label) {
          var h = document.createElement("h4");
          h.className = "event-review-heading";
          if (sec.emoji) {
            var em = document.createElement("span");
            em.className = "event-review-emoji";
            em.setAttribute("aria-hidden", "true");
            em.textContent = sec.emoji + " ";
            h.appendChild(em);
          }
          h.appendChild(document.createTextNode(sec.label));
          sectionEl.appendChild(h);
        }
        var bodyP = document.createElement("p");
        bodyP.className = "event-review-body";
        bodyP.textContent = sec.body;
        sectionEl.appendChild(bodyP);
        reviewWrap.appendChild(sectionEl);
      });
      panel.appendChild(reviewWrap);
    } else if (ev.description) {
      var flat = ev.description.replace(/<[^>]*>/g, "");
      if (flat && flat !== ev.one_liner) {
        var p = document.createElement("p");
        p.className = "event-review-body";
        p.textContent = flat;
        panel.appendChild(p);
      }
    }
    var ttsSlot = document.createElement("div");
    ttsSlot.className = "event-tts-slot";
    var pickTtsBtn = tts.createButton(ev);
    if (pickTtsBtn) ttsSlot.appendChild(pickTtsBtn);
    panel.appendChild(ttsSlot);
    card.appendChild(panel);

    header.setAttribute("role", "button");
    header.setAttribute("tabindex", "0");
    header.setAttribute("aria-expanded", "false");
    header.addEventListener("click", function () {
      var open = card.classList.toggle("is-open");
      header.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) injectEventJsonLd(card, ev);
    });
    header.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); header.click(); }
      if (e.key === "Escape" && card.classList.contains("is-open")) {
        card.classList.remove("is-open");
        header.setAttribute("aria-expanded", "false");
      }
    });
    return card;
  }

  function buildListingCard(ev) {
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

    var firstShowing = ev.showings && ev.showings[0];
    var whenText = firstShowing ? formatWhen(firstShowing.date, firstShowing.time) : "";
    var when = document.createElement("div");
    when.className = "event-when";
    when.textContent = whenText || "Date TBA";
    col.appendChild(when);

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
    var parsed = parseReview(ev.description);
    if (parsed.sections.length > 0) {
      var reviewWrap = document.createElement("div");
      reviewWrap.className = "event-review";
      parsed.sections.forEach(function (sec, idx) {
        var sectionEl = document.createElement("section");
        sectionEl.className = idx === 0
          ? "event-review-section event-review-first"
          : "event-review-section";
        if (sec.label) {
          var h = document.createElement("h4");
          h.className = "event-review-heading";
          if (sec.emoji) {
            var em = document.createElement("span");
            em.className = "event-review-emoji";
            em.setAttribute("aria-hidden", "true");
            em.textContent = sec.emoji + " ";
            h.appendChild(em);
          }
          h.appendChild(document.createTextNode(sec.label));
          sectionEl.appendChild(h);
        }
        var bodyP = document.createElement("p");
        bodyP.className = "event-review-body";
        bodyP.textContent = sec.body;
        sectionEl.appendChild(bodyP);
        reviewWrap.appendChild(sectionEl);
      });
      panel.appendChild(reviewWrap);
    } else if (ev.description) {
      var flat = ev.description.replace(/<[^>]*>/g, "");
      if (flat && flat !== ev.one_liner) {
        var p = document.createElement("p");
        p.className = "event-review-body";
        p.textContent = flat;
        panel.appendChild(p);
      }
    }
    var listingTtsBtn = tts.createButton(ev);
    if (listingTtsBtn) {
      var listingTtsSlot = document.createElement("div");
      listingTtsSlot.className = "event-tts-slot";
      listingTtsSlot.appendChild(listingTtsBtn);
      panel.appendChild(listingTtsSlot);
    }
    if (panel.childNodes.length > 0) card.appendChild(panel);

    header.setAttribute("role", "button");
    header.setAttribute("tabindex", "0");
    header.setAttribute("aria-expanded", "false");
    header.addEventListener("click", function () {
      var exp = card.classList.toggle("is-expanded");
      header.setAttribute("aria-expanded", exp ? "true" : "false");
      if (exp) injectEventJsonLd(card, ev);
    });
    header.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); header.click(); }
      if (e.key === "Escape" && card.classList.contains("is-expanded")) {
        card.classList.remove("is-expanded");
        header.setAttribute("aria-expanded", "false");
      }
    });
    return card;
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
    events.forEach(function (ev) { frag.appendChild(buildListingCard(ev)); });
    listingsEl.appendChild(frag);
  }

  function renderNeedsResearch(events) {
    var host = document.getElementById("needs-research");
    if (!host) return;
    host.innerHTML = "";
    var details = document.createElement("details");
    details.className = "needs-research-section";
    var summary = document.createElement("summary");
    summary.className = "needs-research-summary";
    summary.textContent = "Pending more research — light evidence available (" + events.length + " events)";
    details.appendChild(summary);
    var body = document.createElement("div");
    body.className = "needs-research-body";
    if (events.length === 0) {
      var note = document.createElement("p");
      note.className = "needs-research-empty";
      note.textContent = "No low-confidence reviews in this filter.";
      body.appendChild(note);
    } else {
      var frag = document.createDocumentFragment();
      events.forEach(function (ev) { frag.appendChild(buildListingCard(ev)); });
      body.appendChild(frag);
    }
    details.appendChild(body);
    host.appendChild(details);
  }
})();
