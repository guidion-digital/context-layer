import re

# The heading of a git-log block that older revisions of the regenerator appended to every
# generated file. Nothing writes one any more; the constant exists so `strip_recent_changes`
# can still find and delete a block a consumer repo committed while that behaviour was live.
LEGACY_RECENT_HEADER = "Recent changes (last 7 days of git log):"


def normalize_newline(md: str) -> str:
    return md.rstrip() + "\n"


def recent_changes_pattern() -> re.Pattern:
    return re.compile(rf"{re.escape(LEGACY_RECENT_HEADER)}\n.*?(?=\n## |\Z)", re.DOTALL)


def strip_recent_changes(md: str) -> str:
    """The document without the legacy git-log block.

    One-directional: the block is deleted wherever it is found and never written back. It was
    a rolling 7-day window pasted into the file, which meant a PR opened on nearly every run
    carrying nothing but commit subjects that git already records.

    Applied to the model's output as well as the committed file, because a repo whose
    committed file still carries a block hands it to the model as input, and the minimal-edit
    instruction would otherwise have the model preserve it. Delete this once no consumer repo
    has one left.
    """
    return recent_changes_pattern().sub("", md).rstrip() + "\n"


def upsert_frontmatter_field(md: str, key: str, value: str) -> str:
    fm_match = re.match(r"\A---\n(.*?)\n---\n", md, re.DOTALL)
    if not fm_match:
        return md

    fm = fm_match.group(1)
    key_pattern = re.compile(rf"(?m)^{re.escape(key)}:\s*.*$")
    line = f"{key}: {value}"

    if key_pattern.search(fm):
        fm = key_pattern.sub(line, fm, count=1)
    else:
        fm = fm.rstrip("\n") + "\n" + line

    return md[: fm_match.start()] + f"---\n{fm}\n---\n" + md[fm_match.end():]


def freshness_bullet_patterns(key: str) -> tuple:
    """The two spellings a Freshness bullet is written in.

    ``- `last_reviewed`: ...``   what this function has always written.
    ``- **Last reviewed:** ...`` what CONTEXT_TEMPLATE.md ships, and what humans keep writing.

    Matching only the first is why a template-shaped file grew a duplicate bullet on every run
    while the human-readable one it already had stayed frozen at its original date.
    """
    label = re.escape(key.replace("_", " "))
    return (
        re.compile(rf"(?mi)^[-*]\s+`?{re.escape(key)}`?:\s*.*$"),
        re.compile(rf"(?mi)^[-*]\s+\*\*\s*{label}\s*:?\s*\*\*\s*:?\s*.*$"),
    )


def upsert_freshness_bullet(md: str, key: str, value: str) -> str:
    """Set a Freshness bullet, keeping whichever spelling the file already uses."""
    section_match = re.search(r"(?ms)^##\s+Freshness\s*$\n(.*?)(?=^##\s+|\Z)", md)
    slug_pattern, prose_pattern = freshness_bullet_patterns(key)
    slug_line = f"- `{key}`: {value}"
    prose_line = f"- **{key.replace('_', ' ').capitalize()}:** {value}"

    if section_match:
        body = section_match.group(1)

        if slug_pattern.search(body):
            body = slug_pattern.sub(slug_line, body, count=1)
        elif prose_pattern.search(body):
            body = prose_pattern.sub(prose_line, body, count=1)
        else:
            # No bullet for this key at all: follow the style the section already uses, so a
            # file never ends up carrying both spellings.
            stripped = body.rstrip("\n")
            trailing = body[len(stripped):] or "\n"
            uses_prose = re.search(r"(?m)^[-*]\s+\*\*", body) is not None
            body = stripped + "\n" + (prose_line if uses_prose else slug_line) + trailing

        return md[: section_match.start(1)] + body + md[section_match.end(1):]

    append = "\n\n## Freshness\n" + slug_line + "\n"
    return md.rstrip("\n") + append


def apply_deterministic_postprocessing(
    source_md: str,
    generated_md: str,
    today_iso: str,
) -> str:
    """Normalize deterministic sections and freshness fields in model output."""
    content = strip_recent_changes(generated_md)

    source_normalized = strip_recent_changes(source_md)
    model_changed = content != source_normalized

    if model_changed:
        content = upsert_frontmatter_field(content, "last_reviewed", today_iso)
        # The Freshness bullet alone left the frontmatter field to the model, which is how
        # `generated_by: "OpenAI"` reached a committed file -- a value outside the template's
        # closed vocabulary. Stamp both.
        content = upsert_frontmatter_field(content, "generated_by", "CI-generated")
        content = upsert_freshness_bullet(content, "last_reviewed", today_iso)
        content = upsert_freshness_bullet(content, "generated_by", "CI-generated")

    return normalize_newline(content)
