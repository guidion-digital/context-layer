#!/usr/bin/env python3

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
import urllib.request
import urllib.error

# Defaults mirror the `inputs:` block of .github/workflows/regenerate-context.yaml, so the
# script behaves identically whether the action or a manual local run invokes it.
DEFAULT_CONTEXT_FILE = "AI/CONTEXT.md"
DEFAULT_MODEL = "gpt-5.6"
DEFAULT_REPO_OWNER = "UNSET — please set this"

# Resolved from this file, never the working directory: the action runs the script from the
# *caller's* checkout, and a manual run happens from inside whichever repo is being updated.
TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "CONTEXT_TEMPLATE.md"

RECENT_HEADER = "Recent changes (last 7 days of git log):"

# A bracketed span with any non-space content is a placeholder to drop. `[ ]` is not -- that is
# the roadmap checkbox, which is shape the model should copy.
PLACEHOLDER = re.compile(r"\[([^\[\]\n]*)\]")


def template_skeleton(template_md: str) -> str:
    """CONTEXT_TEMPLATE.md with everything a model might copy verbatim removed.

    The required-headings list can only carry section *names*. It cannot say "two lists, one
    of them naming the system each responsibility is delegated to", which is why generated
    files kept collapsing `Does:` / `Does not do (delegated to):` into a one-sided summary.
    Sending the template fixes that -- but the template is also full of worked examples, and
    handing a model `| Customer | Salesforce | Reads |` invites Salesforce rows into an
    infrastructure repo's context file.

    So: keep the section comments, the `Does:` labels, the direction legend, table header
    rows and the Freshness bullet style; drop the `[e.g. ...]` placeholders, the example table
    rows, and the recent-changes block, which the code maintains and a model would paraphrase.
    """
    def drop_placeholder(match: re.Match) -> str:
        return "..." if match.group(1).strip() else match.group(0)

    lines: list[str] = []
    table_row = 0

    for raw in template_md.split(RECENT_HEADER)[0].splitlines():
        stripped = raw.strip()

        if stripped.startswith("|"):
            table_row += 1
            separator = set(stripped.replace("|", "").replace(" ", "")) <= {"-", ":"}
            if table_row > 1 and not separator:
                continue
        elif stripped:
            # Blank lines do not end a table here: the template separates its rows with them.
            table_row = 0

        lines.append(PLACEHOLDER.sub(drop_placeholder, raw))

    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


if not TEMPLATE_PATH.is_file():
    raise RuntimeError(f"CONTEXT_TEMPLATE.md not found at {TEMPLATE_PATH}")

template_md = template_skeleton(TEMPLATE_PATH.read_text(encoding="utf-8"))

context_file = os.environ.get('CONTEXT_FILE', '').strip() or DEFAULT_CONTEXT_FILE
repo_name = os.environ.get('GITHUB_REPOSITORY', '').strip()
if not repo_name:
    raise RuntimeError("GITHUB_REPOSITORY is required for canonical `repo` metadata")
repo_owner = os.environ.get('REPO_OWNER', '').strip() or DEFAULT_REPO_OWNER
repo_constraint = f"- Set frontmatter `repo` exactly to: {repo_name}"
owner_constraint = f"- Set frontmatter `owner` exactly to: {repo_owner}"

system_prompt = (
    "You are a technical documentation maintainer responsible for keeping a repository's "
    f"{context_file} file accurate and up to date. You will be given the current file, a "
    "summary of recent git history, and the repository's directory structure. Update the "
    "file so it accurately reflects the current state of the repository. "
    ""
    "Use a strict minimal-edit approach: preserve unchanged text byte-for-byte whenever "
    "possible. Only modify sections directly justified by the provided inputs. Do not "
    "reformat, reorder, rename headings, or compress detailed sections into short summaries "
    "unless required by real repository changes or to fix invalid syntax. "
    ""
    "When an existing context file is substantial, preserve its structure, section coverage, "
    "and level of detail. Avoid dropping tables, lists, caveats, and architecture notes unless "
    "the inputs clearly show they are obsolete. "
    ""
    "The frontmatter must include a `summary:` field, alongside domain, main_systems, "
    "owner, criticality, last_reviewed, and review_confidence. "
    ""
    "`summary` is the only body text published to the org-wide context index, and it is what "
    "another agent reads to decide whether this repository is worth opening at all. Write it "
    "in the house style the org has converged on, in four moves: what this repo is; what it "
    "owns or is the source of truth for; `Relevant for questions about:` ...; and "
    "`Not relevant for:` ... . Aim for 650-1250 characters — long enough to carry that "
    "closing relevant/not-relevant pair, which is the most useful triage material in the "
    "index. Keep it aligned with domain and main_systems, and do not compress it to a single "
    "sentence. "
    ""
    "Fields must be well-formed YAML that can be parsed by an LLM or human without errors. "
    ""
    "Return ONLY the full updated file content — no explanation, no markdown code fence, "
    "no surrounding text of any kind."
)

