# Building a Guidion Context Layer for Enhanced Architecture and AI/-Assisted Engineering

Shared context for better architecture decisions, onboarding, and AI-assisted engineering

## **Why we're doing this**

Every team knows its own piece of the system well. Nobody has a complete picture of how the pieces talk to each other.

This creates three concrete problems:

- New developers and product people spend weeks just understanding context
- Technical decisions (stack, tools, integrations) get made without knowing what already exists, leading to shadow stacks, duplicated solutions, or incompatible choices
- AI coding assistants (Cursor, Claude Code, Copilot, etc.) operate without company context and suggest solutions that don't fit our architecture

Guidion Context Layer fixes this by building a living, versioned, partially auto-generated context layer that describes every project, how it relates to the rest of the system, and which architectural constraints must be respected.

Beyond engineering, the same context supports business and product decisions: knowing which systems own which processes, what a proposed change would touch, and where a capability already exists makes it easier to scope initiatives, estimate effort, and avoid funding work that duplicates something we already have.

This is not documentation for documentation's sake.

The goal is to create a shared context layer for:

- onboarding developers and product people faster
- making better architectural decisions
- avoiding duplicated or incompatible solutions
- helping AI coding assistants understand our stack
- preparing the foundation for future agentic workflows and MCP-enabled agents
- lessening the need for product owners

In short:

We are building both a map and a nervous system for our technology stack.

## **How it works**

The system has three layers:

```
each repo
    └── AI/CONTEXT.md     ← written by the team, auto-refreshed weekly in CI
    ↓
weekly aggregation job    ← scheduled cron, not triggered per-commit
    ↓
company-context-ai.md     ← dense, structured — for Cursor, Claude Code, agents
company-context.md        ← narrative, readable — for Confluence, onboarding, product
```

