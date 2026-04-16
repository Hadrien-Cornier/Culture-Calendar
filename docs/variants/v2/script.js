(function () {
  "use strict";

  var DATA_URL = "../../data.json";

  var params = new URLSearchParams(window.location.search);
  var debugDate = params.get("debug_date");

  var loadingEl = document.getElementById("loading");
  var errorEl = document.getElementById("error");
  var listEl = document.getElementById("event-list");

  fetch(DATA_URL)
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(render)
    .catch(function (err) {
      loadingEl.hidden = true;
      errorEl.hidden = false;
      errorEl.textContent = "Failed to load events: " + err.message;
    });

  function render(events) {
    loadingEl.hidden = true;

    var flat = flattenScreenings(events);

    if (debugDate) {
      flat = flat.filter(function (s) {
        return s.date === debugDate;
      });
    }

    flat.sort(function (a, b) {
      return a.date < b.date ? -1 : a.date > b.date ? 1 :
        a.time < b.time ? -1 : a.time > b.time ? 1 : 0;
    });

    var grouped = groupByDate(flat);
    var dateKeys = Object.keys(grouped).sort();

    if (dateKeys.length === 0) {
      listEl.innerHTML = '<p class="loading">No events found.</p>';
      return;
    }

    var frag = document.createDocumentFragment();

    dateKeys.forEach(function (dateStr) {
      var id = "d-" + dateStr;
      var label = formatDateLabel(dateStr);

      var header = document.createElement("h2");
      header.className = "date-header";
      header.id = id;
      header.textContent = label;
      frag.appendChild(header);

      grouped[dateStr].forEach(function (s) {
        var row = document.createElement("div");
        row.className = "event-row";

        var meta = document.createElement("div");
        meta.className = "event-meta";

        var timeSpan = document.createElement("span");
        timeSpan.className = "event-time";
        timeSpan.textContent = formatTime(s.time);

        var dot = document.createElement("span");
        dot.className = "event-dot";
        dot.textContent = "·";
        dot.setAttribute("aria-hidden", "true");

        var venueSpan = document.createElement("span");
        venueSpan.className = "event-venue";
        venueSpan.textContent = s.venue;

        meta.appendChild(timeSpan);
        meta.appendChild(dot);
        meta.appendChild(venueSpan);

        var titleDiv = document.createElement("div");
        titleDiv.className = "event-title";
        if (s.url) {
          var a = document.createElement("a");
          a.href = s.url;
          a.textContent = s.title;
          a.target = "_blank";
          a.rel = "noopener";
          titleDiv.appendChild(a);
        } else {
          titleDiv.textContent = s.title;
        }

        row.appendChild(meta);
        row.appendChild(titleDiv);
        frag.appendChild(row);
      });
    });

    listEl.appendChild(frag);
  }

  function flattenScreenings(events) {
    var result = [];
    events.forEach(function (ev) {
      var screenings = ev.screenings || [];
      if (screenings.length > 0) {
        screenings.forEach(function (s) {
          result.push({
            title: ev.title,
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
          result.push({
            title: ev.title,
            date: d,
            time: times[i] || times[0] || "",
            venue: ev.venue || "",
            url: ev.url || ""
          });
        });
      }
    });
    return result;
  }

  function groupByDate(flat) {
    var groups = {};
    flat.forEach(function (item) {
      if (!groups[item.date]) groups[item.date] = [];
      groups[item.date].push(item);
    });
    return groups;
  }

  function formatDateLabel(dateStr) {
    var parts = dateStr.split("-");
    var d = new Date(
      parseInt(parts[0], 10),
      parseInt(parts[1], 10) - 1,
      parseInt(parts[2], 10)
    );
    var days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
    var months = ["January", "February", "March", "April", "May", "June",
      "July", "August", "September", "October", "November", "December"];
    return days[d.getDay()] + ", " + months[d.getMonth()] + " " + d.getDate() + ", " + d.getFullYear();
  }

  function formatTime(t) {
    if (!t) return "";
    var parts = t.split(":");
    var h = parseInt(parts[0], 10);
    var m = parts[1] || "00";
    var ampm = h >= 12 ? "PM" : "AM";
    if (h === 0) h = 12;
    else if (h > 12) h -= 12;
    return h + ":" + m + " " + ampm;
  }
})();
