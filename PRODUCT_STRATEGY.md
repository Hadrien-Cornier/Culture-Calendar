# Austin Culture Calendar — Product Strategy

*A G-stack brief — JTBD, 7 Powers, Obviously Awesome, North Star Metric.*
*Applied to the actual product as it exists today: 222 enriched events across 12 Austin venues, AI-generated criticism, average rating 4.6/10 (i.e., the critic is willing to say "no").*

---

## What this product actually is (and isn't)

This is **not** a calendar app. Calendars are commodity infrastructure (Google Calendar, Eventbrite, every venue's own site).

This is **a critic's tipsheet** — an opinionated, AI-powered weekly briefing that tells a discerning Austin resident which films, concerts, operas, and book clubs are worth their Tuesday night. The closest analogues are *The New Yorker*'s "Goings On About Town," *4 Columns*, *The L Magazine* in its prime — short, pointed, voiced curation that respects the reader's time.

The defining artifact is the **rating distribution**: 5 events at 9+, 34 at 7–8, 183 below 7. A product that calls 82% of events mediocre or worse is not optimizing for engagement — it is optimizing for *trust*. That is the entire point.

---

## 1. Jobs to Be Done (Christensen)

**Functional job:** *"When I have a free evening this week, help me decide what's worth leaving the house for, without spending 45 minutes cross-referencing eight venue websites."*

**Emotional job:** *"Help me feel like a culturally literate Austinite who knows what's happening — and avoid the regret of finding out about a great concert the day after it happened."*

**Social job:** *"Give me something interesting to text to a friend on a Tuesday morning."*

**Hire / fire competition:**
- **Hired over:** Do512, Austin Chronicle listings, Eventbrite, scrolling Instagram, group texts.
- **Fired in favor of:** A trusted human friend who already curates this for you. Inertia (staying home).

The job is **decision support under information overload**, not event discovery. Discovery is solved. Curation is not.

---

## 2. 7 Powers (Helmer) — Where is the moat?

| Power | Present? | Notes |
|---|---|---|
| **Scale Economies** | Weak | Scraping/LLM costs are roughly linear per venue. |
| **Network Economies** | Absent today | No user-to-user value loop. *Latent option:* user reviews, "going" signals. |
| **Counter-Positioning** | **Strong** | Incumbents (Do512, Eventbrite, venue sites) cannot publish opinionated 4.6/10-average ratings — they depend on venue and advertiser goodwill. A non-commercial critic can. |
| **Switching Costs** | Weak | Free RSS-style product; users can leave. *Latent:* personal taste profile, saved events, ICS subscriptions. |
| **Branding** | **Building** | The voice ("French cinéaste," "distinguished criticism") *is* the product. Brand = trust = the moat. |
| **Cornered Resource** | **Building** | Proprietary editorial prompts + venue-specific scrapers + 222-event corpus of reasoned criticism. Replicating requires both LLM craft *and* hyperlocal scraping infrastructure. |
| **Process Power** | **Building** | The two-phase scrape→enrich pipeline with config-driven schemas is hard to replicate quickly, even with a capable team. |

**The real moat is the compound of three things:** (1) editorial *voice* that's recognizable and trusted, (2) sourcing *rigor* — we actually scrape every venue every week, and (3) the *willingness to say no* — most events are not great, and the product reflects that. Each by itself is weak. Together they are very hard to copy because they require simultaneously being technical *and* having taste *and* being willing to forgo monetization that would compromise the rating.

---

## 3. Obviously Awesome Positioning (April Dunford)

**Competitive alternatives:** Eventbrite, Do512, Austin Chronicle, individual venue newsletters, group texts with friends.

**Unique attributes:**
- AI-generated long-form criticism per event (not blurbs)
- Cross-venue aggregation in one place (rare in Austin)
- Numerical rating with a real distribution (not 4.7-stars-everywhere)
- Free, ad-free, no signup
- ICS export — owns your calendar, not your attention

**Value (what the attributes enable):** *Five minutes a week to know what's worth your time. Confidence that if it's rated 8+, it's actually good.*

**Best-fit customer:** The Austin transplant or returning local who cares about cultural depth — classical, art-house film, opera, literary readings — but doesn't have the time or local network to keep up. Ages 28–55, often single or partnered without kids in tow, education- and design-conscious.

**Market category:** *Curated cultural concierge for a single metro.* (Not "events platform." Not "calendar.") Closest spiritual category: city-specific critic publications. Adjacent: Substack-era newsletters with strong editorial voice.

**Onliness statement (Neumeier):** *The only AI-powered critical tipsheet for Austin's classical, art-house, and literary scenes that rates honestly enough to tell you when nothing is worth going to.*

---

## 4. North Star Metric (Hacking Growth)

**Candidate metrics considered:**
- DAU / MAU — wrong: this is a weekly-decision product, not a daily-engagement product.
- Events viewed — wrong: rewards browsing, punishes the curated-tipsheet model.
- ICS downloads — closer, but a one-time act.
- **Confirmed attendance from our recommendations** — best, but unmeasurable without instrumentation.

**Proposed North Star:** **Weekly Returning Readers Who Add ≥1 Event to Their Calendar (WRR-Add).**

Why: it captures the full job — they came back (trust), they read (engagement), they *acted* (the recommendation was good enough to claim a Saturday night). It cannot be gamed by lowering rating standards, because that erodes the trust loop on the next visit.

**Input metrics that drive WRR-Add:**
1. Editorial accuracy (do 8+ ratings hold up?)
2. Coverage completeness (did we miss the obvious can't-miss?)
3. Time-to-decision (under 5 minutes from open to add?)
4. Surprise rate (did we surface ≥1 event the reader didn't know about?)

---

## 5. Strategic tensions to navigate

- **Honesty vs. growth.** A 4.6 average rating is a trust asset and a virality liability. Resolution: keep the rating, make the *good* events more shareable.
- **Voice vs. scale.** AI-generated criticism in a strong voice is the moat. The moment it sounds generic, the moat evaporates. Editorial QA on the prompt is more important than venue count.
- **Free vs. defensible.** No paywall today is correct (trust-building phase). Long-term defensibility likely requires either reader-supported (Substack model) or a "for serious culture-goers" tier — never venue-paid placement, which would destroy the rating's credibility.
- **Austin-only vs. expansion.** The brand is hyperlocal. Premature expansion to a second city dilutes voice and forces process before it's ready. Earn the right to expand by becoming undisputed in Austin first.

---

## 6. Six-month bets

1. **Sharpen the voice.** Audit the bottom-rated and top-rated reviews — are they *interesting* to read, or just informative? The product wins on prose, not data.
2. **Instrument WRR-Add.** Even crude analytics on returning visitors and ICS downloads beats flying blind.
3. **One human-written editor's pick per week.** A single hand-curated note signals the rest of the criticism is held to a real standard.
4. **Defend the rating.** Publicly publish the rubric. Refuse all venue partnerships that would compromise it. The refusal is itself marketing.
