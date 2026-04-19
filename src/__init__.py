"""Culture-Calendar core package.

The event pipeline flows through this package in roughly this order:

1. :mod:`src.scrapers` — per-venue scrapers extending
   :class:`src.base_scraper.BaseScraper`. Registered in
   :mod:`src.scrapers.__init__` and orchestrated by
   :class:`src.scraper.MultiVenueScraper`.
2. :mod:`src.validation_service` — optional fail-fast health check over
   scraped events (wired up via ``--validate`` on
   ``update_website_data.py``).
3. :mod:`src.enrichment_layer` — LLM-driven classification + missing-field
   extraction against the schemas in ``config/master_config.yaml``
   (loaded by :mod:`src.config_loader`).
4. :mod:`src.processor` — generates AI ratings + critic-style reviews via
   :mod:`src.llm_service`; refusal-shaped responses are filtered through
   :mod:`src.refusal`.
5. :mod:`src.summary_generator` — Claude-generated one-liner hooks.
6. :mod:`src.recurring_events` — expands repeating events into
   concrete occurrences.
7. :mod:`src.calendar_generator` — emits ICS calendar files on demand.

The entry-point ``update_website_data.py`` at the repo root stitches
these together and writes ``docs/data.json``. See ``AGENTS.md`` for a
file-level pipeline map and ``CLAUDE.md`` for the overnight run
protocol + feature inventory.
"""
