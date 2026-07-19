#!/usr/bin/env python3
"""Send the weekly tipsheet email to Buttondown subscribers.

Picks the top events for the target ISO week (default: NEXT week, since the
weekly workflow runs Saturday and the tipsheet covers the upcoming
Monday-Sunday), renders a self-contained HTML email (inline styles - email
clients strip external stylesheets, so ``../styles.css`` from the digest page
can't be reused), and sends it through the Buttondown v1 API.

**Setup (one time, manual)**

1. Create a Buttondown account and note the username. The site's signup
   form posts to ``https://buttondown.email/api/emails/embed-subscribe/<username>``
   (see ``distribution.buttondown_endpoint`` in ``config/master_config.yaml``).
2. Verify the sender address in Buttondown (Settings → Sending).
3. Add ``BUTTONDOWN_API_KEY`` (Buttondown → Settings → API) to the GitHub
   repo secrets; the weekly workflow picks it up automatically.

**Idempotency**

The subject line is deterministic per ISO week, and before sending the
script lists recent emails and skips if one with the same subject already
exists - rerunning the workflow (or running this script twice) never
double-sends.

**Behavior without configuration**

No ``BUTTONDOWN_API_KEY`` → prints a skip notice and exits 0, so CI stays
green while the account is being set up. Zero picks for the target week →
also a clean skip (nobody wants an empty newsletter).

**Buttondown body format**

The API's ``body`` field is Markdown, but raw HTML blocks pass through
untouched, which is the standard way to send fully-designed emails. If the
rendering ever looks off, switch ``render_email_html`` to emit Markdown.

CLI:

``python scripts/send_weekly_email.py``            send next week's tipsheet
``python scripts/send_weekly_email.py --week 2026-W31``
``python scripts/send_weekly_email.py --dry-run --out /tmp/email.html``
``python scripts/send_weekly_email.py --draft``    create draft, don't send
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Sequence

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _load_digest_module():
    """Import scripts/build_weekly_digest.py as a module (not a package).

    Registers the module in sys.modules before exec_module so @dataclass
    decoration works under Python 3.13 (see AGENTS.md pitfall note).
    """
    spec = importlib.util.spec_from_file_location(
        "build_weekly_digest", REPO_ROOT / "scripts" / "build_weekly_digest.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_weekly_digest"] = module
    spec.loader.exec_module(module)
    return module


digest = _load_digest_module()

BUTTONDOWN_API = "https://api.buttondown.email/v1"
SITE_URL = digest.SITE_URL  # https://hadrien-cornier.github.io/Culture-Calendar/


# ---------------------------------------------------------------------------
# Week targeting + subject
# ---------------------------------------------------------------------------


def target_week(today: Optional[date] = None) -> tuple[int, int]:
    """The ISO week starting after ``today``'s week (the upcoming Mon-Sun)."""
    today = today or datetime.now().date()
    year, week = digest.iso_week_from_date(today)
    monday, _ = digest.iso_week_range(year, week)
    return digest.iso_week_from_date(monday + timedelta(days=7))


def email_subject(monday: date, sunday: date) -> str:
    """Deterministic per ISO week - this is the idempotency key."""
    return f"Culture Calendar: top picks for {digest._format_range(monday, sunday)}"


# ---------------------------------------------------------------------------
# Email HTML rendering (self-contained, inline styles)
# ---------------------------------------------------------------------------
# Design: a skimmable weekly tipsheet with a clean, minimal aesthetic -
# white background, dark charcoal text, sans-serif throughout. Structure:
# one featured pick with a short review excerpt, then compact rows carrying
# only badge + title + meta + one-liner. Full-length reviews stay on the
# site; the email's job is a 30-second skim.

_SERIF = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
_SANS = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
_PAPER = "#ffffff"        # clean white
_INK = "#2d2d2d"          # dark charcoal
_MUTED = "#666666"        # medium gray
_ACCENT = "#2d2d2d"       # same as ink (monochrome)
_BADGE_SOFT_BG = "#e8e8e8"  # light gray for lower-rated picks
_HAIRLINE = "#e0e0e0"     # subtle gray

