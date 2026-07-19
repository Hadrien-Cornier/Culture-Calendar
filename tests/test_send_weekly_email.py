"""Tests for scripts/send_weekly_email.py (Buttondown weekly tipsheet).

Covers week targeting, the deterministic idempotency subject, the
self-contained email HTML contract (inline styles + absolute URLs only  - 
email clients strip external stylesheets), skip behavior without an API
key, and duplicate-send prevention.
"""

from datetime import date
from unittest.mock import Mock

import pytest

import scripts.send_weekly_email as swe


# ---------------------------------------------------------------------------
# Week targeting + subject
# ---------------------------------------------------------------------------


def test_target_week_returns_next_iso_week():
    # 2026-07-18 is a Saturday in ISO week 29; target is week 30.
    year, week = swe.target_week(date(2026, 7, 18))
    assert (year, week) == (2026, 30)
    monday, sunday = swe.digest.iso_week_range(year, week)
    assert monday == date(2026, 7, 20)
    assert sunday == date(2026, 7, 26)


def test_target_week_crosses_year_boundary():
    year, week = swe.target_week(date(2026, 12, 31))
    monday, _ = swe.digest.iso_week_range(year, week)
    assert monday > date(2026, 12, 31)


def test_subject_is_deterministic_and_readable():
    monday, sunday = date(2026, 7, 27), date(2026, 8, 2)
    s1 = swe.email_subject(monday, sunday)
    assert s1 == swe.email_subject(monday, sunday)
    assert "July 27" in s1 and "August 2" in s1 and "2026" in s1


# ---------------------------------------------------------------------------
# Email HTML contract
# ---------------------------------------------------------------------------


def _pick(title="Test <Film> & Friends", rating=9, venue="AFS"):
    d = swe.digest
    review = d.parse_review(
        "<p>★ Rating: 9/10</p>"
        "<p>🎭 <strong>Artistic Merit</strong> - A <em>fine</em> film.</p>"
    )
    return d.DigestPick(
        event_id="evt1",
        title=title,
        rating=rating,
        one_liner='A "great" night out.',
        description_html="",
        review=review,
        category_label="Film",
        venue=venue,
        url="https://example.com/event",
        in_week=(
            d.WeekScreening(
                date="2026-07-27", time="7:30 PM", venue=venue, url="https://example.com/event"
            ),
        ),
    )


def test_email_html_escapes_and_formats():
    monday, sunday = date(2026, 7, 27), date(2026, 8, 2)
    html = swe.render_email_html([_pick()], monday, sunday, "2026-W31")
    assert "Test &lt;Film&gt; &amp; Friends" in html
    assert "AFS · Film" in html
    assert "Mon, Jul 27" in html
    assert "9/10" in html
    assert "Artistic Merit" in html
    assert "https://example.com/event" in html


def test_email_html_is_self_contained():
    """No external stylesheets and no relative links - email clients strip them."""
    monday, sunday = date(2026, 7, 27), date(2026, 8, 2)
    html = swe.render_email_html([_pick()], monday, sunday, "2026-W31")
    assert 'rel="stylesheet"' not in html
    assert "<link" not in html
    assert 'href="../' not in html
    assert 'href="/' not in html
    assert "style=" in html  # inline styles present


def test_email_html_links_to_site_anchor_and_digest_page():
    monday, sunday = date(2026, 7, 27), date(2026, 8, 2)
    html = swe.render_email_html([_pick()], monday, sunday, "2026-W31")
    assert "#event=evt1" in html
    assert "#event=../" not in html
    assert "/weekly/2026-W31.html" in html


def test_review_without_strong_label_is_not_duplicated():
    """When the review text carries '🎭 Artistic Merit – ...' inline (no
    <strong> tag), parse_review leaves label empty and the body keeps the
    prefix - the renderer must not prepend it a second time."""
    d = swe.digest
    pick = _pick()
    object.__setattr__(
        pick,
        "review",
        d.parse_review("<p>🎭 Artistic Merit – A fine film, tightly paced.</p>"),
    )
    html = swe.render_email_html([pick], date(2026, 7, 27), date(2026, 8, 2), "2026-W31")
    assert html.count("Artistic Merit") == 1


# ---------------------------------------------------------------------------
# Buttondown idempotency + sending (mocked HTTP)
# ---------------------------------------------------------------------------


def _resp(payload):
    r = Mock()
    r.json.return_value = payload
    r.raise_for_status = Mock()
    return r


def test_already_sent_matches_exact_subject(monkeypatch):
    get = Mock(
        return_value=_resp(
            {"results": [{"subject": "Culture Calendar: top picks for July 27–August 2, 2026"}], "next": None}
        )
    )
    monkeypatch.setattr(swe.requests, "get", get)
    assert swe.already_sent("key", "Culture Calendar: top picks for July 27–August 2, 2026") is True
    assert swe.already_sent("key", "some other subject") is False


def test_already_sent_paginates(monkeypatch):
    pages = [
        _resp({"results": [{"subject": "a"}], "next": "page2"}),
        _resp({"results": [{"subject": "b"}], "next": None}),
    ]
    monkeypatch.setattr(
        swe.requests, "get", lambda url, **k: pages[1] if url == "page2" else pages[0]
    )
    assert swe.already_sent("key", "b") is True
    assert swe.already_sent("key", "c") is False  # only 2 pages exist


