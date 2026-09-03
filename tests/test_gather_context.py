import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from gather_context import DEFAULT_CONTEXT_FILE, find_case_variant, gather


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout


def commit(repo: Path, message: str) -> None:
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", message)


class GatherTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "repo"
        self.repo.mkdir()

        git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "README.md").write_text("hi\n")
        git(self.repo, "add", "README.md")
        commit(self.repo, "initial commit")

        self.addCleanup(self._tmp.cleanup)

    def add_context(self, path: str, body: str) -> None:
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        git(self.repo, "add", "--", path)
        commit(self.repo, f"add {path}")


class TestGather(GatherTestCase):
    def test_writes_the_three_inputs_the_regenerator_reads(self):
        nested = self.repo / "src" / "app"
        nested.mkdir(parents=True)
        (nested / "main.py").write_text("x\n")

        gather(self.repo)

        tmp = self.repo / ".tmp"
        for name in ("context.md", "readmes.txt", "git-log.txt", "repo-tree.txt"):
            self.assertTrue(tmp.joinpath(name).is_file(), f"{name} missing")

        tree = tmp.joinpath("repo-tree.txt").read_text()
        self.assertIn("--- repo root ---", tree)
        # Paths are repo-relative; the `./` the shell original emitted is normalised away so
        # the root listing shares a namespace with the explicitly listed directories.
        self.assertIn("README.md", tree)
        self.assertNotIn("./README.md", tree)
        self.assertIn("src/app/main.py", tree)

    def test_tree_depth_bounds_the_listing(self):
        deep = self.repo / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)
        (deep / "leaf.py").write_text("x\n")

        gather(self.repo, tree_depth=2)
        shallow = (self.repo / ".tmp" / "repo-tree.txt").read_text()

        gather(self.repo, tree_depth=4)
        deeper = (self.repo / ".tmp" / "repo-tree.txt").read_text()

        self.assertIn("a/b", shallow)
        self.assertNotIn("a/b/c", shallow)
        self.assertIn("a/b/c/d", deeper)
        self.assertNotIn("a/b/c/d/leaf.py", deeper)

    def test_overlapping_tree_dirs_are_not_listed_twice(self):
        nested = self.repo / "projects" / "web"
        nested.mkdir(parents=True)
        (nested / "main.tf").write_text("x\n")

        gather(self.repo, tree_dirs=".,projects")
        tree = (self.repo / ".tmp" / "repo-tree.txt").read_text()

        self.assertEqual(
            tree.count("projects/web/main.tf"),
            1,
            "an overlapping tree_dirs entry repeated a path already listed",
        )
        self.assertIn("--- projects/ ---", tree)

    def test_readmes_are_sent_in_full_root_first(self):
        """The tree lists names; this is the only input carrying file contents."""
        nested = self.repo / "projects" / "networking"
        nested.mkdir(parents=True)
        (nested / "README.md").write_text("So, You Want Internet Access\n", encoding="utf-8")
        (self.repo / "README.md").write_text("# Root\n\nWorkspaces are named X-Y-Z.\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        commit(self.repo, "add readmes")

        gather(self.repo)
        out = (self.repo / ".tmp" / "readmes.txt").read_text()

        self.assertIn("Workspaces are named X-Y-Z.", out)
        self.assertIn("So, You Want Internet Access", out)
        self.assertIn("--- projects/networking/README.md ---", out)
        # Root first: it is the one describing the whole repo.
        self.assertLess(out.index("--- README.md ---"), out.index("--- projects/"))

    def test_untracked_readmes_are_not_sent(self):
        """Only tracked files, so a local build directory cannot inject prompt text."""
        stray = self.repo / ".terraform" / "modules" / "vendored"
        stray.mkdir(parents=True)
        (stray / "README.md").write_text("VENDORED THIRD PARTY DOCS\n", encoding="utf-8")

        gather(self.repo)

        self.assertNotIn(
            "VENDORED THIRD PARTY DOCS",
            (self.repo / ".tmp" / "readmes.txt").read_text(),
        )

    def test_readmes_file_is_written_even_with_no_readmes(self):
        git(self.repo, "rm", "-q", "README.md")
        commit(self.repo, "drop readme")

        gather(self.repo)

        self.assertEqual((self.repo / ".tmp" / "readmes.txt").read_text(), "")

    def test_context_md_is_empty_when_repo_has_no_context_file(self):
        gather(self.repo)

        self.assertEqual((self.repo / ".tmp" / "context.md").read_text(), "")

    def test_automation_commits_are_excluded_from_the_git_log(self):
        (self.repo / "a.txt").write_text("a\n")
        git(self.repo, "add", "a.txt")
        commit(self.repo, "feat: a real change")

        (self.repo / "b.txt").write_text("b\n")
        git(self.repo, "add", "b.txt")
        commit(self.repo, f"chore: regenerate {DEFAULT_CONTEXT_FILE}")

        gather(self.repo)
        log = (self.repo / ".tmp" / "git-log.txt").read_text()

        self.assertIn("feat: a real change", log)
        self.assertNotIn("chore: regenerate", log)

    def test_dot_git_glob_quirk_of_the_shell_original_is_reproduced(self):
        workflows = self.repo / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yaml").write_text("on: push\n")

        gather(self.repo)
        tree = (self.repo / ".tmp" / "repo-tree.txt").read_text()

        # `-not -path './.git*'` swallows .github too. Asserted so the default stays visible
        # rather than becoming folklore; nothing depends on it any more.
        self.assertNotIn(".github", tree)

    def test_dot_directories_are_listed_when_named_explicitly(self):
        """The `.git*` exclusion applies to the `.` entry only.

        Pinned because it is easy to read the exclusion as "workflows are unreachable" when
        it only means "not by default".
        """
        workflows = self.repo / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yaml").write_text("on: push\n")

        gather(self.repo, tree_dirs=".,.github")
        tree = (self.repo / ".tmp" / "repo-tree.txt").read_text()

        self.assertIn("--- .github/ ---", tree)
        self.assertIn(".github/workflows/ci.yaml", tree)

    def test_tree_dirs_selects_additional_directories(self):
        (self.repo / "infra").mkdir()
        (self.repo / "infra" / "main.tf").write_text("x\n")

        gather(self.repo, tree_dirs=".,infra")
        tree = (self.repo / ".tmp" / "repo-tree.txt").read_text()

        self.assertIn("--- infra/ ---", tree)
        self.assertIn("infra/main.tf", tree)

    def test_missing_tree_dir_is_skipped_rather_than_raising(self):
        gather(self.repo, tree_dirs=".,does-not-exist")

        self.assertIn("--- does-not-exist/ ---", (self.repo / ".tmp" / "repo-tree.txt").read_text())


class TestCaseVariant(GatherTestCase):
    def test_canonical_path_reports_no_variant(self):
        self.add_context(DEFAULT_CONTEXT_FILE, "---\nrepo: x\n---\n\n# Context\n")

        self.assertIsNone(find_case_variant(self.repo))
        self.assertIsNone(gather(self.repo))

    def test_variant_is_found_with_its_original_casing(self):
        self.add_context("ai/context.md", "---\nrepo: x\n---\n\n# Old spelling\n")

        # Detected via `git ls-files`, so this holds on APFS where the two spellings collide.
        self.assertEqual(find_case_variant(self.repo), "ai/context.md")

    def test_variant_content_seeds_context_md(self):
        self.add_context("ai/context.md", "---\nrepo: x\n---\n\n# Old spelling\n")

        variant = gather(self.repo)

        self.assertEqual(variant, "ai/context.md")
        self.assertIn("# Old spelling", (self.repo / ".tmp" / "context.md").read_text())

    def test_multiple_variants_raise_rather_than_guessing(self):
        self.add_context("ai/context.md", "one\n")

        # Only reachable on a case-sensitive filesystem; on APFS the second add collides.
        try:
            self.add_context("AI/Context.md", "two\n")
        except subprocess.CalledProcessError:
            self.skipTest("case-insensitive filesystem cannot hold both spellings")

        if len(git(self.repo, "ls-files").splitlines()) < 3:
            self.skipTest("case-insensitive filesystem collapsed the two spellings")

        with self.assertRaises(RuntimeError):
            find_case_variant(self.repo)


if __name__ == "__main__":
    unittest.main()
