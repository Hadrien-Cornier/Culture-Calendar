"""Regression tests for parseReview() in docs/script.js.

Two bugs covered:

1. **Brevity-shape descriptions** put the emoji *inside* ``<strong>``,
   which produced doubled emoji in the rendered heading
   (``🎭 🎭 Artistic Merit``).
2. **Tiny-Words-shape descriptions** pack all section headings into a
   single ``<p>`` separated by ``<br>``. The old parser captured only
   the first ``<strong>`` and dumped every other heading into the body
   as inline plain text.

Two backstops:

- ``test_data_json_has_both_shapes`` — pure-Python structural assertion
  that runs in CI without any JS toolchain.
- ``test_*_via_node`` — exercise the real JS parser via ``node`` +
  ``jsdom`` when both are available locally; skipped otherwise.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_JS = REPO_ROOT / "docs" / "script.js"
DATA_JSON = REPO_ROOT / "docs" / "data.json"


# ----------------------------- node + jsdom path -----------------------------


def _run_parse_review(html: str) -> dict:
    if shutil.which("node") is None:
        pytest.skip("node not on PATH")
    harness = f"""
      let JSDOM;
      try {{ JSDOM = require('jsdom').JSDOM; }} catch (_) {{
        process.stderr.write('NO_JSDOM');
        process.exit(3);
      }}
      const fs = require('fs');
      const src = fs.readFileSync({json.dumps(str(SCRIPT_JS))}, 'utf8');
      const start = src.indexOf('function parseReview(');
      if (start < 0) {{ process.exit(2); }}
      let depth = 0, i = start, end = -1;
      while (i < src.length) {{
        const ch = src[i];
        if (ch === '{{') depth++;
        else if (ch === '}}') {{ depth--; if (depth === 0) {{ end = i + 1; break; }} }}
        i++;
      }}
      const fn = src.slice(start, end);
      global.DOMParser = new JSDOM().window.DOMParser;
      eval(fn);
      console.log(JSON.stringify(parseReview({json.dumps(html)})));
    """
    proc = subprocess.run(
        ["node", "-e", harness],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode == 3 or "NO_JSDOM" in proc.stderr:
        pytest.skip("jsdom not installed; skipping JS unit test")
    if proc.returncode != 0:
        raise AssertionError(f"node harness failed:\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


BREVITY_DESC = (
    "<p>★ Rating: 8/10</p>"
    "<p><strong>🎭 Artistic Merit</strong> – Butler's prose deploys short sentences.</p>"
    "<p><strong>📚 Cultural Significance</strong> – Foundational Black speculative voice.</p>"
)

TINY_WORDS_DESC = (
    "<p>★ Rating: [8/10]  <br>"
    "🎭 <strong>Artistic Merit</strong>: Oyamada's prose disorients.  <br>"
    "✨ <strong>Originality</strong>: Factory's unknowable output fuses Kafka.  <br>"
    "📚 <strong>Cultural Significance</strong>: Skewers Japan's work obsession.  <br>"
    "💡 <strong>Intellectual Depth</strong>: Pointless gigs expose capitalism.  </p>"
    "<p>This slim debut skewers the corporate maw with deadpan wit.</p>"
)

OUTSIDE_EMOJI_DESC = (
    "<p>★ Rating: 9/10</p>"
    "<p>🎭 <strong>Artistic Merit</strong>  <br>Fellini orchestrates dream and reality.</p>"
    "<p>📚 <strong>Cultural Significance</strong>  <br>8½ birthed a generation of meta-cinema.</p>"
)


def test_brevity_no_doubled_emoji_in_label_via_node():
    out = _run_parse_review(BREVITY_DESC)
    assert out["rating"] == "8"
    sections = out["sections"]
    assert len(sections) == 2
    assert sections[0]["emoji"] == "🎭"
    assert sections[0]["label"] == "Artistic Merit"
    assert sections[1]["emoji"] == "📚"
    assert sections[1]["label"] == "Cultural Significance"


def test_tiny_words_splits_into_distinct_sections_via_node():
    out = _run_parse_review(TINY_WORDS_DESC)
    sections = out["sections"]
    labels = [s["label"] for s in sections if s["label"]]
    assert {"Artistic Merit", "Originality", "Cultural Significance", "Intellectual Depth"} <= set(labels)
    cs = next(s for s in sections if s["label"] == "Cultural Significance")
    assert "Intellectual Depth" not in cs["body"]
    assert "Skewers Japan" in cs["body"]


def test_outside_emoji_format_still_works_via_node():
    out = _run_parse_review(OUTSIDE_EMOJI_DESC)
    sections = out["sections"]
    assert len(sections) == 2
    assert sections[0]["emoji"] == "🎭"
    assert sections[0]["label"] == "Artistic Merit"


# --------------------- pure-Python structural backstop ----------------------

# Captures `<strong>...</strong>` blocks where the strong content begins
# with an emoji glyph followed by a label. parseReview must capture the
# label without that leading emoji (otherwise we get the Brevity bug).
STRONG_WITH_LEADING_EMOJI = re.compile(
    r"<strong>\s*([\U0001F300-\U0001FAFF☀-➿✀-➿])\s+([^<]+?)\s*</strong>",
    re.UNICODE,
)


def _load_descriptions() -> list[str]:
    with DATA_JSON.open(encoding="utf-8") as f:
        events = json.load(f)
    return [(ev.get("description") or "") for ev in events]


def test_data_json_contains_brevity_shape():
    """The Brevity bug is reproducible from data.json — descriptions exist
    where ``<strong>`` wraps an emoji + label, the trigger condition for
    the doubled-emoji rendering bug."""
    descriptions = _load_descriptions()
    affected = [d for d in descriptions if STRONG_WITH_LEADING_EMOJI.search(d)]
    assert affected, "expected at least one description with emoji-inside-strong"


def test_data_json_contains_multi_strong_per_paragraph():
    """The Tiny Words bug is reproducible from data.json — at least one
    description packs multiple ``<strong>`` headings into one ``<p>``."""
    descriptions = _load_descriptions()
    multi = []
    for d in descriptions:
        for p in re.findall(r"<p>(.*?)</p>", d, flags=re.DOTALL):
            if p.count("<strong>") >= 2:
                multi.append(p)
                break
    assert multi, "expected at least one <p> containing multiple <strong> blocks"
