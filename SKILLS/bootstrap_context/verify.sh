#!/usr/bin/env bash
# Verify AI/CONTEXT.md conforms to CONTEXT_TEMPLATE.md and cites nothing invented.
#
# Usage, from the repo root:
#   bash skills/bootstrap_context/verify.sh [path/to/CONTEXT.md]
#
# Exit 0 = all checks passed. Exit 1 = at least one failure.
# A clean run means the file is well-formed and its identifiers are real.
# It does not mean the content is correct — only a human review establishes that.

set -uo pipefail

CTX="${1:-AI/CONTEXT.md}"
FAILED=0

pass() { printf '  \033[32mok\033[0m    %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAILED=1; }
warn() { printf '  \033[33mwarn\033[0m  %s\n' "$1"; }

if [ ! -f "$CTX" ]; then
  echo "verify: no such file: $CTX" >&2
  exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "verify: must be run inside a git work tree" >&2
  exit 1
fi

echo "Verifying $CTX"
echo
echo "Frontmatter"

# --- frontmatter present ---
if [ "$(head -1 "$CTX")" = "---" ]; then
  pass "opens with YAML frontmatter"
else
  fail "must open with '---' on line 1"
fi

fm_value() {
  sed -n '2,/^---$/p' "$CTX" | grep -m1 "^$1:" | sed "s/^$1:[[:space:]]*//"
}

check_vocab() {
  local field="$1"; shift
  local value; value="$(fm_value "$field")"
  if [ -z "$value" ]; then
    fail "$field: missing"
    return
  fi
  for allowed in "$@"; do
    if [ "$value" = "$allowed" ]; then
      pass "$field: $value"
      return
    fi
  done
  fail "$field: '$value' is not one of: $*"
}

check_vocab criticality       low medium high business-critical
check_vocab review_confidence low medium high
check_vocab generated_by      manual AI-assisted CI-generated

for field in repo project_name owner domain summary last_reviewed validated_by; do
  if [ -n "$(fm_value "$field")" ]; then
    pass "$field: present"
  else
    fail "$field: missing or empty"
  fi
done

# last_reviewed must be an ISO date
lr="$(fm_value last_reviewed)"
if printf '%s' "$lr" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'; then
  pass "last_reviewed is YYYY-MM-DD"
else
  fail "last_reviewed must be YYYY-MM-DD, got '$lr'"
fi

# a bootstrap draft is low-confidence and unvalidated
if [ "$(fm_value review_confidence)" = "low" ] && [ "$(fm_value validated_by)" != "none" ]; then
  warn "review_confidence is low but validated_by is not 'none' — intentional?"
fi

echo
echo "Mandatory sections"

MANDATORY=(
  "Overview"
  "Purpose and responsibilities"
  "Source of truth / data ownership"
  "External integrations"
  "APIs exposed"
  "APIs / services consumed"
  "Deployment"
  "Architectural notes and key decisions"
  "Known risks / fragile areas"
  "AI assistant guidance"
  "Roadmap / active migrations"
  "Freshness"
)

for section in "${MANDATORY[@]}"; do
  n=$(grep -cxF "## $section" "$CTX")
  case "$n" in
    1) pass "## $section" ;;
    0) fail "## $section — missing" ;;
    *) fail "## $section — appears $n times, expected once" ;;
  esac
done

# H1 title
if grep -qE '^# .+' "$CTX"; then
  pass "has an H1 title"
else
  fail "missing H1 title line"
fi

# the code-wins clause is a required guarantee, not decoration
if grep -qF 'the code wins' "$CTX"; then
  pass "retains the 'code wins' clause"
else
  fail "missing the 'If this file contradicts the actual code, the code wins' clause"
fi

echo
echo "Tables where the template requires them"

# Sections the company-level matrices are derived from must be tabular.
for section in "Source of truth / data ownership" "External integrations" "APIs exposed" "APIs / services consumed"; do
  body=$(awk -v s="## $section" '
    $0 == s {inside=1; next}
    /^## / {inside=0}
    inside {print}
  ' "$CTX")
  if printf '%s' "$body" | grep -qE '^\|.*\|'; then
    pass "$section contains a table"
  else
    fail "$section has no table — prose does not aggregate into the company matrices"
  fi
done

echo
echo "Machine-maintained tail"

HEADING='Recent changes (last 7 days of git log):'
n=$(grep -cxF "$HEADING" "$CTX")
case "$n" in
  1) pass "log heading present exactly once, byte-identical" ;;
  0) fail "missing literal heading '$HEADING' — the workflow will stop maintaining the section" ;;
  *) fail "log heading appears $n times, expected once" ;;
