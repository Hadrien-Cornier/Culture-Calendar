(function () {
  "use strict";

  var DATA_URL = "../../data.json";
  var SYNOPSIS_LIMIT = 140;

  var feedEl = document.getElementById("feed");
  var loadingEl = document.getElementById("loading");
  var errorEl = document.getElementById("error");
  var countEl = document.getElementById("count");

  var params = new URLSearchParams(window.location.search);
  var debugDate = params.get("debug_date");

  var WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  var MONTHS = ["January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"];

  fetch(DATA_URL)
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (events) {
      loadingEl.hidden = true;
      var items = flattenToRows(events);
      countEl.textContent = items.length + " events";
      renderFeed(items);
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

  function renderFeed(items) {
    var byDate = {};
    var dateOrder = [];

    items.forEach(function (item) {
      if (!byDate[item.date]) {
        byDate[item.date] = [];
        dateOrder.push(item.date);
      }
      byDate[item.date].push(item);
    });

    var frag = document.createDocumentFragment();

    dateOrder.forEach(function (dateKey) {
      var events = byDate[dateKey];
      var d = parseDate(dateKey);

      var block = document.createElement("div");
      block.className = "date-block";

      var header = document.createElement("div");
      header.className = "date-header";
      header.id = "d-" + dateKey;

      var dayNum = document.createElement("span");
      dayNum.className = "date-day";
      dayNum.textContent = d.getDate();
      header.appendChild(dayNum);

      var weekday = document.createElement("span");
      weekday.className = "date-weekday";
      weekday.textContent = WEEKDAYS[d.getDay()];
      header.appendChild(weekday);

      var full = document.createElement("span");
      full.className = "date-full";
      full.textContent = MONTHS[d.getMonth()] + " " + d.getDate() + ", " + d.getFullYear();
      header.appendChild(full);

      block.appendChild(header);

      events.forEach(function (item) {
        var row = document.createElement("div");
        row.className = "event-row";

        var timeEl = document.createElement("span");
        timeEl.className = "event-time";
        timeEl.textContent = item.time || "\u00a0";
        row.appendChild(timeEl);

        var titleCol = document.createElement("div");
        titleCol.className = "event-title-col";

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
        titleCol.appendChild(title);
        row.appendChild(titleCol);

        var metaCol = document.createElement("div");
        metaCol.className = "event-meta-col";

        var tag = document.createElement("span");
        var typeClass = "cat-tag";
        var normalType = item.type.replace(" ", "_");
        if (["movie", "concert", "book_club", "opera", "dance"].indexOf(normalType) !== -1) {
          typeClass += " cat-tag--" + normalType;
        }
        tag.className = typeClass;
        tag.textContent = item.type.replace("_", " ");
        metaCol.appendChild(tag);

        if (item.venue) {
          var venue = document.createElement("span");
          venue.className = "event-venue";
          venue.textContent = item.venue;
          metaCol.appendChild(venue);
        }

        row.appendChild(metaCol);

        var ratingCol = document.createElement("div");
        ratingCol.className = "event-rating-col";

        if (item.rating > 0) {
          var ratingNum = document.createElement("span");
          ratingNum.className = "event-rating";
          ratingNum.textContent = item.rating;
          ratingCol.appendChild(ratingNum);

          var ratingLabel = document.createElement("span");
          ratingLabel.className = "event-rating-label";
          ratingLabel.textContent = "/10";
          ratingCol.appendChild(ratingLabel);
        }

        row.appendChild(ratingCol);

        if (item.synopsis) {
          var syn = document.createElement("p");
          syn.className = "event-synopsis";
          syn.textContent = item.synopsis;
          row.appendChild(syn);
        }

        block.appendChild(row);
      });

      frag.appendChild(block);
    });

    feedEl.appendChild(frag);
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