# How much fits in a skim: 1 featured + 9 compact rows, overflow linked out.
FEATURED_COUNT = 1
ROW_COUNT = 9


def _a(href: str, text: str, color: str = _ACCENT, bold: bool = False) -> str:
    weight = "font-weight:bold;" if bold else ""
    return (
        f'<a href="{digest._esc(href)}" style="color:{color};text-decoration:none;{weight}">'
        f"{digest._esc(text)}</a>"
    )


def _event_url(pick: "digest.DigestPick") -> str:
    return f"{SITE_URL}#event={digest._esc(pick.event_id)}" if pick.event_id else SITE_URL


def _badge(rating: Optional[int]) -> str:
    """Small square score chip - dark charcoal for 8+, light gray below."""
    if rating is None:
        return ""
    if rating >= 8:
        style = f"background:{_ACCENT};color:{_PAPER};"
    else:
        style = f"background:{_BADGE_SOFT_BG};color:{_INK};"
    return (
        f'<span style="{style}border-radius:3px;padding:1px 7px;font-size:12px;'
        f'font-family:{_SANS};font-weight:bold;">{rating}</span>'
    )


def _when_short(pick: "digest.DigestPick") -> str:
    """First in-week screening, '+N more' when there are several showings."""
    if not pick.in_week:
        return ""
    first = digest._format_when(pick.in_week[0])
    extra = len(pick.in_week) - 1
    return f"{first} · +{extra} more" if extra else first


def _excerpt(text: str, limit: int = 240) -> str:
    """Sentence-aware truncation for the featured pick's review excerpt."""
    plain = digest._strip_html(text or "").strip()
    if len(plain) <= limit:
        return plain
    cut = plain[:limit]
    for end in (". ", "! ", "? "):
        idx = cut.rfind(end)
        if idx >= limit // 2:
            return cut[: idx + 1]
    return cut.rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _render_featured(pick: "digest.DigestPick", digest_page: str) -> str:
    """The week's top-rated event: title, one-liner, and a short review
    excerpt - the only pick that gets any prose in the email."""
    meta = f"{pick.venue} · {pick.category_label}"
    when = _when_short(pick)
    if when:
        meta = f"{meta} · {when}"
    parts = [
        '<div style="padding:20px 0 16px;">',
        f'<div style="font-family:{_SANS};font-size:11px;letter-spacing:2px;color:{_ACCENT};font-weight:bold;">PICK OF THE WEEK</div>',
        f'<div style="font-family:{_SERIF};font-size:26px;font-weight:bold;line-height:1.2;margin:8px 0 4px;">'
        f"{_badge(pick.rating)} {_a(_event_url(pick), pick.title, color=_INK)}</div>",
        f'<div style="font-family:{_SANS};font-size:13px;color:{_MUTED};">{digest._esc(meta)}</div>',
    ]
    if pick.one_liner:
        parts.append(
            f'<div style="font-family:{_SERIF};font-style:italic;font-size:16px;line-height:1.45;margin:10px 0 0;">'
            f"{digest._esc(pick.one_liner)}</div>"
        )
    # Short excerpt from the first non-empty review section. Label is only
    # prepended when parse_review extracted one - otherwise the body already
    # carries it inline and we'd duplicate it.
    for section in pick.review.sections:
        excerpt = _excerpt(section.body)
        if not excerpt:
            continue
        heading = f"<strong>{digest._esc(section.label)}.</strong> " if section.label else ""
        parts.append(
            f'<div style="font-family:{_SANS};font-size:14px;line-height:1.55;margin:8px 0 0;">'
            f"{heading}{digest._esc(excerpt)}</div>"
        )
        break
    links = [_a(digest_page, "Full review →", bold=True)]
    if pick.url:
        links.append(_a(pick.url, "Venue page →"))
    parts.append(
        f'<div style="font-family:{_SANS};font-size:13px;margin-top:10px;">'
        + " &nbsp;·&nbsp; ".join(links)
        + "</div>"
    )
    parts.append("</div>")
    return "\n".join(parts)


