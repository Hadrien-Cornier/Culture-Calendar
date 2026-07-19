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

_FONT = "Georgia, 'Times New Roman', serif"
_INK = "#1a1a1a"
_MUTED = "#666666"
_ACCENT = "#8a2b1d"
_RULE = "border-top:1px solid #e3ddd3;"


def _a(href: str, text: str, color: str = _ACCENT) -> str:
    return (
        f'<a href="{digest._esc(href)}" style="color:{color};text-decoration:none;">'
        f"{digest._esc(text)}</a>"
    )


def _render_pick_html(pick: "digest.DigestPick", ordinal: int) -> str:
    event_url = (
        f"{SITE_URL}#event={digest._esc(pick.event_id)}" if pick.event_id else SITE_URL
    )
    title_link = _a(event_url, pick.title, color=_INK)
    rating = (
        f'<span style="background:{_ACCENT};color:#fff;border-radius:3px;'
        f'padding:1px 6px;font-size:12px;">{pick.rating}/10</span> '
        if pick.rating is not None
        else ""
    )
    whens = " · ".join(digest._format_when(s) for s in pick.in_week)
    meta = digest._esc(f"{pick.venue} · {pick.category_label}")
    parts = [
        f'<div style="{_RULE}padding:18px 0;">',
        f'<div style="font-size:12px;color:{_MUTED};letter-spacing:1px;">{ordinal:02d}</div>',
        f'<div style="font-size:19px;font-weight:bold;margin:2px 0;">{rating}{title_link}</div>',
        f'<div style="font-size:13px;color:{_MUTED};">{meta} - {digest._esc(whens)}</div>',
    ]
    if pick.one_liner:
        parts.append(
            f'<div style="font-style:italic;margin:6px 0;color:{_INK};">'
            f"{digest._esc(pick.one_liner)}</div>"
        )
    # Mirror build_weekly_digest._render_review: only prepend emoji+label as a
    # heading when parse_review actually extracted a label - otherwise the body
    # already starts with them ("🎭 Artistic Merit – ...") and we'd duplicate.
    for section in pick.review.sections:
        heading = ""
        if section.label:
            emoji = f"{digest._esc(section.emoji)} " if section.emoji else ""
            heading = f"{emoji}<strong>{digest._esc(section.label)}</strong> "
        parts.append(
            f'<div style="font-size:14px;line-height:1.55;margin:6px 0;">'
            f"{heading}{digest._esc(section.body)}</div>"
        )
    if pick.url:
        parts.append(
            f'<div style="font-size:13px;margin-top:4px;">{_a(pick.url, "Official page →")}</div>'
        )
    parts.append("</div>")
    return "\n".join(parts)


def render_email_html(
    picks: Sequence["digest.DigestPick"], monday: date, sunday: date, week_label: str
) -> str:
    """Standalone HTML email body: inline styles only, absolute URLs only."""
    range_label = digest._format_range(monday, sunday)
    body_picks = "\n".join(_render_pick_html(p, i + 1) for i, p in enumerate(picks))
    digest_page = f"{SITE_URL}weekly/{week_label}.html"
    return f"""<div style="max-width:640px;margin:0 auto;font-family:{_FONT};color:{_INK};">
<div style="padding:16px 0;border-bottom:2px solid {_INK};">
<div style="font-size:12px;letter-spacing:2px;color:{_MUTED};">CULTURE CALENDAR · {digest._esc(week_label)}</div>
<div style="font-size:26px;font-weight:bold;margin-top:4px;">Top picks · week of {digest._esc(range_label)}</div>
<div style="font-size:13px;color:{_MUTED};margin-top:4px;">
{_a(SITE_URL, "Full calendar")} · {_a(digest_page, "Read this week on the site")} · {_a(SITE_URL + "calendar.ics", "Add to your calendar")}
</div>
</div>
{body_picks}
<div style="{_RULE}padding:14px 0;font-size:12px;color:{_MUTED};">
You're receiving this because you subscribed at {_a(SITE_URL, "Culture Calendar")}.
Ratings and reviews are AI-generated; double-check times with the venue.
</div>
</div>"""


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
        # distinct subject, no idempotency check.
        subject = f"[TEST] {subject}"
    elif not args.draft and active_subscriber_count(api_key) == 0:
        # Buttondown rejects sends to an empty list with a 422; nothing to do.
        print("No active subscribers yet - skipping send (nothing to do).")
        return 0

    if not args.to and already_sent(api_key, subject):
        print(f"An email with subject {subject!r} already exists - not sending again.")
        return 0

    result = send_email(api_key, subject, body_html, draft=args.draft)
    print(
        f"Buttondown email created (id={result.get('id', '?')}, "
        f"status={'draft' if args.draft else 'about_to_send'})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
