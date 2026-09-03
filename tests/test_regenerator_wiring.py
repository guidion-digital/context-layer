"""Assert the regeneration logic has exactly one copy, and that the wiring to it holds.

`.github/workflows/regenerate-context.yaml` used to inline the regenerator as a
`python3 - <<'PYEOF'` heredoc while `scripts/_regenerator.py` kept a second copy for
a second caller. The two drifted. The workflow now calls this repository's root
`action.yml`, which runs the scripts directly, so there is one production copy.

That fix depends on wiring a test can check: the action reference has to stay a pinned tag on
this repository (a `./`-relative reference silently resolves against the *calling* repo), the
inputs on both sides have to line up, and nobody should quietly re-inline the Python.
"""

import os
import re
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github/workflows/regenerate-context.yaml"
ACTION = REPO_ROOT / "action.yml"
SCRIPT = REPO_ROOT / "scripts/_regenerator.py"
TEMPLATE = REPO_ROOT / "CONTEXT_TEMPLATE.md"

ACTION_REPO = "guidion-digital/context-layer"

# Inputs the action forwards as environment variables but does not own a default for.
SECRET_INPUTS = {"openai_api_key"}


def action_reference(workflow_text: str) -> str:
    """The ref the workflow pins the regeneration action to."""
    matches = re.findall(rf"(?m)^\s*uses:\s*{re.escape(ACTION_REPO)}@(\S+)\s*$", workflow_text)
    if len(matches) != 1:
        raise AssertionError(
            f"expected exactly one `uses: {ACTION_REPO}@...` step, found {len(matches)}"
        )
    return matches[0]


def action_step_inputs(workflow_text: str) -> set:
    """The `with:` keys the workflow passes to the regeneration action."""
    lines = workflow_text.splitlines()
    uses = next(i for i, l in enumerate(lines) if f"uses: {ACTION_REPO}@" in l)
    indent = len(lines[uses]) - len(lines[uses].lstrip())

    keys = set()
    seen_with = False
    for line in lines[uses + 1:]:
        if line.strip() and (len(line) - len(line.lstrip())) < indent:
            break  # dedented out of this step
        if re.fullmatch(rf" {{{indent}}}with:\s*", line):
            seen_with = True
            continue
        key = re.fullmatch(rf" {{{indent + 2}}}(\w+):\s*.*", line)
        if seen_with and key:
            keys.add(key.group(1))

    return keys


def yaml_block_defaults(text: str, name_indent: int) -> dict:
    """Map `<name>:` entries at `name_indent` to their nested `default:`, if any."""
    defaults = {}
    current = None

    for line in text.splitlines():
        name = re.fullmatch(rf" {{{name_indent}}}(\w+):\s*", line)
        if name:
            current = name.group(1)
            defaults.setdefault(current, None)
            continue

        default = re.fullmatch(rf" {{{name_indent + 2}}}default:\s*(.*?)\s*", line)
        if default and current:
            defaults[current] = default.group(1).strip("\"'")

    return defaults


def workflow_call_inputs(workflow_text: str) -> dict:
    body = workflow_text.split("workflow_call:", 1)[1].split("\npermissions:", 1)[0]
    return yaml_block_defaults(body.split("inputs:", 1)[1].split("    secrets:", 1)[0], 6)


def action_inputs(action_text: str) -> dict:
    body = action_text.split("\ninputs:", 1)[1].split("\noutputs:", 1)[0]
    return yaml_block_defaults(body, 2)


def template_body_lines(template: str) -> list:
    """(line number, stripped text) for body lines outside HTML comments.

    The per-section `<!-- ... -->` comments are deliberate prose -- guidance for whoever fills
    the file in -- so they are not subject to the list-formatting rules below.
    """
    body = template.split("---", 2)[2]
    out, in_comment = [], False

    for number, line in enumerate(body.splitlines(), start=1):
        stripped = line.strip()

        if in_comment:
            in_comment = "-->" not in stripped
            continue
        if stripped.startswith("<!--"):
            in_comment = "-->" not in stripped
            continue

        out.append((number, stripped))

    return out


class WiringTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.workflow_text = WORKFLOW.read_text(encoding="utf-8")
        self.action_text = ACTION.read_text(encoding="utf-8")

    def test_workflow_does_not_inline_a_second_regenerator(self) -> None:
        self.assertNotIn(
            "<<'PYEOF'",
            self.workflow_text,
            "the workflow is inlining Python again; call the action instead so there is one copy",
        )
        self.assertNotIn("api.openai.com", self.workflow_text)

    def test_action_reference_is_a_pinned_tag_on_this_repo(self) -> None:
        ref = action_reference(self.workflow_text)

        self.assertRegex(
            ref,
            r"^\d+\.\d+\.\d+$",
            "pin the action to a released tag: a branch would make every caller track "
            "unreleased changes, and a `./` path resolves against the *calling* repo",
        )

    def test_action_and_workflow_inputs_line_up(self) -> None:
        passed = action_step_inputs(self.workflow_text)
        declared = set(action_inputs(self.action_text))

        self.assertEqual(
            passed - declared, set(), "workflow passes inputs the action does not declare"
        )
        self.assertEqual(
            declared - passed, set(), "action declares inputs the workflow never passes"
        )

    def test_defaults_agree_across_workflow_action_and_script(self) -> None:
        workflow = workflow_call_inputs(self.workflow_text)
        action = action_inputs(self.action_text)
        script = SCRIPT.read_text(encoding="utf-8")

        for name, default in action.items():
            if name in SECRET_INPUTS:
                continue
            self.assertIn(name, workflow, f"action input {name} has no workflow counterpart")
            self.assertEqual(
                default,
                workflow[name],
                f"`{name}` default differs between action.yml and the reusable workflow",
            )

        for constant, input_name in (
            ("DEFAULT_CONTEXT_FILE", "context_file"),
            ("DEFAULT_MODEL", "model"),
        ):
            match = re.search(rf'(?m)^{constant} = "(.*)"$', script)
            self.assertIsNotNone(match, f"{constant} not found in _regenerator.py")
            self.assertEqual(
                match.group(1),
                action[input_name],
                f"{constant} does not match the action's `{input_name}` default",
            )

    def test_case_variant_detection_is_not_duplicated(self) -> None:
        """One implementation of "which spelling is the context file under?".

        The guard step used to scan the filesystem with `find`, which cannot tell
        `AI/CONTEXT.md` from `ai/context.md` on a case-insensitive filesystem. That job now
        belongs to gather_context.find_case_variant, which reads the git index, and the
        workflow consumes the action's output rather than deciding again.
        """
        self.assertNotIn(
            "tolower($0)==target",
            self.workflow_text,
            "the workflow is detecting case variants again; consume the action's output",
        )
        self.assertIn(
            "${{ steps.regenerate.outputs.case_variant }}",
            self.workflow_text,
            "downstream steps must consume the action's case_variant output",
        )
        self.assertIn("case_variant", self.action_text)

    def test_secret_never_reaches_a_run_body(self) -> None:
        """The key travels by environment variable, never interpolated into a script.

        An expression expanded into a `run:` body ends up on a process command line, readable
        by anything else on the runner, and echoed if a step ever gains `set -x`. Masking does
        not save you there: it only rewrites log output.
        """
        env_assignment = re.compile(r"^\s+[A-Z_]+: \$\{\{ inputs\.openai_api_key \}\}\s*$")

        uses = [
            line for line in self.action_text.splitlines()
            if "inputs.openai_api_key" in line and not line.lstrip().startswith("#")
        ]

        self.assertTrue(uses, "the action no longer forwards openai_api_key at all")
        for line in uses:
            self.assertRegex(
                line,
                env_assignment,
                "openai_api_key must be forwarded as an `env:` entry, not inlined into a "
                "`run:` body or an action argument",
            )

        self.assertNotIn(
            "set -x",
            self.action_text,
            "`set -x` would echo the expanded command, secrets included",
        )

    def test_secret_is_masked_defensively(self) -> None:
        """Masking follows the value, so a caller passing a non-secret would leak it."""
        self.assertIn(
            "::add-mask::",
            self.action_text,
            "mask the key inside the action so it does not depend on how the caller sourced it",
        )

    def test_workflow_passes_the_key_from_secrets(self) -> None:
        self.assertIn(
            "openai_api_key: ${{ secrets.OPENAI_API_KEY }}",
            self.workflow_text,
            "the reusable workflow must source the key from its `secrets:` block",
        )

    def test_every_declared_input_is_actually_used(self) -> None:
        """An input the action declares but never forwards is a silent no-op for callers."""
        runs = self.action_text.split("\nruns:", 1)[1]

        for name in action_inputs(self.action_text):
            self.assertIn(
                f"inputs.{name}",
                runs,
                f"action declares `{name}` but no step forwards it",
            )

    def test_action_runs_scripts_that_exist(self) -> None:
        referenced = re.findall(r"\$GITHUB_ACTION_PATH/(\S+\.py)", self.action_text)

        self.assertTrue(referenced, "the action should run the scripts, not reimplement them")
        for relative in referenced:
            self.assertTrue(
                (REPO_ROOT / relative).is_file(),
                f"action.yml runs {relative}, which does not exist at the repo root",
            )