def _render_row(pick: "digest.DigestPick") -> str:
    """Compact three-line row: badge + linked title, meta, one-liner."""
    meta_bits = [pick.venue, _when_short(pick), pick.category_label]
    meta = " · ".join(digest._esc(b) for b in meta_bits if b)
    parts = [
        f'<div style="border-top:1px solid {_HAIRLINE};padding:11px 0;">',
        f'<div style="font-family:{_SERIF};font-size:17px;font-weight:bold;line-height:1.3;">'
        f"{_badge(pick.rating)}&nbsp; {_a(_event_url(pick), pick.title, color=_INK)}</div>",
        f'<div style="font-family:{_SANS};font-size:12px;color:{_MUTED};margin-top:2px;">{meta}</div>',
    ]
    if pick.one_liner:
        parts.append(
            f'<div style="font-family:{_SANS};font-size:13px;line-height:1.4;margin-top:3px;">'
            f"{digest._esc(pick.one_liner)}</div>"
        )
    parts.append("</div>")
    return "\n".join(parts)


def render_email_html(
    picks: Sequence["digest.DigestPick"], monday: date, sunday: date, week_label: str
) -> str:
    """Standalone HTML email body: inline styles only, absolute URLs only."""
    range_label = digest._format_range(monday, sunday)
    digest_page = f"{SITE_URL}weekly/{week_label}.html"
    featured = list(picks[:FEATURED_COUNT])
    rows = list(picks[FEATURED_COUNT : FEATURED_COUNT + ROW_COUNT])
    overflow = len(picks) - len(featured) - len(rows)

    header = f"""<div style="font-family:{_SANS};border-bottom:1px solid {_INK};padding:14px 0 10px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
<td style="font-size:14px;letter-spacing:3px;font-weight:bold;color:{_INK};">CULTURE CALENDAR</td>
<td align="right" style="font-size:11px;letter-spacing:1px;color:{_MUTED};">{digest._esc(range_label.upper())}</td>
</tr></table>
</div>"""

    intro = f"""<div style="padding:18px 0 0;">
<div style="font-family:{_SERIF};font-size:29px;font-weight:bold;line-height:1.15;">What's worth it this week.</div>
<div style="font-family:{_SANS};font-size:14px;color:{_MUTED};margin-top:6px;">
{len(picks)} top-rated events across Austin. Skim below - {_a(digest_page, "full reviews live on the site")}.
</div>
</div>"""

    blocks = [header, intro]
    blocks.extend(_render_featured(p, digest_page) for p in featured)
    blocks.extend(_render_row(p) for p in rows)

    if overflow > 0:
        blocks.append(
            f'<div style="border-top:1px solid {_HAIRLINE};padding:13px 0;font-family:{_SANS};font-size:14px;">'
            f'{_a(digest_page, f"Plus {overflow} more rated picks in the full tipsheet →", bold=True)}</div>'
        )

    blocks.append(
        f"""<div style="border-top:1px solid {_INK};margin-top:4px;padding:12px 0;font-family:{_SANS};font-size:12px;color:{_MUTED};line-height:1.7;">
{_a(SITE_URL, "Full calendar")} · {_a(SITE_URL + "calendar.ics", "Add to your calendar")} · {_a(digest_page, "This week on the site")}<br/>
You're receiving this because you subscribed at {_a(SITE_URL, "Culture Calendar")}.
Ratings and reviews are AI-generated; double-check times with the venue.
</div>"""
    )

    inner = "\n".join(blocks)
    return (
        f'<div style="background:{_PAPER};padding:26px 14px;">'
        f'<div style="max-width:600px;margin:0 auto;color:{_INK};">{inner}</div></div>'
    )


# ---------------------------------------------------------------------------
# Buttondown API
# ---------------------------------------------------------------------------


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Token {api_key}", "Content-Type": "application/json"}


def _checked(resp: requests.Response) -> requests.Response:
    """raise_for_status, but log the response body first - Buttondown's 4xx
    bodies carry the actual validation message, which is otherwise lost."""
    if not resp.ok:
        print(f"Buttondown {resp.status_code} {resp.request.method} {resp.url}:")
        print(resp.text[:2000])
    resp.raise_for_status()
    return resp


