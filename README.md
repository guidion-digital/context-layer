The [Guidion Context Layer](https://guidiondev.atlassian.net/wiki/spaces/DIG/pages/5882544147/Building+a+Guidion+Context+Layer+for+Enhanced+Architecture+and+AI-Assisted+Engineering) rationale.

---

# Bootstrapping You Repo

Before you start automatic re-generation of your repos `AI/CONTEXT.md` using the workflow (see below), you should first bootstrap it with the [context bootstrap skill](./SKILLS/bootstrap_context/PLAYBOOK.md). This requires running that prompt through an agent locally, on a fully cloned copy of the main branch. You'll need [the whole directory](./SKILLS/bootstrap_context/).

# Re-usable Workflow Usage

This re-usable workflow does everything: checks the repo out, decides whether anything has changed since the last regeneration, regenerates the file, and opens a PR. Example (see [the workflow](.github/workflows/regenerate-context.yaml) for every
input):

```yaml
name: Regenerate CONTEXT.md

on:
  schedule:
    - cron: "0 5 * * 1" # 07:00 Amsterdam time (CEST/UTC+2) every Monday
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

jobs:
  regenerate:
    uses: guidion-digital/context-layer/.github/workflows/regenerate-context.yaml@CHECK_LATEST_TAG
    with:
      tree_dirs: "."
      tree_depth: "4"
      repo_owner: "Cinfra"
      prompt_addition: |
        You are a technical documentation maintainer for a Terraform/AWS infrastructure
        repository at Guidion.
    secrets:
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

`tree_depth` is the input worth tuning. It defaults to `3`; on a monorepo, a plain `tree_dirs: "."` at depth `4` covers the tree more evenly and costs less than naming deeper directories by hand — see [Tuning the directory listing](#tuning-the-directory-listing).

> [!NOTE]
> If you need an `OPENAI_API_KEY`, you can ~~add your repo to [this list](https://github.com/guidion-digital/code-infrastructure/blob/master/guidion-digital/organisation.tf#L166) for access to the Guidion organisation one.~~ ask Cinfra (we'll change things back to code once we're done testing new repo bootstrapping)

## Using the action directly

The workflow reaches the regeneration logic through this repo's root `action.yml`, and you can call that action yourself if you need the regeneration to sit inside a job you already own. It is the same code, but it is only the middle of the job:

```yaml
jobs:
  regenerate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0 # the git-log input needs history

      - uses: guidion-digital/context-layer@CHECK_LATEST_TAG
        with:
          tree_dirs: "."
          tree_depth: "4"
          repo_owner: "Cinfra"
          openai_api_key: ${{ secrets.OPENAI_API_KEY }}

      # ...and now the file is sitting in the working tree, uncommitted, and the rest is
      # yours: decide whether it changed, commit it, open the PR.
```

You then own everything around it. The action writes the context file into the working tree and stops: no change detection, no commit, no PR. It also has no loop-breaker guard, so a scheduled job built this way regenerates on every run rather than only when the repo has
actually moved on since the last context PR. Its `case_variant` output names a tracked file differing from `context_file` only by case, if you want to clean the stray spelling up.

Prefer the re-usable workflow unless you specifically need this.

# Where the regeneration logic lives

Callers only ever touch the reusable workflow above. Behind it, the actual work is one copy of one thing:

```
CONTEXT_TEMPLATE.md                 the contract: sections, fields, table shapes, vocabularies
action.yml                          composite action: runs the two scripts below
scripts/gather_context.py           builds .tmp/{context.md,readmes.txt,git-log.txt,repo-tree.txt}
scripts/_regenerator.py             prompt, OpenAI call, deterministic post-processing
.github/workflows/regenerate-context.yaml
                                    checkout, loop-breaker guard, `uses: action.yml`, PR
```

`CONTEXT_TEMPLATE.md` is the single source of truth for what a context file looks like, and it reaches the model two ways. `_regenerator.py` sends it as a **skeleton** — the same document with its `[e.g. ...]` placeholders and worked example rows stripped, because handing a model `| Customer | Salesforce | Reads |` invites Salesforce rows into an infrastructure repo's file.
That is what carries the shape a heading list cannot: table columns, the `Does:` / `Does not do (delegated to):` pairing, the direction legend, the Freshness bullet style.

The required-headings and required-fields lists stay as Python literals rather than being parsed from the template at runtime, because `required_h2_headings` also feeds the quality gate, and a safety check should not depend on parsing a human-edited markdown file. `tests/test_regenerator_wiring.py` fails the build when they drift from the template.

The `Recent changes (last 7 days of git log):` block is the one section the code owns outright: the model is told not to write it, and `ensure_recent_changes_section` appends or rewrites it from the real git log on every run. Changes confined to that block do not count as a change for freshness purposes — a moving 7-day window is not a review.

The workflow reaches the action as `uses: guidion-digital/context-layer@<tag>`, not `./`. A reusable workflow cannot load a file from its own repository — `actions/checkout` and any relative `uses:` resolve against the _calling_ repo — but a remote composite action is fetched into the runner's action directory, separately from the workspace, and `$GITHUB_ACTION_PATH` points at it. Since `action.yml` sits at the repo root, that path _is_ the repo root, so the scripts stay where the tests and a manual local run already expect them. Callers need no extra token: the fetch uses the same repository Actions-access grant that already lets them resolve the reusable workflow.

`OPENAI_API_KEY` reaches the script as a step environment variable, never interpolated into a `run:` body — an expanded expression would land on a process command line, where anything else on the runner can read it. An action cannot declare `secrets:` (Actions gives actions no secrets context), so an input is the only mechanism, and it is what the first-party actions use. The action also calls `::add-mask::` on the value itself, because masking follows the value rather than the input name: a caller passing `secrets.OPENAI_API_KEY` gets masking for free, one passing a `vars.` entry would not. `tests/test_regenerator_wiring.py` enforces both.

### What the model is given

Four inputs, built by `gather_context.py` into `.tmp/`:

| Input           |                                                               |
| --------------- | ------------------------------------------------------------- |
| `context.md`    | the existing context file, or empty when there is none        |
| `readmes.txt`   | every tracked `README.md`, in full, root first                |
| `git-log.txt`   | seven days of `--oneline --stat`, automation commits excluded |
| `repo-tree.txt` | a directory listing — file _names_ only                       |

`readmes.txt` is the only input carrying file contents other than the context file itself. It exists because the tree lists names: the model could see that `projects/cloud-infra/networking/README.md` existed without reading a byte of the Transit Gateway explanation inside it, which is exactly where the best hand-written context files got their architectural notes. Discovered through `git ls-files`, so a local `terraform init` or a vendored dependency cannot inject text into the prompt. No cap — the largest README payload across the whole `guidion-digital` org is 8.7 KB.

### Tuning the directory listing

The listing carries names, not contents, so `tree_dirs` and `tree_depth` decide how much it can know. `tree_depth` was hardcoded at 2, which stops above the environment directories in a monorepo (`projects/web` but never `projects/web/development`) and produces noticeably vaguer files. It defaults to 3 and is now an input.

Raising the depth is usually better than naming deeper directories by hand — measured on
`guidion-digital/infrastructure`:

| `tree_dirs`                       | `tree_depth` | listing      |
| --------------------------------- | ------------ | ------------ |
| `.,projects,projects/cloud-infra` | 2            | 2,978 chars  |
| `.,projects,projects/cloud-infra` | 3            | 15,005 chars |
| `.`                               | 4            | 14,049 chars |

A plain `.` at depth 4 costs slightly less than the hand-tuned three-entry list at depth 3 and covers the tree evenly, so once depth is tunable most repos need nothing but `.`. Overlapping entries are de-duplicated and paths are repo-relative, so listing a directory that is already covered adds only what is genuinely new.

> [!IMPORTANT]
> The action reference is pinned, so **cutting a release means bumping it first**: set
> `uses: guidion-digital/context-layer@X.Y.Z` in `.github/workflows/regenerate-context.yaml`
> to the tag you are about to create, then tag. A workflow tagged `X.Y.Z` that still points at
> `X.Y.(Z-1)` runs the previous version's regenerator. `tests/test_regenerator_wiring.py`
> checks that the reference is a pinned semver tag on this repo, that the action's inputs and
> the workflow's line up, and that nobody has re-inlined the Python — it cannot check that the
> number is the _right_ one.

## Local tests

```sh
python3 -m unittest tests/test_context_regen_postprocess.py tests/test_gather_context.py tests/test_regenerator_wiring.py -v
```

| Suite                               | Covers                                                                                                                                                   |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_context_regen_postprocess.py` | deterministic post-processing: freshness bullets, frontmatter stamping, recent-changes replacement                                                       |
| `test_gather_context.py`            | the `.tmp/` inputs: READMEs, git log, tree depth, case-variant detection                                                                                 |
| `test_regenerator_wiring.py`        | the workflow → action → scripts wiring, secret handling, template conformance, the skeleton stripper, and helper parity between the two remaining copies |

These suites also run in CI via `.github/workflows/test-context-regenerator.yaml`.