# --- Helper parity -----------------------------------------------------------------------
# One copy of the helpers now ships (scripts/_regenerator.py). A second lives in
# scripts/context_regen_postprocess.py purely so the unit tests can import them -- nothing in
# production uses it, so it can drift unless something compares the two.

HELPERS_START = "def normalize_newline("
HELPERS_END = "content = ensure_recent_changes_section(content, git_log)"

# The helper region is exec'd without the module's own preamble, so seed what it closes over.
HELPERS_PREAMBLE = 'import re\nRECENT_HEADER = "Recent changes (last 7 days of git log):"\n'

# `template_skeleton` sits above the environment reads, so it can be lifted on its own.
SKELETON_START = "def template_skeleton("
SKELETON_END = "if not TEMPLATE_PATH.is_file():"

FRESHNESS_CASES = (
    "## Freshness\n\n- **Last reviewed:** 2026-01-01\n- **Generated by:** manual\n",
    "## Freshness\n- `last_reviewed`: 2026-01-01\n",
    "## Freshness\n\n- **Last reviewed:** 2026-01-01\n",
    "# Context\n\nNo freshness section here.\n",
    "## Freshness\n\n- **Last reviewed:** 2026-01-01\n\n"
    "Recent changes (last 7 days of git log):\nolder entry\n",
    "## Freshness\n\n- **LAST REVIEWED :**  2026-01-01\n",
)


@contextmanager
def cwd(path: Path):
    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


def load_helpers(source: str, label: str) -> dict:
    """Exec only the deterministic-helper definitions from a regenerator source.

    Deliberately bounded: executing further would reach the live OpenAI request.
    """
    try:
        start = source.index(HELPERS_START)
        end = source.index(HELPERS_END)
    except ValueError as exc:
        raise AssertionError(f"{label}: helper region not found ({exc})") from exc

    namespace: dict = {"__name__": "__helper_parity__"}
    exec(compile(HELPERS_PREAMBLE + source[start:end], label, "exec"), namespace)  # noqa: S102
    return namespace


def load_template_skeleton():
    """Lift `template_skeleton` out of _regenerator.py without running its preamble."""
    source = SCRIPT.read_text(encoding="utf-8")
    start, end = source.index(SKELETON_START), source.index(SKELETON_END)
    namespace: dict = {"__name__": "__skeleton__"}
    exec(  # noqa: S102
        compile(HELPERS_PREAMBLE + "PLACEHOLDER = re.compile(r'\\[([^\\[\\]\\n]*)\\]')\n"
                + source[start:end], "_regenerator.py", "exec"),
        namespace,
    )
    return namespace["template_skeleton"]


class HelperParityTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        from scripts import context_regen_postprocess

        self.copies = {
            "_regenerator.py": load_helpers(SCRIPT.read_text(encoding="utf-8"), "_regenerator.py"),
            "context_regen_postprocess.py": vars(context_regen_postprocess),
        }

    def assert_all_agree(self, call) -> None:
        results = {}
        for name, namespace in self.copies.items():
            try:
                results[name] = call(namespace)
            except KeyError as exc:
                self.fail(f"{name} is missing {exc}")

        reference_name, reference = next(iter(results.items()))
        for name, value in results.items():
            self.assertEqual(value, reference, f"{name} disagrees with {reference_name}")

    def test_upsert_freshness_bullet_agrees_across_copies(self) -> None:
        for case in FRESHNESS_CASES:
            for key, value in (("last_reviewed", "2026-09-02"), ("generated_by", "CI-generated")):
                with self.subTest(case=case[:40], key=key):
                    self.assert_all_agree(
                        lambda ns: ns["upsert_freshness_bullet"](case, key, value)
                    )

    def test_upsert_frontmatter_field_agrees_across_copies(self) -> None:
        md = '---\nrepo: old\ngenerated_by: "OpenAI"\n---\n\n# Context\n'

        for key, value in (("repo", "guidion-digital/x"), ("generated_by", "CI-generated")):
            with self.subTest(key=key):
                self.assert_all_agree(lambda ns: ns["upsert_frontmatter_field"](md, key, value))

    def test_recent_changes_helpers_agree_across_copies(self) -> None:
        with_block = "# Context\n\nRecent changes (last 7 days of git log):\nmodel invented this\n"
        without_block = "# Context\n\n## Freshness\n\n- **Last reviewed:** 2026-01-01\n"

        for md in (with_block, without_block):
            with self.subTest(md=md[:30]):
                self.assert_all_agree(
                    lambda ns: ns["ensure_recent_changes_section"](md, "abc feat: x")
                )
                self.assert_all_agree(lambda ns: ns["strip_recent_changes"](md))


class ReadmeUsageTests(unittest.TestCase):
    """The README's copy-paste examples are the caller-facing contract.

    They went stale once already -- an input was added and the example kept working while
    silently omitting it. Renaming or removing an input should break the docs loudly.
    """

    maxDiff = None

    def setUp(self) -> None:
        self.readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.workflow_inputs = set(workflow_call_inputs(WORKFLOW.read_text(encoding="utf-8")))
        self.action_inputs = set(action_inputs(ACTION.read_text(encoding="utf-8")))

    def usage_blocks(self) -> list:
        """(target, with-keys) for each fenced example that calls into this repo."""
        blocks = []

        for block in re.findall(r"```yaml\n(.*?)```", self.readme, re.S):
            match = re.search(rf"uses:\s*{re.escape(ACTION_REPO)}(\S*)@", block)
            if not match:
                continue

            keys, indent = [], None
            for line in block.splitlines():
                if re.match(r"\s*with:\s*$", line):
                    indent = len(line) - len(line.lstrip()) + 2
                    continue
                if indent is None:
                    continue
                key = re.match(rf" {{{indent}}}(\w+):", line)
                if key:
                    keys.append(key.group(1))
                elif line.strip() and not line.startswith(" " * (indent + 1)):
                    indent = None

            blocks.append((match.group(1), keys))

        return blocks

    def test_examples_exist_for_both_entry_points(self) -> None:
        targets = {target for target, _ in self.usage_blocks()}

        self.assertIn("", targets, "no example calls the action at the repo root")
        self.assertTrue(
            any(t.endswith("regenerate-context.yaml") for t in targets),
            "no example calls the reusable workflow",
        )

    def test_documented_inputs_all_exist(self) -> None:
        for target, keys in self.usage_blocks():
            declared = (
                self.workflow_inputs
                if target.endswith("regenerate-context.yaml")
                else self.action_inputs
            )
            for key in keys:
                with self.subTest(target=target or "action.yml", key=key):
                    self.assertIn(
                        key,
                        declared,
                        f"README documents `{key}`, which is not an input of {target or 'action.yml'}",
                    )


