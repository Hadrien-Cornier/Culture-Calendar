(function () {
  "use strict";

  var DATA_URL = "../../data.json";
  var SYNOPSIS_LIMIT = 120;
  var DAYS_TO_SHOW = 60;

  var gridEl = document.getElementById("heatmap-grid");
  var monthsEl = document.getElementById("heatmap-months");
  var panelEl = document.getElementById("event-panel");
  var loadingEl = document.getElementById("loading");
  var errorEl = document.getElementById("error");
  var countEl = document.getElementById("count");

  var params = new URLSearchParams(window.location.search);
  var debugDate = params.get("debug_date");

  var WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  var tooltip = null;
  var selectedCell = null;

  fetch(DATA_URL)
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (events) {
      loadingEl.hidden = true;
      var items = flattenToRows(events);
      var byDate = indexByDate(items);
      var dayRange = buildDayRange();
      renderHeatmap(dayRange, byDate);
      renderMonthLabels(dayRange);
      countEl.textContent = items.length + " events";
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

  function indexByDate(items) {
    var map = {};
    items.forEach(function (item) {
      if (!map[item.date]) {
        map[item.date] = [];
      }
      map[item.date].push(item);
    });
    return map;
  }

  function buildDayRange() {
    var today = new Date();
    today.setHours(0, 0, 0, 0);
    var days = [];
    for (var i = 0; i < DAYS_TO_SHOW; i++) {
      var d = new Date(today);
      d.setDate(d.getDate() + i);
      days.push(d);
    }
    return days;
  }

  function formatDateKey(d) {
    var y = d.getFullYear();
    var m = String(d.getMonth() + 1).padStart(2, "0");
    var day = String(d.getDate()).padStart(2, "0");
    return y + "-" + m + "-" + day;
  }

  function computeMaxCount(dayRange, byDate) {
    var max = 0;
    dayRange.forEach(function (d) {
      var key = formatDateKey(d);
      var count = byDate[key] ? byDate[key].length : 0;
      if (count > max) max = count;
    });
    return max;
  }

  function getLevel(count, maxCount) {
    if (count === 0) return 0;
    if (maxCount === 0) return 0;
    var ratio = count / maxCount;
    if (ratio <= 0.25) return 1;
    if (ratio <= 0.5) return 2;
    if (ratio <= 0.75) return 3;
    return 4;
  }

  function renderHeatmap(dayRange, byDate) {
    var maxCount = computeMaxCount(dayRange, byDate);
    var frag = document.createDocumentFragment();

    var startDay = dayRange[0].getDay();
    var weekCol = document.createElement("div");
    weekCol.className = "heatmap-week";

    for (var pad = 0; pad < startDay; pad++) {
      var empty = document.createElement("button");
      empty.className = "heatmap-cell empty";
      empty.disabled = true;
      empty.setAttribute("aria-hidden", "true");
      weekCol.appendChild(empty);
    }

    var currentDow = startDay;

    dayRange.forEach(function (d) {
      if (currentDow === 0 && weekCol.children.length > 0) {
        frag.appendChild(weekCol);
        weekCol = document.createElement("div");
        weekCol.className = "heatmap-week";
      }

      var key = formatDateKey(d);
      var events = byDate[key] || [];
      var count = events.length;
      var level = getLevel(count, maxCount);

      var cell = document.createElement("button");
      cell.className = "heatmap-cell";
      cell.setAttribute("data-level", String(level));
      cell.setAttribute("data-date", key);
      cell.setAttribute("aria-label",
        MONTHS[d.getMonth()] + " " + d.getDate() + ": " + count + " event" + (count !== 1 ? "s" : ""));

      cell.addEventListener("click", function () {
        selectDay(key, byDate);
        if (selectedCell) selectedCell.classList.remove("selected");
        cell.classList.add("selected");
        selectedCell = cell;
      });

      cell.addEventListener("mouseenter", function (e) {
        showTooltip(e, MONTHS[d.getMonth()] + " " + d.getDate() + ", " + d.getFullYear() + " — " + count + " event" + (count !== 1 ? "s" : ""));
      });

      cell.addEventListener("mouseleave", hideTooltip);

      weekCol.appendChild(cell);
      currentDow = (currentDow + 1) % 7;
    });

    if (weekCol.children.length > 0) {
      frag.appendChild(weekCol);
    }

    gridEl.appendChild(frag);
  }

  function renderMonthLabels(dayRange) {
    var weeks = gridEl.children;
    if (weeks.length === 0) return;

    var seenMonths = {};
    var labels = [];

    for (var w = 0; w < weeks.length; w++) {
      var cells = weeks[w].querySelectorAll("[data-date]");
      if (cells.length === 0) continue;
      var firstDate = cells[0].getAttribute("data-date");
      var parts = firstDate.split("-");
      var monthKey = parts[0] + "-" + parts[1];
      if (!seenMonths[monthKey]) {
        seenMonths[monthKey] = true;
        var monthIdx = parseInt(parts[1], 10) - 1;
        labels.push({ week: w, label: MONTHS[monthIdx] });
      }
    }

    var cellWidth = 15;
    labels.forEach(function (entry) {
      var span = document.createElement("span");
      span.textContent = entry.label;
      span.style.marginLeft = (entry.week === 0 ? 0 : entry.week * cellWidth) + "px";
      span.style.position = labels.indexOf(entry) === 0 ? "relative" : "absolute";
      if (labels.indexOf(entry) > 0) {
        span.style.left = (entry.week * cellWidth + 32) + "px";
      }
      monthsEl.appendChild(span);
    });

    monthsEl.style.position = "relative";
    monthsEl.style.height = "1.25rem";
  }

  function selectDay(dateKey, byDate) {
    var events = byDate[dateKey] || [];
    var d = parseDate(dateKey);

    panelEl.innerHTML = "";

    var header = document.createElement("div");
    header.className = "panel-header";

    var dateLabel = document.createElement("h2");
    dateLabel.className = "panel-date";
    dateLabel.textContent = WEEKDAYS[d.getDay()] + ", " + MONTHS[d.getMonth()] + " " + d.getDate();
    header.appendChild(dateLabel);

    var countLabel = document.createElement("span");
    countLabel.className = "panel-count";
    countLabel.textContent = events.length + " event" + (events.length !== 1 ? "s" : "");
    header.appendChild(countLabel);

    panelEl.appendChild(header);

    if (events.length === 0) {
      var empty = document.createElement("p");
      empty.className = "panel-prompt";
      empty.textContent = "No events on this day.";
      panelEl.appendChild(empty);
      return;
    }

    var list = document.createElement("ul");
    list.className = "event-list";

    events.forEach(function (item) {
      var li = document.createElement("li");
      li.className = "event-item";

      var timeEl = document.createElement("div");
      timeEl.className = "event-time";
      timeEl.textContent = item.time || "\u00a0";
      li.appendChild(timeEl);

      var body = document.createElement("div");
      body.className = "event-body";

      var title = document.createElement("div");
      title.className = "event-title";
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
      meta.className = "event-meta";

      var dot = document.createElement("span");
      dot.className = "type-dot type-dot--" + item.type;
      dot.setAttribute("aria-label", item.type.replace("_", " "));
      meta.appendChild(dot);

      var venue = document.createElement("span");
      venue.textContent = item.venue;
      meta.appendChild(venue);

      if (item.rating > 0) {
        var rating = document.createElement("span");
        rating.className = "event-rating";
        rating.textContent = item.rating + "/10";
        meta.appendChild(rating);
      }

      body.appendChild(meta);

      if (item.synopsis) {
        var syn = document.createElement("p");
        syn.className = "event-synopsis";
        syn.textContent = item.synopsis;
        body.appendChild(syn);
      }

      li.appendChild(body);
      list.appendChild(li);
    });

    panelEl.appendChild(list);
    panelEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function showTooltip(e, text) {
    hideTooltip();
    tooltip = document.createElement("div");
    tooltip.className = "tooltip";
    tooltip.textContent = text;
    document.body.appendChild(tooltip);
    var x = e.clientX + 10;
    var y = e.clientY - 30;
    if (x + 200 > window.innerWidth) x = e.clientX - 200;
    if (y < 0) y = e.clientY + 20;
    tooltip.style.left = x + "px";
    tooltip.style.top = y + "px";
  }

  function hideTooltip() {
    if (tooltip && tooltip.parentNode) {
      tooltip.parentNode.removeChild(tooltip);
    }
    tooltip = null;
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
