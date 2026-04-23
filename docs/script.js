/**
 * Culture-Calendar frontend.
 *
 * Single IIFE renders the static GitHub Pages site. No framework, no
 * bundler — everything runs directly in the browser from this file.
 * All data comes from ``docs/data.json`` (written by
 * ``update_website_data.py`` server-side).
 *
 * Module layout (by line number):
 *
 *   11-55   Constants, DOM refs, state.
 *   60-165  Data loading, occurrence expansion, merge-across-venues.
 *   166-215 Grouping (groupEvents, dedupeShowings).
 *   217-245 Rating + review parsing helpers.
 *   247-285 Date/time formatters.
 *   287-336 Search + filter (getSearchQuery, matchesQuery, filterEvents).
 *   338-449 Search UI (suggestions dropdown + autocomplete).
 *   451-584 Top-picks renderer (buildPickCard, renderPicks).
 *   585-705 Merit-listings renderer (buildListingCard, renderListings).
 *   706-735 "Pending more research" bucket for low-confidence reviews.
 *   740+    Read-aloud (Web Speech API) handlers + bootstrap.
 *
 * Feature inventory: every CSS selector this module depends on must
 * be mirrored in ``.overnight/feature-inventory.json`` so the
 * continuity-user persona catches silent regressions. See
 * ``CLAUDE.md §Feature Inventory`` and ``AGENTS.md §Invariants``.
 *
 * When changing UX here:
 * - Update or add an inventory entry in the same commit.
 * - Run ``scripts/check_live_site.py`` against the updated site for
 *   selector-level regression checks.
 * - For architectural changes, tag the commit ``[persona-gate]`` so
 *   the pre-push hook runs the LLM council (see ``.githooks/pre-push``).
 */
