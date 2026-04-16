(function () {
  "use strict";

  var DATA_URL = "../../data.json";
  var SYNOPSIS_LIMIT = 200;

  var tableEl = document.getElementById("table");
  var loadingEl = document.getElementById("loading");
  var errorEl = document.getElementById("error");
  var countEl = document.getElementById("count");
  var filterBar = document.getElementById("filter-bar");
  var filterInput = document.getElementById("filter-input");
  var helpEl = document.getElementById("help");

  var allItems = [];
  var visibleItems = [];
  var selectedIndex = -1;
  var detailOpen = false;
  var filterActive = false;

  var params = new URLSearchParams(window.location.search);
  var debugDate = params.get("debug_date");

  fetch(DATA_URL)
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (events) {
      loadingEl.hidden = true;
      allItems = flattenToRows(events);
      visibleItems = allItems;
      renderTable(visibleItems);
      countEl.textContent = visibleItems.length + " events";
      if (visibleItems.length > 0) {
        selectRow(0);
      }
    })
    .catch(function (err) {
      loadingEl.hidden = true;
      errorEl.hidden = false;
      errorEl.textContent = "error: " + err.message;
    });

  document.addEventListener("keydown", handleKey);

  function handleKey(e) {
    if (helpEl && !helpEl.hidden) {
      if (e.key === "?" || e.key === "Escape") {
        helpEl.hidden = true;
        e.preventDefault();
      }
      return;
    }

    if (filterActive) {
      if (e.key === "Escape") {
        closeFilter();
        e.preventDefault();
      } else if (e.key === "Enter") {
        closeFilter();
        e.preventDefault();
      }
      return;
    }

    switch (e.key) {
      case "j":
      case "ArrowDown":
        e.preventDefault();
        moveSelection(1);
        break;
      case "k":
      case "ArrowUp":
        e.preventDefault();
        moveSelection(-1);
        break;
      case "g":
        e.preventDefault();
        if (visibleItems.length > 0) selectRow(0);
        break;
      case "G":
        e.preventDefault();
        if (visibleItems.length > 0) selectRow(visibleItems.length - 1);
        break;
      case "/":
        e.preventDefault();
        openFilter();
        break;
      case "?":
        e.preventDefault();
        if (helpEl) helpEl.hidden = false;
        break;
      case "Enter":
        e.preventDefault();
        openSelected();
        break;
      case "Escape":
        e.preventDefault();
        closeDetail();
        break;
    }
  }

  function moveSelection(delta) {
    if (visibleItems.length === 0) return;
    var next = selectedIndex + delta;
    if (next < 0) next = 0;
    if (next >= visibleItems.length) next = visibleItems.length - 1;
    selectRow(next);
  }

  function selectRow(idx) {
    var rows = tableEl.querySelectorAll(".row");
    if (selectedIndex >= 0 && selectedIndex < rows.length) {
      rows[selectedIndex].setAttribute("aria-selected", "false");
    }
    closeDetail();
    selectedIndex = idx;
    if (idx >= 0 && idx < rows.length) {
      rows[idx].setAttribute("aria-selected", "true");
      rows[idx].scrollIntoView({ block: "nearest" });
    }
  }

  function openSelected() {
    if (selectedIndex < 0 || selectedIndex >= visibleItems.length) return;
    var item = visibleItems[selectedIndex];
    if (item.url) {
      window.open(item.url, "_blank", "noopener");
    } else {
      toggleDetail();
    }
  }

  function toggleDetail() {
    if (detailOpen) {
      closeDetail();
      return;
    }
    if (selectedIndex < 0 || selectedIndex >= visibleItems.length) return;
    var item = visibleItems[selectedIndex];
    var rows = tableEl.querySelectorAll(".row");
    if (!rows[selectedIndex]) return;

    var pane = document.createElement("div");
    pane.className = "detail-pane";
    pane.id = "detail-pane";

    var title = document.createElement("div");
    title.className = "detail-title";
    title.textContent = item.title;
    pane.appendChild(title);

    var desc = document.createElement("div");
    desc.textContent = item.synopsis;
    pane.appendChild(desc);

    rows[selectedIndex].after(pane);
    detailOpen = true;
  }

  function closeDetail() {
    var existing = document.getElementById("detail-pane");
    if (existing) existing.remove();
    detailOpen = false;
  }

  function openFilter() {
    filterBar.hidden = false;
    filterInput.value = "";
    filterInput.focus();
    filterActive = true;
    filterInput.addEventListener("input", onFilterInput);
  }

  function closeFilter() {
    filterActive = false;
    filterBar.hidden = true;
    filterInput.removeEventListener("input", onFilterInput);

    var query = filterInput.value.trim().toLowerCase();
    if (query === "") {
      visibleItems = allItems;
    } else {
      visibleItems = allItems.filter(function (item) {
        return item.title.toLowerCase().indexOf(query) !== -1 ||
               item.venue.toLowerCase().indexOf(query) !== -1 ||
               item.type.toLowerCase().indexOf(query) !== -1;
      });
    }

    renderTable(visibleItems);
    countEl.textContent = visibleItems.length + " events";
    if (visibleItems.length > 0) {
      selectRow(0);
    } else {
      selectedIndex = -1;
    }
  }

  function onFilterInput() {
    var query = filterInput.value.trim().toLowerCase();
    if (query === "") {
      visibleItems = allItems;
    } else {
      visibleItems = allItems.filter(function (item) {
        return item.title.toLowerCase().indexOf(query) !== -1 ||
               item.venue.toLowerCase().indexOf(query) !== -1 ||
               item.type.toLowerCase().indexOf(query) !== -1;
      });
    }
    renderTable(visibleItems);
    countEl.textContent = visibleItems.length + " events";
    selectedIndex = -1;
  }

  function renderTable(items) {
    tableEl.innerHTML = "";
    if (items.length === 0) {
      tableEl.innerHTML = '<div class="status">no matching events</div>';
      return;
    }

    var frag = document.createDocumentFragment();

    items.forEach(function (item, idx) {
      var row = document.createElement("div");
      row.className = "row";
      row.setAttribute("role", "row");
      row.setAttribute("aria-selected", "false");
      row.setAttribute("tabindex", "-1");

      row.addEventListener("click", function () {
        selectRow(idx);
      });

      var dateCell = document.createElement("span");
      dateCell.className = "row-date";
      dateCell.textContent = item.date + (item.time ? " " + item.time : "");
      row.appendChild(dateCell);

      var ratingCell = document.createElement("span");
      ratingCell.className = "row-rating";
      ratingCell.textContent = item.rating > 0 ? item.rating : "·";
      row.appendChild(ratingCell);

      var titleCell = document.createElement("span");
      titleCell.className = "row-title";
      if (item.url) {
        var a = document.createElement("a");
        a.href = item.url;
        a.textContent = item.title;
        a.target = "_blank";
        a.rel = "noopener";
        a.addEventListener("click", function (e) { e.stopPropagation(); });
        titleCell.appendChild(a);
      } else {
        titleCell.textContent = item.title;
      }
      row.appendChild(titleCell);

      var venueCell = document.createElement("span");
      venueCell.className = "row-venue";
      var tag = document.createElement("span");
      tag.className = "row-tag tag-" + item.type;
      tag.textContent = item.type.replace("_", " ");
      venueCell.appendChild(tag);
      venueCell.appendChild(document.createTextNode(" " + item.venue));
      row.appendChild(venueCell);

      var emptyCell = document.createElement("span");
      row.appendChild(emptyCell);

      frag.appendChild(row);
    });

    tableEl.appendChild(frag);
  }

  function flattenToRows(events) {
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

    result.sort(function (a, b) {
      return a.date < b.date ? -1 : a.date > b.date ? 1 :
        a.title < b.title ? -1 : a.title > b.title ? 1 : 0;
    });

    if (debugDate) {
      result = result.filter(function (it) { return it.date === debugDate; });
    }

    return result;
  }

  function extractSynopsis(ev) {
    if (ev.one_liner_summary) return ev.one_liner_summary;
    if (ev.description) {
      var text = ev.description.replace(/<[^>]*>/g, "");
      if (text.length > SYNOPSIS_LIMIT) {
        return text.substring(0, SYNOPSIS_LIMIT) + "...";
      }
      return text;
    }
    if (ev.program) {
      if (ev.program.length > SYNOPSIS_LIMIT) {
        return ev.program.substring(0, SYNOPSIS_LIMIT) + "...";
      }
      return ev.program;
    }
    return "No description available.";
  }
})();
