---

repo: [repo name]
project_name: [project / system name]
owner: [team or person responsible]
domain: [e.g. field-service, customer-care, data, mobile, integrations]
criticality: [low / medium / high / business-critical]
summary: [What is this repo for, what does the code do]
main_stack:
  - [e.g. Salesforce Apex]
  - [e.g. React Native]
  - [e.g. Node.js]
  - [e.g. Terraform]
main_systems:
  - [e.g. Salesforce FSL]
  - [e.g. AWS API Gateway]
  - [e.g. Home App]
last_reviewed: [YYYY-MM-DD]
review_confidence: [low / medium / high]
generated_by: [manual / AI-assisted / CI-generated]
validated_by: [person or team]
---

# [Project / repo name]

## Overview

<!-- 2-4 lines. What this system does, who uses it, why it exists. -->

- **Owner:** [Team or person responsible]
- **Main stack:** [e.g. Salesforce Apex, React Native, Python, Terraform/AWS]
- **Environment:** [e.g. Salesforce production org + sandbox | AWS eu-west-1 | both]

---

## Purpose and responsibilities

<!-- What this system does and what it explicitly does NOT do. The boundary matters. -->

Does:

- ...

Does not do (delegated to):

- ... → [name of responsible system]

---

## Source of truth / data ownership

<!-- Which business objects or data domains this system owns, reads, writes, or only displays. -->

| Domain object / data | Source of truth | This system role | Notes |

|---|---|---|---|

| Customer | Salesforce | Reads | Customer CRM is owned by Salesforce |
| Appointment | Salesforce FSL | Reads/writes status | Scheduling logic lives in FSL |
| Photos | AWS S3 | Writes | Uploaded from mobile app |
| [object/data] | [system] | [owns / reads / writes / displays] | [notes] |

---

## External integrations

<!-- Every system this repo integrates with. -->

| System          | Type       | Direction   | Notes                                   |
| --------------- | ---------- | ----------- | --------------------------------------- |
| Salesforce FSL  | REST API   | → outbound  | Creates or updates service appointments |
| AWS API Gateway | Middleware | ← inbound   | Receives requests from external apps    |
| [system]        | [type]     | [direction] | [notes]                                 |

Direction legend:

- `→ outbound`: this system calls another system
- `← inbound`: another system calls this system
- `↔ bidirectional`: both systems exchange data

---

## APIs exposed

<!-- Endpoints or interfaces that other systems consume. -->

| Endpoint / method    | Purpose            | Consumer             |
| -------------------- | ------------------ | -------------------- |
| `POST /appointments` | Create appointment | Self-service web app |
| [endpoint]           | [purpose]          | [who uses it]        |

---

## APIs / services consumed

<!-- External dependencies this system calls. -->

| Service             | Purpose            | Authentication          |
| ------------------- | ------------------ | ----------------------- |
| Salesforce REST API | Read/write records | OAuth 2.0 connected app |
| AWS S3              | File uploads       | IAM role                |
| [service]           | [purpose]          | [auth]                  |

---

## Deployment

**CI/CD:** [e.g. GitHub Actions | Bitbucket Pipelines | manual]

**Infra:** [e.g. Terraform on AWS | Salesforce change sets | mix]

**Branch strategy:** [e.g. main → prod, develop → staging]

**Environments:**

- [e.g. dev / staging / production]

---

## Architectural notes and key decisions

<!-- Non-obvious decisions a new developer needs to know. Why you chose X over Y. -->

- [e.g. "Using APIGEE as middleware because... — currently migrating to AWS API Gateway"]
- [e.g. "Scheduling logic lives on Salesforce even though it is complex, to avoid sync overhead"]

---

## Known risks / fragile areas

<!-- Things that are easy to break or should not be changed without extra care. -->

- [e.g. "Appointment status changes may trigger Salesforce Flows and customer notifications"]
- [e.g. "Integration X is being replaced; avoid extending it unless approved"]
- [e.g. "Authentication logic is shared with system Y"]

---

## AI assistant guidance

<!-- Instructions for Cursor, Claude Code, Copilot, or future agents working in this repo. -->

When modifying this repo:

- [e.g. Do not create a new data store for appointment state]
- [e.g. Salesforce FSL is the source of truth for scheduling]
- [e.g. Use existing API client X for Salesforce calls]
- [e.g. Ask for architecture review when changing integrations, authentication, or exposed APIs]

If this file contradicts the actual code, the code wins — flag the discrepancy to the repo owner instead of trusting the doc

---

## Roadmap / active migrations

<!-- Planned changes that affect integrations or architecture. -->

- [ ] [e.g. Migrate self-service web app → Salesforce Experience Cloud]
- [ ] [e.g. Replace external logistics integration with internal Salesforce solution]

---

## Freshness

- **Last reviewed:** [YYYY-MM-DD]
- **Review confidence:** [low / medium / high]
- **Generated by:** [manual / AI-assisted / CI-generated]
- **Validated by:** [person or team]
- **Update when:** integrations change, stack changes, exposed APIs change, data ownership changes, or a relevant architectural decision is made

Recent changes (last 7 days of git log):

<!--
Machine-maintained. Leave the heading line above exactly as it is, including the colon:
the regeneration workflow matches that literal string and replaces everything below it
with the current `git log --oneline --stat --since="7 days ago"` output on every run.

Keep this block last in the file. If you delete the heading, the workflow stops
maintaining the section rather than re-adding it — nothing else in the file is affected.
Do not hand-edit the entries; they are overwritten.
-->
