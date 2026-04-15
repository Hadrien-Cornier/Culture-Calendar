(function () {
  "use strict";

  var DATA_URL = "../../data.json";

  var picksList = document.getElementById("picks-list");
  var listingsEl = document.getElementById("listings");
  var loadingEl = document.getElementById("loading");
  var errorEl = document.getElementById("error");

  var params = new URLSearchParams(window.location.search);
  var debugDate = params.get("debug_date");

  var MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  fetch(DATA_URL)
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (events) {
      loadingEl.hidden = true;
      var grouped = groupEvents(events);
      renderPicks(grouped.slice(0, 10));
      renderListings(grouped);
    })
    .catch(function (err) {
      loadingEl.hidden = true;
      errorEl.hidden = false;
      errorEl.textContent = "Error: " + err.message;
    });

  function groupEvents(events) {
    var byTitle = {};
    var order = [];

    events.forEach(function (ev) {
      var key = ev.title || "Untitled";
      if (!byTitle[key]) {
        byTitle[key] = {
          title: ev.title,
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

    if (debugDate) {
      result = result.filter(function (ev) {
        return ev.showings.some(function (s) { return s.date === debugDate; });
      });
    }

    result.sort(function (a, b) {
      return b.rating - a.rating || a.title.localeCompare(b.title);
    });

    return result;
  }

  function ratingClass(r) {
    if (r >= 8) return "high";
    if (r >= 5) return "mid";
    return "low";
  }

  function formatDate(str) {
    var parts = str.split("-");
    var m = parseInt(parts[1], 10) - 1;
    var d = parseInt(parts[2], 10);
    return MONTHS_SHORT[m] + " " + d;
  }

  function getReviewText(ev) {
    if (ev.description) return ev.description.replace(/<[^>]*>/g, "");
    if (ev.program) return ev.program;
    if (ev.one_liner) return ev.one_liner;
    return "";
  }

  function renderPicks(picks) {
    var frag = document.createDocumentFragment();

    picks.forEach(function (ev) {
      var li = document.createElement("li");
      li.className = "pick-item";

      var badge = document.createElement("span");
      badge.className = "pick-rating pick-rating--" + ratingClass(ev.rating);
      badge.textContent = ev.rating > 0 ? ev.rating : "\u2014";
      li.appendChild(badge);

      var title = document.createElement("span");
      title.className = "pick-title";
      if (ev.url) {
        var a = document.createElement("a");
        a.href = ev.url;
        a.target = "_blank";
        a.rel = "noopener";
        a.textContent = ev.title;
        title.appendChild(a);
      } else {
        title.textContent = ev.title;
      }
      li.appendChild(title);

      var meta = document.createElement("span");
      meta.className = "pick-meta";
      meta.textContent = ev.type.replace("_", " ");
      li.appendChild(meta);

      frag.appendChild(li);
    });

    picksList.appendChild(frag);
  }

  function renderListings(events) {
    var frag = document.createDocumentFragment();

    events.forEach(function (ev) {
      var card = document.createElement("div");
      card.className = "event-card";

      var header = document.createElement("div");
      header.className = "event-header";

      var badge = document.createElement("span");
      badge.className = "event-rating-badge rating-" + ratingClass(ev.rating);
      badge.textContent = ev.rating > 0 ? ev.rating : "\u2014";
      header.appendChild(badge);

      var titleCol = document.createElement("div");
      titleCol.className = "event-title-col";

      var titleText = document.createElement("div");
      titleText.className = "event-title-text";
      if (ev.url) {
        var a = document.createElement("a");
        a.href = ev.url;
        a.target = "_blank";
        a.rel = "noopener";
        a.className = "event-title-link";
        a.textContent = ev.title;
        titleText.appendChild(a);
        a.addEventListener("click", function (e) { e.stopPropagation(); });
      } else {
        titleText.textContent = ev.title;
      }
      titleCol.appendChild(titleText);

      var subtitle = document.createElement("div");
      subtitle.className = "event-subtitle";
      var subtitleParts = [];
      if (ev.venue) subtitleParts.push(ev.venue);
      if (ev.showings.length > 0) {
        subtitleParts.push(ev.showings.length + " showing" + (ev.showings.length > 1 ? "s" : ""));
      }
      subtitle.textContent = subtitleParts.join(" \u00b7 ");
      titleCol.appendChild(subtitle);

      header.appendChild(titleCol);

      var tag = document.createElement("span");
      tag.className = "event-category-tag";
      tag.textContent = ev.type.replace("_", " ");
      header.appendChild(tag);

      var arrow = document.createElement("span");
      arrow.className = "expand-indicator";
      arrow.textContent = "\u25b6";
      arrow.setAttribute("aria-hidden", "true");
      header.appendChild(arrow);

      card.appendChild(header);

      var review = getReviewText(ev);
      if (review) {
        var reviewDiv = document.createElement("div");
        reviewDiv.className = "event-review";

        var label = document.createElement("div");
        label.className = "event-review-label";
        label.textContent = "Review";
        reviewDiv.appendChild(label);

        var text = document.createElement("p");
        text.textContent = review;
        reviewDiv.appendChild(text);

        card.appendChild(reviewDiv);
      }

      if (ev.showings.length > 0) {
        var showingsDiv = document.createElement("div");
        showingsDiv.className = "event-showings";

        var dedupedShowings = dedupeShowings(ev.showings);
        dedupedShowings.forEach(function (s) {
          var chip = document.createElement("span");
          chip.className = "showing-chip";
          chip.textContent = formatDate(s.date) + (s.time ? " " + s.time : "");
          showingsDiv.appendChild(chip);
        });

        card.appendChild(showingsDiv);
      }

      header.addEventListener("click", function () {
        card.classList.toggle("is-expanded");
      });

      header.setAttribute("role", "button");
      header.setAttribute("tabindex", "0");
      header.setAttribute("aria-expanded", "false");
      header.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          card.classList.toggle("is-expanded");
          header.setAttribute("aria-expanded",
            card.classList.contains("is-expanded") ? "true" : "false");
        }
      });
      header.addEventListener("click", function () {
        header.setAttribute("aria-expanded",
          card.classList.contains("is-expanded") ? "true" : "false");
      });

      frag.appendChild(card);
    });

    listingsEl.appendChild(frag);
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
})();
