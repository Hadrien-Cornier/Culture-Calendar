# 🗓️ Culture Calendar Redesign — Full UI & UX Product Requirements

This document supersedes the earlier product requirements now archived in `PRODUCT_REQUIREMENTS_ARCHIVE.md`. It provides a comprehensive overview of the redesign, complete with UX guidance, technical implementation details, and a markdown wireframe.

## tl;dr

This document outlines a comprehensive UI/UX redesign for the Culture Calendar web experience. The goal is to create an elegant, timeless, and high-utility interface that prioritizes “What’s happening today?” while allowing rich cultural discovery across film, music, and literature events in Austin.

We will redesign both the **list view** and the **calendar view**, integrate **ET Book typography**, hide or simplify secondary filters, and restructure information architecture around clarity, elegance, and decision-making.

---

## 🎯 Goals

### Business Goals

- Increase .ics calendar downloads and event clickthroughs
- Establish the site as a high-trust, design-forward source for culture
- Improve mobile usability and desktop information density

### User Goals

- See what’s on *today* without clicking or scrolling
- Understand what an event is about at a glance
- Read longer reviews if interested — not by default
- Access filters only if needed, without distraction

### Non-Goals

- No login, personalization, social, or ticketing features
- No recommendation engine logic changes in this scope
- No real-time interactivity (static site remains GitHub Pages-compatible)

---

## 👤 User Stories

- “As someone planning tonight, I want to immediately see the best events today with a summary I can scan quickly.”
- “As a curious cultural fan, I want to read rich reviews if I choose, but not be bombarded by them.”
- “As someone on my phone, I want everything to be readable and not cluttered with options.”
- “As a design lover, I want the site to feel like an elegant literary calendar — not a modern tech dashboard.”

---

## 🧑‍🎨 Design Language & Visual Aesthetic

- Primary typeface: **ET Book** (self-hosted `.woff2` or via CDN)
- Serif-only typography for all elements
- Use **italics, small caps, and spacing** instead of bolding or color
- Very limited use of icons or emoji — for signal only, not decoration
- Layout should evoke **a printed cultural calendar or fine arts publication**

---

## ✨ Features & Experience

### ✅ 1. Landing Experience

- Immediately show **Today’s Events** list
- Hide filters by default
- Subtle tab-switching element to toggle views:

```plaintext
[ Today ] [ This Weekend ] [ This Week ] [ Calendar ]
```

---

### ✅ 2. List View (Default View)
- For each event, display:
  - 🎬 Title
  - 🕘 Time & Venue
  - ★ Rating (text-based: “★★★★☆ Recommended”)
  - 🧠 One-line vibe summary (e.g. “Bleak UK road film about obsession and loneliness”)
  - 📚 Subtext/Tags (e.g. “Psychological · Female-led · 1990s · 88 min”)
  - [ Read Review ▼ ] button (reveals full AI review inline)
  - Use generous spacing between events to maintain readability

---

### ✅ 3. Review Interaction
- Full AI reviews are hidden by default
- On click, [ Read Review ▼ ] opens either:
  - An inline accordion or
  - A light modal overlay
- Review collapses with [ Collapse ▲ ] or outside click

---

### ✅ 4. Calendar View
- Monthly grid: full-width, responsive 7-column layout
- Each cell can contain multiple “event pills” (short entries with time + title)
- On hover (desktop) or tap (mobile), show preview tooltip with vibe summary + tag line
- Clicking a day opens full summary list below the calendar
- No three-letter truncation

---

### ✅ 5. Filters & Controls
- Filters are collapsed by default
- Accessed via a simple toggle:

```
[ Show Filters ▸ ]
```

- When expanded, show:

```
▾ Filters:
──────────────
✔️  Venue Filter: Checkbox group for 7 cultural venues  
✔️  Category Filter: Film · Music · Literature  
✔️  Rating Threshold: User-defined numerical input (1–10)  
    — Not "7+" or "9+" presets  
✔️  Country or Language: Optional tag input field  
```

- No time-based filtering needed (work-hour events already auto-excluded)

---

## 🧱 Wireframe Layout (Markdown/Figma Style)