class TemplateConformanceTests(unittest.TestCase):
    """CONTEXT_TEMPLATE.md is the contract; the prompt's lists are a transcription of it.

    The lists cannot be replaced by the template at runtime, because `required_h2_headings`
    also feeds the quality gate -- a safety check should not depend on parsing a
    human-edited markdown file. So they stay, and this fails the build when they drift.
    """

    maxDiff = None

    def setUp(self) -> None:
        self.template = TEMPLATE.read_text(encoding="utf-8")
        self.script = SCRIPT.read_text(encoding="utf-8")

    def test_required_headings_match_the_template(self) -> None:
        from_template = ["## " + h for h in re.findall(r"(?m)^##\s+(.+?)\s*$", self.template)]
        from_code = re.findall(r'"(## [^"]+)"', self.script)

        self.assertEqual(
            from_code,
            from_template,
            "required_h2_headings has drifted from CONTEXT_TEMPLATE.md",
        )

    def test_required_frontmatter_fields_match_the_template(self) -> None:
        frontmatter = self.template.split("---", 2)[1]
        from_template = re.findall(r"(?m)^(\w+):", frontmatter)

        block = re.search(r"template_frontmatter_fields = \[(.*?)\]", self.script, re.S)
        self.assertIsNotNone(block, "template_frontmatter_fields not found")
        from_code = re.findall(r'"(\w+)"', block.group(1))

        self.assertEqual(
            from_code,
            from_template,
            "template_frontmatter_fields has drifted from CONTEXT_TEMPLATE.md",
        )

    def test_no_run_together_paragraph_blocks(self) -> None:
        """Consecutive plain lines render as one paragraph, not as separate items.

        Markdown collapses single newlines, so an enumeration written as bare lines --
        `**CI/CD:** ...` then `**Infra:** ...`, or three risk bullets without dashes -- comes
        out as a wall of text. Make it a list, or put a blank line between the items.
        """
        run: list[tuple[int, str]] = []

        for number, stripped in template_body_lines(self.template):
            plain = bool(stripped) and not stripped.startswith(("|", "#", "- ", "* ", "---"))

            if plain:
                run.append((number, stripped))
                continue

            self.assertLess(
                len(run), 2, f"these lines render as one paragraph: {run}"
            )
            run = []

        self.assertLess(len(run), 2, f"these lines render as one paragraph: {run}")

    def test_no_plain_line_directly_follows_a_list_item(self) -> None:
        """A bare line right after a `- ` item is folded into that item by markdown.

        Catches a single dropped dash in the middle of a list, which neither the
        run-together nor the label rule can see.
        """
        previous_was_item = False

        for number, stripped in template_body_lines(self.template):
            plain = bool(stripped) and not stripped.startswith(("|", "#", "- ", "* ", "---"))

            self.assertFalse(
                plain and previous_was_item,
                f"line {number} is swallowed into the list item above it: {stripped[:60]!r}",
            )
            previous_was_item = stripped.startswith(("- ", "* "))

    def test_label_lines_are_followed_by_a_list(self) -> None:
        """`Does not do (delegated to):` introduces items, so items have to look like items.

        A label followed by bare text reads as a list to a human and as a paragraph to
        markdown -- and to a model copying the shape, which is how generated files kept
        flattening the delegation half of the boundary into prose.
        """
        # The one label the code owns: its body is git log output, replaced on every run.
        machine_owned = "Recent changes (last 7 days of git log):"

        lines = template_body_lines(self.template)

        for position, (number, stripped) in enumerate(lines):
            is_label = (
                stripped.endswith(":")
                and not stripped.startswith(("#", "|", "- ", "* "))
                and stripped != machine_owned
            )
            if not is_label:
                continue

            following = next((text for _, text in lines[position + 1:] if text), "")
            self.assertTrue(
                following.startswith(("- ", "* ", "|")),
                f"line {number} `{stripped}` introduces items, but the next line is "
                f"{following[:60]!r} -- make it a list item",
            )

    def test_task_list_items_are_real_list_items(self) -> None:
        """`[ ] thing` is a paragraph; `- [ ] thing` is a checkbox."""
        for number, line in enumerate(self.template.splitlines(), start=1):
            if line.lstrip().startswith("[ ]"):
                self.fail(f"line {number} is a task item without a `- ` prefix: {line.strip()!r}")

    def test_template_frontmatter_is_valid_yaml_shape(self) -> None:
        """The prompt demands well-formed YAML; the template must not model otherwise.

        Checked without PyYAML (CI has no pip install): a list item under a `key:` has to
        start with `- `, which is what `main_stack` and `main_systems` originally did not.
        """
        frontmatter = self.template.split("---", 2)[1]

        for line in frontmatter.splitlines():
            if not line.strip():
                continue
            self.assertRegex(
                line,
                r"^(\w+:|\s+-\s|\s{2,}\S)",
                f"frontmatter line is neither a key nor a list item: {line!r}",
            )