prompt_addition = os.environ.get('PROMPT_ADDITION', '').strip()
if prompt_addition:
    system_prompt += "\n\n" + prompt_addition

with open('.tmp/context.md', 'r', encoding='utf-8') as f:
    context_md = f.read()

with open('.tmp/git-log.txt', 'r', encoding='utf-8') as f:
    git_log = f.read().strip()

with open('.tmp/repo-tree.txt', 'r', encoding='utf-8') as f:
    repo_tree = f.read()

# Tolerated as missing so a stale `.tmp/` from before READMEs were gathered fails on content,
# not on a traceback. gather_context.py always writes the file, empty if the repo has none.
readmes_path = Path('.tmp/readmes.txt')
readmes = readmes_path.read_text(encoding='utf-8').strip() if readmes_path.is_file() else ''

# Only the tree lists file *names*; this is the one place the model sees file *contents*, and
# for most repos it is where the architectural reasoning is actually written down.
readme_section = f"""
The repository's README files, in full. These are the closest thing to a written record of why
this repo is built the way it is -- prefer them over inference from the directory listing, and
carry specifics (names, rules, manual steps, constraints) across rather than paraphrasing them
into generalities:

{readmes}
""" if readmes else """
The repository has no README files.
"""

required_h2_headings = [
    "## Overview",
    "## Purpose and responsibilities",
    "## Source of truth / data ownership",
    "## External integrations",
    "## APIs exposed",
    "## APIs / services consumed",
    "## Deployment",
    "## Architectural notes and key decisions",
    "## Known risks / fragile areas",
    "## AI assistant guidance",
    "## Roadmap / active migrations",
    "## Freshness",
]

template_frontmatter_fields = [
    "repo",
    "project_name",
    "owner",
    "domain",
    "criticality",
    "summary",
    "main_stack",
    "main_systems",
    "last_reviewed",
    "review_confidence",
    "generated_by",
    "validated_by",
]

# Closed vocabularies from the CONTEXT.md template, enforced by the org context index
# generator (gcl-master-layer/scripts/find-context.py). Values outside these are reported in
# the index review PR, so state them rather than leaving the model to invent its own.
frontmatter_vocabularies = {
    "criticality": ["low", "medium", "high", "business-critical"],
    "review_confidence": ["low", "medium", "high"],
    "generated_by": ["manual", "AI-assisted", "CI-generated"],
}

# `domain` is checked the same way but is open by design: a value outside the list is flagged
# for a human rather than rejected, so offer the list without forbidding anything else.
domain_vocabulary = [
    "appointment-completion", "appointment-scheduling", "cloud-infra", "customer-care",
    "customer-self-service", "data", "expert-negotiations", "field-service", "finance",
    "healthcare-advisory", "infrastructure", "integrations", "mobile", "partner-integrations",
    "platform", "self-service-booking", "ticket-lifecycle",
]

vocabulary_lines = "\n".join(
    f"- {key}: " + " | ".join(values) for key, values in frontmatter_vocabularies.items()
)

existing_chars = len(context_md.strip())
existing_h2_count = len(re.findall(r"(?m)^##\s+", context_md))

user_prompt = f"""Current {context_file}:
{context_md}

Recent git history (last 7 days):
{git_log or '(no commits in the last 7 days)'}

Current repo structure:
{repo_tree}
{readme_section}
Existing file stats:
- characters: {existing_chars}
- H2 headings: {existing_h2_count}

Update {context_file} to reflect any changes. If nothing meaningful changed, return the file \
unchanged.

If an existing file is present and substantial, preserve section coverage and level of detail.
Do not replace detailed sections with generic summaries. Keep key headings/tables/lists unless \
the provided inputs clearly justify removal.

Required frontmatter fields (must exist):
{', '.join(template_frontmatter_fields)}

Closed vocabularies — a value outside these is rejected by the org context index:
{vocabulary_lines}

Preferred `domain` values. Anything else is flagged for human review, so only go outside this \
list if none of these fit:
{', '.join(domain_vocabulary)}

Canonical metadata constraints:
{repo_constraint}
{owner_constraint}

Required H2 sections (must exist, even if value is n/a with one-line explanation):
{chr(10).join(required_h2_headings)}

Shape to follow. This is the house template with its examples stripped out; match its
sections, table columns, labels and bullet styles, and heed the HTML comments. The `...`
markers are placeholders, never content -- replace them with facts about this repository, and
never copy a placeholder through:

{template_md}

Do not write a `Recent changes (last 7 days of git log):` section. It is appended
automatically from the real git log after you return, and anything you write there is
discarded."""

