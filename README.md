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

jobs:
  regenerate:
    uses: guidion-digital/context-layer/.github/workflows/regenerate-context.yaml@b1b1841bbe672fb196d6e53d5ed62421369f3134
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
```

> [!NOTE] If you need an `OPENAI_API_KEY`, you can add your repo to [this list](https://github.com/guidion-digital/code-infrastructure/blob/master/guidion-digital/organisation.tf#L166) for access to the Guidion organisation one
