(function () {
  "use strict";

  var DATA_URL = "../../data.json";
  var SYNOPSIS_LIMIT = 140;

  var gridEl = document.getElementById("grid");
  var loadingEl = document.getElementById("loading");
  var errorEl = document.getElementById("error");

  var params = new URLSearchParams(window.location.search);
  var debugDate = params.get("debug_date");

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

    var items = flattenToCards(events);

    if (debugDate) {
      items = items.filter(function (it) { return it.date === debugDate; });
    }

    items.sort(function (a, b) {
      return a.date < b.date ? -1 : a.date > b.date ? 1 :
        a.title < b.title ? -1 : a.title > b.title ? 1 : 0;
    });

    if (items.length === 0) {
      gridEl.innerHTML = '<p class="loading">No events found.</p>';
      return;
    }

    var frag = document.createDocumentFragment();

    items.forEach(function (item) {
      var container = document.createElement("div");
      container.className = "card-container";
      container.tabIndex = 0;
      container.setAttribute("role", "group");
      container.setAttribute("aria-label", item.title + " — hover or focus to see synopsis");

      var card = document.createElement("div");
      card.className = "card";

      card.appendChild(buildFront(item));
      card.appendChild(buildBack(item));

      container.appendChild(card);
      frag.appendChild(container);
    });

    gridEl.appendChild(frag);
  }

  function buildFront(item) {
    var front = document.createElement("div");
    front.className = "card-front";

    var poster = document.createElement("div");
    poster.className = "card-poster poster-" + item.type;
    var posterText = document.createElement("span");
    posterText.className = "card-poster-text";
    posterText.textContent = item.title.substring(0, 20);
    posterText.setAttribute("aria-hidden", "true");
    poster.appendChild(posterText);
    front.appendChild(poster);

    var body = document.createElement("div");
    body.className = "card-body";

    var topRow = document.createElement("div");
    topRow.className = "card-top-row";

    var chip = document.createElement("span");
    chip.className = "venue-chip chip-" + item.type;
    chip.textContent = item.venue;
    topRow.appendChild(chip);

    var dateSpan = document.createElement("span");
    dateSpan.className = "card-date";
    dateSpan.textContent = formatDate(item.date);
    topRow.appendChild(dateSpan);

    body.appendChild(topRow);

    var titleEl = document.createElement("h2");
    titleEl.className = "card-title";
    if (item.url) {
      var a = document.createElement("a");
      a.href = item.url;
      a.textContent = item.title;
      a.target = "_blank";
      a.rel = "noopener";
      titleEl.appendChild(a);
    } else {
      titleEl.textContent = item.title;
    }
    body.appendChild(titleEl);

    if (item.rating > 0) {
      var ratingEl = document.createElement("div");
      ratingEl.className = "card-rating";
      ratingEl.innerHTML = '<span class="star" aria-hidden="true">&#9733;</span> ' + item.rating + '/10';
      body.appendChild(ratingEl);
    }

    front.appendChild(body);
    return front;
  }

  function buildBack(item) {
    var back = document.createElement("div");
    back.className = "card-back";

    var title = document.createElement("div");
    title.className = "card-back-title";
    title.textContent = item.title;
    back.appendChild(title);

    var synopsis = document.createElement("p");
    synopsis.className = "card-back-synopsis";
    synopsis.textContent = item.synopsis;
    back.appendChild(synopsis);

    var venue = document.createElement("div");
    venue.className = "card-back-venue";
    venue.textContent = item.venue + (item.time ? " — " + formatTime(item.time) : "");
    back.appendChild(venue);

    return back;
  }

  function flattenToCards(events) {
    var seen = {};
    var result = [];

    events.forEach(function (ev) {
      var screenings = ev.screenings || [];
      var type = ev.type || ev.event_category || "other";
      var rating = ev.rating || 0;
      var synopsis = extractSynopsis(ev);

      if (screenings.length > 0) {
        var key = ev.title + "|" + type;
        if (seen[key]) return;
        seen[key] = true;
        result.push({
          title: ev.title,
          date: screenings[0].date,
          time: screenings[0].time || "",
          venue: screenings[0].venue || ev.venue || "",
          url: screenings[0].url || ev.url || "",
          type: type,
          rating: rating,
          synopsis: synopsis
        });
      } else {
        var dates = ev.dates || [];
        var times = ev.times || [];
        if (dates.length > 0) {
          var dedup = ev.title + "|" + type;
          if (seen[dedup]) return;
          seen[dedup] = true;
          result.push({
            title: ev.title,
            date: dates[0],
            time: times[0] || "",
            venue: ev.venue || "",
            url: ev.url || "",
            type: type,
            rating: rating,
            synopsis: synopsis
          });
        }
      }
    });

    return result;
  }

  function extractSynopsis(ev) {
    if (ev.one_liner_summary) return ev.one_liner_summary;
    if (ev.description) {
      var text = ev.description.replace(/<[^>]*>/g, "");
      if (text.length > SYNOPSIS_LIMIT) {
        return text.substring(0, SYNOPSIS_LIMIT) + "…";
      }
      return text;
    }
    if (ev.program) {
      if (ev.program.length > SYNOPSIS_LIMIT) {
        return ev.program.substring(0, SYNOPSIS_LIMIT) + "…";
      }
      return ev.program;
    }
    return "No description available.";
  }

  function formatDate(dateStr) {
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
})();
