The [Guidion Context Layer](https://guidiondev.atlassian.net/wiki/spaces/DIG/pages/5882544147/Building+a+Guidion+Context+Layer+for+Enhanced+Architecture+and+AI-Assisted+Engineering) rationale.

---

# Re-usable Workflow Usage

You can give your repos a `CONTEXT.md` with the re-usable workflow found in this repo. Example usage:

```yaml
name: Regenerate CONTEXT.md

on:
  schedule:
    - cron: "0 5 * * 1" # 07:00 Amsterdam time (CEST/UTC+2) every Monday
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write
  statuses: write

jobs:
  regenerate:
    uses: guidion-digital/context-layer/.github/workflows/regenerate-context.yaml@0.0.2
    with:
      context_file: CONTEXT.md
      base_branch: master
      tree_dirs: ".,projects,cloud-infra"
      model: gpt-5.3-codex
      prompt_addition: |
        You are a technical documentation maintainer for a Terraform/AWS infrastructure
        repository at Guidion.
    secrets:
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}

  set_freshness_when_unchanged:
    needs: regenerate
    if: needs.regenerate.outputs.changed == 'false'
    uses: guidion-digital/context-layer/.github/workflows/set-freshness.yaml@0.0.2
    with:
      context_name: CONTEXT.md
      sha: ${{ github.sha }}
```

The above example includes a call to the `set-freshness` workflow, which sets a freshness date in your repo's metadata when no PR is generated for lack of meaningful changes to your context. You will also need the following workflow to update the freshness date when there _is_ a PR merge:

```yaml
name: Set Freshness Status On Context Merge

on:
  pull_request:
    types: [closed]

permissions:
  contents: read
  statuses: write

jobs:
  set-freshness:
    if: >
      github.event.pull_request.merged == true &&
      github.event.pull_request.base.ref == github.event.repository.default_branch &&
      startsWith(github.event.pull_request.head.ref, 'chore/context-update-')
    uses: guidion-digital/context-layer/.github/workflows/set-freshness.yaml@0.0.2
    with:
      context_name: CONTEXT.md
      sha: ${{ github.event.pull_request.merge_commit_sha }}
```

> [!NOTE]
> If you need an `OPENAI_API_KEY`, you can add your repo to [this list](https://github.com/guidion-digital/code-infrastructure/blob/master/guidion-digital/organisation.tf#L166) for access to the Guidion organisation one.

You can get freshness date out of your repo with something like:

```sh
gh api repos/guidion-digital/code-infrastructure/statuses/master | jq '[.[] | select(.context | startswith("context-freshness/"))]'
```

where `master` is your default branch.
