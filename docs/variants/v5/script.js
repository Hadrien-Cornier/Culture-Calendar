(function () {
  "use strict";

  var DATA_URL = "../../data.json";
  var SYNOPSIS_LIMIT = 140;

  var dateRail = document.getElementById("date-rail");
  var eventBody = document.getElementById("event-body");
  var loadingEl = document.getElementById("loading");
  var errorEl = document.getElementById("error");
  var countEl = document.getElementById("count");

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
      render(grouped);
      countEl.textContent = items.length + " events";
      observeDates();
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

  function render(groups) {
    var railFrag = document.createDocumentFragment();
    var bodyFrag = document.createDocumentFragment();

    groups.forEach(function (group) {
      var d = parseDate(group.date);
      var label = MONTHS[d.getMonth()] + " " + d.getDate();
      var weekday = WEEKDAYS[d.getDay()];

      var link = document.createElement("a");
      link.className = "rail-link";
      link.href = "#date-" + group.date;
      link.setAttribute("data-date", group.date);

      var daySpan = document.createElement("span");
      daySpan.className = "rail-day";
      daySpan.textContent = weekday;
      link.appendChild(daySpan);
      link.appendChild(document.createTextNode(label));

      link.addEventListener("click", function (e) {
        e.preventDefault();
        var target = document.getElementById("date-" + group.date);
        if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
      });

      railFrag.appendChild(link);

      var section = document.createElement("section");
      section.className = "date-section";
      section.id = "date-" + group.date;

      var heading = document.createElement("div");
      heading.className = "date-heading";

      var headingDay = document.createElement("span");
      headingDay.className = "date-heading-day";
      headingDay.textContent = label;

      var headingWeekday = document.createElement("span");
      headingWeekday.className = "date-heading-weekday";
      headingWeekday.textContent = weekday;

      var headingCount = document.createElement("span");
      headingCount.className = "date-heading-count";
      headingCount.textContent = group.events.length + " event" + (group.events.length !== 1 ? "s" : "");

      heading.appendChild(headingDay);
      heading.appendChild(headingWeekday);
      heading.appendChild(headingCount);
      section.appendChild(heading);

      var grid = document.createElement("div");
      grid.className = "event-grid";

      group.events.forEach(function (item) {
        grid.appendChild(createCard(item));
      });

      section.appendChild(grid);
      bodyFrag.appendChild(section);
    });

    dateRail.appendChild(railFrag);
    eventBody.appendChild(bodyFrag);
  }

  function createCard(item) {
    var card = document.createElement("article");
    card.className = "event-card";

    var header = document.createElement("div");
    header.className = "event-card-header";

    var chip = document.createElement("span");
    chip.className = "genre-chip genre-chip--" + item.type;
    chip.textContent = item.type.replace("_", " ");
    header.appendChild(chip);

    if (item.time) {
      var time = document.createElement("span");
      time.className = "event-time";
      time.textContent = item.time;
      header.appendChild(time);
    }

    if (item.rating > 0) {
      var rating = document.createElement("span");
      rating.className = "event-rating";
      rating.textContent = item.rating + "/10";
      header.appendChild(rating);
    }

    card.appendChild(header);

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
    card.appendChild(title);

    var venue = document.createElement("div");
    venue.className = "event-venue";
    venue.textContent = item.venue;
    card.appendChild(venue);

    if (item.synopsis) {
      var syn = document.createElement("p");
      syn.className = "event-synopsis";
      syn.textContent = item.synopsis;
      card.appendChild(syn);
    }

    return card;
  }

  function observeDates() {
    if (!window.IntersectionObserver) return;

    var sections = document.querySelectorAll(".date-section");
    var links = dateRail.querySelectorAll(".rail-link");
    var linkMap = {};
    links.forEach(function (l) {
      linkMap[l.getAttribute("data-date")] = l;
    });

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        var id = entry.target.id.replace("date-", "");
        var link = linkMap[id];
        if (!link) return;
        if (entry.isIntersecting) {
          links.forEach(function (l) { l.classList.remove("active"); });
          link.classList.add("active");
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