**Where these files live:** each `CONTEXT.md` lives at `AI/CONTEXT.md` (case-sensitive). The company-level files (`company-context.md`, `company-context-ai.md`, and the derived matrices) are written to a single [central context index](https://github.com/guidion-digital/gcl-master-layer), produced by the weekly aggregation job that reads every repo's `CONTEXT.md`. So there are two distinct layers: per-repo context (one file per repo, owned by that team) and company context (the consolidated view, living centrally).

Over time, the company-level context can also generate additional views:

- integration matrix
- ownership matrix
- source-of-truth matrix
- active migrations/roadmap view
- AI assistant constraints summary
- architecture impact map

## A few important design decisions

### Full regeneration, not incremental patching

When a repo's CI updates CONTEXT.md, the LLM reads the current codebase and rewrites the whole file from scratch. It does not try to merge diffs. This keeps the file coherent over time and prevents the accumulation of stale fragments. Incremental merging sounds elegant, but breaks down quickly when multiple LLM-generated sections conflict.

The history lives in Git, not in the file. Because every regeneration is a commit, the diff between versions already captures _what_ changed — so the generator should put the _why_ in a descriptive commit message (what triggered the refresh, which sections changed, and the reason) instead of trying to keep changelogs inside CONTEXT.md itself. `git log` on the file then gives a clean timeline, and `git annotate` / `git blame` lets both us and agents trace any given line back to the commit that introduced it.

This is useful for humans debugging why something changed, and for agents that need provenance before trusting a piece of context.

### Aggregation is scheduled, not event-driven

The main company context files are regenerated once a week or once a month. Frequency is configurable.

There is no need for real-time propagation.

A weekly snapshot is accurate enough for onboarding, AI context, and architectural decisions. It also keeps costs low and the process simple.

### Repos refresh weekly, not on every commit

The CI job that updates CONTEXT.md runs on a weekly schedule against the latest state of main, not on every merge.

If the main (prod) branch hasn't changed since the last successful run, the weekly job skips entirely — many repos only change a few times a year, so this keeps cost and noise at zero for them.

This reduces noise and cost while keeping documentation reasonably fresh.

Teams (and possibly agents) can also trigger it manually after significant changes.

## Technical approach — is this actually viable?

Yes. What the LLM does per repo:

It reads the codebase or a targeted subset:

- README
- integration files
- API definitions
- infrastructure config
- CI/CD files
- relevant metadata
- recent PRs are useful
- existing CONTEXT.md

Then it produces an updated version of CONTEXT.md. Input is bounded and predictable. Cost per run is low.

**What to avoid:**

Do not try to diff two CONTEXT.md files and surgically merge changes into the main company markdown.

This feels precise, but produces incoherent output over time. LLM-generated prose from different models, at different times, with different styles, does not merge cleanly.

The real risk is not technical. It is governance.

To manage this:

- every CONTEXT.md includes a last_reviewed date
- every repo has a clear owner
- stale context is flagged, not blocked
- AI-generated changes should create PRs, not commit directly to main
- high-criticality repositories should be validated by a tech lead
- The weekly aggregation reads review_confidence, validated_by, and last_reviewed from each CONTEXT.md: low-confidence or stale files are flagged or excluded from the company context instead of being treated as equally true.

**Feedback loop — LessonsLearned.md**

Because each CONTEXT.md is regenerated from scratch, the generator has no memory of past corrections and tends to repeat the same mistakes. To prevent this, each repo keeps a short `LessonsLearned.md` in the `AI` folder (a few bullet points, owner-maintained) listing recurring generation errors e.g. "integration X is inbound, not outbound", "do not list the legacy auth flow, it's deprecated". This file is fed into the generation prompt alongside the codebase.

It is a correction memory, not documentation: keep it short, and prune entries once the generator stops making the mistake. The entry is added by whoever reviews the weekly regeneration, at the moment they correct an error, so the review that already happens becomes the trigger.

## **MCP readiness**

The Guidion Context Layer is not an MCP server. It is the knowledge base and context model that a future MCP server can expose to AI agents.

The distinction:

Guidion Context Layer = what we know about the stack

MCP server = how agents access that knowledge and interact with tools

This means the Context Layer prepares us for future MCP-enabled workflows, such as:

- finding all systems that touch a given object or business process
- checking which system is the source of truth for a domain object
- retrieving architectural constraints before modifying a repo
- identifying owners of systems and integrations
- validating whether a proposed solution fits the existing architecture
- generating onboarding briefs for a team, system, or domain
- preparing architecture review drafts

A future MCP server could expose resources and tools such as:

`get_repo_context(repo_name)`

`get_system_context(system_name)`

`find_systems_touching_object("ServiceAppointment")`

`get_source_of_truth("Appointment")`

`list_integrations_between("Home App", "Salesforce FSL")`

`get_architectural_constraints(repo_name)`

`search_company_context(query)`

`check_architecture_fit(proposed_solution)`

The first version of this should be read-only.

- No write actions.
- No deployment actions.
- No Salesforce mutations.
- No production changes.

The goal is to first make our context accessible and reliable. Execution can come later, with approvals, access control, and audit logs.

## **Template CONTEXT.md**

Copy [this template](./CONTEXT_TEMPLATE.md) and fill it in for your repo.

## **FAQ**

**Do I have to use exactly this format?**

The main sections are mandatory.

You can add domain-specific sections, but do not remove existing ones.

If a section does not apply, write n/a with a short explanation.

**Who fills in the file?**

The team that owns the repo, with input from the tech lead.

This is a team artefact, not a one-person job.

**How often does it need to be updated?**

Whenever integrations, stack, source-of-truth ownership, exposed APIs, or relevant architectural decisions change.

From Phase 2 onward, technical sections can be auto-regenerated weekly by CI. The team's job will be to validate and keep the roadmap, risks, source-of-truth notes, and architectural decisions current.

**Can I use an LLM to write the first version?**

Yes — encouraged.

Give the model:

- the repo README
- the main integration files
- API definitions
- infrastructure files
- this template

You should have a solid draft quickly.

Validate with the tech lead before committing.

**What if a repo doesn't change for months?**

We flag repositories where context is older than 60 days on active or high-criticality projects for manual review, and we route the flag to the repo owner rather than to a shared channel where it gets ignored.

This is a prompt, not a hard block — but on business-critical repositories, an unreviewed flag older than 90 days is escalated to the tech lead in the architecture review cadence. This ensures accountability.

**Why weekly and not on every commit?**

Regenerating on every merge would create noise, unnecessary cost, and potential conflicts.

A weekly snapshot is accurate enough for the use cases this serves:

- onboarding
- AI context
- architectural decisions
- integration awareness
- future MCP-enabled workflows

Teams can always trigger a manual refresh after a significant change.

## **Success criteria**

This project is successful if:

- a new developer reaches first meaningful PR on a connected system measurably faster than the current baseline (measure onboarding time before rollout on the pilot repos, compare after)
- tech leads can see dependencies before making architectural decisions
- duplicated solutions become easier to detect
- AI coding assistants produce more architecture-aware suggestions
- ownership and source-of-truth boundaries become clearer
- future MCP-enabled agents have reliable context to query
- Business decisions can be more intelligently made

The goal is not to create more documentation.

The goal is to create the shared context infrastructure required for better engineering, better architecture, and safer AI-assisted workflows.

## Follow-up ideas

### 1) Idea: org metadata snapshots (retrieve-only)

**Status:** idea / not implemented
**Raised from:** `tkt-partner-api` context review (Rest Route / partner contract CMDT visibility)

#### Problem

Important runtime configuration (especially Custom Metadata) often lives only in the org. Package repos and `ai/context.md` files then drift from what is actually configured (e.g. `gui_utl__Rest_Route__mdt`, partner API transition and response-filter CMDT). Editing that config in the org should not require treating it as package source that gets redeployed and overwritten.

#### Proposed approach

- **Retrieve only** (never deploy from this path): scheduled or on-demand `sf project retrieve` of an **allowlisted** set of CMDT types.
- **GitHub Actions**: cron + `workflow_dispatch`; auth via existing CI Connected App / JWT pattern; commit or open a PR when the snapshot changes.
- **Shared how, local what**:
  - Reusable workflow in `sf-workflows` (auth, retrieve, commit/PR).
  - Each relevant repo owns its allowlist and snapshot directory (e.g. `ai/org-snapshots/<env>/`).
- **Not its own repo** by default — snapshots should sit next to the package/app that needs the context. A central config inventory repo is optional later if ops needs a single dump.
- **Per environment**: separate trees (e.g. `uat/` vs `prod/`); start with one primary env (prod or main UAT).
- **Scope**: only “important metadata banks” (routes, API contracts, similar). Skip high-churn or secrets-adjacent config.

#### Explicit non-goals

- Not deployable package source; do not merge snapshots into `src/` paths that release pipelines deploy.
- Not a full org metadata backup.