def _first_newsletter(api_key: str) -> dict:
    resp = _checked(
        requests.get(f"{BUTTONDOWN_API}/newsletters", headers=_headers(api_key), timeout=30)
    )
    payload = resp.json()
    results = payload.get("results", payload if isinstance(payload, list) else [])
    return results[0] if results else {}


def newsletter_slug(api_key: str) -> str:
    """The account's first newsletter slug/username, for keeping
    distribution.buttondown_endpoint in sync with the actual account."""
    nl = _first_newsletter(api_key)
    return str(nl.get("slug") or nl.get("username") or nl.get("name") or "")


def newsletter_id(api_key: str) -> str:
    return str(_first_newsletter(api_key).get("id") or "")


def inspect_newsletter(api_key: str) -> dict:
    """Dump the newsletter object (settings, template fields) for diagnosis."""
    return _first_newsletter(api_key)


def patch_newsletter(api_key: str, fields: dict) -> dict:
    """PATCH newsletter settings (e.g. template changes)."""
    nl_id = newsletter_id(api_key)
    resp = _checked(
        requests.patch(
            f"{BUTTONDOWN_API}/newsletters/{nl_id}",
            headers=_headers(api_key),
            json=fields,
            timeout=30,
        )
    )
    return resp.json()


def _redact_secrets(obj):
    """Strip credential-shaped fields from API payloads before printing.

    The newsletter object embeds the account's api_key in plaintext (learned
    the hard way: an --inspect dump put it into public CI logs). Any field
    whose name contains key/token/secret is masked, recursively.
    """
    if isinstance(obj, dict):
        return {
            k: ("***" if any(t in k.lower() for t in ("key", "token", "secret")) else _redact_secrets(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_secrets(v) for v in obj]
    return obj


def active_subscriber_count(api_key: str) -> int:
    """Number of subscribers who would actually receive a send."""
    resp = _checked(requests.get(f"{BUTTONDOWN_API}/subscribers", headers=_headers(api_key), timeout=30))
    payload = resp.json()
    results = payload.get("results", payload if isinstance(payload, list) else [])
    return sum(1 for s in results if s.get("type") in (None, "regular", "activated"))


def subscribe_email(api_key: str, email: str) -> None:
    """Add an address to the list (idempotent - 'already exists' is fine)."""
    resp = requests.post(
        f"{BUTTONDOWN_API}/subscribers",
        headers=_headers(api_key),
        json={"email_address": email, "type": "regular"},
        timeout=30,
    )
    if resp.ok:
        print(f"Subscribed {email}.")
        return
    if resp.status_code in (400, 409) and "already" in resp.text.lower():
        print(f"{email} is already subscribed.")
        return
    _checked(resp)


def already_sent(api_key: str, subject: str, max_pages: int = 5) -> bool:
    """True if an email with this exact subject already exists."""
    url = f"{BUTTONDOWN_API}/emails"
    for _ in range(max_pages):
        resp = _checked(requests.get(url, headers=_headers(api_key), timeout=30))
        payload = resp.json()
        results = payload.get("results", payload if isinstance(payload, list) else [])
        if any(e.get("subject") == subject for e in results):
            return True
        url = payload.get("next") if isinstance(payload, dict) else None
        if not url:
            return False
    return False


def send_email(api_key: str, subject: str, body_html: str, draft: bool = False) -> dict:
    # Buttondown requires the X-Buttondown-Live-Dangerously confirmation header
    # the first time an API key creates an email with status 'about_to_send'
    # (returns 400 sending_requires_confirmation otherwise). Sending it every
    # time is harmless.
    headers = _headers(api_key)
    if not draft:
        headers["X-Buttondown-Live-Dangerously"] = "true"
    resp = _checked(
        requests.post(
            f"{BUTTONDOWN_API}/emails",
            headers=headers,
            json={
                "subject": subject,
                "body": body_html,
                "status": "draft" if draft else "about_to_send",
            },
            timeout=30,
        )
    )
    return resp.json()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--week", help="Target ISO week YYYY-Www (default: next week)")
    parser.add_argument("--data", type=Path, default=digest.DATA_PATH)
    parser.add_argument("--limit", type=int, default=digest.DEFAULT_PICK_LIMIT)
    parser.add_argument("--dry-run", action="store_true", help="Render only; no API calls")
    parser.add_argument("--draft", action="store_true", help="Create a draft, don't send")
    parser.add_argument(
        "--to",
        metavar="EMAIL",
        help="Test mode: subscribe EMAIL to the list first, then send the tipsheet",
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Print the Buttondown newsletter settings JSON and exit",
    )
    parser.add_argument(
        "--patch",
        metavar="JSON",
        help='PATCH newsletter settings, e.g. \'{"email_template": "..."}\'',
    )
    parser.add_argument("--out", type=Path, default=Path("/tmp/weekly-email.html"))
    args = parser.parse_args(argv)

    if args.inspect or args.patch:
        api_key = os.getenv("BUTTONDOWN_API_KEY", "").strip()
        if not api_key:
            print("BUTTONDOWN_API_KEY not set.")
            return 1
        if args.patch:
            result = patch_newsletter(api_key, json.loads(args.patch))
            print(json.dumps(_redact_secrets(result), indent=2)[:4000])
        else:
            print(json.dumps(_redact_secrets(inspect_newsletter(api_key)), indent=2)[:6000])
            resp = _checked(
                requests.get(f"{BUTTONDOWN_API}/emails", headers=_headers(api_key), timeout=30)
            )
            payload = resp.json()
            emails = payload.get("results", payload if isinstance(payload, list) else [])
            print(f"\nExisting emails ({len(emails)}):")
            for e in emails[:10]:
                print(f"  - {e.get('subject')!r} [status={e.get('status')}]")
        return 0

    if args.week:
        year, week = digest.parse_iso_week_arg(args.week)
    else:
        year, week = target_week()
    monday, sunday = digest.iso_week_range(year, week)
    week_label = digest.iso_week_label(year, week)

    events = digest.load_events(args.data)
    picks = digest.select_picks(events, monday=monday, sunday=sunday, limit=args.limit)
    if not picks:
        print(f"No picks for {week_label} - skipping email (nothing to send).")
        return 0

    subject = email_subject(monday, sunday)
    body_html = render_email_html(picks, monday, sunday, week_label)
    print(f"Subject: {subject}")
    print(f"Picks: {len(picks)} (top: {picks[0].title})")

    if args.dry_run:
        args.out.write_text(body_html, encoding="utf-8")
        print(f"Dry run - wrote {args.out} ({len(body_html)} bytes), no API calls made.")
        return 0

    api_key = os.getenv("BUTTONDOWN_API_KEY", "").strip()
    if not api_key:
        print(
            "BUTTONDOWN_API_KEY not set - skipping send. "
            "Add it to the repo secrets to enable the weekly tipsheet."
        )
        return 0

    # Diagnostic: surface the account slug so distribution.buttondown_endpoint
    # in master_config.yaml can be kept in sync with the real account.
    slug = newsletter_slug(api_key)
    if slug:
        print(f"Buttondown newsletter slug: {slug!r} (signup endpoint: "
              f"https://buttondown.email/api/emails/embed-subscribe/{slug})")

    if args.to:
        subscribe_email(api_key, args.to)
        # Test sends are repeatable and never block the real weekly send:
        # distinct subject per recipient, no idempotency check.
        from datetime import datetime as _dt
        subject = f"[TEST {_dt.now().strftime('%H:%M')}] {subject}"
    elif not args.draft and active_subscriber_count(api_key) == 0:
        # Buttondown rejects sends to an empty list with a 422; nothing to do.
        print("No active subscribers yet - skipping send (nothing to do).")
        return 0

    if not args.to and already_sent(api_key, subject):
        print(f"An email with subject {subject!r} already exists - not sending again.")
        return 0

    try:
        result = send_email(api_key, subject, body_html, draft=args.draft)
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 400 and "email_duplicate" in e.response.text:
            print(f"Buttondown flagged this as a duplicate - skipping send.")
            return 0
        raise
    print(
        f"Buttondown email created (id={result.get('id', '?')}, "
        f"status={'draft' if args.draft else 'about_to_send'})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
