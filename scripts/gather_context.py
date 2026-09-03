#!/usr/bin/env python3
"""Build the `.tmp/` inputs that `_regenerator.py` reads.

`action.yml` runs this as a CLI and the reusable workflow calls that action, so CI goes
through the same path a manual run does. `gather()` stays importable for anything that wants
the inputs without the command line.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath

# The canonical context path. Exact, case included — a repo carrying any other spelling is
# corrected to this one rather than left alone.
DEFAULT_CONTEXT_FILE = "AI/CONTEXT.md"

# How far below each listed directory to walk. Was hardcoded at 2, which stopped above the
# environment directories in a monorepo -- `projects/web` but never `projects/web/development`
# -- and produced noticeably vaguer context files. `tree_dirs` existed mostly to work around
# it, by naming deeper directories by hand.
DEFAULT_TREE_DEPTH = 3

# Commits this automation creates. Excluded from the git log we show the model, so a freshly
# merged regeneration PR does not read as a repo change worth regenerating for.
AUTOMATION_GREPS = [
    "^chore: regenerate ",
    "^Merge pull request .* from .*/chore/context-update-",
]


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def find_case_variant(repo_root: Path, context_file: str = DEFAULT_CONTEXT_FILE) -> str | None:
    """Return a tracked path that differs from `context_file` only by case, if one exists.

    Reads the git index rather than the filesystem on purpose. The index records the exact case
    a path was committed under regardless of the filesystem underneath, whereas on a
    case-insensitive filesystem (APFS, the default on macOS) `AI/CONTEXT.md` and `ai/context.md`
    are the same directory entry and cannot be told apart by `find` or `os.listdir`.
    """
    target = context_file.lower()
    matches = [
        line
        for line in _git(repo_root, "ls-files").splitlines()
        if line.lower() == target and line != context_file
    ]

    if len(matches) > 1:
        raise RuntimeError(
            f"Multiple case-insensitive matches for {context_file}; clean up manually: {matches}"
        )

    return matches[0] if matches else None


def _write_context(repo_root: Path, tmp: Path, context_file: str, variant: str | None) -> None:
    canonical = repo_root / context_file
    source = canonical if canonical.is_file() else None

    if source is None and variant is not None:
        candidate = repo_root / variant
        if candidate.is_file():
            source = candidate

    tmp.joinpath("context.md").write_text(
        source.read_text(encoding="utf-8") if source else "",
        encoding="utf-8",
    )


def _write_readmes(repo_root: Path, tmp: Path) -> None:
    """Concatenate every tracked README into one input.

    The tree lists file *names*; nothing else in `.tmp/` carries file contents. So the model
    could see that `projects/cloud-infra/networking/README.md` existed and not a byte of the
    Transit Gateway explanation inside it -- which is where the best hand-written context
    files got their architectural notes from.

    Tracked files only, so a local `terraform init` or a stray build directory cannot inject
    text into the prompt. Root README first: it is the one that describes the whole repo.
    """
    readmes = [
        path for path in _git(repo_root, "ls-files").splitlines()
        if PurePosixPath(path).name.lower() == "readme.md"
    ]
    readmes.sort(key=lambda path: (path.count("/"), path))

    sections = []
    for relative in readmes:
        candidate = repo_root / relative
        if not candidate.is_file():
            continue
        try:
            body = candidate.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            continue
        if body:
            sections.append(f"--- {relative} ---\n{body}")

    tmp.joinpath("readmes.txt").write_text("\n\n".join(sections) + "\n" if sections else "",
                                           encoding="utf-8")


def _write_git_log(repo_root: Path, tmp: Path) -> None:
    args = ["log", "--oneline", "--stat", "--since=7 days ago", "--invert-grep"]
    for pattern in AUTOMATION_GREPS:
        args += ["--grep", pattern]

    tmp.joinpath("git-log.txt").write_text(_git(repo_root, *args), encoding="utf-8")


def _write_repo_tree(
    repo_root: Path, tmp: Path, tree_dirs: str, tree_depth: int = DEFAULT_TREE_DEPTH
) -> None:
    """List each requested directory, without repeating a path already listed.

    Overlapping entries are normal -- `.` and `projects` and `projects/cloud-infra` describe
    nested slices of one tree -- and every repetition is prompt budget spent saying the same
    thing twice. Leading `./` is dropped so the root listing shares a namespace with the rest
    and can actually be compared against it.
    """
    lines: list[str] = []
    seen: set[str] = set()

    def add(paths: list[str]) -> None:
        for path in sorted(paths):
            normalised = path[2:] if path.startswith("./") else path
            if normalised and normalised not in seen:
                seen.add(normalised)
                lines.append(normalised)

    for raw_dir in tree_dirs.split(","):
        directory = raw_dir.strip()
        if not directory:
            continue

        if directory == ".":
            lines.append("--- repo root ---")
            add(_find(repo_root, ".", exclude_dot_prefixes=True, max_depth=tree_depth))
        else:
            lines.append(f"--- {directory}/ ---")
            base = repo_root / directory
            if base.is_dir():
                add(_find(base, directory, exclude_dot_prefixes=False, max_depth=tree_depth))

    tmp.joinpath("repo-tree.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _find(
    base: Path, label: str, exclude_dot_prefixes: bool, max_depth: int = DEFAULT_TREE_DEPTH
) -> list[str]:
    """Port of `find <base> -maxdepth N [-not -path './.git*' -not -path './.tmp*']`.

    `exclude_dot_prefixes` reproduces a quirk of the shell original rather than a clean
    intention: the glob `./.git*` matches `./.github` and `./.gitignore` as readily as `./.git`.

    It applies to the `.` entry only, so this hides nothing a caller cannot get back -- naming
    `.github` in `tree_dirs` lists it as normal. What it is, is a surprising default: a
    directory silently dropped that you have to already know to ask for by name.

    Kept for parity with a second code path that generated context files outside CI. That path
    is gone, so nothing depends on the quirk any more and it is safe to drop.
    """
    found = [label]

    def descend(directory: Path, prefix: str, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = list(directory.iterdir())
        except OSError:
            return
        for entry in entries:
            path = f"{prefix}/{entry.name}"
            if exclude_dot_prefixes and (
                path.startswith("./.git") or path.startswith("./.tmp")
            ):
                continue
            found.append(path)
            if entry.is_dir() and not entry.is_symlink():
                descend(entry, path, depth + 1)

    descend(base, label, 1)
    return found


def gather(
    repo_root: Path,
    context_file: str = DEFAULT_CONTEXT_FILE,
    tree_dirs: str = ".",
    tree_depth: int = DEFAULT_TREE_DEPTH,
) -> str | None:
    """Write .tmp/{context.md,readmes.txt,git-log.txt,repo-tree.txt}. Returns the case variant."""
    repo_root = Path(repo_root)
    variant = find_case_variant(repo_root, context_file)

    tmp = repo_root / ".tmp"
    tmp.mkdir(exist_ok=True)

    _write_context(repo_root, tmp, context_file, variant)
    _write_readmes(repo_root, tmp)
    _write_git_log(repo_root, tmp)
    _write_repo_tree(repo_root, tmp, tree_dirs, tree_depth)

    return variant


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--context-file", default=DEFAULT_CONTEXT_FILE)
    parser.add_argument(
        "--tree-dirs",
        default=".",
        help='Comma-separated directories to summarise for the model. "." for the repo root.',
    )
    parser.add_argument(
        "--tree-depth",
        type=int,
        default=DEFAULT_TREE_DEPTH,
        help="How many levels below each listed directory to walk.",
    )

    args = parser.parse_args()
    variant = gather(args.repo_root, args.context_file, args.tree_dirs, args.tree_depth)

    if variant:
        print(f"Found case-mismatched context file: {variant}")

    # Surfaced as an action output so a caller can clean the stray path up. Written the
    # GitHub Actions way when running there, and simply skipped when running locally.
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write(f"case_variant={variant or ''}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
