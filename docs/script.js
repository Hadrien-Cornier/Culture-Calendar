(function () {
  "use strict";

  var picksList = document.getElementById("picks-list");
  var listingsEl = document.getElementById("listings");
  var loadingEl = document.getElementById("loading");
  var errorEl = document.getElementById("error");
  var searchInput = document.getElementById("search-input");
  var venueFiltersEl = document.getElementById("venue-filters");
  var categoryFiltersEl = document.getElementById("category-filters");
  var filterCountEl = document.getElementById("filter-count");
  var filterClearEl = document.getElementById("filter-clear");

  var allGrouped = [];
  var currentStartIso = "";
  var currentPicksEndIso = "";
  var searchDebounceTimer = null;

  var params = new URLSearchParams(window.location.search);
  var debugDate = params.get("debug_date");
  var daysAhead = parseInt(params.get("days") || "14", 10);
  var picksDays = parseInt(params.get("picks_days") || "7", 10);
  var showAll = params.get("all") === "1";

  var currentQuery = (params.get("q") || "").trim();
  var currentVenue = params.get("venue") || "";
  var currentCategory = params.get("category") || "";

  if (searchInput && currentQuery) {
    searchInput.value = currentQuery;
  }

  function syncURLState() {
    var next = new URLSearchParams(window.location.search);
    if (currentQuery) next.set("q", currentQuery); else next.delete("q");
    if (currentVenue) next.set("venue", currentVenue); else next.delete("venue");
    if (currentCategory) next.set("category", currentCategory); else next.delete("category");
    var qs = next.toString();
    var newUrl = window.location.pathname + (qs ? "?" + qs : "") + window.location.hash;
    try {
      window.history.replaceState(null, "", newUrl);
    } catch (e) {
      // ignore — file:// or sandbox restrictions
    }
  }

  function hasActiveFilters() {
    return !!(currentQuery || currentVenue || currentCategory);
  }

  var MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var DAYS_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  var TYPE_LABELS = {
    movie: "Film",
    opera: "Opera",
    concert: "Concert",
    book_club: "Book Club",
    dance: "Dance",
    ballet: "Ballet",
    symphony: "Symphony",
    other: "Event"
  };
  function formatType(t) {
    if (!t) return "";
    if (TYPE_LABELS[t]) return TYPE_LABELS[t];
    return t.replace(/_/g, " ").replace(/\b\w/g, function (c) {
      return c.toUpperCase();
    });
  }

  var headerIdCounter = 0;

  function todayISO() {
    if (debugDate) return debugDate;
    var d = new Date();
    return d.getFullYear() + "-" +
      String(d.getMonth() + 1).padStart(2, "0") + "-" +
      String(d.getDate()).padStart(2, "0");
  }
  function isoPlusDays(iso, n) {
    var d = new Date(iso + "T00:00:00");
    d.setDate(d.getDate() + n);
    return d.getFullYear() + "-" +
      String(d.getMonth() + 1).padStart(2, "0") + "-" +
      String(d.getDate()).padStart(2, "0");
  }
  function dayOfWeek(iso) {
    var d = new Date(iso + "T00:00:00");
    return DAYS_SHORT[d.getDay()];
  }

  var DATA_URL = (window.location && window.location.hostname || "").indexOf("github.io") !== -1 ? "/Culture-Calendar/data.json" : "data.json";

  function load() {
    loadingEl.textContent = "Fetching this week's picks\u2026";
    loadingEl.hidden = false;
    errorEl.hidden = true;
    picksList.innerHTML = "";
    renderSkeleton();
    var old = listingsEl.querySelectorAll(".event-card, .empty-state");
    old.forEach(function (n) { n.parentNode.removeChild(n); });

    fetch(DATA_URL)
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (raw) {
        var events = Array.isArray(raw) ? raw : (raw.events || []);
        loadingEl.hidden = true;
        var grouped = groupEvents(events);

        var startIso = todayISO();
        var picksEndIso = isoPlusDays(startIso, picksDays);

        allGrouped = grouped;
        currentStartIso = startIso;
        currentPicksEndIso = picksEndIso;

        renderVenueChips(grouped);
        renderCategoryChips(grouped);

        if (grouped.length === 0) {
          renderEmptyState();
          updateHeadings(startIso, picksEndIso, currentQuery);
          return;
        }

        applyFilterAndRender();
      })
      .catch(function (err) {
        loadingEl.hidden = true;
        renderError(err);
      });
  }

  function renderError(err) {
    errorEl.hidden = false;
    errorEl.innerHTML = "";
    var msg = document.createElement("p");
    msg.className = "error-message";
    msg.textContent = "We couldn't load this week's events. Check your connection and try again.";
    errorEl.appendChild(msg);

    var retry = document.createElement("button");
    retry.className = "error-retry";
    retry.type = "button";
    retry.textContent = "Try again";
    retry.addEventListener("click", load);
    errorEl.appendChild(retry);

    var details = document.createElement("details");
    details.className = "error-details";
    var summary = document.createElement("summary");
    summary.textContent = "Technical details";
    details.appendChild(summary);
    var code = document.createElement("code");
    code.textContent = (err && err.message) ? err.message : String(err);
    details.appendChild(code);
    errorEl.appendChild(details);
  }

  function renderSkeleton() {
    var frag = document.createDocumentFragment();
    for (var i = 0; i < 5; i++) {
      var row = document.createElement("li");
      row.className = "skeleton-pick";
      row.setAttribute("aria-hidden", "true");

      var counter = document.createElement("span");
      counter.className = "skeleton-bar skeleton-bar--counter";
      row.appendChild(counter);

      var badge = document.createElement("span");
      badge.className = "skeleton-bar skeleton-bar--badge";
      row.appendChild(badge);

      var title = document.createElement("span");
      title.className = "skeleton-bar skeleton-bar--title";
      row.appendChild(title);

      frag.appendChild(row);
    }
    picksList.appendChild(frag);
  }

  function renderEmptyState() {
    var empty = document.createElement("div");
    empty.className = "empty-state";
    var text = document.createElement("p");
    text.textContent = "No events in the next " + daysAhead + " days.";
    empty.appendChild(text);
    if (!showAll) {
      var more = document.createElement("p");
      var link = document.createElement("a");
      link.href = "?all=1";
      link.textContent = "Show all events";
      more.appendChild(link);
      more.appendChild(document.createTextNode(" to see everything we've indexed."));
      empty.appendChild(more);
    }
    listingsEl.appendChild(empty);
  }

  load();

  // Normalize recurring event titles so weekly instances merge into one card.
  // e.g. "Book Club - Week 2" and "Book Club - This Week's Story" → "Book Club"
  var RECURRING_STRIP = /\s*[-–—]\s*(?:this\s+week'?s?\s+\w+|week\s+\d+|session\s+\d+|part\s+\d+|meeting\s+\d+|episode\s+\d+)\s*$/i;

  function normalizeTitle(title) {
    if (!title) return "Untitled";
    return title.replace(RECURRING_STRIP, "").trim() || title;
  }

  function groupEvents(events) {
    var byTitle = {};
    var order = [];

    events.forEach(function (ev) {
      var key = normalizeTitle(ev.title || "Untitled");
      if (!byTitle[key]) {
        byTitle[key] = {
          title: key,
          rating: ev.rating || 0,
          type: ev.type || ev.event_category || "other",
          venue: ev.venue || "",
          url: ev.url || "",
          description: ev.description || "",
          one_liner: ev.one_liner_summary || "",
          program: ev.program || "",
          showings: []
        };
        order.push(key);
      }

      var entry = byTitle[key];
      var screenings = ev.screenings || [];
      if (screenings.length > 0) {
        screenings.forEach(function (s) {
          entry.showings.push({
            date: s.date,
            time: s.time || "",
            venue: s.venue || ev.venue || "",
            url: s.url || ev.url || ""
          });
        });
      } else {
        var dates = ev.dates || [];
        var times = ev.times || [];
        dates.forEach(function (d, i) {
          entry.showings.push({
            date: d,
            time: times[i] || "",
            venue: ev.venue || "",
            url: ev.url || ""
          });
        });
      }
    });

    var result = order.map(function (k) { return byTitle[k]; });

    result.forEach(function (ev) {
      ev.showings = dedupeShowings(ev.showings);
    });

    if (!showAll) {
      var startIso = todayISO();
      var endIso = isoPlusDays(startIso, daysAhead);
      result = result
        .map(function (ev) {
          var futureShowings = ev.showings.filter(function (s) {
            return s.date >= startIso && s.date <= endIso;
          });
          return Object.assign({}, ev, { showings: futureShowings });
        })
        .filter(function (ev) { return ev.showings.length > 0; });
    }

    result.sort(function (a, b) {
      return b.rating - a.rating || a.title.localeCompare(b.title);
    });

    return result;
  }

  function updateHeadings(startIso, picksEndIso, query) {
    var picksHeading = document.querySelector(".picks-heading");
    var listingsHeading = document.querySelector(".listings-heading");
    if (query) {
      if (picksHeading) {
        picksHeading.textContent = "Top picks \u00b7 results for \u201c" + query + "\u201d";
      }
      if (listingsHeading) {
        listingsHeading.textContent = "All events \u00b7 results for \u201c" + query + "\u201d";
      }
      return;
    }
    if (picksHeading) {
      picksHeading.textContent = "Top picks · " +
        formatDate(startIso, { noDay: true }) + "–" +
        formatDate(picksEndIso, { noDay: true });
    }
    if (listingsHeading) {
      if (!showAll) {
        var listingsEnd = isoPlusDays(startIso, daysAhead);
        listingsHeading.textContent = "All events \u00b7 " +
          formatDate(startIso, { noDay: true }) + "\u2013" +
          formatDate(listingsEnd, { noDay: true }) +
          " \u00b7 sorted by rating";
      } else {
        listingsHeading.textContent = "All events \u00b7 sorted by rating";
      }
    }
  }

  function matchesQuery(ev, q) {
    if (!q) return true;
    var title = (ev.title || "").toLowerCase();
    return title.indexOf(q) !== -1;
  }

  function matchesVenue(ev, venue) {
    if (!venue) return true;
    return (ev.venue || "") === venue;
  }

  function matchesCategory(ev, category) {
    if (!category) return true;
    return (ev.type || "other") === category;
  }

  function uniqueCategories(grouped) {
    var seen = {};
    var list = [];
    grouped.forEach(function (ev) {
      var c = (ev.type || "other");
      var key = c.toLowerCase();
      if (!seen[key]) {
        seen[key] = true;
        list.push(c);
      }
    });
    list.sort(function (a, b) {
      return formatType(a).localeCompare(formatType(b));
    });
    return list;
  }

  function uniqueVenues(grouped) {
    var seen = {};
    var list = [];
    grouped.forEach(function (ev) {
      var v = (ev.venue || "").trim();
      if (!v) return;
      if (!seen[v]) {
        seen[v] = true;
        list.push(v);
      }
    });
    list.sort(function (a, b) { return a.localeCompare(b); });
    return list;
  }

  function renderVenueChips(grouped) {
    if (!venueFiltersEl) return;
    venueFiltersEl.innerHTML = "";
    var venues = uniqueVenues(grouped);

    var items = [{ label: "All", value: "" }].concat(
      venues.map(function (v) { return { label: v, value: v }; })
    );

    items.forEach(function (item) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "filter-chip";
      if (item.value === currentVenue) chip.classList.add("is-active");
      chip.textContent = item.label;
      chip.setAttribute("aria-pressed", item.value === currentVenue ? "true" : "false");
      chip.addEventListener("click", function () {
        if (currentVenue === item.value) return;
        currentVenue = item.value;
        var chips = venueFiltersEl.querySelectorAll(".filter-chip");
        chips.forEach(function (c) {
          c.classList.remove("is-active");
          c.setAttribute("aria-pressed", "false");
        });
        chip.classList.add("is-active");
        chip.setAttribute("aria-pressed", "true");
        if (allGrouped.length > 0) applyFilterAndRender();
      });
      venueFiltersEl.appendChild(chip);
    });
  }

  function renderCategoryChips(grouped) {
    if (!categoryFiltersEl) return;
    categoryFiltersEl.innerHTML = "";
    var categories = uniqueCategories(grouped);

    var items = [{ label: "All", value: "" }].concat(
      categories.map(function (c) { return { label: formatType(c), value: c }; })
    );

    items.forEach(function (item) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "filter-chip";
      if (item.value === currentCategory) chip.classList.add("is-active");
      chip.textContent = item.label;
      chip.setAttribute("aria-pressed", item.value === currentCategory ? "true" : "false");
      chip.addEventListener("click", function () {
        if (currentCategory === item.value) return;
        currentCategory = item.value;
        var chips = categoryFiltersEl.querySelectorAll(".filter-chip");
        chips.forEach(function (c) {
          c.classList.remove("is-active");
          c.setAttribute("aria-pressed", "false");
        });
        chip.classList.add("is-active");
        chip.setAttribute("aria-pressed", "true");
        if (allGrouped.length > 0) applyFilterAndRender();
      });
      categoryFiltersEl.appendChild(chip);
    });
  }

  function updateFilterStatus(visibleCount) {
    if (!filterCountEl) return;
    var total = allGrouped.length;
    if (total === 0) {
      filterCountEl.textContent = "";
    } else if (hasActiveFilters()) {
      filterCountEl.textContent = "Showing " + visibleCount + " of " + total + " events";
    } else {
      filterCountEl.textContent = "Showing all " + total + " events";
    }
    if (filterClearEl) {
      filterClearEl.hidden = !hasActiveFilters();
    }
  }

  function applyFilterAndRender() {
    picksList.innerHTML = "";
    var oldNodes = listingsEl.querySelectorAll(".event-card, .empty-state");
    oldNodes.forEach(function (n) { n.parentNode.removeChild(n); });

    var q = (currentQuery || "").toLowerCase();
    var venue = currentVenue;
    var category = currentCategory;
    var filtered = allGrouped.filter(function (ev) {
      return matchesQuery(ev, q) &&
        matchesVenue(ev, venue) &&
        matchesCategory(ev, category);
    });

    updateFilterStatus(filtered.length);
    syncURLState();

    if (filtered.length === 0) {
      renderEmptyState();
      updateHeadings(currentStartIso, currentPicksEndIso, currentQuery);
      return;
    }

    var picksPool;
    if (q || showAll) {
      picksPool = filtered;
    } else {
      picksPool = filtered.filter(function (ev) {
        return ev.showings.some(function (s) {
          return s.date >= currentStartIso && s.date <= currentPicksEndIso;
        });
      });
    }
    renderPicks(picksPool.slice(0, 10));
    renderListings(filtered);
    updateHeadings(currentStartIso, currentPicksEndIso, currentQuery);
  }

  function resetFilters() {
    currentQuery = "";
    currentVenue = "";
    currentCategory = "";
    if (searchInput) searchInput.value = "";
    if (venueFiltersEl) {
      var vChips = venueFiltersEl.querySelectorAll(".filter-chip");
      vChips.forEach(function (c, i) {
        c.classList.toggle("is-active", i === 0);
        c.setAttribute("aria-pressed", i === 0 ? "true" : "false");
      });
    }
    if (categoryFiltersEl) {
      var cChips = categoryFiltersEl.querySelectorAll(".filter-chip");
      cChips.forEach(function (c, i) {
        c.classList.toggle("is-active", i === 0);
        c.setAttribute("aria-pressed", i === 0 ? "true" : "false");
      });
    }
    if (allGrouped.length > 0) applyFilterAndRender();
  }

  if (filterClearEl) {
    filterClearEl.addEventListener("click", resetFilters);
  }

  if (searchInput) {
    searchInput.addEventListener("input", function (e) {
      var value = e.target.value || "";
      if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
      searchDebounceTimer = setTimeout(function () {
        currentQuery = value.trim();
        if (allGrouped.length > 0) applyFilterAndRender();
      }, 150);
    });
  }

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
      if (emoji && label && label.indexOf(emoji) === -1) {
        label = label;
      }
      if (label || body) sections.push({ emoji: emoji, label: label, body: body });
    });
    var flat = sections.map(function (s) { return s.body; }).join("\n\n");
    return { rating: rating, sections: sections, flat: flat };
  }

  function ratingClass(r) {
    if (r >= 8) return "high";
    if (r >= 5) return "mid";
    return "low";
  }

  // Web Speech API "Read aloud". Cross-browser: voiceschanged handling,
  // mobile Play/Stop-only (Android Chromium pause() cancels), sentence chunking
  // for long text (Safari cutoff workaround), global single-utterance policy.
  var tts = (function () {
    var supported = typeof window !== "undefined"
      && typeof window.speechSynthesis !== "undefined"
      && typeof window.SpeechSynthesisUtterance !== "undefined";
    var voices = [];
    var isMobile = false;
    try {
      isMobile = !!(window.matchMedia && window.matchMedia("(pointer: coarse)").matches);
    } catch (e) { isMobile = false; }
    var activeController = null;

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
      if (!voices || voices.length === 0) return null;
      for (var i = 0; i < voices.length; i++) {
        var v = voices[i];
        if (v && v.lang && v.lang.toLowerCase().indexOf("en") === 0 && v.localService) {
          return v;
        }
      }
      for (var j = 0; j < voices.length; j++) {
        var w = voices[j];
        if (w && w.lang && w.lang.toLowerCase().indexOf("en") === 0) return w;
      }
      return voices[0] || null;
    }

    function countWords(str) {
      if (!str) return 0;
      var parts = str.trim().split(/\s+/);
      var n = 0;
      for (var i = 0; i < parts.length; i++) if (parts[i]) n++;
      return n;
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

    function makeChunks(text) {
      if (!text) return [];
      if (countWords(text) > 200) return splitSentences(text);
      return [text];
    }

    function stripLeadingEmoji(str) {
      if (!str) return "";
      try {
        return str.replace(/^[\p{Extended_Pictographic}\p{Emoji}\s]+/u, "").trim();
      } catch (e) {
        return str.replace(/^[\s\u2000-\u3300\uD83C-\uDBFF\uDC00-\uDFFF]+/, "").trim();
      }
    }

    function buildText(parsed, oneLiner) {
      var parts = [];
      if (oneLiner) parts.push(String(oneLiner).trim());
      var sections = (parsed && parsed.sections) || [];
      for (var i = 0; i < sections.length; i++) {
        var sec = sections[i];
        var label = stripLeadingEmoji(sec.label || "");
        var body = (sec.body || "").trim();
        if (label && body) parts.push(label + ": " + body);
        else if (body) parts.push(body);
        else if (label) parts.push(label);
      }
      return parts.filter(Boolean).join("\n\n");
    }

    function cancelActive() {
      if (activeController) {
        try { activeController._cancelInternal(); } catch (e) { /* noop */ }
        activeController = null;
      }
      if (supported) {
        try { window.speechSynthesis.cancel(); } catch (e) { /* noop */ }
      }
    }

    function speak(chunks, onState) {
      cancelActive();
      if (!supported || !chunks || chunks.length === 0) {
        onState("error", "Your browser blocked audio — try a different browser or enable TTS in settings.");
        return null;
      }
      var cancelled = false;
      var index = 0;
      var voice = pickVoice();
      var startTimer = null;
      var firstStarted = false;

      function clearStartTimer() {
        if (startTimer) { clearTimeout(startTimer); startTimer = null; }
      }

      function speakNext() {
        if (cancelled) return;
        if (index >= chunks.length) {
          activeController = null;
          onState("ended");
          return;
        }
        var utter = new window.SpeechSynthesisUtterance(chunks[index]);
        utter.rate = 0.95;
        utter.pitch = 1.0;
        utter.volume = 1.0;
        if (voice) {
          utter.voice = voice;
          utter.lang = voice.lang;
        }
        utter.onstart = function () {
          if (index === 0 && !firstStarted) {
            firstStarted = true;
            clearStartTimer();
          }
          if (!cancelled) onState("playing");
        };
        utter.onend = function () {
          if (cancelled) return;
          index++;
          speakNext();
        };
        utter.onerror = function () {
          if (cancelled) return;
          cancelled = true;
          clearStartTimer();
          activeController = null;
          onState("error", "Your browser blocked audio — try a different browser or enable TTS in settings.");
        };
        try {
          window.speechSynthesis.speak(utter);
        } catch (e) {
          cancelled = true;
          clearStartTimer();
          activeController = null;
          onState("error", "Your browser blocked audio — try a different browser or enable TTS in settings.");
          return;
        }
        if (index === 0 && !firstStarted) {
          startTimer = setTimeout(function () {
            if (firstStarted || cancelled) return;
            cancelled = true;
            try { window.speechSynthesis.cancel(); } catch (e) { /* noop */ }
            activeController = null;
            onState("error", "Your browser blocked audio — try a different browser or enable TTS in settings.");
          }, 1500);
        }
      }

      activeController = {
        _cancelInternal: function () {
          cancelled = true;
          clearStartTimer();
          try { window.speechSynthesis.cancel(); } catch (e) { /* noop */ }
          onState("stopped");
        },
        cancel: function () {
          if (activeController === this) activeController = null;
          cancelled = true;
          clearStartTimer();
          try { window.speechSynthesis.cancel(); } catch (e) { /* noop */ }
          onState("stopped");
        },
        pause: function () {
          try { window.speechSynthesis.pause(); } catch (e) { /* noop */ }
          onState("paused");
        },
        resume: function () {
          try { window.speechSynthesis.resume(); } catch (e) { /* noop */ }
          onState("playing");
        }
      };
      speakNext();
      return activeController;
    }

    function createButton(parsed, oneLiner) {
      if (!supported) return null;
      var text = buildText(parsed, oneLiner);
      if (!text) return null;

      var container = document.createElement("div");
      container.className = "event-tts";

      var controls = document.createElement("div");
      controls.className = "event-tts-controls";

      var playBtn = document.createElement("button");
      playBtn.type = "button";
      playBtn.className = "event-tts-btn event-tts-play";
      playBtn.textContent = "\u25B6 Read aloud";
      playBtn.setAttribute("aria-label", "Read aloud");

      var pauseBtn = null, resumeBtn = null;
      if (!isMobile) {
        pauseBtn = document.createElement("button");
        pauseBtn.type = "button";
        pauseBtn.className = "event-tts-btn event-tts-pause";
        pauseBtn.textContent = "\u23F8 Pause";
        pauseBtn.setAttribute("aria-label", "Pause read aloud");
        pauseBtn.hidden = true;

        resumeBtn = document.createElement("button");
        resumeBtn.type = "button";
        resumeBtn.className = "event-tts-btn event-tts-resume";
        resumeBtn.textContent = "\u25B6 Resume";
        resumeBtn.setAttribute("aria-label", "Resume read aloud");
        resumeBtn.hidden = true;
      }

      var stopBtn = document.createElement("button");
      stopBtn.type = "button";
      stopBtn.className = "event-tts-btn event-tts-stop";
      stopBtn.textContent = "\u25A0 Stop";
      stopBtn.setAttribute("aria-label", "Stop read aloud");
      stopBtn.hidden = true;

      var status = document.createElement("span");
      status.className = "event-tts-status";
      status.setAttribute("aria-live", "polite");
      status.setAttribute("role", "status");

      var myController = null;

      function resetControls() {
        container.classList.remove("is-playing", "is-paused", "is-error");
        playBtn.hidden = false;
        stopBtn.hidden = true;
        if (pauseBtn) pauseBtn.hidden = true;
        if (resumeBtn) resumeBtn.hidden = true;
      }

      function setState(state, message) {
        if (state === "playing") {
          container.classList.add("is-playing");
          container.classList.remove("is-paused", "is-error");
          playBtn.hidden = true;
          stopBtn.hidden = false;
          if (pauseBtn) pauseBtn.hidden = false;
          if (resumeBtn) resumeBtn.hidden = true;
          status.textContent = "Playing audio.";
        } else if (state === "paused") {
          container.classList.remove("is-playing", "is-error");
          container.classList.add("is-paused");
          playBtn.hidden = true;
          stopBtn.hidden = false;
          if (pauseBtn) pauseBtn.hidden = true;
          if (resumeBtn) resumeBtn.hidden = false;
          status.textContent = "Paused.";
        } else if (state === "ended") {
          resetControls();
          status.textContent = "Finished.";
          myController = null;
        } else if (state === "stopped") {
          resetControls();
          status.textContent = "Stopped.";
          myController = null;
        } else if (state === "error") {
          resetControls();
          container.classList.add("is-error");
          status.textContent = message || "Audio unavailable.";
          myController = null;
        }
      }

      playBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        myController = speak(makeChunks(text), setState);
      });
      stopBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        if (myController) myController.cancel();
        else setState("stopped");
      });
      if (pauseBtn) {
        pauseBtn.addEventListener("click", function (e) {
          e.stopPropagation();
          if (myController) myController.pause();
        });
      }
      if (resumeBtn) {
        resumeBtn.addEventListener("click", function (e) {
          e.stopPropagation();
          if (myController) myController.resume();
        });
      }

      controls.appendChild(playBtn);
      if (pauseBtn) controls.appendChild(pauseBtn);
      if (resumeBtn) controls.appendChild(resumeBtn);
      controls.appendChild(stopBtn);
      container.appendChild(controls);
      container.appendChild(status);
      return container;
    }

    return {
      supported: supported,
      createButton: createButton
    };
  })();

  function formatDate(str, opts) {
    opts = opts || {};
    var parts = str.split("-");
    var m = parseInt(parts[1], 10) - 1;
    var d = parseInt(parts[2], 10);
    var base = MONTHS_SHORT[m] + " " + d;
    if (opts.noDay) return base;
    return dayOfWeek(str) + " " + base;
  }

  function formatTime(t) {
    if (!t) return "";
    var m = t.match(/^(\d{1,2}):(\d{2})$/);
    if (m) {
      var hh = parseInt(m[1], 10);
      var mm = m[2];
      var ampm = hh >= 12 ? "PM" : "AM";
      var h12 = hh % 12 === 0 ? 12 : hh % 12;
      return h12 + ":" + mm + " " + ampm;
    }
    return t;
  }

  function dedupeShowings(showings) {
    var seen = {};
    var result = [];
    showings.forEach(function (s) {
      var key = s.date + "|" + s.time;
      if (!seen[key]) {
        seen[key] = true;
        result.push(s);
      }
    });
    result.sort(function (a, b) {
      return a.date < b.date ? -1 : a.date > b.date ? 1 :
        (a.time || "").localeCompare(b.time || "");
    });
    return result;
  }

  function renderPicks(picks) {
    var frag = document.createDocumentFragment();

    picks.forEach(function (ev) {
      var li = document.createElement("li");
      li.className = "pick-item";

      var badge = document.createElement("span");
      badge.className = "pick-rating pick-rating--" + ratingClass(ev.rating);
      if (ev.rating > 0) {
        var pickRatingValue = document.createElement("span");
        pickRatingValue.className = "rating-value";
        pickRatingValue.textContent = ev.rating;
        badge.appendChild(pickRatingValue);
        var pickRatingScale = document.createElement("span");
        pickRatingScale.className = "rating-scale";
        pickRatingScale.textContent = " / 10";
        badge.appendChild(pickRatingScale);
        badge.setAttribute("aria-label", "rated " + ev.rating + " out of 10");
      } else {
        badge.textContent = "\u2014";
        badge.setAttribute("aria-label", "not yet rated");
      }
      li.appendChild(badge);

      var titleRow = document.createElement("span");
      titleRow.className = "pick-title";
      titleRow.textContent = ev.title;
      li.appendChild(titleRow);

      var meta = document.createElement("span");
      meta.className = "pick-meta";
      var next = ev.showings[0];
      var pickTypeLabel = formatType(ev.type);
      var pickVenueLower = (ev.venue || "").toLowerCase();
      var parts = [];
      if (pickTypeLabel && pickTypeLabel.toLowerCase() !== pickVenueLower) {
        parts.push(pickTypeLabel);
      }
      if (next) {
        parts.push(formatDate(next.date) +
          (next.time ? " \u00b7 " + formatTime(next.time) : ""));
      }
      if (ev.venue) parts.unshift(ev.venue);
      meta.textContent = parts.join(" \u00b7 ");
      li.appendChild(meta);

      // Expandable review panel inside the pick
      var parsed = parseReview(ev.description);
      var hasContent = ev.one_liner || parsed.sections.length > 0 || (ev.program && ev.program.trim());
      if (hasContent) {
        var pickPanel = document.createElement("div");
        pickPanel.className = "pick-panel";

        var pickPanelInner = document.createElement("div");
        pickPanelInner.className = "pick-panel-inner";

        if (ev.one_liner) {
          var oneLiner = document.createElement("p");
          oneLiner.className = "event-oneliner";
          oneLiner.textContent = ev.one_liner;
          pickPanelInner.appendChild(oneLiner);
        }

        if (parsed.sections.length > 0) {
          parsed.sections.forEach(function (sec, idx) {
            var sectionEl = document.createElement("section");
            sectionEl.className = idx === 0 ? "event-review-section event-review-first" : "event-review-section";
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
            pickPanelInner.appendChild(sectionEl);
          });
        } else if (ev.program) {
          var programP = document.createElement("p");
          programP.className = "event-review-body";
          programP.textContent = ev.program;
          pickPanelInner.appendChild(programP);
        }

        var pickTtsNode = tts.createButton(parsed, ev.one_liner);
        if (pickTtsNode) pickPanelInner.appendChild(pickTtsNode);

        if (ev.url) {
          var external = document.createElement("a");
          external.className = "event-external-link";
          external.href = ev.url;
          external.target = "_blank";
          external.rel = "noopener";
          external.textContent = "View at venue \u2197";
          external.addEventListener("click", function (e) { e.stopPropagation(); });
          pickPanelInner.appendChild(external);
        }

        pickPanel.appendChild(pickPanelInner);
        li.appendChild(pickPanel);

        li.style.cursor = "pointer";
        li.setAttribute("role", "button");
        li.setAttribute("tabindex", "0");
        li.setAttribute("aria-expanded", "false");
        li.addEventListener("click", function () {
          var expanded = li.classList.toggle("is-expanded");
          li.setAttribute("aria-expanded", expanded ? "true" : "false");
        });
        li.addEventListener("keydown", function (e) {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            li.click();
          }
        });
      }

      frag.appendChild(li);
    });

    picksList.appendChild(frag);
  }

  function renderListings(events) {
    var frag = document.createDocumentFragment();

    events.forEach(function (ev) {
      var card = document.createElement("article");
      card.className = "event-card";

      var header = document.createElement("button");
      header.className = "event-header";
      header.type = "button";
      header.setAttribute("aria-expanded", "false");

      var badge = document.createElement("span");
      badge.className = "event-rating-badge rating-" + ratingClass(ev.rating);
      if (ev.rating > 0) {
        var ratingValue = document.createElement("span");
        ratingValue.className = "rating-value";
        ratingValue.textContent = ev.rating;
        badge.appendChild(ratingValue);
        var ratingScale = document.createElement("span");
        ratingScale.className = "rating-scale";
        ratingScale.textContent = " / 10";
        badge.appendChild(ratingScale);
        badge.setAttribute("aria-label", "rated " + ev.rating + " out of 10");
      } else {
        badge.textContent = "\u2014";
        badge.setAttribute("aria-label", "not yet rated");
      }
      header.appendChild(badge);

      var titleCol = document.createElement("span");
      titleCol.className = "event-title-col";

      var titleText = document.createElement("span");
      titleText.className = "event-title-text";
      var titleId = "event-title-" + (++headerIdCounter);
      titleText.id = titleId;
      titleText.textContent = ev.title;
      titleCol.appendChild(titleText);

      var subtitle = document.createElement("span");
      subtitle.className = "event-subtitle";
      subtitle.style.display = "block";
      var subParts = [];
      if (ev.venue) subParts.push(ev.venue);
      var typeLabel = formatType(ev.type);
      var venueLower = (ev.venue || "").toLowerCase();
      if (typeLabel && typeLabel.toLowerCase() !== venueLower) {
        subParts.push(typeLabel);
      }
      subtitle.textContent = subParts.join(" \u00b7 ");
      titleCol.appendChild(subtitle);

      header.appendChild(titleCol);

      var arrow = document.createElement("span");
      arrow.className = "expand-indicator";
      arrow.textContent = "\u25b6";
      arrow.setAttribute("aria-hidden", "true");
      header.appendChild(arrow);

      card.appendChild(header);

      if (ev.showings.length > 0) {
        var showings = document.createElement("ul");
        showings.className = "event-showings-list";
        ev.showings.forEach(function (s) {
          var row = document.createElement("li");
          row.className = "showing-row";

          var dateEl = document.createElement("span");
          dateEl.className = "showing-date";
          dateEl.textContent = formatDate(s.date);
          row.appendChild(dateEl);

          if (s.time) {
            var timeEl = document.createElement("span");
            timeEl.className = "showing-time";
            timeEl.textContent = formatTime(s.time);
            row.appendChild(timeEl);
          }

          showings.appendChild(row);
        });
        card.appendChild(showings);
      }

      var panel = document.createElement("div");
      panel.className = "event-panel";
      panel.setAttribute("aria-labelledby", titleId);

      var panelInner = document.createElement("div");
      panelInner.className = "event-panel-inner";

      if (ev.one_liner) {
        var oneLiner = document.createElement("p");
        oneLiner.className = "event-oneliner";
        oneLiner.textContent = ev.one_liner;
        panelInner.appendChild(oneLiner);
      }

      var parsed = parseReview(ev.description);
      var hasReview = parsed.sections.length > 0 || (ev.program && ev.program.trim());

      if (hasReview) {
        var reviewLabel = document.createElement("div");
        reviewLabel.className = "event-review-label";
        reviewLabel.textContent = "Critic's take";
        panelInner.appendChild(reviewLabel);

        var byline = document.createElement("p");
        byline.className = "event-byline";
        byline.textContent = "By The Austin Culture Oracle";
        panelInner.appendChild(byline);

        if (ev.showings.length > 0) {
          var dateline = document.createElement("time");
          dateline.className = "event-dateline";
          dateline.textContent = formatDate(ev.showings[0].date);
          panelInner.appendChild(dateline);
        }

        if (parsed.sections.length > 0) {
          parsed.sections.forEach(function (sec, idx) {
            var sectionEl = document.createElement("section");
            sectionEl.className = idx === 0 ? "event-review-section event-review-first" : "event-review-section";

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
              var labelNode = document.createTextNode(sec.label);
              h.appendChild(labelNode);
              sectionEl.appendChild(h);
            }

            var bodyP = document.createElement("p");
            bodyP.className = "event-review-body";
            bodyP.textContent = sec.body;
            sectionEl.appendChild(bodyP);

            panelInner.appendChild(sectionEl);
          });
        } else if (ev.program) {
          var programP = document.createElement("p");
          programP.className = "event-review-body";
          programP.textContent = ev.program;
          panelInner.appendChild(programP);
        }
      }

      var listingTtsNode = tts.createButton(parsed, ev.one_liner);
      if (listingTtsNode) panelInner.appendChild(listingTtsNode);

      if (ev.url) {
        var external = document.createElement("a");
        external.className = "event-external-link";
        external.href = ev.url;
        external.target = "_blank";
        external.rel = "noopener";
        external.textContent = "View at venue \u2197";
        panelInner.appendChild(external);
      }

      if (panelInner.childNodes.length > 0) {
        panel.appendChild(panelInner);
        card.appendChild(panel);
      }

      header.addEventListener("click", function () {
        var expanded = card.classList.toggle("is-expanded");
        header.setAttribute("aria-expanded", expanded ? "true" : "false");
      });

      frag.appendChild(card);
    });

    listingsEl.appendChild(frag);
  }
})();