payload = {
    "model": os.environ.get('MODEL', '').strip() or DEFAULT_MODEL,
    "input": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
}

req = urllib.request.Request(
    "https://api.openai.com/v1/responses",
    data=json.dumps(payload).encode(),
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
    },
)

try:
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read())
except urllib.error.HTTPError as e:
    err_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
    raise RuntimeError(f"OpenAI API request failed: HTTP {e.code} {e.reason}\n{err_body}")

content = body.get("output_text")
if not content:
    output = body.get("output", [])
    chunks = []
    for item in output:
        for part in item.get("content", []):
            if part.get("type") in ("output_text", "text") and "text" in part:
                chunks.append(part["text"])
    content = "".join(chunks)

if not content:
    raise RuntimeError(f"OpenAI API response did not include output text. Body: {json.dumps(body)}")

def normalize_newline(md: str) -> str:
    return md.rstrip() + "\n"


def format_git_log(git_log_text: str) -> str:
    """Render `git log --oneline --stat` output as a markdown list.

    Raw, the block renders as one run-together wall of text, because markdown collapses
    single newlines inside a paragraph. `--stat` lines arrive indented by git, which is the
    signal to nest them under the commit they belong to.
    """
    lines = []

    for raw in git_log_text.splitlines():
        if not raw.strip():
            continue
        lines.append(("  - " if raw[:1].isspace() else "- ") + raw.strip())

    return "\n".join(lines)


def recent_changes_pattern() -> re.Pattern:
    return re.compile(rf"{re.escape(RECENT_HEADER)}\n.*?(?=\n## |\Z)", re.DOTALL)


def ensure_recent_changes_section(generated_md: str, git_log_text: str) -> str:
    """Append or rewrite the git-log block. Unconditional, by design.

    This used to run only when the *existing* file already carried the header, so a file
    generated from nothing never got one -- and never would, since the next run would find no
    header either. Any repo getting its first context file was in that state, while
    CONTEXT_TEMPLATE.md told humans the section was part of the shape.
    """
    recent_body = format_git_log(git_log_text) or "(no commits in the last 7 days)"
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

content = ensure_recent_changes_section(content, git_log)
content = normalize_newline(content)

content = upsert_frontmatter_field(content, "repo", repo_name)
content = upsert_frontmatter_field(content, "owner", repo_owner)

source_normalized = normalize_newline(context_md)

def count_h2(md: str) -> int:
    return len(re.findall(r"(?m)^##\s+", md))

def present_required_h2(md: str, required: list[str]) -> int:
    return sum(1 for h in required if h in md)

# Quality gate: if we already have a substantial context file, reject outputs
# that lose too much structure/detail.
source_substantial = len(source_normalized.strip()) >= 2500 and count_h2(source_normalized) >= 10
generated_too_small = len(content.strip()) < int(len(source_normalized.strip()) * 0.7)
generated_h2_lossy = count_h2(content) < max(8, int(count_h2(source_normalized) * 0.7))
required_h2_missing = present_required_h2(content, required_h2_headings) < max(8, len(required_h2_headings) - 2)

if source_substantial and (generated_too_small or generated_h2_lossy or required_h2_missing):
    print("Generated output failed quality gate; preserving existing context content.")
    content = source_normalized

model_changed = strip_recent_changes(content) != strip_recent_changes(source_normalized)

if model_changed:
    today = datetime.now(timezone.utc).date().isoformat()
    content = upsert_frontmatter_field(content, "last_reviewed", today)
    # The Freshness bullet alone left the frontmatter field to the model, which is how
    # `generated_by: "OpenAI"` reached a committed file -- a value outside the template's
    # closed vocabulary. Stamp both.
    content = upsert_frontmatter_field(content, "generated_by", "CI-generated")
    content = upsert_freshness_bullet(content, "last_reviewed", today)
    content = upsert_freshness_bullet(content, "generated_by", "CI-generated")

content = normalize_newline(content)

os.makedirs(os.path.dirname(context_file) or ".", exist_ok=True)

with open(context_file, "w") as f:
    f.write(content)

print(f"{context_file} written successfully.")