```
HEADER

┌────────────────────────────────────────────────────────────┐
│                🎭 CULTURE CALENDAR (ET Book)               │
│             ⬤ Film ⬤ Music ⬤ Books — All Events            │
├────────────────────────────────────────────────────────────┤
│ [ Today ] [ This Weekend ] [ This Week ] [ Calendar View ] │
└────────────────────────────────────────────────────────────┘

LIST VIEW

📅 TODAY — June 21
────────────────────────────────────────────────────────────

🎬 BUTTERFLY KISS
9:00 PM — AFS  
★★★★☆ RECOMMENDED  
Bleak UK road film about obsession and loneliness  
(Psychological · Female-led · 1990s · 88 min)  
[ Read Review ▼ ]

────────────────────────────────────────────────────────────

🎻 LA FOLLIA: BAROQUE LEGENDS
7:30 PM — La Follia Austin  
★★★★★ MUST-SEE  
Candlelit Vivaldi & Corelli performed live  
(Baroque · Chamber Music · Local Virtuosos · 90 min)  
[ Read Review ▼ ]

────────────────────────────────────────────────────────────

📚 BOOK CLUB — "Solaris"  
6:30 PM — Alienated Majesty Books  
★★★★☆ RECOMMENDED  
Sci-fi discussion on identity and consciousness  
(Lem · Sci-Fi · Existential · 1972 · Russian)  
[ Read Review ▼ ]

REVIEW EXPANSION

[ Read Review ▼ ] → expands to:

⭐ Full AI Review — Butterfly Kiss

Michael Winterbottom’s 1995 cult road film delivers a brutal, poetic narrative of obsession and trauma. Inspired by New German Cinema and British realism, the film follows Eunice and Miriam through bleak industrial towns, exploring intimacy, violence, and female alienation...

[ Collapse ▲ ]

CALENDAR VIEW

📅 JUNE 2025
────────────────────────────────────────────────────────────

[Mon] [Tue] [Wed] [Thu] [Fri] [Sat] [Sun]
────────────────────────────────────────────
  1      2      3      4      5      6      7
                      🎬 Film @ AFS
                             📚 Book Club

  8      9     10     11     12     13     14
                      🎻 La Follia
                      🎬 Hyperreal Screening

 15     16     17     18     19     20     21
              🎬 Butterfly Kiss
                             📚 Solaris

 → Click any day to reveal:

────────────────────────────────────────────

📅 June 21
🎬 BUTTERFLY KISS — 9:00 PM — AFS  
(Psychological · UK · Female Antihero)

🎻 LA FOLLIA — 7:30 PM — Chamber Music  
(Vivaldi · Baroque · Intimate)

📚 BOOK CLUB: Solaris — 6:30 PM  
(Sci-fi · Consciousness · Lem)
```

---

## ✅ Success Metrics
- +30% increase in .ics downloads
- 40%+ users expand a review at least once
- Time on site > 2:00 avg
- Bounce rate < 30% mobile

---

## 🛠️ Technical Implementation

### Fonts
- ET Book loaded via .woff2 or CDN
- Fallback: Garamond, Georgia

### CSS/JS
- Use CSS Grid for calendar layout
- Use JS (or Alpine.js or minimal React) for:
  - Toggling reviews
  - Switching view modes
  - Expanding calendar details
- Avoid any build toolchains that prevent GitHub Pages deployment

### Data
- Events still pulled via Python scraper
- Event metadata includes:
  - Title, time, venue, rating (1–10), one-liner summary, tag list, full review

---

## 📅 Milestones

**Week 1**
- Set up ET Book + base typography styles
- Build new list view with expandable reviews

**Week 2**
- Overhaul calendar layout + event pill display
- Implement calendar interaction model (hover/tap, click to expand)

**Week 3**
- Implement filter toggle logic + styling
- QA full responsive behavior
- Connect to live data source + deploy

---

## 📖 Narrative

The Culture Calendar isn’t just a listings site — it’s a cultural artifact in itself. By pairing thoughtful curation with elegant presentation, this redesign creates a space that feels more like a print magazine than a tech platform. It’s for people who value story, clarity, and beautiful information. With this redesign, Culture Calendar becomes not just useful, but essential.

