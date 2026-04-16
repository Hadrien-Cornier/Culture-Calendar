(function () {
  "use strict";

  var DATA_URL = "../../data.json";
  var SYNOPSIS_LIMIT = 120;

  var rail = document.getElementById("timeline-rail");
  var track = document.getElementById("timeline-track");
  var eventArea = document.getElementById("event-area");
  var loadingEl = document.getElementById("loading");
  var errorEl = document.getElementById("error");
  var countEl = document.getElementById("count");
  var hintEl = document.getElementById("drag-hint");

  var params = new URLSearchParams(window.location.search);
  var debugDate = params.get("debug_date");

  var WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  fetch(DATA_URL)
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (events) {
      loadingEl.hidden = true;
      var items = flattenToRows(events);
      var grouped = groupByDate(items);
      renderTimeline(grouped);
      renderEvents(grouped);
      countEl.textContent = items.length + " events";
      initDragScroll();
      observeSections(grouped);
    })
    .catch(function (err) {
      loadingEl.hidden = true;
      errorEl.hidden = false;
      errorEl.textContent = "Error: " + err.message;
    });

  function flattenToRows(events) {
    var seen = {};
    var result = [];

    events.forEach(function (ev) {
      var screenings = ev.screenings || [];
      var type = ev.type || ev.event_category || "other";
      var rating = ev.rating || 0;
      var synopsis = extractSynopsis(ev);

      if (screenings.length > 0) {
        screenings.forEach(function (s) {
          var key = ev.title + "|" + s.date + "|" + (s.time || "");
          if (seen[key]) return;
          seen[key] = true;
          result.push({
            title: ev.title,
            date: s.date,
            time: s.time || "",
            venue: s.venue || ev.venue || "",
            url: s.url || ev.url || "",
            type: type,
            rating: rating,
            synopsis: synopsis
          });
        });
      } else {
        var dates = ev.dates || [];
        var times = ev.times || [];
        if (dates.length > 0) {
          dates.forEach(function (d, i) {
            var key = ev.title + "|" + d + "|" + (times[i] || "");
            if (seen[key]) return;
            seen[key] = true;
            result.push({
              title: ev.title,
              date: d,
              time: times[i] || "",
              venue: ev.venue || "",
              url: ev.url || "",
              type: type,
              rating: rating,
              synopsis: synopsis
            });
          });
        }
      }
    });

    result.sort(function (a, b) {
      return a.date < b.date ? -1 : a.date > b.date ? 1 :
        (a.time || "").localeCompare(b.time || "") ||
        a.title.localeCompare(b.title);
    });

    if (debugDate) {
      result = result.filter(function (it) { return it.date === debugDate; });
    }

    return result;
  }

  function groupByDate(items) {
    var groups = [];
    var map = {};

    items.forEach(function (item) {
      if (!map[item.date]) {
        var group = { date: item.date, events: [] };
        map[item.date] = group;
        groups.push(group);
      }
      map[item.date].events.push(item);
    });

    return groups;
  }

  function renderTimeline(groups) {
    var frag = document.createDocumentFragment();

    groups.forEach(function (group) {
      var d = parseDate(group.date);
      var col = document.createElement("div");
      col.className = "day-column";
      col.setAttribute("data-date", group.date);
      col.setAttribute("role", "button");
      col.setAttribute("tabindex", "0");
      col.setAttribute("aria-label", MONTHS[d.getMonth()] + " " + d.getDate() + ", " + group.events.length + " events");

      var weekday = document.createElement("div");
      weekday.className = "day-weekday";
      weekday.textContent = WEEKDAYS[d.getDay()];

      var date = document.createElement("div");
      date.className = "day-date";
      date.textContent = MONTHS[d.getMonth()] + " " + d.getDate();

      var count = document.createElement("div");
      count.className = "day-count";
      count.textContent = group.events.length + " event" + (group.events.length !== 1 ? "s" : "");

      col.appendChild(weekday);
      col.appendChild(date);
      col.appendChild(count);

      col.addEventListener("click", function () {
        var target = document.getElementById("date-" + group.date);
        if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
      });

      col.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          var target = document.getElementById("date-" + group.date);
          if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });

      frag.appendChild(col);
    });

    track.appendChild(frag);
  }

  function renderEvents(groups) {
    var frag = document.createDocumentFragment();

    groups.forEach(function (group) {
      var d = parseDate(group.date);
      var section = document.createElement("section");
      section.className = "date-section";
      section.id = "date-" + group.date;

      var label = document.createElement("div");
      label.className = "date-label";

      var dateText = document.createTextNode(MONTHS[d.getMonth()] + " " + d.getDate());
      label.appendChild(dateText);

      var wkday = document.createElement("span");
      wkday.className = "date-label-weekday";
      wkday.textContent = WEEKDAYS[d.getDay()];
      label.appendChild(wkday);

      section.appendChild(label);

      var cards = document.createElement("div");
      cards.className = "cards";

      group.events.forEach(function (item) {
        cards.appendChild(createCard(item));
      });

      section.appendChild(cards);
      frag.appendChild(section);
    });

    eventArea.appendChild(frag);
  }

  function createCard(item) {
    var card = document.createElement("article");
    card.className = "card";

    var timeEl = document.createElement("div");
    timeEl.className = "card-time";
    timeEl.textContent = item.time || "\u00a0";
    card.appendChild(timeEl);

    var body = document.createElement("div");
    body.className = "card-body";

    var title = document.createElement("div");
    title.className = "card-title";
    if (item.url) {
      var a = document.createElement("a");
      a.href = item.url;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = item.title;
      title.appendChild(a);
    } else {
      title.textContent = item.title;
    }
    body.appendChild(title);

    var meta = document.createElement("div");
    meta.className = "card-meta";

    var dot = document.createElement("span");
    dot.className = "type-dot type-dot--" + item.type;
    dot.setAttribute("aria-label", item.type.replace("_", " "));
    meta.appendChild(dot);

    var venue = document.createElement("span");
    venue.className = "card-venue";
    venue.textContent = item.venue;
    meta.appendChild(venue);

    if (item.rating > 0) {
      var rating = document.createElement("span");
      rating.className = "card-rating";
      rating.textContent = item.rating + "/10";
      meta.appendChild(rating);
    }

    body.appendChild(meta);

    if (item.synopsis) {
      var syn = document.createElement("p");
      syn.className = "card-synopsis";
      syn.textContent = item.synopsis;
      body.appendChild(syn);
    }

    card.appendChild(body);
    return card;
  }

  function initDragScroll() {
    var isDragging = false;
    var startX = 0;
    var scrollLeft = 0;
    var hasDragged = false;

    rail.addEventListener("mousedown", function (e) {
      isDragging = true;
      hasDragged = false;
      startX = e.pageX;
      scrollLeft = rail.scrollLeft;
      rail.classList.add("grabbing");
      e.preventDefault();
    });

    document.addEventListener("mousemove", function (e) {
      if (!isDragging) return;
      var dx = e.pageX - startX;
      if (Math.abs(dx) > 3) hasDragged = true;
      rail.scrollLeft = scrollLeft - dx;
    });

    document.addEventListener("mouseup", function () {
      if (isDragging) {
        isDragging = false;
        rail.classList.remove("grabbing");
        if (hasDragged && hintEl) {
          hintEl.classList.add("hidden");
        }
      }
    });

    var touchStartX = 0;
    var touchScrollLeft = 0;

    rail.addEventListener("touchstart", function (e) {
      touchStartX = e.touches[0].pageX;
      touchScrollLeft = rail.scrollLeft;
    }, { passive: true });

    rail.addEventListener("touchmove", function (e) {
      var dx = e.touches[0].pageX - touchStartX;
      rail.scrollLeft = touchScrollLeft - dx;
      if (Math.abs(dx) > 3 && hintEl) {
        hintEl.classList.add("hidden");
      }
    }, { passive: true });

    rail.style.overflowX = "auto";
    rail.style.overflowY = "hidden";
    rail.style.webkitOverflowScrolling = "touch";
    rail.style.scrollbarWidth = "none";
  }

  function observeSections(groups) {
    if (!window.IntersectionObserver) return;

    var sections = document.querySelectorAll(".date-section");
    var columns = track.querySelectorAll(".day-column");
    var colMap = {};
    columns.forEach(function (c) {
      colMap[c.getAttribute("data-date")] = c;
    });

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var dateId = entry.target.id.replace("date-", "");
        columns.forEach(function (c) { c.classList.remove("active"); });
        var activeCol = colMap[dateId];
        if (activeCol) {
          activeCol.classList.add("active");
          var colLeft = activeCol.offsetLeft;
          var railWidth = rail.offsetWidth;
          var target = colLeft - railWidth / 2 + activeCol.offsetWidth / 2;
          rail.scrollTo({ left: target, behavior: "smooth" });
        }
      });
    }, { rootMargin: "-10% 0px -80% 0px" });

    sections.forEach(function (s) { observer.observe(s); });
  }

  function parseDate(str) {
    var parts = str.split("-");
    return new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
  }

  function extractSynopsis(ev) {
    if (ev.one_liner_summary) return ev.one_liner_summary;
    if (ev.description) {
      var text = ev.description.replace(/<[^>]*>/g, "");
      if (text.length > SYNOPSIS_LIMIT) {
        return text.substring(0, SYNOPSIS_LIMIT) + "\u2026";
      }
      return text;
    }
    if (ev.program) {
      if (ev.program.length > SYNOPSIS_LIMIT) {
        return ev.program.substring(0, SYNOPSIS_LIMIT) + "\u2026";
      }
      return ev.program;
    }
    return "";
  }
})();