def test_send_email_posts_about_to_send(monkeypatch):
    post = Mock(return_value=_resp({"id": "email_123"}))
    monkeypatch.setattr(swe.requests, "post", post)
    result = swe.send_email("key", "subj", "<div>body</div>")
    assert result["id"] == "email_123"
    payload = post.call_args.kwargs["json"]
    assert payload["status"] == "about-to-send"
    assert payload["subject"] == "subj"


def test_send_email_draft_mode(monkeypatch):
    post = Mock(return_value=_resp({"id": "email_124"}))
    monkeypatch.setattr(swe.requests, "post", post)
    swe.send_email("key", "subj", "<div>body</div>", draft=True)
    assert post.call_args.kwargs["json"]["status"] == "draft"


# ---------------------------------------------------------------------------
# main() skip paths
# ---------------------------------------------------------------------------


def test_main_skips_without_api_key(monkeypatch, capsys):
    monkeypatch.delenv("BUTTONDOWN_API_KEY", raising=False)
    rc = swe.main(["--week", "2026-W31"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "BUTTONDOWN_API_KEY not set" in out


def test_main_dry_run_writes_file(monkeypatch, tmp_path, capsys):
    out_file = tmp_path / "email.html"
    rc = swe.main(["--week", "2026-W31", "--dry-run", "--out", str(out_file)])
    assert rc == 0
    html = out_file.read_text()
    assert "CULTURE CALENDAR · 2026-W31" in html
    assert "no API calls made" in capsys.readouterr().out


def test_main_skips_empty_week(monkeypatch, capsys):
    monkeypatch.setattr(swe.digest, "select_picks", lambda *a, **k: [])
    rc = swe.main(["--week", "2026-W31"])
    assert rc == 0
    assert "nothing to send" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Account helpers: slug discovery, subscribe, subscriber guard, error logging
# ---------------------------------------------------------------------------


def test_newsletter_slug(monkeypatch):
    monkeypatch.setattr(
        swe.requests, "get",
        lambda url, **k: _resp({"results": [{"slug": "my-list", "name": "My List"}]}),
    )
    assert swe.newsletter_slug("key") == "my-list"


def test_active_subscriber_count(monkeypatch):
    monkeypatch.setattr(
        swe.requests, "get",
        lambda url, **k: _resp({"results": [
            {"type": "regular"}, {"type": "unactivated"}, {"type": "regular"},
        ]}),
    )
    assert swe.active_subscriber_count("key") == 2


def test_subscribe_email_posts_and_tolerates_existing(monkeypatch):
    post = Mock(return_value=_resp({"id": "sub1"}))
    monkeypatch.setattr(swe.requests, "post", post)
    swe.subscribe_email("key", "a@b.c")
    assert post.call_args.kwargs["json"]["email_address"] == "a@b.c"

    conflict = Mock(ok=False, status_code=400, text='{"email_address": ["already exists"]}',
                    request=Mock(method="POST"), url="u")
    monkeypatch.setattr(swe.requests, "post", Mock(return_value=conflict))
    swe.subscribe_email("key", "a@b.c")  # must not raise


def test_checked_logs_body_and_raises(capsys):
    import requests as real_requests
    bad = Mock(ok=False, status_code=422, text='{"status": ["Invalid enum"]}',
               request=Mock(method="POST"), url="https://api.buttondown.email/v1/emails")
    bad.raise_for_status = Mock(
        side_effect=real_requests.exceptions.HTTPError("422 Client Error")
    )
    with pytest.raises(real_requests.exceptions.HTTPError):
        swe._checked(bad)
    assert "Invalid enum" in capsys.readouterr().out


def test_main_skips_send_when_no_subscribers(monkeypatch, capsys):
    monkeypatch.setenv("BUTTONDOWN_API_KEY", "k")
    monkeypatch.setattr(swe, "newsletter_slug", lambda k: "slug")
    monkeypatch.setattr(swe, "active_subscriber_count", lambda k: 0)
    send = Mock()
    monkeypatch.setattr(swe, "send_email", send)
    rc = swe.main(["--week", "2026-W31"])
    assert rc == 0
    assert "No active subscribers" in capsys.readouterr().out
    send.assert_not_called()


def test_main_to_mode_subscribes_then_sends(monkeypatch, capsys):
    monkeypatch.setenv("BUTTONDOWN_API_KEY", "k")
    monkeypatch.setattr(swe, "newsletter_slug", lambda k: "slug")
    calls = []
    monkeypatch.setattr(swe, "subscribe_email", lambda k, e: calls.append(("sub", e)))
    monkeypatch.setattr(swe, "already_sent", lambda k, s: False)
    monkeypatch.setattr(
        swe, "send_email", lambda k, s, b, draft=False: calls.append(("send", s)) or {"id": "e1"}
    )
    count = Mock(return_value=5)
    monkeypatch.setattr(swe, "active_subscriber_count", count)
    rc = swe.main(["--week", "2026-W31", "--to", "me@example.com"])
    assert rc == 0
    assert calls[0] == ("sub", "me@example.com")
    assert calls[1][0] == "send"
    count.assert_not_called()  # --to bypasses the subscriber guard