class TemplateSkeletonTests(unittest.TestCase):
    """What actually gets sent: the template with anything copyable stripped out."""

    def setUp(self) -> None:
        self.skeleton = load_template_skeleton()(TEMPLATE.read_text(encoding="utf-8"))

    def test_worked_examples_are_removed(self) -> None:
        for leak in ("e.g.", "Customer CRM", "Salesforce FSL", "Home App", "POST /appointments"):
            self.assertNotIn(
                leak,
                self.skeleton,
                f"{leak!r} would be handed to the model as if it were content",
            )

    def test_load_bearing_shape_is_kept(self) -> None:
        for keep in (
            "Does:",
            "Does not do (delegated to):",
            "→ outbound",
            "| Domain object / data | Source of truth | This system role | Notes |",
            "- **Last reviewed:**",
            "the code wins",
            "The boundary matters.",
            "[ ]",
        ):
            self.assertIn(keep, self.skeleton, f"{keep!r} is shape the model needs")

    def test_every_required_heading_survives(self) -> None:
        for heading in re.findall(r'"(## [^"]+)"', SCRIPT.read_text(encoding="utf-8")):
            self.assertIn(heading, self.skeleton)

    def test_recent_changes_block_is_not_sent(self) -> None:
        """The code owns that section; a model given it would paraphrase the log."""
        self.assertNotIn("Recent changes (last 7 days of git log):", self.skeleton)


class GatherCliTests(unittest.TestCase):
    """The action invokes gather_context.py as a CLI, so the CLI has to work standalone."""

    def test_cli_writes_the_same_inputs_the_action_relies_on(self) -> None:
        import subprocess
        import sys

        with TemporaryDirectory() as workdir:
            repo = Path(workdir)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            repo.joinpath("thing.tf").write_text("resource {}\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
                 "commit", "-q", "-m", "init"],
                check=True,
            )

            with cwd(repo):
                result = subprocess.run(
                    [sys.executable, str(REPO_ROOT / "scripts/gather_context.py"),
                     "--context-file", "AI/CONTEXT.md", "--tree-dirs", "."],
                    capture_output=True,
                    text=True,
                )

            self.assertEqual(result.returncode, 0, result.stderr)
            for name in ("context.md", "readmes.txt", "git-log.txt", "repo-tree.txt"):
                self.assertTrue(repo.joinpath(".tmp", name).is_file(), f".tmp/{name} missing")


if __name__ == "__main__":
    unittest.main()
