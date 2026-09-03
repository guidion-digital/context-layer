import re

RECENT_HEADER = "Recent changes (last 7 days of git log):"


def normalize_newline(md: str) -> str:
    return md.rstrip() + "\n"


def format_git_log(git_log: str) -> str:
    """Render `git log --oneline --stat` output as a markdown list.

    Raw, the block renders as one run-together wall of text, because markdown collapses
    single newlines inside a paragraph. `--stat` lines arrive indented by git, which is the
    signal to nest them under the commit they belong to.
    """
    lines = []

    for raw in git_log.splitlines():
        if not raw.strip():
            continue
        lines.append(("  - " if raw[:1].isspace() else "- ") + raw.strip())

    return "\n".join(lines)


def recent_changes_pattern() -> re.Pattern:
    return re.compile(rf"{re.escape(RECENT_HEADER)}\n.*?(?=\n## |\Z)", re.DOTALL)


def ensure_recent_changes_section(generated_md: str, git_log: str) -> str:
    """Append or rewrite the git-log block. Unconditional, by design.

    This used to run only when the *existing* file already carried the header, so a file
    generated from nothing never got one -- and never would, since the next run would find no
    header either. Any repo getting its first context file was in that state, while
    CONTEXT_TEMPLATE.md told humans the section was part of the shape.
    """
    recent_body = format_git_log(git_log) or "(no commits in the last 7 days)"
    recent_block = f"{RECENT_HEADER}\n\n{recent_body}"
    section_pattern = recent_changes_pattern()

    if section_pattern.search(generated_md):
        return section_pattern.sub(recent_block, generated_md, count=1)

    return generated_md.rstrip() + "\n\n" + recent_block


def strip_recent_changes(md: str) -> str:
    """The document without its git-log block, for comparing two revisions of it.

    A moving 7-day window rewrites that block on every run. Comparing it would report a change
    nobody made, stamping `last_reviewed` on a file whose prose is untouched.
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
    """Set a Freshness bullet, keeping whichever spelling the file already uses.

    The section body stops at the recent-changes header as well as the next H2 and EOF. That
    block is the last thing in a template-shaped file and sits *inside* the Freshness section
    as far as the heading regex is concerned, so without the bound an appended bullet lands
    underneath the git log rather than among the bullets.
    """
    section_match = re.search(
        rf"(?ms)^##\s+Freshness\s*$\n(.*?)(?=^##\s+|^{re.escape(RECENT_HEADER)}|\Z)", md
    )
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
    git_log: str,
    today_iso: str,
) -> str:
    """Normalize deterministic sections and freshness fields in model output."""
    content = ensure_recent_changes_section(generated_md, git_log)
    content = normalize_newline(content)

    source_normalized = normalize_newline(source_md)
    model_changed = strip_recent_changes(content) != strip_recent_changes(source_normalized)

    if model_changed:
        content = upsert_frontmatter_field(content, "last_reviewed", today_iso)
        # The Freshness bullet alone left the frontmatter field to the model, which is how
        # `generated_by: "OpenAI"` reached a committed file -- a value outside the template's
        # closed vocabulary. Stamp both.
        content = upsert_frontmatter_field(content, "generated_by", "CI-generated")
        content = upsert_freshness_bullet(content, "last_reviewed", today_iso)
        content = upsert_freshness_bullet(content, "generated_by", "CI-generated")

    return normalize_newline(content)
