import re

RECENT_HEADER = "Recent changes (last 7 days of git log):"


def normalize_newline(md: str) -> str:
    return md.rstrip() + "\n"


def replace_recent_changes_if_present(source_md: str, generated_md: str, git_log: str) -> str:
    """If source had a recent-changes section, deterministically rewrite it in output."""
    if RECENT_HEADER not in source_md:
        return generated_md

    recent_body = git_log or "(no commits in the last 7 days)"
    recent_block = f"{RECENT_HEADER}\n{recent_body}"
    section_pattern = re.compile(
        rf"{re.escape(RECENT_HEADER)}\n.*?(?=\n## |\Z)",
        re.DOTALL,
    )

    if section_pattern.search(generated_md):
        return section_pattern.sub(recent_block, generated_md, count=1)

    return generated_md.rstrip() + "\n\n" + recent_block


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


def upsert_freshness_bullet(md: str, key: str, value: str) -> str:
    section_match = re.search(r"(?ms)^##\s+Freshness\s*$\n(.*?)(?=^##\s+|\Z)", md)
    bullet_line = f"- `{key}`: {value}"
    bullet_pattern = re.compile(rf"(?m)^[-*]\s+`?{re.escape(key)}`?:\s*.*$")

    if section_match:
        body = section_match.group(1)
        if bullet_pattern.search(body):
            body = bullet_pattern.sub(bullet_line, body, count=1)
        else:
            body = body.rstrip("\n") + "\n" + bullet_line + "\n"
        return md[: section_match.start(1)] + body + md[section_match.end(1):]

    append = "\n\n## Freshness\n" + bullet_line + "\n"
    return md.rstrip("\n") + append


def apply_deterministic_postprocessing(
    source_md: str,
    generated_md: str,
    git_log: str,
    today_iso: str,
) -> str:
    """Normalize deterministic sections and freshness fields in model output."""
    content = replace_recent_changes_if_present(source_md, generated_md, git_log)
    content = normalize_newline(content)

    source_normalized = normalize_newline(source_md)
    model_changed = content != source_normalized

    if model_changed:
        content = upsert_frontmatter_field(content, "last_reviewed", today_iso)
        content = upsert_freshness_bullet(content, "last_reviewed", today_iso)
        content = upsert_freshness_bullet(content, "generated_by", "CI-generated")

    return normalize_newline(content)
