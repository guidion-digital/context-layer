---
id: bootstrap-context
title: Bootstrap CONTEXT.md
version: 1.1.0
intent: first-generation-of-a-repo-context-file
requires:
  - local-clone-of-target-repo
  - file-write
  - git-history
mode: read-write
---

# Bootstrap CONTEXT.md

Use this playbook to create the initial generation of the `AI/CONTEXT.md` file.

This is a one-time bootstrap. Once the file exists, the reusable
`regenerate-context.yaml` workflow keeps it fresh on a weekly schedule.

This file is plain instructions, not tied to a specific LLM vendor or tool.

## What this playbook is guarding against

The failure mode is not a missing file. It is a *plausible* file: one that names
the right directories, lists the right technologies, and tells a reader nothing
they could not have got from `ls`. That file passes review, gets aggregated, and
quietly teaches every downstream agent a shallow model of the system.

Structural signals — file listings, resource counts, grep censuses — tell you
what *kinds* of thing exist. They do not tell you how the system works. The
difference between a useful context file and a plausible one is whether you
opened the code.

Budget accordingly: expect the read to take most of the effort, and the writing
to be comparatively quick.

## Step 0 — Establish scope and policy

Before reading anything, settle four things.

**Does `AI/CONTEXT.md` already exist?** If it does — in the working tree or in
`git log` — this is a re-bootstrap, not a first generation. Proceed, but treat
the existing file as unvalidated output, **not** as a model. Conform to
`CONTEXT_TEMPLATE.md`, not to the existing file's shape; a previous generator
may have used a looser template. Diff your result against it and, in the PR,
justify every structural deviation and every metadata field you changed.

**Who owns this repo?** Read `.github/CODEOWNERS` rather than trusting a
workflow input or directory name. Note per-path owners — they are real
ownership boundaries and belong in the file.

**Is there an `AI/LessonsLearned.md`?** If so, read it first and treat every
entry as binding: it records corrections a human already made to a previous
generation. If it does not exist, you will create it in Step 4.

**What is the disclosure policy?** Default, unless the repo owner says
otherwise:

> Identifiers already committed to this repo — account IDs, role and resource
> names, ARNs, resource IDs, CIDRs, hostnames, domain names, partner and client
> names — **belong in the file**. The context layer's value depends on them. Do
> not mask, abbreviate, or generalise them.
>
> Never record secret values, or any string that embeds a live credential:
> webhook URLs with an integration token, presigned URLs, connection strings,
> API keys. Reference these by host and source file instead, and flag them to
> the owner as rotation candidates.

Publishing a masked identifier costs the reader real value; publishing a live
token costs the company a credential. Those are not symmetric, so the policy is
not "be cautious with both".

## Step 1 — Read intent

Read [INTENT.md](./INTENT.md) to understand what `AI/CONTEXT.md` is for, who
consumes it, and how the weekly company-level aggregation uses its metadata.

## Step 2 — Read the code

This is the step that determines whether the output is worth anything.

### Coverage floor

Open **in full** — not by filename, not by grep:

- The README, and any nested READMEs
- Every root module's provider, backend, and variable configuration
- The shared/platform directory in its entirety, if the repo has one
- All identity, networking, and security configuration
- Repo-level agent guidance (`AGENTS.md`, `CLAUDE.md`, `.cursor/`)
- Every CI/CD workflow
- At least one representative unit per business domain or product area

If you have read fewer than ~20 files in full, or under 10% of the repo's
source files, you are not ready to write.

### Density check

A large repo does not yield a faithful context file in 200 lines. If your draft
feels short relative to the repo, you skimmed — go back. Record honestly in the
Freshness section which areas you read in full and which you characterised
structurally.

### Hunt for what a newcomer would trip over

Generic risks ("IAM changes are risky") are near-worthless. Specific ones are
the whole point of the Known risks section. At minimum:

- `grep -rn 'FIXME\|TODO\|HACK\|XXX\|deprecated'` — in-repo debt markers are the
  owners telling you where the bodies are buried
- **Silent-failure patterns:** error-swallowing defaults (`try()`, `lookup()`
  with fallbacks, `|| true`, bare `rescue`/`except`), filters that drop
  malformed entries rather than failing, iterations over a possibly-empty
  collection that therefore skip validation
- **Dangling references:** a key used to index a map or list where that key no
  longer exists
- **Labels that disagree with wiring:** a resource named X attached to Y
- **Overly broad grants:** `"*"`, `0.0.0.0/0`, `authorize_all_groups`, wildcard
  principals
- **Hardcoded identifiers** that duplicate something derivable, and will drift
  when the underlying resource is recreated
- **Naming contracts:** comments saying another system looks a resource up by
  name. These are interfaces; record them as such.

When something looks wrong, establish *what kind* of wrong before writing it
down:

```sh
git log -S '<the suspicious string>' --oneline -- <path>
```

