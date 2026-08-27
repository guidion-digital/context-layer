import unittest

from scripts.context_regen_postprocess import apply_deterministic_postprocessing


TODAY = "2026-08-27"


class TestContextRegenPostprocess(unittest.TestCase):
    def test_unchanged_content_does_not_mutate_freshness_fields(self):
        source = """---
domain: infra
last_reviewed: 2026-08-01
---

# Context

## Freshness
- `last_reviewed`: 2026-08-01
"""

        out = apply_deterministic_postprocessing(
            source_md=source,
            generated_md=source,
            git_log="",
            today_iso=TODAY,
        )

        self.assertEqual(out, source.rstrip() + "\n")
        self.assertNotIn("`generated_by`", out)
        self.assertIn("last_reviewed: 2026-08-01", out)

    def test_changed_content_updates_frontmatter_and_freshness_once(self):
        source = """---
domain: infra
last_reviewed: 2026-08-01
---

# Context

## Freshness
- `last_reviewed`: 2026-08-01
- `generated_by`: manual
"""

        generated = source + "\nExtra line\n"

        out = apply_deterministic_postprocessing(
            source_md=source,
            generated_md=generated,
            git_log="",
            today_iso=TODAY,
        )

        self.assertIn(f"last_reviewed: {TODAY}", out)
        self.assertIn(f"- `last_reviewed`: {TODAY}", out)
        self.assertIn("- `generated_by`: CI-generated", out)
        self.assertEqual(out.count("- `generated_by`"), 1)

    def test_missing_freshness_section_is_added(self):
        source = """---
domain: infra
last_reviewed: 2026-08-01
---

# Context
"""

        generated = source + "\nChanged\n"

        out = apply_deterministic_postprocessing(
            source_md=source,
            generated_md=generated,
            git_log="",
            today_iso=TODAY,
        )

        self.assertIn("## Freshness", out)
        self.assertIn(f"- `last_reviewed`: {TODAY}", out)
        self.assertIn("- `generated_by`: CI-generated", out)

    def test_recent_changes_section_is_replaced_deterministically(self):
        source = """---
domain: infra
last_reviewed: 2026-08-01
---

# Context

Recent changes (last 7 days of git log):
old

## Freshness
- `last_reviewed`: 2026-08-01
"""

        generated = """---
domain: infra
last_reviewed: 2026-08-01
---

# Context

Recent changes (last 7 days of git log):
model text

## Freshness
- `last_reviewed`: 2026-08-01
"""

        out = apply_deterministic_postprocessing(
            source_md=source,
            generated_md=generated,
            git_log="abc123 Update docs",
            today_iso=TODAY,
        )

        self.assertIn("Recent changes (last 7 days of git log):\nabc123 Update docs", out)

    def test_transform_is_idempotent(self):
        source = """---
domain: infra
last_reviewed: 2026-08-01
---

# Context

## Freshness
- `last_reviewed`: 2026-08-01
"""
        generated = source + "\nChanged\n"

        once = apply_deterministic_postprocessing(
            source_md=source,
            generated_md=generated,
            git_log="",
            today_iso=TODAY,
        )
        twice = apply_deterministic_postprocessing(
            source_md=once,
            generated_md=once,
            git_log="",
            today_iso=TODAY,
        )

        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