esac

if [ "$n" = "1" ]; then
  tail_body=$(sed -n "/^$(printf '%s' "$HEADING" | sed 's/[].[^$*\/]/\\&/g')$/,\$p" "$CTX")
  if printf '%s' "$tail_body" | grep -qE '^```'; then
    fail "log section is fenced — the workflow writes raw git log output, no fence"
  else
    pass "log section is unfenced"
  fi
  # heading should be the last section in the file
  if printf '%s' "$tail_body" | grep -qE '^## '; then
    fail "a '## ' section appears after the log heading — it must be last"
  else
    pass "log heading is the final section"
  fi
fi

echo
echo "Cited identifiers exist in tracked source"

# Anything that looks like a concrete infrastructure identifier and appears in
# the prose must be findable in tracked source. This is the fabrication check.
SRC="$(mktemp)"; trap 'rm -f "$SRC" "$PROSE"' EXIT
git ls-files -z | xargs -0 cat 2>/dev/null > "$SRC"

# Exclude the machine-maintained tail: those are commit subjects, not claims.
PROSE="$(mktemp)"
sed "/^$(printf '%s' "$HEADING" | sed 's/[].[^$*\/]/\\&/g')$/,\$d" "$CTX" > "$PROSE"

check_ids() {
  local label="$1" pattern="$2"
  local id ids=() bogus=()
  while IFS= read -r id; do
    [ -n "$id" ] && ids+=("$id")
  done < <(grep -oE "$pattern" "$PROSE" 2>/dev/null | sort -u)
  if [ "${#ids[@]}" -eq 0 ]; then
    pass "$label: none cited"
    return
  fi
  for id in "${ids[@]}"; do
    grep -qF "$id" "$SRC" || bogus+=("$id")
  done
  if [ "${#bogus[@]}" -eq 0 ]; then
    pass "$label: ${#ids[@]} cited, all found in source"
  else
    fail "$label: not found in tracked source: ${bogus[*]}"
  fi
}

check_ids "AWS account IDs"   '\b[0-9]{12}\b'
check_ids "ARNs"              'arn:aws[a-z-]*:[a-z0-9-]*:[a-z0-9-]*:[0-9]*:[A-Za-z0-9/:_.*-]+'
check_ids "AWS resource IDs"  '\b(i|vpc|subnet|sg|tgw|tgw-attach|tgw-rtb|rtb|igw|nat|eni|ami|vol|snap|pl|acl|eipalloc)-[0-9a-f]{8,17}\b'
check_ids "UUIDs"             '\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'
check_ids "Org / OU IDs"      '\b(o-[a-z0-9]{10,32}|ou-[a-z0-9]{4,32}-[a-z0-9]{8,32})\b'
check_ids "IPv4 / CIDR"       '\b([0-9]{1,3}\.){3}[0-9]{1,3}(/[0-9]{1,2})?\b'

echo
echo "Credential leak check"

# Not exhaustive — a backstop for the obvious shapes.
LEAKS=0
leak() { fail "possible credential in file: $1"; LEAKS=1; }
grep -qE 'AKIA[0-9A-Z]{16}'                      "$PROSE" && leak "AWS access key ID"
grep -qE '\bASIA[0-9A-Z]{16}\b'                  "$PROSE" && leak "AWS temporary access key"
grep -qE 'gh[pousr]_[A-Za-z0-9]{36,}'            "$PROSE" && leak "GitHub token"
grep -qE 'xox[abposr]-[A-Za-z0-9-]{10,}'         "$PROSE" && leak "Slack token"
grep -qE -e '-----BEGIN [A-Z ]*PRIVATE KEY-----' "$PROSE" && leak "private key block"
grep -qE 'https://[^ )]*/(integrations|hooks|services)/[A-Za-z0-9_-]{16,}' "$PROSE" && leak "webhook URL with embedded token"
[ "$LEAKS" -eq 0 ] && pass "no obvious credential shapes found"

echo
if [ "$FAILED" -eq 0 ]; then
  printf '\033[32mAll checks passed.\033[0m Well-formed and no fabricated identifiers.\n'
  echo "This is not a content review — a human still has to validate it."
else
  printf '\033[31mVerification failed.\033[0m Fix the items marked FAIL above.\n'
fi
exit "$FAILED"