Distinguish intentional, dormant, and actually-broken, and say which. "May be
inconsistent — verify" is weak. "Dormant because its `for_each` currently
matches nothing; the moment X happens, Y breaks" is what a reader can act on.

### Ask what table this repo type most needs

`CONTEXT_TEMPLATE.md` is deliberately generic. Adding one domain-specific
section is usually the highest-value thing you can do:

- Infrastructure repos → an account / environment / workspace inventory
- Service repos → an endpoint or event-contract inventory
- Data repos → a dataset, lineage, or schema-ownership inventory
- Monorepos → a package-to-owner-to-deploy-target map

Mandatory sections stay. Add, do not replace.

## Step 3 — Write AI/CONTEXT.md

Generate `AI/CONTEXT.md` — that exact, case-sensitive path.

Follow [CONTEXT_TEMPLATE.md](./CONTEXT_TEMPLATE.md): it is the source of truth
for sections, fields, table shapes, and vocabularies. Where the template
specifies a **table**, write a table — prose does not aggregate into the
company-level integration, ownership, and source-of-truth matrices. Keep every
mandatory section; where one genuinely does not apply, write `n/a` with a short
explanation rather than removing it.

### Metadata

`criticality`, `generated_by`, and `review_confidence` are controlled
vocabularies read by the weekly aggregation. Use them exactly.

For `review_confidence`:

- `low` — first generation, or regenerated with no human validation since.
  **Every bootstrap output is `low`.**
- `medium` — a human has reviewed it against the code at least once.
- `high` — the owner or tech lead has validated it and re-verified it since the
  last significant change.

Thoroughness of *generation* never raises this — only human validation does. A
thorough unvalidated draft is still `low`; explain why in the Freshness body
rather than inflating the field. Being flagged as unvalidated is the correct
state for a draft, and the aggregation depends on that signal meaning something.

Set `validated_by` to `none`. It is a parsed field, not a place for a sentence.

If you change a metadata value that a previous generation had set — especially
`criticality` — do not do it silently. Raise it in the PR as an explicit
question for the owner.

### The machine-maintained tail

The file must end with exactly this shape — heading, blank line, the template's
HTML comment, blank line, then the raw `git log` output with no code fence:

```
Recent changes (last 7 days of git log):

<!-- ...the comment block from the template, unchanged... -->

<output of: git log --oneline --stat --since="7 days ago">
```

The heading line must appear **exactly once** and be byte-identical, colon
included: the regeneration workflow matches that literal string and replaces
everything below it. Do not wrap the log in a fence, and do not put anything
after it.

## Step 4 — Seed AI/LessonsLearned.md

If it does not already exist, create `AI/LessonsLearned.md`. `INTENT.md`
specifies it as the correction memory fed into every future generation prompt —
without it, the regenerator repeats the same mistakes forever, because full
regeneration gives it no memory of past fixes.

Seed it with what *this* run got wrong or nearly got wrong, and with anything a
naive reader of the code would misread. Keep entries short and imperative. It
is a correction memory, not documentation: prune entries once the generator
stops making the mistake.

## Step 5 — Verify before opening the PR

Run [verify.sh](./verify.sh) from the repo root:

```sh
bash skills/bootstrap_context/verify.sh
```

It checks template conformance, controlled vocabularies, the machine-maintained
tail, and — most importantly — that **every identifier cited in the file
actually exists in tracked source**. That last check catches invented ARNs and
mistyped account IDs, the failure mode that most damages a reader's trust in
everything else in the file.

Fix what it reports. A clean run is not proof the content is right, only that it
is well-formed and not fabricated.

## Step 6 — Emit the weekly regeneration steering

The weekly workflow regenerates this file **from scratch**, so whatever steering
it carries determines the quality of every future generation. A bootstrap that
produces a deep file but leaves the workflow's `prompt_addition` at a one-line
description has bought one good week.

Update `prompt_addition` in `.github/workflows/regenerate-context.yaml` to carry
forward what this run established: the depth mandate, the disclosure policy, the
domain-specific sections this repo needs, and the naming contracts that must not
be renamed.

Check also that the upstream reusable workflow's template matches
`CONTEXT_TEMPLATE.md`. If the previous generation's shape suggests otherwise —
prose where the template specifies tables is the tell — say so plainly in the
PR: this draft will be flattened on the next scheduled run unless upstream is
aligned or pinned first. Flag it; do not silently accept it.

## Step 7 — Review before it lands

Open a pull request; do not commit to the main branch. The first generation is a
draft to be validated by the repo owner or tech lead before merging.

Stage only the files this playbook produced. Leave unrelated working-tree
changes alone.

The PR body must state:

- Which areas you read in full and which you characterised structurally
- Any metadata value you changed from a previous generation, as an explicit
  question for the owner
- Anything you found that looks like a live defect or a security-relevant
  default, called out separately from the file itself so it is not missed
- Any live credential you found committed, named by file and flagged for
  rotation — never reproduced
- Whether the weekly regeneration will preserve or clobber this file's structure