(function () {
  "use strict";

  var DATA_URL = (window.location && window.location.hostname || "").indexOf("github.io") !== -1
    ? "/Culture-Calendar/data.json"
    : "data.json";
  var CONFIG_URL = (window.location && window.location.hostname || "").indexOf("github.io") !== -1
    ? "/Culture-Calendar/config.json"
    : "config.json";
  var CATEGORY_LABELS = {
    movie: "Film", film: "Film", concert: "Concert", book_club: "Book Club",
    opera: "Opera", dance: "Dance", ballet: "Ballet", visual_arts: "Visual Arts",
    other: "Other"
  };
  var MONTHS_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  var WEEKDAY_SHORT = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];

  var picksList = document.getElementById("picks-list");
  var listingsEl = document.getElementById("listings");
  var loadingEl = document.getElementById("loading");
  var errorEl = document.getElementById("error");
  var searchInput = document.getElementById("event-search");
  var searchSuggestions = document.getElementById("search-suggestions");

  var allEvents = [];
  var searchDebounceTimer = null;
  var SEARCH_DEBOUNCE_MS = 150;
  var MAX_SUGGESTIONS_PER_GROUP = 20;

  /* task-T7.2: Plausible analytics queue shim.
     Plausible's script (loaded async in docs/index.html) exposes
     window.plausible as a global function. Because the script is async,
     custom events fired before it finishes loading would be dropped.
     This shim queues any early calls on window.plausible.q; the real
     script replays the queue on load. Call sites use the literal
     plausible("cc_*") form so the analytics event names are greppable.

     task-T5.1: Greppable analytics event catalog (regression guard).
     Per-platform share events (T1.1): cc_share_twitter, cc_share_bluesky,
     cc_share_threads, cc_share_mastodon, cc_share_linkedin,
     cc_share_whatsapp, cc_share_sms, cc_share_email, cc_share_copy.
     Calendar intents (T1.3, T1.4): cc_share_google_calendar,
     cc_share_apple_calendar.
     Mailing list (T2.2): cc_subscribe_email. All platform IDs plus
     cc_subscribe_email must stay greppable in this file; the T5.1 queue
     validator asserts both with a plain grep so silent removals fail CI. */
  window.plausible = window.plausible || function () {
    (window.plausible.q = window.plausible.q || []).push(arguments);
  };

  /* task-T7.2: Wire subscribe-link click tracking via event delegation.
     Distinguishes ICS (webcal:// or .ics) from RSS (feed.xml / rss). */
  document.addEventListener("click", function (e) {
    var a = e.target && e.target.closest && e.target.closest("a.subscribe-link");
    if (!a) return;
    var href = (a.getAttribute("href") || "").toLowerCase();
    if (href.indexOf("webcal:") === 0 || href.indexOf(".ics") !== -1) {
      window.plausible("cc_subscribe_ics");
    } else if (href.indexOf("feed.xml") !== -1 || href.indexOf("/rss") !== -1) {
      window.plausible("cc_subscribe_rss");
    }
  }, true);
  /* task-T2.4: Deep-link index. Keyed by slug(event.id || event.title),
     populated as each card is built so #event=<id> can scroll + expand. */
  var cardIndex = {};
  var EVENT_HASH_PREFIX = "#event=";

  /* task-T1.5: Web Speech API read-aloud button.
     Supported cross-browser (desktop + mobile). Second click on an active
     button cancels. Sentence-chunked so Safari does not truncate long text. */
  var tts = (function () {
    var supported = typeof window !== "undefined"
      && typeof window.speechSynthesis !== "undefined"
      && typeof window.SpeechSynthesisUtterance !== "undefined";
    var voices = [];
    var activeBtn = null;

    function refreshVoices() {
      try { voices = window.speechSynthesis.getVoices() || []; }
      catch (e) { voices = []; }
    }
    if (supported) {
      refreshVoices();
      if (typeof window.speechSynthesis.addEventListener === "function") {
        window.speechSynthesis.addEventListener("voiceschanged", refreshVoices);
      } else {
        window.speechSynthesis.onvoiceschanged = refreshVoices;
      }
    }

    function pickVoice() {
      if (!voices.length) return null;
      for (var i = 0; i < voices.length; i++) {
        var v = voices[i];
        if (v && v.lang && v.lang.toLowerCase().indexOf("en") === 0 && v.localService) return v;
      }
      for (var j = 0; j < voices.length; j++) {
        var w = voices[j];
        if (w && w.lang && w.lang.toLowerCase().indexOf("en") === 0) return w;
      }
      return voices[0] || null;
    }

    function stripHtml(s) {
      if (!s) return "";
      return String(s).replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
    }

    function splitSentences(text) {
      if (!text) return [];
      var raw = text.match(/[^.!?]+[.!?]+(\s|$)|[^.!?]+$/g) || [text];
      var out = [];
      for (var i = 0; i < raw.length; i++) {
        var s = raw[i].trim();
        if (s) out.push(s);
      }
      return out;
    }

    function cancel() {
      if (!supported) return;
      try { window.speechSynthesis.cancel(); } catch (e) { /* noop */ }
    }

    function resetButton(btn) {
      if (!btn) return;
      btn.classList.remove("is-playing");
      btn.textContent = "\u25B6 Read aloud";
      btn.setAttribute("aria-label", "Read aloud");
    }

    function clearActive() {
      if (activeBtn) resetButton(activeBtn);
      activeBtn = null;
    }

    function buildText(ev) {
      var parts = [];
      if (ev.one_liner) parts.push(String(ev.one_liner).trim());
      var body = stripHtml(ev.description);
      if (body) parts.push(body);
      return parts.filter(Boolean).join(" ").trim();
    }

    function speakNow(btn, text) {
      cancel();
      clearActive();
      var chunks = splitSentences(text);
      if (!chunks.length) return;
      var voice = pickVoice();
      activeBtn = btn;
      btn.classList.add("is-playing");
      btn.textContent = "\u25A0 Stop";
      btn.setAttribute("aria-label", "Stop read aloud");
      var idx = 0;
      function next() {
        if (activeBtn !== btn) return;
        if (idx >= chunks.length) { clearActive(); return; }
        var u = new window.SpeechSynthesisUtterance(chunks[idx]);
        u.rate = 0.95;
        u.pitch = 1.0;
        u.volume = 1.0;
        if (voice) { u.voice = voice; u.lang = voice.lang; }
        u.onend = function () { if (activeBtn !== btn) return; idx++; next(); };
        u.onerror = function () { if (activeBtn === btn) clearActive(); };
        try { window.speechSynthesis.speak(u); }
        catch (e) { clearActive(); }
      }
      next();
    }

    function createButton(ev) {
      if (!supported) return null;
      var text = buildText(ev);
      if (!text) return null;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "tts-button";
      btn.textContent = "\u25B6 Read aloud";
      btn.setAttribute("aria-label", "Read aloud");
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        if (activeBtn === btn) { cancel(); clearActive(); return; }
        speakNow(btn, text);
      });
      return btn;
    }

    /* task-T4.2: speak arbitrary text driven by a controlling button.
       Used by the "Audio brief" button in the picks section to read a
       concatenated summary of the top picks. Cancels any in-flight
       utterance, mirrors the same is-playing toggle behavior. */
    function speak(btn, text) {
      if (!supported || !btn || !text) return;
      if (activeBtn === btn) { cancel(); clearActive(); return; }
      speakNow(btn, text);
    }

    return { supported: supported, createButton: createButton, speak: speak };
  })();

  /* task-T6.3: Share this pick button.
     Primary path: Web Share API (navigator.share) — invokes the OS share
     sheet on mobile / supporting desktops. Fallback path: inline popover
     with three deterministic options — mailto: for email, twitter.com
     intent URL for X/Twitter, and navigator.clipboard.writeText for
     copy-to-clipboard (degrades to a hidden textarea + execCommand on
     older browsers). Share URL points at the per-event shell page
     (events/<slug>.html) which carries per-event OG and JSON-LD meta
     so link-unfurl bots can render rich previews; the shell itself
     auto-redirects real users to /#event=<slug> for the live modal. */
  function _slugForShare(raw) {
    if (!raw) return "";
    var s = String(raw)
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
    return s || "event";
  }
  var share = (function () {
    /* task-T1.1: Share popover iterates a single PLATFORMS registry so
       every surface (per-event Share button + weekly-digest button) goes
       through the same code path. Each platform fires its own Plausible
       event cc_share_<id> for per-channel attribution; a generic cc_share
       still fires on initial click for back-compat with T6.3 telemetry. */
    function enc(s) { return encodeURIComponent(s); }

    function _firstShowing(ev) {
      if (!ev) return null;
      var list = ev.showings;
      if (list && list.length) return list[0];
      var dates = ev.dates || [];
      var times = ev.times || [];
      if (dates.length) {
        return { date: dates[0], time: times[0] || "", venue: ev.venue || "", url: ev.url || "" };
      }
      return null;
    }

    /* task-T1.3: Build Google Calendar TEMPLATE URL.
       Google's /calendar/render?action=TEMPLATE accepts:
         dates=YYYYMMDDTHHMMSS/YYYYMMDDTHHMMSS (local) or YYYYMMDD/YYYYMMDD (all-day).
       We emit floating-local times (no Z suffix) since event times in the data
       are venue-local wall-clock; Google renders in the viewer's timezone which
       is fine for Austin events viewed by Austinites. Falls back to an all-day
       entry when no time is known. Assumes ~2h duration when only start known. */
    function _gcalDates(date, time) {
      if (!date) return "";
      var d = String(date).replace(/-/g, "");
      if (!time) {
        var next = new Date(date + "T00:00:00");
        next.setDate(next.getDate() + 1);
        var y = next.getFullYear();
        var m = String(next.getMonth() + 1).padStart(2, "0");
        var day = String(next.getDate()).padStart(2, "0");
        return d + "/" + y + m + day;
      }
      var parts = String(time).split(":");
      var hh = (parts[0] || "00").padStart(2, "0");
      var mm = (parts[1] || "00").padStart(2, "0");
      var start = d + "T" + hh + mm + "00";
      var startMs = new Date(date + "T" + hh + ":" + mm + ":00").getTime();
      var endDate = new Date(startMs + 2 * 60 * 60 * 1000);
      var ey = endDate.getFullYear();
      var em = String(endDate.getMonth() + 1).padStart(2, "0");
      var ed = String(endDate.getDate()).padStart(2, "0");
      var eh = String(endDate.getHours()).padStart(2, "0");
      var emin = String(endDate.getMinutes()).padStart(2, "0");
      var end = "" + ey + em + ed + "T" + eh + emin + "00";
      return start + "/" + end;
    }

    function eventShareable(ev) {
      var rawId = (ev && (ev.id || ev.event_id || ev.title)) || "";
      var slug = _slugForShare(rawId);
      var url = slug ? OG_DEFAULT_URL + "events/" + slug + ".html" : OG_DEFAULT_URL;
      var title = (ev && ev.title) || "Culture Calendar pick";
      // task-T1.2: pre-craft shareText from event one_liner hook, fall back to title
      var oneLiner = (ev && (ev.one_liner_summary || ev.one_liner)) || "";
      var shareText = oneLiner ? title + " — " + String(oneLiner).trim() : title;
      var first = _firstShowing(ev);
      var location = (first && first.venue) || (ev && ev.venue) || "";
      var gcalDates = first ? _gcalDates(first.date, first.time) : "";
      /* task-T1.4: Apple Calendar handoff. iOS / macOS subscribe to a
         webcal:// URL pointing at the per-event .ics file emitted by
         scripts/build_event_ics.py (task-T1.1) into docs/events/<slug>.ics.
         The webcal:// scheme triggers the native Calendar add-event sheet
         on Apple platforms and falls back to the default .ics handler on
         other OSes. Omitted when the event has no slug. */
      var icsUrl = slug
        ? "webcal://hadrien-cornier.github.io/Culture-Calendar/events/" + slug + ".ics"
        : "";
      return {
        title: title,
        text: shareText,
        url: url,
        subject: "Culture Calendar: " + title,
        body: shareText + "\n\n" + url + "\n",
        location: location,
        gcalDates: gcalDates,
        icsUrl: icsUrl
      };
    }

    function digestShareable(tag, url) {
      var title = "Austin Culture Calendar — Top Picks (" + tag + ")";
      var text = "This week’s AI-curated top picks for Austin cultural events";
      return {
        title: title,
        text: text,
        url: url,
        subject: title,
        body: text + ":\n\n" + url + "\n"
      };
    }

    var PLATFORMS = [
      {
        id: "twitter",
        label: "🐦 Twitter / X",
        href: function (s) {
          return "https://twitter.com/intent/tweet?text="
            + enc(s.text) + "&url=" + enc(s.url);
        }
      },
      {
        id: "threads",
        label: "🧵 Threads",
        href: function (s) {
          return "https://www.threads.net/intent/post?text="
            + enc(s.text + " " + s.url);
        }
      },
      {
        id: "bluesky",
        label: "🦋 Bluesky",
        href: function (s) {
          return "https://bsky.app/intent/compose?text="
            + enc(s.text + " " + s.url);
        }
      },
      {
        id: "mastodon",
        label: "🐘 Mastodon",
        href: function (s) {
          return "https://mastodonshare.com/?text="
            + enc(s.text) + "&url=" + enc(s.url);
        }
      },
      {
        id: "linkedin",
        label: "💼 LinkedIn",
        href: function (s) {
          return "https://www.linkedin.com/sharing/share-offsite/?url="
            + enc(s.url);
        }
      },
      {
        id: "whatsapp",
        label: "💬 WhatsApp",
        href: function (s) {
          return "https://wa.me/?text=" + enc(s.text + " " + s.url);
        }
      },
      {
        id: "sms",
        label: "📱 SMS",
        href: function (s) { return "sms:?&body=" + enc(s.text + " " + s.url); },
        sameTab: true
      },
      {
        id: "email",
        label: "✉ Email",
        href: function (s) {
          return "mailto:?subject=" + enc(s.subject)
            + "&body=" + enc(s.body);
        },
        sameTab: true
      },
      /* task-T1.3: Google Calendar TEMPLATE intent. Only rendered when the
         shareable carries gcalDates (per-event shares do; digest shares don't,
         since a weekly digest isn't a single event). The trackPlatform() call
         replaces dashes in the id with underscores so the Plausible event
         name matches the greppable cc_share_google_calendar literal used by
         the T5.1 analytics catalog. */
      {
        id: "google-calendar",
        label: "📅 Google Calendar",
        appliesTo: function (s) { return !!s.gcalDates; },
        href: function (s) {
          return "https://calendar.google.com/calendar/render?action=TEMPLATE"
            + "&text=" + enc(s.title)
            + "&dates=" + s.gcalDates
            + "&details=" + enc(s.body)
            + (s.location ? "&location=" + enc(s.location) : "");
        }
      },
      /* task-T1.4: Apple Calendar webcal:// intent. Only rendered when the
         shareable carries icsUrl (per-event shares do; digest shares don't
         — there's no single .ics for a digest). webcal:// is the canonical
         Apple handoff scheme: iOS / macOS hijack it to open the Calendar
         add-subscription / add-event sheet. Falls back gracefully on
         Android / Windows which treat webcal:// as plain http for .ics. */
      {
        id: "apple-calendar",
        label: "🍎 Apple Calendar",
        appliesTo: function (s) { return !!s.icsUrl; },
        href: function (s) { return s.icsUrl; },
        sameTab: true
      },
      {
        id: "copy",
        label: "📋 Copy link",
        action: "copy"
      }
    ];

    function copyToClipboard(text) {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(text);
      }
      return new Promise(function (resolve, reject) {
        try {
          var ta = document.createElement("textarea");
          ta.value = text;
          ta.setAttribute("readonly", "");
          ta.style.position = "absolute";
          ta.style.left = "-9999px";
          document.body.appendChild(ta);
          ta.select();
          document.execCommand("copy");
          document.body.removeChild(ta);
          resolve();
        } catch (err) { reject(err); }
      });
    }

    function closePopover(btn, pop) {
      if (pop && pop.parentNode) pop.parentNode.removeChild(pop);
      btn.setAttribute("aria-expanded", "false");
      btn._sharePopover = null;
    }

    function flashCopied(node, label) {
      node.textContent = "✓ Copied";
      setTimeout(function () { node.textContent = label; }, 1400);
    }

    function trackPlatform(id) {
      /* Per-platform Plausible events:
         cc_share_twitter, cc_share_threads, cc_share_bluesky,
         cc_share_mastodon, cc_share_linkedin, cc_share_whatsapp,
         cc_share_sms, cc_share_email, cc_share_copy,
         cc_share_google_calendar (task-T1.3),
         cc_share_apple_calendar (task-T1.4).
         IDs may contain dashes (e.g. "google-calendar", "apple-calendar");
         Plausible event names convert to underscores so the analytics
         catalog in the top-of-file header stays a clean grep target. */
      var slug = String(id).replace(/-/g, "_");
      try { window.plausible("cc_share_" + slug); } catch (e) { /* no-op */ }
    }

    function buildPopover(btn, shareable) {
      var pop = document.createElement("div");
      pop.className = "share-popover";
      pop.setAttribute("role", "menu");

      PLATFORMS.forEach(function (p) {
        /* task-T1.3: Platforms may opt out for a given shareable via
           appliesTo() — e.g. google-calendar hides itself on the digest
           button since there's no single event datetime to import. */
        if (typeof p.appliesTo === "function" && !p.appliesTo(shareable)) return;
        var node;
        if (p.action === "copy") {
          node = document.createElement("button");
          node.type = "button";
        } else {
          node = document.createElement("a");
          node.href = p.href(shareable);
          node.rel = p.sameTab ? "noopener" : "noopener noreferrer";
          if (!p.sameTab) node.target = "_blank";
        }
        node.className = "share-option share-option-" + p.id;
        node.setAttribute("role", "menuitem");
        node.setAttribute("data-platform", p.id);
        node.textContent = p.label;

        if (p.action === "copy") {
          node.addEventListener("click", function (e) {
            e.stopPropagation();
            trackPlatform(p.id);
            copyToClipboard(shareable.url).then(function () {
              flashCopied(node, p.label);
              setTimeout(function () { closePopover(btn, pop); }, 900);
            }, function () {
              node.textContent = "✗ Copy failed";
            });
          });
        } else {
          node.addEventListener("click", function () {
            trackPlatform(p.id);
            setTimeout(function () { closePopover(btn, pop); }, 0);
          });
        }
        pop.appendChild(node);
      });

      return pop;
    }

    function openPopover(btn, shareable) {
      if (btn._sharePopover) { closePopover(btn, btn._sharePopover); return; }
      var pop = buildPopover(btn, shareable);
      btn.insertAdjacentElement("afterend", pop);
      btn._sharePopover = pop;
      btn.setAttribute("aria-expanded", "true");
      setTimeout(function () {
        document.addEventListener("click", function onDoc(e) {
          if (!pop.contains(e.target) && e.target !== btn) {
            closePopover(btn, pop);
            document.removeEventListener("click", onDoc, true);
          }
        }, true);
      }, 0);
    }

    function shareShareable(btn, shareable) {
      window.plausible("cc_share");
      if (navigator.share) {
        try {
          navigator.share({
            title: shareable.title,
            text: shareable.text,
            url: shareable.url
          }).catch(function () { /* user cancel */ });
          return;
        } catch (e) { /* fall through to popover */ }
      }
      openPopover(btn, shareable);
    }

    function shareEvent(btn, ev) { shareShareable(btn, eventShareable(ev)); }

    function createButton(ev) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "share-button";
      btn.textContent = "↗ Share";
      btn.setAttribute("aria-label", "Share this pick");
      btn.setAttribute("aria-haspopup", "menu");
      btn.setAttribute("aria-expanded", "false");
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        shareEvent(btn, ev);
      });
      return btn;
    }

    function createDigestButton(tag, url) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "email-digest-button audio-brief-button share-button";
      btn.textContent = "✉ Share this digest";
      btn.setAttribute(
        "aria-label",
        "Share this week's digest via email, Twitter, Bluesky, or more"
      );
      btn.setAttribute("aria-haspopup", "menu");
      btn.setAttribute("aria-expanded", "false");
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        shareShareable(btn, digestShareable(tag, url));
      });
      return btn;
    }

    return {
      createButton: createButton,
      createDigestButton: createDigestButton,
      shareEvent: shareEvent
    };
  })();

  /* task-T3.1: Client-side taste graph.
     Persists thumbs up/down signals to localStorage.cc_taste with shape
     { thumbs: { <slug>: +1 | -1 }, saves: [<slug>, ...] }. Thumb clicks
     are idempotent toggles; save clicks toggle membership in the saves
     list. Silently no-ops if storage is unavailable (private mode,
     quota, etc.) so the UI still renders. Downstream tasks (T3.3
     re-rank, T7.2 analytics) extend the same store.
     task-T3.2: added saves:[ids] + star button + savedEvents accessor. */
  var taste = (function () {
    var STORAGE_KEY = "cc_taste";
    var memory = { thumbs: {}, saves: [] };
    var available = false;

    function load() {
      try {
        var raw = window.localStorage && window.localStorage.getItem(STORAGE_KEY);
        available = true;
        if (!raw) return;
        var parsed = JSON.parse(raw);
        if (parsed && typeof parsed === "object") {
          if (parsed.thumbs && typeof parsed.thumbs === "object") {
            memory.thumbs = parsed.thumbs;
          }
          if (Array.isArray(parsed.saves)) {
            memory.saves = parsed.saves.filter(function (s) {
              return typeof s === "string" && s.length > 0;
            });
          }
        }
      } catch (e) { available = false; }
    }
    load();

    function persist() {
      if (!available) return;
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(memory));
      } catch (e) { /* quota / private mode — keep in-memory copy */ }
    }

    function eventSlug(ev) {
      var raw = (ev && (ev.id || ev.event_id || ev.title)) || "";
      return ogCardSlug(raw);
    }

    function getThumb(slug) {
      if (!slug) return 0;
      var v = memory.thumbs[slug];
      return v === 1 || v === -1 ? v : 0;
    }

    function setThumb(slug, value) {
      if (!slug) return 0;
      if (value === 1 || value === -1) memory.thumbs[slug] = value;
      else delete memory.thumbs[slug];
      persist();
      try {
        document.dispatchEvent(new CustomEvent("cc:thumbs-changed", {
          detail: { slug: slug, value: getThumb(slug) }
        }));
      } catch (err) { /* old browser — rerank runs on next natural render */ }
      return getThumb(slug);
    }

    function getAllThumbs() {
      var out = {};
      Object.keys(memory.thumbs).forEach(function (k) {
        var v = memory.thumbs[k];
        if (v === 1 || v === -1) out[k] = v;
      });
      return out;
    }

    function applyState(upBtn, downBtn, current) {
      if (upBtn) {
        var upOn = current === 1;
        upBtn.classList.toggle("is-active", upOn);
        upBtn.setAttribute("aria-pressed", upOn ? "true" : "false");
      }
      if (downBtn) {
        var downOn = current === -1;
        downBtn.classList.toggle("is-active", downOn);
        downBtn.setAttribute("aria-pressed", downOn ? "true" : "false");
      }
    }

    function createControls(ev) {
      var slug = eventSlug(ev);
      if (!slug) return null;
      var wrap = document.createElement("div");
      wrap.className = "thumb-controls";
      wrap.setAttribute("role", "group");
      wrap.setAttribute("aria-label", "Rate this event");

      var upBtn = document.createElement("button");
      upBtn.type = "button";
      upBtn.className = "thumb-button thumb-up";
      upBtn.setAttribute("aria-label", "Thumbs up");
      upBtn.textContent = "\uD83D\uDC4D";

      var downBtn = document.createElement("button");
      downBtn.type = "button";
      downBtn.className = "thumb-button thumb-down";
      downBtn.setAttribute("aria-label", "Thumbs down");
      downBtn.textContent = "\uD83D\uDC4E";

      applyState(upBtn, downBtn, getThumb(slug));

      upBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        var current = getThumb(slug);
        var next = current === 1 ? 0 : 1;
        applyState(upBtn, downBtn, setThumb(slug, next));
        if (next === 1) window.plausible("cc_thumb_up");
      });
      downBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        var current = getThumb(slug);
        var next = current === -1 ? 0 : -1;
        applyState(upBtn, downBtn, setThumb(slug, next));
        if (next === -1) window.plausible("cc_thumb_down");
      });

      wrap.appendChild(upBtn);
      wrap.appendChild(downBtn);
      var saveBtn = createSaveButton(ev);
      if (saveBtn) wrap.appendChild(saveBtn);
      return wrap;
    }

    /* task-T3.2: Save (star) button. Toggles membership in
       memory.saves and dispatches cc:saves-changed so the My Picks
       filter can refresh without a full app re-bind. */
    function getSave(slug) {
      if (!slug) return false;
      return memory.saves.indexOf(slug) !== -1;
    }
    function setSave(slug, on) {
      if (!slug) return false;
      var idx = memory.saves.indexOf(slug);
      if (on && idx === -1) memory.saves.push(slug);
      else if (!on && idx !== -1) memory.saves.splice(idx, 1);
      persist();
      return getSave(slug);
    }
    function savedEvents() { return memory.saves.slice(); }
    function isSaved(ev) {
      var slug = eventSlug(ev);
      return slug ? getSave(slug) : false;
    }
    function applySaveState(btn, on) {
      btn.classList.toggle("is-saved", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      btn.textContent = on ? "\u2605" : "\u2606";
      btn.setAttribute("aria-label", on ? "Unsave event" : "Save event");
      btn.setAttribute("title", on ? "Saved — click to remove" : "Save to My Picks");
    }
    function createSaveButton(ev) {
      var slug = eventSlug(ev);
      if (!slug) return null;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "save-button";
      applySaveState(btn, getSave(slug));
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        var next = !getSave(slug);
        applySaveState(btn, setSave(slug, next));
        if (next) window.plausible("cc_save");
        try {
          document.dispatchEvent(new CustomEvent("cc:saves-changed", {
            detail: { slug: slug, saved: next }
          }));
        } catch (err) { /* old browser — filter will still update on next render */ }
      });
      return btn;
    }

    return {
      getThumb: getThumb,
      setThumb: setThumb,
      getAllThumbs: getAllThumbs,
      getSave: getSave,
      setSave: setSave,
      isSaved: isSaved,
      savedEvents: savedEvents,
      createControls: createControls,
      createSaveButton: createSaveButton,
      eventSlug: eventSlug
    };
  })();
  window.cultureCalendar = window.cultureCalendar || {};
  window.cultureCalendar.taste = taste;

  /* task-T2.1: Load docs/config.json into window.CC_CONFIG at init.
     Config is non-fatal — a missing or malformed config.json leaves
     CC_CONFIG as an empty object so downstream consumers (e.g. the
     Buttondown signup endpoint in T2.2) can safely read optional keys
     and fall back when they're unset. */
  window.CC_CONFIG = window.CC_CONFIG || {};
  fetch(CONFIG_URL)
    .then(function (r) { return r.ok ? r.json() : {}; })
    .then(function (cfg) {
      window.CC_CONFIG = (cfg && typeof cfg === "object") ? cfg : {};
      if (typeof document.dispatchEvent === "function" && typeof CustomEvent === "function") {
        document.dispatchEvent(new CustomEvent("cc:config-loaded", { detail: window.CC_CONFIG }));
      }
    })
    .catch(function () { /* no-op: CC_CONFIG stays {} */ });

  fetch(DATA_URL)
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(function (raw) {
      allEvents = Array.isArray(raw) ? raw : (raw.events || []);
      loadingEl.hidden = true;
      renderAll();
      handleEventHash();
    })
    .catch(function (err) {
      loadingEl.hidden = true;
      errorEl.hidden = false;
      errorEl.textContent = "Error: " + err.message;
    });

  initSearch();
  initMyPicksToggle();
  initSignupForm();

  /* task-T2.2: Buttondown email signup with stub fallback.
     Endpoint comes from window.CC_CONFIG.buttondown_endpoint (loaded async
     from docs/config.json). When unset, the form shows a stub confirmation
     without POSTing. Submit always fires cc_subscribe_email so we can
     measure intent independently of whether Buttondown is wired up yet. */
  function initSignupForm() {
    var form = document.getElementById("signup-form");
    if (!form) return;
    var input = document.getElementById("signup-email");
    var statusEl = document.getElementById("signup-form-status");
    if (!input || !statusEl) return;

    function setStatus(msg, kind) {
      statusEl.textContent = msg;
      statusEl.className = "signup-form-status" + (kind ? " is-" + kind : "");
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var email = (input.value || "").trim();
      if (!email || email.indexOf("@") === -1) {
        setStatus("Please enter a valid email address.", "error");
        input.focus();
        return;
      }
      try { window.plausible("cc_subscribe_email"); } catch (err) { /* no-op */ }
      var endpoint = (window.CC_CONFIG && window.CC_CONFIG.buttondown_endpoint) || "";
      if (!endpoint) {
        setStatus("Mailing list coming soon — we saved your interest.", "success");
        form.reset();
        return;
      }
      setStatus("Subscribing…", "pending");
      var body = new URLSearchParams();
      body.append("email", email);
      fetch(endpoint, {
        method: "POST",
        mode: "no-cors",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString()
      }).then(function () {
        setStatus("Check your inbox to confirm your subscription.", "success");
        form.reset();
      }).catch(function () {
        setStatus("Subscription failed — please try again later.", "error");
      });
    });
  }

  function groupEvents(events) {
    var byTitle = {};
    var order = [];
    events.forEach(function (ev) {
      var key = ev.title || "Untitled";
      if (!byTitle[key]) {
        byTitle[key] = {
          title: ev.title,
          rating: ev.rating || 0,
          type: (ev.type || ev.event_category || "other").toLowerCase(),
          venue: ev.venue || "",
          url: ev.url || "",
          description: ev.description || "",
          one_liner: ev.one_liner_summary || "",
          review_confidence: (ev.review_confidence || "unknown").toLowerCase(),
          showings: []
        };
        order.push(key);
      } else if ((ev.review_confidence || "").toLowerCase() === "low") {
        byTitle[key].review_confidence = "low";
      }
      var entry = byTitle[key];
      var screenings = ev.screenings || [];
      if (screenings.length > 0) {
        screenings.forEach(function (s) {
          entry.showings.push({ date: s.date, time: s.time || "", venue: s.venue || ev.venue || "", url: s.url || ev.url || "" });
        });
      } else {
        var dates = ev.dates || [];
        var times = ev.times || [];
        dates.forEach(function (d, i) {
          entry.showings.push({ date: d, time: times[i] || "", venue: ev.venue || "", url: ev.url || "" });
        });
      }
    });
    var result = order.map(function (k) { return byTitle[k]; });
    result.forEach(function (ev) { ev.showings = dedupeShowings(ev.showings); });
    result.sort(function (a, b) { return b.rating - a.rating || a.title.localeCompare(b.title); });
    return result;
  }

  function dedupeShowings(list) {
    var seen = {}, out = [];
    list.forEach(function (s) {
      var k = s.date + "|" + s.time;
      if (!seen[k]) { seen[k] = true; out.push(s); }
    });
    out.sort(function (a, b) { return a.date < b.date ? -1 : a.date > b.date ? 1 : (a.time || "").localeCompare(b.time || ""); });
    return out;
  }

  function ratingClass(r) { return r >= 8 ? "high" : r >= 5 ? "mid" : "low"; }

  /* task-T2.1: JSON-LD Event schema injection.
     Runs the first time a card opens. Injects a
     <script type="application/ld+json"> tag so search engines and
     SERP-style previews can read Event metadata per
     https://schema.org/Event. Injected once per card. */
  function buildEventJsonLd(ev) {
    var first = ev.showings && ev.showings[0];
    var data = {
      "@context": "https://schema.org",
      "@type": "Event",
      "name": ev.title || "Untitled event"
    };
    if (first && first.date) {
      data.startDate = first.time ? (first.date + "T" + first.time) : first.date;
    }
    var venueName = (first && first.venue) || ev.venue;
    if (venueName) {
      data.location = { "@type": "Place", "name": venueName };
    }
    if (ev.description) {
      var flat = String(ev.description).replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
      if (flat) data.description = flat;
    }
    var offerUrl = (first && first.url) || ev.url;
    if (offerUrl) {
      data.offers = { "@type": "Offer", "url": offerUrl };
    }
    return data;
  }

  function injectEventJsonLd(card, ev) {
    if (!card || card.dataset.jsonLdInjected === "1") return;
    try {
      var script = document.createElement("script");
      script.type = "application/ld+json";
      script.textContent = JSON.stringify(buildEventJsonLd(ev));
      card.appendChild(script);
      card.dataset.jsonLdInjected = "1";
    } catch (e) { /* noop */ }
  }

  /* task-T2.3: Dynamic Open Graph / Twitter meta tags for deep-linked
     events. Static fallback lives in index.html <head>. When the URL
     carries #event=<id>, we rewrite the meta tags so social-card
     scrapers (Twitter, LinkedIn, Slack, iMessage) see an event-
     specific title, description, and SVG card image generated by
     scripts/build_og_cards.py (docs/og/<slug>.svg). T2.4 adds the
     hashchange handler that wires this up; exposing updateOGMetaForEvent
     here keeps that task a small one-liner. */
  var OG_SITE_ORIGIN = "https://hadrien-cornier.github.io/Culture-Calendar";
  var OG_DEFAULT_TITLE = "Culture Calendar — Austin cultural events, AI-curated";
  var OG_DEFAULT_DESCRIPTION = "Austin cultural events, AI-curated. Films, concerts, opera, ballet, and literary events — sorted by merit, not marketing.";
  var OG_DEFAULT_URL = OG_SITE_ORIGIN + "/";
  var OG_DEFAULT_IMAGE = OG_SITE_ORIGIN + "/og/site-default.svg";

  function ogCardSlug(eventId) {
    if (!eventId) return "";
    var lowered = String(eventId).toLowerCase();
    var safe = lowered.replace(/[^a-z0-9._-]+/g, "-");
    safe = safe.replace(/^[-.]+|[-.]+$/g, "");
    safe = safe.replace(/-{2,}/g, "-");
    return safe;
  }

  /* task-T5.3: Cross-links from an expanded event card to the matching
     venue page (docs/venues/<slug>.html, built by
     scripts/build_venue_pages.py) and any person pages
     (docs/people/<slug>.html, built by scripts/build_people_pages.py).
     Slug algorithm mirrors the Python slugify() in both builders:
     lowercase, non-[a-z0-9] collapsed to "-", trimmed hyphens. Pages
     are generated server-side; chips render unconditionally when the
     event data carries the name so the continuity-user persona can
     assert .venue-link / .people-link stay alive on the live site. */
  var CROSS_LINK_NAME_BLOCKLIST = {
    "": 1, "various": 1, "various artists": 1, "others": 1, "other": 1,
    "unknown": 1, "n/a": 1, "na": 1, "tba": 1, "tbd": 1,
    "anonymous": 1, "traditional": 1
  };

  function crossLinkSlug(name) {
    if (!name) return "";
    var lowered = String(name).trim().toLowerCase();
    var slug = lowered.replace(/[^a-z0-9]+/g, "-");
    return slug.replace(/^-+|-+$/g, "");
  }

  function cleanCrossLinkName(value) {
    if (typeof value !== "string") return "";
    var stripped = value.trim();
    if (!stripped) return "";
    if (CROSS_LINK_NAME_BLOCKLIST[stripped.toLowerCase()]) return "";
    return stripped;
  }

  function collectPeopleNames(ev) {
    var seen = {};
    var out = [];
    function add(raw) {
      if (!raw) return;
      if (Array.isArray(raw)) { raw.forEach(add); return; }
      var cleaned = cleanCrossLinkName(raw);
      if (!cleaned) return;
      var key = cleaned.toLowerCase();
      if (seen[key]) return;
      seen[key] = 1;
      out.push(cleaned);
    }
    var t = ev && ev.type;
    if (t === "movie" || t === "film") {
      add(ev.director); add(ev.directors);
    } else if (t === "book_club") {
      add(ev.author); add(ev.authors);
    } else if (t === "concert" || t === "opera") {
      add(ev.composer); add(ev.composers);
    }
    return out;
  }

  function makeCrossLinkChip(label, href, className, ariaLabel) {
    var a = document.createElement("a");
    a.className = className;
    a.href = href;
    a.textContent = label + " \u2192";
    if (ariaLabel) a.setAttribute("aria-label", ariaLabel);
    a.addEventListener("click", function (e) { e.stopPropagation(); });
    return a;
  }

  function buildCrossLinks(ev) {
    if (!ev) return null;
    var wrap = document.createElement("div");
    wrap.className = "event-cross-links";
    var added = 0;

    var venueName = ev.venue;
    if (venueName) {
      var venueSlug = crossLinkSlug(venueName);
      if (venueSlug) {
        var venuePage = "venues/" + venueSlug + ".html";
        wrap.appendChild(makeCrossLinkChip(
          venueName, venuePage, "cross-link-chip venue-link",
          "Open " + venueName + " venue page"
        ));
        added += 1;
      }
    }

    var people = collectPeopleNames(ev);
    for (var i = 0; i < people.length; i += 1) {
      var personName = people[i];
      var personSlug = crossLinkSlug(personName);
      if (!personSlug) continue;
      var personPage = "people/" + personSlug + ".html";
      wrap.appendChild(makeCrossLinkChip(
        personName, personPage, "cross-link-chip people-link",
        "Open " + personName + " profile page"
      ));
      added += 1;
    }

    return added > 0 ? wrap : null;
  }

  function setMetaContent(selector, content) {
    var el = document.head.querySelector(selector);
    if (!el) return;
    el.setAttribute("content", content);
  }

  function flattenText(html) {
    if (!html) return "";
    return String(html).replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
  }

  function resetOGMetaToDefault() {
    setMetaContent('meta[property="og:title"]', OG_DEFAULT_TITLE);
    setMetaContent('meta[property="og:description"]', OG_DEFAULT_DESCRIPTION);
    setMetaContent('meta[property="og:url"]', OG_DEFAULT_URL);
    setMetaContent('meta[property="og:image"]', OG_DEFAULT_IMAGE);
    setMetaContent('meta[property="og:type"]', "website");
    setMetaContent('meta[name="twitter:title"]', OG_DEFAULT_TITLE);
    setMetaContent('meta[name="twitter:description"]', OG_DEFAULT_DESCRIPTION);
    setMetaContent('meta[name="twitter:image"]', OG_DEFAULT_IMAGE);
  }

  function updateOGMetaForEvent(ev) {
    if (!ev) { resetOGMetaToDefault(); return; }
    var eventId = ev.id || ev.event_id || ev.title || "";
    var slug = ogCardSlug(eventId);
    var imgUrl = slug ? (OG_SITE_ORIGIN + "/og/" + slug + ".svg") : OG_DEFAULT_IMAGE;
    var title = ev.title ? (ev.title + " — Culture Calendar") : OG_DEFAULT_TITLE;
    var one = (ev.one_liner_summary || ev.one_liner || "").trim();
    var flat = one || flattenText(ev.description) || OG_DEFAULT_DESCRIPTION;
    if (flat.length > 280) flat = flat.slice(0, 277) + "…";
    var hashId = ev.id || ev.event_id || "";
    var pageUrl = hashId ? (OG_DEFAULT_URL + "#event=" + encodeURIComponent(hashId)) : OG_DEFAULT_URL;
    setMetaContent('meta[property="og:type"]', "article");
    setMetaContent('meta[property="og:title"]', title);
    setMetaContent('meta[property="og:description"]', flat);
    setMetaContent('meta[property="og:url"]', pageUrl);
    setMetaContent('meta[property="og:image"]', imgUrl);
    setMetaContent('meta[name="twitter:title"]', title);
    setMetaContent('meta[name="twitter:description"]', flat);
    setMetaContent('meta[name="twitter:image"]', imgUrl);
  }

  window.cultureCalendar = window.cultureCalendar || {};
  window.cultureCalendar.updateOGMetaForEvent = updateOGMetaForEvent;
  window.cultureCalendar.resetOGMetaToDefault = resetOGMetaToDefault;

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
      if (label || body) sections.push({ emoji: emoji, label: label, body: body });
    });
    var flat = sections.map(function (s) { return s.body; }).join("\n\n");
    return { rating: rating, sections: sections, flat: flat };
  }

  function formatDate(str) {
    var p = str.split("-");
    return MONTHS_SHORT[parseInt(p[1], 10) - 1] + " " + parseInt(p[2], 10);
  }

  function formatTime(t) {
    if (!t) return "";
    var m = t.match(/^(\d{1,2}):(\d{2})$/);
    if (!m) return t;
    var hh = parseInt(m[1], 10);
    var ampm = hh >= 12 ? "PM" : "AM";
    var h12 = hh % 12 === 0 ? 12 : hh % 12;
    return h12 + ":" + m[2] + " " + ampm;
  }

  function formatTimeShort(t) {
    if (!t) return "";
    var m = t.match(/^(\d{1,2}):(\d{2})$/);
    if (!m) return t;
    var hh = parseInt(m[1], 10);
    var ampm = hh >= 12 ? "pm" : "am";
    var h12 = hh % 12 === 0 ? 12 : hh % 12;
    var mm = m[2];
    return h12 + (mm === "00" ? "" : ":" + mm) + ampm;
  }

  function formatWhen(dateStr, timeStr) {
    if (!dateStr) return "";
    var p = dateStr.split("-");
    if (p.length !== 3) return dateStr + (timeStr ? " \u00b7 " + formatTimeShort(timeStr) : "");
    var y = parseInt(p[0], 10);
    var mo = parseInt(p[1], 10) - 1;
    var d = parseInt(p[2], 10);
    var dt = new Date(y, mo, d);
    var wd = isNaN(dt.getTime()) ? "" : WEEKDAY_SHORT[dt.getDay()];
    var datePart = (wd ? wd + ", " : "") + MONTHS_SHORT[mo] + " " + d;
    var timePart = formatTimeShort(timeStr);
    return timePart ? datePart + " \u00b7 " + timePart : datePart;
  }

  function getSearchQuery() {
    return (searchInput && searchInput.value || "").trim().toLowerCase();
  }

  function categoryLabel(type) {
    var key = (type || "").toLowerCase();
    return CATEGORY_LABELS[key] || key.replace(/_/g, " ");
  }

  function matchesQuery(ev, q) {
    if (!q) return true;
    var title = (ev.title || "").toLowerCase();
    var venue = (ev.venue || "").toLowerCase();
    var type = (ev.type || ev.event_category || "").toLowerCase();
    var label = categoryLabel(type).toLowerCase();
    return title.indexOf(q) !== -1
      || venue.indexOf(q) !== -1
      || type.indexOf(q) !== -1
      || label.indexOf(q) !== -1;
  }

  /* task-T3.2: My Picks filter state — when true, only events saved to
     localStorage.cc_taste.saves pass the filter. Search still composes
     on top, so users can narrow saved events further. */
  var myPicksOnly = false;

  function filterEvents(events) {
    var q = getSearchQuery();
    var filtered = events;
    if (q) filtered = filtered.filter(function (ev) { return matchesQuery(ev, q); });
    if (myPicksOnly) filtered = filtered.filter(function (ev) { return taste.isSaved(ev); });
    return filtered;
  }

  function renderAll() {
    cardIndex = {};
    var filtered = filterEvents(allEvents);
    var grouped = groupEvents(filtered);
    var needsResearch = [];
    var merit = [];
    grouped.forEach(function (ev) {
      if (ev.review_confidence === "low") needsResearch.push(ev);
      else merit.push(ev);
    });
    var now = new Date();
    now.setHours(0, 0, 0, 0);
    var cap = new Date(now);
    cap.setDate(cap.getDate() + 7);
    var thisWeek = merit.filter(function (ev) {
      if (!ev.showings || !ev.showings[0]) return false;
      var p = ev.showings[0].date.split("-");
      var d = new Date(parseInt(p[0], 10), parseInt(p[1], 10) - 1, parseInt(p[2], 10));
      return d >= now && d < cap;
    });
    renderPicks(rerankByTaste(thisWeek, merit).slice(0, 10));
    renderListings(merit);
    renderNeedsResearch(needsResearch);
  }

  /* task-T3.3: Taste-based re-rank of top picks.
     Pure function. Scans every grouped event for thumbs (+1 / -1) and
     saves (+1) signals, aggregates them into per-category and per-venue
     bias, then adds a ±2-point boost to each pick's AI rating and sorts
     by the adjusted score. Input arrays are not mutated. A taste-empty
     state produces the same order as the AI rating alone.
     task-T3.4: returns scored {ev, score, reason} items. `reason` is the
     title of the strongest positive signal (thumbs-up or save) that
     promoted this pick, used by buildPickCard to render the
     "Because you liked X" annotation. */
  function rerankByTaste(picks, events) {
    if (!picks || picks.length === 0) return [];
    var thumbs = taste.getAllThumbs();
    var savedList = taste.savedEvents();
    var savedSet = {};
    savedList.forEach(function (s) { savedSet[s] = true; });

    var catBias = {};
    var venBias = {};
    // task-T3.4: per-bucket "leader" — the highest-weighted positively-
    // signaled event title for each category and venue. Alphabetical
    // tiebreak keeps selection deterministic across renders.
    var catLeader = {};
    var venLeader = {};
    var anySignal = false;

    (events || []).forEach(function (ev) {
      var slug = taste.eventSlug(ev);
      if (!slug) return;
      var w = 0;
      if (thumbs[slug] === 1 || thumbs[slug] === -1) w += thumbs[slug];
      if (savedSet[slug]) w += 1;
      if (!w) return;
      anySignal = true;
      var cat = (ev.type || ev.event_category || "other").toLowerCase();
      var ven = (ev.venue || "").toLowerCase();
      catBias[cat] = (catBias[cat] || 0) + w;
      if (ven) venBias[ven] = (venBias[ven] || 0) + w;
      if (w > 0) {
        var title = ev.title || "";
        if (title) {
          var ca = catLeader[cat];
          if (!ca || w > ca.weight || (w === ca.weight && title < ca.title)) {
            catLeader[cat] = { title: title, weight: w };
          }
          if (ven) {
            var va = venLeader[ven];
            if (!va || w > va.weight || (w === va.weight && title < va.title)) {
              venLeader[ven] = { title: title, weight: w };
            }
          }
        }
      }
    });

    var scored = picks.map(function (ev) {
      var boost = 0;
      var reason = null;
      if (anySignal) {
        var cat = (ev.type || "other").toLowerCase();
        var ven = (ev.venue || "").toLowerCase();
        var raw = (catBias[cat] || 0) + (ven ? (venBias[ven] || 0) : 0);
        // Halve the raw signal, clamp to ±2, so taste nudges rather
        // than dominates the editorial rating.
        boost = Math.max(-2, Math.min(2, raw * 0.5));
        if (boost > 0) {
          // Prefer venue match (more specific signal); fall back to
          // category match. Skip self-matches so we never say
          // "because you liked X" on X itself.
          var lead = null;
          if (ven && (venBias[ven] || 0) > 0
              && venLeader[ven] && venLeader[ven].title !== ev.title) {
            lead = venLeader[ven];
          }
          if (!lead && (catBias[cat] || 0) > 0
              && catLeader[cat] && catLeader[cat].title !== ev.title) {
            lead = catLeader[cat];
          }
          if (lead) reason = lead.title;
        }
      }
      return { ev: ev, score: (ev.rating || 0) + boost, reason: reason };
    });
    scored.sort(function (a, b) {
      return b.score - a.score
        || (b.ev.rating || 0) - (a.ev.rating || 0)
        || (a.ev.title || "").localeCompare(b.ev.title || "");
    });
    return scored;
  }

  /* task-T2.4: Deep-link support for #event=<id>.
     registerCardForHash is called from both card builders; handleEventHash
     runs on initial render, on hashchange, and on DOMContentLoaded. */
  function registerCardForHash(card, ev, header, openClass) {
    var rawId = ev.id || ev.event_id || ev.title || "";
    var slug = ogCardSlug(rawId);
    if (!slug) return;
    card.dataset.eventId = slug;
    var expand = function () {
      if (!card.classList.contains(openClass)) header.click();
    };
    cardIndex[slug] = { card: card, expand: expand, event: ev };
  }

  function handleEventHash() {
    var h = (window.location && window.location.hash) || "";
    if (!h || h.indexOf(EVENT_HASH_PREFIX) !== 0) return;
    var raw = h.slice(EVENT_HASH_PREFIX.length);
    if (!raw) return;
    var decoded;
    try { decoded = decodeURIComponent(raw); }
    catch (e) { decoded = raw; }
    var slug = ogCardSlug(decoded);
    var entry = cardIndex[slug] || cardIndex[decoded] || cardIndex[raw];
    if (!entry) return;
    try { entry.card.scrollIntoView({ behavior: "smooth", block: "start" }); }
    catch (e) { entry.card.scrollIntoView(); }
    entry.expand();
    if (entry.event) updateOGMetaForEvent(entry.event);
  }

  window.addEventListener("hashchange", handleEventHash);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", handleEventHash);
  }

  /* task-T3.3: re-run rerankByTaste whenever taste signals change so
     the user sees their thumbs/saves reshape the top picks without a
     page reload. The initMyPicksToggle listener updates the My Picks
     count + conditional re-render; this one is unconditional. */
  document.addEventListener("cc:thumbs-changed", function () { renderAll(); });
  document.addEventListener("cc:saves-changed", function () { renderAll(); });

  /* task-T3.2: My Picks filter toggle.
     Injected into the masthead next to the search box. Clicking toggles
     myPicksOnly and re-renders. Count reflects the number of saved
     events; the button hides count when zero to avoid "(0)" noise.
     Listens to cc:saves-changed so unsaving while the filter is on
     refreshes the listing. */
  function initMyPicksToggle() {
    var container = document.querySelector(".search-wrap") || document.querySelector(".masthead-inner");
    if (!container || !container.parentNode) return;
    var wrap = document.createElement("div");
    wrap.className = "my-picks-toggle-wrap";
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "my-picks-toggle";
    btn.setAttribute("aria-pressed", "false");
    btn.setAttribute("aria-label", "Show only my saved picks");

    function updateLabel() {
      var count = taste.savedEvents().length;
      btn.textContent = count > 0
        ? "My Picks (" + count + ")"
        : "My Picks";
    }
    updateLabel();

    btn.addEventListener("click", function () {
      myPicksOnly = !myPicksOnly;
      btn.classList.toggle("is-active", myPicksOnly);
      btn.setAttribute("aria-pressed", myPicksOnly ? "true" : "false");
      renderAll();
    });
    document.addEventListener("cc:saves-changed", function () {
      updateLabel();
      if (myPicksOnly) renderAll();
    });

    wrap.appendChild(btn);
    container.parentNode.insertBefore(wrap, container.nextSibling);
  }

  function initSearch() {
    if (!searchInput || !searchSuggestions) return;
    searchInput.addEventListener("input", function () {
      if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
      searchDebounceTimer = setTimeout(applySearch, SEARCH_DEBOUNCE_MS);
    });
    searchInput.addEventListener("focus", function () {
      showSuggestions();
    });
    searchInput.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        searchInput.value = "";
        applySearch();
        hideSuggestions();
        searchInput.blur();
      }
    });
    searchSuggestions.addEventListener("mousedown", function (e) {
      var li = e.target && e.target.closest ? e.target.closest(".suggestion") : null;
      if (!li) return;
      e.preventDefault();
      var val = li.getAttribute("data-value") || "";
      searchInput.value = val;
      applySearch();
      hideSuggestions();
    });
    document.addEventListener("click", function (e) {
      if (!searchSuggestions || searchSuggestions.hidden) return;
      var t = e.target;
      if (t === searchInput || (searchSuggestions.contains && searchSuggestions.contains(t))) return;
      hideSuggestions();
    });
  }

  function applySearch() {
    renderSuggestions();
    renderAll();
  }

  function showSuggestions() {
    if (!searchSuggestions) return;
    searchSuggestions.hidden = false;
    if (searchInput) searchInput.setAttribute("aria-expanded", "true");
    renderSuggestions();
  }

  function hideSuggestions() {
    if (!searchSuggestions) return;
    searchSuggestions.hidden = true;
    if (searchInput) searchInput.setAttribute("aria-expanded", "false");
  }

  function collectSuggestions(q) {
    var venues = {};
    var titles = {};
    var cats = {};
    allEvents.forEach(function (ev) {
      var venue = ev.venue || "";
      var title = ev.title || "";
      var type = (ev.type || ev.event_category || "").toLowerCase();
      var label = categoryLabel(type);
      if (venue && venue.toLowerCase().indexOf(q) !== -1) venues[venue] = true;
      if (title && title.toLowerCase().indexOf(q) !== -1) titles[title] = true;
      if (label && label.toLowerCase().indexOf(q) !== -1) cats[label] = true;
    });
    return {
      venues: Object.keys(venues).sort(),
      titles: Object.keys(titles).sort(),
      categories: Object.keys(cats).sort()
    };
  }

  function renderSuggestions() {
    if (!searchSuggestions) return;
    var q = getSearchQuery();
    var grouped = collectSuggestions(q);
    searchSuggestions.innerHTML = "";
    var frag = document.createDocumentFragment();
    var total = appendSuggestionGroup(frag, "Venues", grouped.venues, "venue")
      + appendSuggestionGroup(frag, "Titles", grouped.titles, "title")
      + appendSuggestionGroup(frag, "Categories", grouped.categories, "category");
    if (total === 0) {
      var empty = document.createElement("li");
      empty.className = "suggestion-empty";
      empty.textContent = q ? "No matches for “" + searchInput.value.trim() + "”" : "No events yet";
      frag.appendChild(empty);
    }
    searchSuggestions.appendChild(frag);
  }

  function appendSuggestionGroup(frag, label, values, type) {
    if (!values || values.length === 0) return 0;
    var header = document.createElement("li");
    header.className = "suggestion-group";
    header.setAttribute("role", "presentation");
    header.textContent = label;
    frag.appendChild(header);
    var limited = values.slice(0, MAX_SUGGESTIONS_PER_GROUP);
    limited.forEach(function (value) {
      var li = document.createElement("li");
      li.className = "suggestion";
      li.setAttribute("role", "option");
      li.setAttribute("data-type", type);
      li.setAttribute("data-value", value);
      var span = document.createElement("span");
      span.className = "suggestion-label";
      span.textContent = value;
      li.appendChild(span);
      frag.appendChild(li);
    });
    return limited.length;
  }

  /* task-T4.2: Cache of the latest rendered picks so the
     audio-brief button can speak them without re-running the
     filter/rerank pipeline on click. */
  var lastRenderedPicks = [];

  function renderPicks(picks) {
    picksList.innerHTML = "";
    picksList.classList.add("top-picks");
    lastRenderedPicks = (picks || []).map(function (item) {
      return item && item.ev ? item.ev : item;
    });
    if (picks.length === 0) {
      var empty = document.createElement("li");
      empty.className = "empty-state";
      empty.textContent = "No picks match your filters.";
      picksList.appendChild(empty);
      return;
    }
    var frag = document.createDocumentFragment();
    picks.forEach(function (item) {
      // task-T3.4: rerankByTaste yields {ev, score, reason}; tolerate a
      // raw event for forward compatibility with callers that bypass it.
      var ev = item && item.ev ? item.ev : item;
      var reason = item && item.reason ? item.reason : null;
      frag.appendChild(buildPickCard(ev, reason));
    });
    picksList.appendChild(frag);
  }

  /* task-T4.2: 5-minute audio brief button.
     Concatenates the title + venue + one-liner of the top five rendered
     picks into a single spoken brief, played via window.speechSynthesis
     using the shared TTS module. The button lives in the picks-section
     header so it is visible without expanding any individual card.
     Hidden when speech synthesis is unsupported (older browsers). */
  function buildWeekBriefText(picks) {
    if (!picks || !picks.length) return "";
    var top = picks.slice(0, 5);
    var intro = "Top picks of the week. " + top.length
      + (top.length === 1 ? " event ahead." : " events ahead.");
    var parts = [intro];
    top.forEach(function (ev, i) {
      var bits = ["Pick " + (i + 1) + ": " + (ev.title || "Untitled")];
      if (ev.venue) bits.push("at " + ev.venue);
      var head = bits.join(" ") + ".";
      var one = ev.one_liner || ev.one_liner_summary || "";
      parts.push(one ? head + " " + String(one).trim() : head);
    });
    return parts.join(" ").replace(/\s+/g, " ").trim();
  }

  function initAudioBrief() {
    if (!tts.supported) return;
    var section = document.getElementById("picks");
    if (!section) return;
    var heading = section.querySelector(".picks-heading");
    if (!heading) return;
    if (section.querySelector(".audio-brief-button")) return;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "audio-brief-button tts-button";
    btn.textContent = "\u25B6 Play brief";
    btn.setAttribute("aria-label", "Play audio brief of the top picks");
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var text = buildWeekBriefText(lastRenderedPicks);
      if (!text) return;
      window.plausible("cc_play_brief");
      tts.speak(btn, text);
    });
    heading.insertAdjacentElement("afterend", btn);
  }
  initAudioBrief();

  /* task-T4.3: Email-this-digest mailto CTA.
     Adds an <a href="mailto:…"> next to the audio-brief button that opens
     the user's default mail app pre-populated with the URL of the current
     ISO-week digest at docs/weekly/<YYYY-Www>.html (the page emitted by
     scripts/build_weekly_digest.py on each deploy). No analytics, no
     backend — Web-native share via the mailto: URI scheme. */
  function currentIsoWeekTag(now) {
    var d = now || new Date();
    var utc = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    var day = utc.getUTCDay() || 7;
    utc.setUTCDate(utc.getUTCDate() + 4 - day);
    var yearStart = new Date(Date.UTC(utc.getUTCFullYear(), 0, 1));
    var week = Math.ceil((((utc - yearStart) / 86400000) + 1) / 7);
    var ww = week < 10 ? "0" + week : String(week);
    return utc.getUTCFullYear() + "-W" + ww;
  }

  /* task-T1.1: email-digest button routes through the same share module
     as per-event share buttons. The class `email-digest-button` is kept
     for CSS continuity and feature-inventory continuity. */
  function initEmailDigest() {
    var section = document.getElementById("picks");
    if (!section) return;
    var heading = section.querySelector(".picks-heading");
    if (!heading) return;
    if (section.querySelector(".email-digest-button")) return;
    var tag = currentIsoWeekTag();
    var digestUrl =
      "https://hadrien-cornier.github.io/Culture-Calendar/weekly/" + tag + ".html";
    var btn = share.createDigestButton(tag, digestUrl);
    heading.insertAdjacentElement("afterend", btn);
  }
  initEmailDigest();

  function buildPickCard(ev, reason) {
    var card = document.createElement("li");
    card.className = "event-card pick-card";
    if (ev.showings && ev.showings[0]) {
      card.dataset.firstDate = ev.showings[0].date;
    }

    var header = document.createElement("div");
    header.className = "event-header";

    var badge = document.createElement("span");
    badge.className = "event-rating-badge rating-" + ratingClass(ev.rating);
    badge.textContent = ev.rating > 0 ? ev.rating + " / 10" : "—";
    badge.setAttribute("aria-label", "rated " + ev.rating + " out of 10");
    header.appendChild(badge);

    var col = document.createElement("div");
    col.className = "event-title-col";
    var title = document.createElement("div");
    title.className = "event-title-text";
    if (ev.url) {
      var a = document.createElement("a");
      a.href = ev.url; a.target = "_blank"; a.rel = "noopener";
      a.className = "event-title-link";
      a.textContent = ev.title;
      a.addEventListener("click", function (e) { e.stopPropagation(); });
      title.appendChild(a);
    } else { title.textContent = ev.title; }
    col.appendChild(title);

    var sub = document.createElement("div");
    sub.className = "event-subtitle";
    var next = ev.showings && ev.showings[0];
    var sp = [CATEGORY_LABELS[ev.type] || (ev.type || "").replace(/_/g, " ")];
    var venueLabel = ev.venue_display_name || ev.venue;
    if (venueLabel) sp.unshift(venueLabel);
    if (next) sp.push(formatDate(next.date) + (next.time ? " · " + formatTime(next.time) : ""));
    sub.textContent = sp.join(" · ");
    col.appendChild(sub);

    /* task-T3.1: surface the venue's street address on a secondary line
       so logistics-focused users can see where to go without expanding. */
    if (ev.venue_address) {
      var addr = document.createElement("div");
      addr.className = "event-venue-address";
      addr.textContent = ev.venue_address;
      col.appendChild(addr);
    }

    /* task-T3.4: surface the strongest positive taste signal that
       promoted this pick. Rendered as a one-liner under the subtitle
       so it is visible without expanding the card. */
    if (reason) {
      var bec = document.createElement("div");
      bec.className = "because-you-liked";
      bec.textContent = "Because you liked " + reason;
      bec.setAttribute("aria-label", "Because you liked " + reason);
      col.appendChild(bec);
    }

    header.appendChild(col);

    var arrow = document.createElement("span");
    arrow.className = "expand-indicator";
    arrow.textContent = "▶";
    arrow.setAttribute("aria-hidden", "true");
    header.appendChild(arrow);
    card.appendChild(header);

    var panel = document.createElement("div");
    panel.className = "event-panel";
    if (ev.one_liner) {
      var ol = document.createElement("p");
      ol.className = "event-oneliner";
      ol.textContent = ev.one_liner;
      panel.appendChild(ol);
    }
    var parsed = parseReview(ev.description);
    if (parsed.sections.length > 0) {
      var reviewWrap = document.createElement("div");
      reviewWrap.className = "event-review";
      parsed.sections.forEach(function (sec, idx) {
        var sectionEl = document.createElement("section");
        sectionEl.className = idx === 0
          ? "event-review-section event-review-first"
          : "event-review-section";
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
          h.appendChild(document.createTextNode(sec.label));
          sectionEl.appendChild(h);
        }
        var bodyP = document.createElement("p");
        bodyP.className = "event-review-body";
        bodyP.textContent = sec.body;
        sectionEl.appendChild(bodyP);
        reviewWrap.appendChild(sectionEl);
      });
      panel.appendChild(reviewWrap);
    } else if (ev.description) {
      var flat = ev.description.replace(/<[^>]*>/g, "");
      if (flat && flat !== ev.one_liner) {
        var p = document.createElement("p");
        p.className = "event-review-body";
        p.textContent = flat;
        panel.appendChild(p);
      }
    }
    var pickCrossLinks = buildCrossLinks(ev);
    if (pickCrossLinks) panel.appendChild(pickCrossLinks);
    var pickActions = document.createElement("div");
    pickActions.className = "event-actions";
    var pickThumbs = taste.createControls(ev);
    if (pickThumbs) pickActions.appendChild(pickThumbs);
    var ttsSlot = document.createElement("div");
    ttsSlot.className = "event-tts-slot";
    var pickTtsBtn = tts.createButton(ev);
    if (pickTtsBtn) ttsSlot.appendChild(pickTtsBtn);
    pickActions.appendChild(ttsSlot);
    var pickShareWrap = document.createElement("div");
    pickShareWrap.className = "event-share-slot";
    pickShareWrap.appendChild(share.createButton(ev));
    pickActions.appendChild(pickShareWrap);
    panel.appendChild(pickActions);
    card.appendChild(panel);

    header.setAttribute("role", "button");
    header.setAttribute("tabindex", "0");
    header.setAttribute("aria-expanded", "false");
    header.addEventListener("click", function () {
      var open = card.classList.toggle("is-open");
      header.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) injectEventJsonLd(card, ev);
    });
    header.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); header.click(); }
      if (e.key === "Escape" && card.classList.contains("is-open")) {
        card.classList.remove("is-open");
        header.setAttribute("aria-expanded", "false");
      }
    });
    registerCardForHash(card, ev, header, "is-open");
    return card;
  }

  function buildListingCard(ev) {
    var card = document.createElement("article");
    card.className = "event-card";
    var header = document.createElement("div");
    header.className = "event-header";
    var badge = document.createElement("span");
    badge.className = "event-rating-badge rating-" + ratingClass(ev.rating);
    badge.textContent = ev.rating > 0 ? ev.rating + " / 10" : "—";
    badge.setAttribute("aria-label", "rated " + ev.rating + " out of 10");
    header.appendChild(badge);

    var col = document.createElement("div");
    col.className = "event-title-col";
    var title = document.createElement("div");
    title.className = "event-title-text";
    if (ev.url) {
      var a = document.createElement("a");
      a.href = ev.url; a.target = "_blank"; a.rel = "noopener";
      a.className = "event-title-link";
      a.textContent = ev.title;
      a.addEventListener("click", function (e) { e.stopPropagation(); });
      title.appendChild(a);
    } else { title.textContent = ev.title; }
    col.appendChild(title);

    var sub = document.createElement("div");
    sub.className = "event-subtitle";
    var sp = [];
    var venueLabel = ev.venue_display_name || ev.venue;
    if (venueLabel) sp.push(venueLabel);
    sp.push(CATEGORY_LABELS[ev.type] || ev.type.replace(/_/g, " "));
    sub.textContent = sp.join(" · ");
    col.appendChild(sub);

    /* task-T3.1: street address rendered below the subtitle so the
       full venue location is visible on the card face without needing
       to expand the review panel. */
    if (ev.venue_address) {
      var addr = document.createElement("div");
      addr.className = "event-venue-address";
      addr.textContent = ev.venue_address;
      col.appendChild(addr);
    }

    var firstShowing = ev.showings && ev.showings[0];
    var whenText = firstShowing ? formatWhen(firstShowing.date, firstShowing.time) : "";
    var when = document.createElement("div");
    when.className = "event-when";
    when.textContent = whenText || "Date TBA";
    col.appendChild(when);

    header.appendChild(col);

    var arrow = document.createElement("span");
    arrow.className = "expand-indicator";
    arrow.textContent = "▶";
    arrow.setAttribute("aria-hidden", "true");
    header.appendChild(arrow);
    card.appendChild(header);

    var panel = document.createElement("div");
    panel.className = "event-panel";
    if (ev.one_liner) {
      var ol = document.createElement("p");
      ol.className = "event-oneliner";
      ol.textContent = ev.one_liner;
      panel.appendChild(ol);
    }
    var parsed = parseReview(ev.description);
    if (parsed.sections.length > 0) {
      var reviewWrap = document.createElement("div");
      reviewWrap.className = "event-review";
      parsed.sections.forEach(function (sec, idx) {
        var sectionEl = document.createElement("section");
        sectionEl.className = idx === 0
          ? "event-review-section event-review-first"
          : "event-review-section";
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
          h.appendChild(document.createTextNode(sec.label));
          sectionEl.appendChild(h);
        }
        var bodyP = document.createElement("p");
        bodyP.className = "event-review-body";
        bodyP.textContent = sec.body;
        sectionEl.appendChild(bodyP);
        reviewWrap.appendChild(sectionEl);
      });
      panel.appendChild(reviewWrap);
    } else if (ev.description) {
      var flat = ev.description.replace(/<[^>]*>/g, "");
      if (flat && flat !== ev.one_liner) {
        var p = document.createElement("p");
        p.className = "event-review-body";
        p.textContent = flat;
        panel.appendChild(p);
      }
    }
    var listingCrossLinks = buildCrossLinks(ev);
    if (listingCrossLinks) panel.appendChild(listingCrossLinks);
    var listingActions = document.createElement("div");
    listingActions.className = "event-actions";
    var listingThumbs = taste.createControls(ev);
    if (listingThumbs) listingActions.appendChild(listingThumbs);
    var listingTtsBtn = tts.createButton(ev);
    if (listingTtsBtn) {
      var listingTtsSlot = document.createElement("div");
      listingTtsSlot.className = "event-tts-slot";
      listingTtsSlot.appendChild(listingTtsBtn);
      listingActions.appendChild(listingTtsSlot);
    }
    var listingShareWrap = document.createElement("div");
    listingShareWrap.className = "event-share-slot";
    listingShareWrap.appendChild(share.createButton(ev));
    listingActions.appendChild(listingShareWrap);
    if (listingActions.childNodes.length > 0) panel.appendChild(listingActions);
    if (panel.childNodes.length > 0) card.appendChild(panel);

    header.setAttribute("role", "button");
    header.setAttribute("tabindex", "0");
    header.setAttribute("aria-expanded", "false");
    header.addEventListener("click", function () {
      var exp = card.classList.toggle("is-expanded");
      header.setAttribute("aria-expanded", exp ? "true" : "false");
      if (exp) injectEventJsonLd(card, ev);
    });
    header.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); header.click(); }
      if (e.key === "Escape" && card.classList.contains("is-expanded")) {
        card.classList.remove("is-expanded");
        header.setAttribute("aria-expanded", "false");
      }
    });
    registerCardForHash(card, ev, header, "is-expanded");
    return card;
  }

  function renderListings(events) {
    listingsEl.innerHTML = "<h2 class=\"listings-heading\">COMPLETE EVENTS — BY MERIT</h2>";
    if (events.length === 0) {
      var empty = document.createElement("p");
      empty.className = "empty-state";
      empty.textContent = "No events match your filters. Try widening them.";
      listingsEl.appendChild(empty);
      return;
    }
    var frag = document.createDocumentFragment();
    events.forEach(function (ev) { frag.appendChild(buildListingCard(ev)); });
    listingsEl.appendChild(frag);
  }

  function renderNeedsResearch(events) {
    var host = document.getElementById("needs-research");
    if (!host) return;
    host.innerHTML = "";
    var details = document.createElement("details");
    details.className = "needs-research-section";
    var summary = document.createElement("summary");
    summary.className = "needs-research-summary";
    summary.textContent = "Pending more research — light evidence available (" + events.length + " events)";
    details.appendChild(summary);
    var body = document.createElement("div");
    body.className = "needs-research-body";
    if (events.length === 0) {
      var note = document.createElement("p");
      note.className = "needs-research-empty";
      note.textContent = "No low-confidence reviews in this filter.";
      body.appendChild(note);
    } else {
      var frag = document.createDocumentFragment();
      events.forEach(function (ev) { frag.appendChild(buildListingCard(ev)); });
      body.appendChild(frag);
    }
    details.appendChild(body);
    host.appendChild(details);
  }
})();
