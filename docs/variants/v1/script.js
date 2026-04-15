(function () {
  "use strict";

  var DATA_URL = "../../data.json";

  var params = new URLSearchParams(window.location.search);
  var debugDate = params.get("debug_date");

  var loadingEl = document.getElementById("loading");
  var errorEl = document.getElementById("error");
  var railEl = document.getElementById("date-rail");
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

    var railFrag = document.createDocumentFragment();
    var listFrag = document.createDocumentFragment();

    dateKeys.forEach(function (dateStr) {
      var id = "d-" + dateStr;
      var label = formatDateLabel(dateStr);
      var shortLabel = formatDateShort(dateStr);

      var railLink = document.createElement("a");
      railLink.href = "#" + id;
      railLink.textContent = shortLabel;
      railLink.dataset.date = dateStr;
      railFrag.appendChild(railLink);

      var header = document.createElement("h2");
      header.className = "date-header";
      header.id = id;
      header.textContent = label;
      listFrag.appendChild(header);

      grouped[dateStr].forEach(function (s) {
        var row = document.createElement("div");
        row.className = "event-row";

        var timeSpan = document.createElement("span");
        timeSpan.className = "event-time";
        timeSpan.textContent = formatTime(s.time);

        var dot1 = document.createElement("span");
        dot1.className = "event-dot";
        dot1.textContent = "·";
        dot1.setAttribute("aria-hidden", "true");

        var titleSpan = document.createElement("span");
        titleSpan.className = "event-title";
        if (s.url) {
          var a = document.createElement("a");
          a.href = s.url;
          a.textContent = s.title;
          a.target = "_blank";
          a.rel = "noopener";
          titleSpan.appendChild(a);
        } else {
          titleSpan.textContent = s.title;
        }

        var dot2 = document.createElement("span");
        dot2.className = "event-dot";
        dot2.textContent = "·";
        dot2.setAttribute("aria-hidden", "true");

        var venueSpan = document.createElement("span");
        venueSpan.className = "event-venue";
        venueSpan.textContent = s.venue;

        row.appendChild(timeSpan);
        row.appendChild(dot1);
        row.appendChild(titleSpan);
        row.appendChild(dot2);
        row.appendChild(venueSpan);
        listFrag.appendChild(row);
      });
    });

    railEl.appendChild(railFrag);
    listEl.appendChild(listFrag);

    setupScrollSpy(dateKeys);
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

  function formatDateShort(dateStr) {
    var parts = dateStr.split("-");
    var d = new Date(
      parseInt(parts[0], 10),
      parseInt(parts[1], 10) - 1,
      parseInt(parts[2], 10)
    );
    var months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return months[d.getMonth()] + " " + d.getDate();
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

  function setupScrollSpy(dateKeys) {
    var headers = dateKeys.map(function (dk) {
      return document.getElementById("d-" + dk);
    }).filter(Boolean);

    if (headers.length === 0) return;

    var railLinks = railEl.querySelectorAll("a");
    var linkMap = {};
    railLinks.forEach(function (link) {
      linkMap[link.dataset.date] = link;
    });

    var ticking = false;

    function onScroll() {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () {
        ticking = false;
        var scrollY = window.scrollY || window.pageYOffset;
        var current = null;
        for (var i = 0; i < headers.length; i++) {
          if (headers[i].offsetTop <= scrollY + 60) {
            current = dateKeys[i];
          } else {
            break;
          }
        }
        railLinks.forEach(function (l) { l.classList.remove("active"); });
        if (current && linkMap[current]) {
          linkMap[current].classList.add("active");
          linkMap[current].scrollIntoView({ block: "nearest" });
        }
      });
    }

    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }
})();
