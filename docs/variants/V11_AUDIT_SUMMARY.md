# v11 Variants — Audit Summary

Aggregated audit findings from v11a–v11j. Use this table to compare variants and guide morning selection.

## Summary Table

| Variant | CRITICAL | HIGH | Top Issue |
|---------|----------|------|-----------|
| v11a | 0 | 1 | [layout-transition] performance anti-pattern |
| v11b | 0 | 1 | [layout-transition] performance anti-pattern |
| v11c | 0 | 1 | [layout-transition] performance anti-pattern |
| v11d | 0 | 1 | [layout-transition] performance anti-pattern |
| v11e | 0 | 1 | [layout-transition] performance anti-pattern |
| v11f | 0 | 1 | [layout-transition] performance anti-pattern |
| v11g | 0 | 0 | None — design audit passes |
| v11h | 0 | 1 | [layout-transition] performance anti-pattern |
| v11i | 0 | 1 | [layout-transition] performance anti-pattern |
| v11j | 0 | 0 | None — design audit passes |

## Notes

- **[layout-transition] pattern**: Animating width, height, padding, or margin causes layout thrash. Affects 8 variants (v11a–f, v11h–i). All inherited from v11-picks-plus base styles.
- **Design audits** (v11g Pitchfork, v11j L'Officiel): Comprehensive design reports with no critical or high-severity issues flagged.
- **Recommendation for selection**: v11g and v11j have no HIGH/CRITICAL issues. Others require addressing the layout-transition pattern before production use.

## Generation

Aggregated on 2026-04-16 from `docs/variants/v11?/audit.md`.
