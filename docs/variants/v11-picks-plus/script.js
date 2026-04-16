(function () {
  "use strict";

  var DATA_URL = "../../data.json";

  var picksList = document.getElementById("picks-list");
  var listingsEl = document.getElementById("listings");
  var loadingEl = document.getElementById("loading");
  var errorEl = document.getElementById("error");

  var params = new URLSearchParams(window.location.search);
  var debugDate = params.get("debug_date");
  var daysAhead = parseInt(params.get("days") || "14", 10);
  var picksDays = parseInt(params.get("picks_days") || "7", 10);
  var showAll = params.get("all") === "1";

  var MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var DAYS_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

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

  fetch(DATA_URL)
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (raw) {
      var events = Array.isArray(raw) ? raw : (raw.events || []);
      loadingEl.hidden = true;
      var grouped = groupEvents(events);

      // Picks are the top-rated events whose FIRST upcoming showing falls
      // within picks_days (default 7), i.e. "this week". Listings use the
      // broader window (default 14 days).
      var startIso = todayISO();
      var picksEndIso = isoPlusDays(startIso, picksDays);
      var picksPool = showAll ? grouped : grouped.filter(function (ev) {
        return ev.showings.some(function (s) {
          return s.date >= startIso && s.date <= picksEndIso;
        });
      });
      renderPicks(picksPool.slice(0, 10));
      renderListings(grouped);
      updateHeadings(startIso, picksEndIso);
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

  function updateHeadings(startIso, picksEndIso) {
    var picksHeading = document.querySelector(".picks-heading");
    if (picksHeading) {
      picksHeading.textContent = "Top picks · " +
        formatDate(startIso, { noDay: true }) + "–" +
        formatDate(picksEndIso, { noDay: true });
    }
    var listingsHeading = document.querySelector(".listings-heading");
    if (listingsHeading && !showAll) {
      var listingsEnd = isoPlusDays(startIso, daysAhead);
      listingsHeading.textContent = "All events · " +
        formatDate(startIso, { noDay: true }) + "–" +
        formatDate(listingsEnd, { noDay: true }) +
        " · sorted by rating";
    }
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
        label = label; // keep label clean; emoji kept separately
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
      var next = ev.showings[0];
      var parts = [ev.type.replace("_", " ")];
      if (next) {
        parts.push(formatDate(next.date) +
          (next.time ? " \u00b7 " + formatTime(next.time) : ""));
      }
      meta.textContent = parts.join(" \u00b7 ");
      li.appendChild(meta);

      frag.appendChild(li);
    });

    picksList.appendChild(frag);
  }

  function renderListings(events) {
    var frag = document.createDocumentFragment();

    events.forEach(function (ev) {
      var card = document.createElement("article");
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
      var subParts = [];
      if (ev.venue) subParts.push(ev.venue);
      subParts.push(ev.type.replace("_", " "));
      subtitle.textContent = subParts.join(" \u00b7 ");
      titleCol.appendChild(subtitle);

      header.appendChild(titleCol);

      var arrow = document.createElement("span");
      arrow.className = "expand-indicator";
      arrow.textContent = "\u25b6";
      arrow.setAttribute("aria-hidden", "true");
      header.appendChild(arrow);

      card.appendChild(header);

      // Always-visible showings list (v1 influence — hours visible at a glance)
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

      // Expanded panel — click reveals one-liner first, then full review
      var panel = document.createElement("div");
      panel.className = "event-panel";

      if (ev.one_liner) {
        var oneLiner = document.createElement("p");
        oneLiner.className = "event-oneliner";
        oneLiner.textContent = ev.one_liner;
        panel.appendChild(oneLiner);
      }

      var parsed = parseReview(ev.description);
      var hasReview = parsed.sections.length > 0 || (ev.program && ev.program.trim());

      if (hasReview) {
        var reviewLabel = document.createElement("div");
        reviewLabel.className = "event-review-label";
        reviewLabel.textContent = "Critic's take";
        panel.appendChild(reviewLabel);

        var byline = document.createElement("p");
        byline.className = "event-byline";
        byline.textContent = "By The Austin Culture Oracle";
        panel.appendChild(byline);

        if (ev.showings.length > 0) {
          var dateline = document.createElement("time");
          dateline.className = "event-dateline";
          dateline.textContent = formatDate(ev.showings[0].date);
          panel.appendChild(dateline);
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

            panel.appendChild(sectionEl);
          });
        } else if (ev.program) {
          var programP = document.createElement("p");
          programP.className = "event-review-body";
          programP.textContent = ev.program;
          panel.appendChild(programP);
        }
      }

      if (panel.childNodes.length > 0) {
        card.appendChild(panel);
      }

      header.addEventListener("click", function () {
        var expanded = card.classList.toggle("is-expanded");
        header.setAttribute("aria-expanded", expanded ? "true" : "false");
      });

      header.setAttribute("role", "button");
      header.setAttribute("tabindex", "0");
      header.setAttribute("aria-expanded", "false");
      header.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          header.click();
        }
      });

      frag.appendChild(card);
    });

    listingsEl.appendChild(frag);
  }
})();
