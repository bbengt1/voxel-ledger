#!/usr/bin/env bash
#
# Secret / PII guard — blocks commits (and CI) that introduce secrets or
# production-identifiable information that could compromise the live
# deployment. Runs automatically via .pre-commit-config.yaml and in CI.
#
# Modes:
#   scripts/check_secrets.sh            # scan staged added lines (pre-commit)
#   scripts/check_secrets.sh --all      # scan the whole tracked tree (CI)
#
# A genuine false positive can be allowed by appending an inline marker
#   # pragma: allowlist secret
# to the offending line (kept rare and reviewed).
#
# NOTE: the kept brand domain (bengtsonprecision3d.com) and the public
# product name are intentionally NOT blocked — they're a deliberate
# portfolio choice. This guard targets *private infra + secrets*.

set -euo pipefail

MODE="${1:-staged}"

# (label, regex) — high-signal only, to keep false positives near zero.
PATTERNS=(
  "internal LAN hostname|[A-Za-z0-9_-]+\.bengtson\.local"
  "personal gmail address|[A-Za-z0-9._%+-]+@gmail\.com"
  "AWS access key|AKIA[0-9A-Z]{16}"
  "GitHub token|gh[pousr]_[A-Za-z0-9]{20,}"
  "GitHub fine-grained PAT|github_pat_[A-Za-z0-9_]{20,}"
  "Slack token|xox[baprs]-[A-Za-z0-9-]{10,}"
  "OpenAI-style key|sk-[A-Za-z0-9]{20,}"
  "Google API key|AIza[0-9A-Za-z_-]{20,}"
  "private key block|-----BEGIN [A-Z ]*PRIVATE KEY-----"
  "JWT|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."
)

# Never scan the guard itself (it contains the patterns) or generated files.
EXCLUDES=(
  ":(exclude)scripts/check_secrets.sh"
  ":(exclude)pnpm-lock.yaml"
)

if [ "$MODE" = "--all" ]; then
  CONTENT="$(git grep -nIE '.' -- . "${EXCLUDES[@]}" 2>/dev/null || true)"
else
  # Staged added lines only (so we block *new* introductions, not history).
  CONTENT="$(git diff --cached --unified=0 -- . "${EXCLUDES[@]}" \
    | grep -E '^\+' | grep -vE '^\+\+\+' || true)"
fi

# Drop explicitly-allowlisted lines.
CONTENT="$(printf '%s\n' "$CONTENT" | grep -v 'pragma: allowlist secret' || true)"

[ -z "$CONTENT" ] && exit 0

FAIL=0
for entry in "${PATTERNS[@]}"; do
  label="${entry%%|*}"
  regex="${entry#*|}"
  matches="$(printf '%s\n' "$CONTENT" | grep -nE -- "$regex" || true)"
  if [ -n "$matches" ]; then
    echo "✗ blocked: $label"
    printf '%s\n' "$matches" | sed 's/^/    /'
    FAIL=1
  fi
done

if [ "$FAIL" -ne 0 ]; then
  cat >&2 <<'MSG'

────────────────────────────────────────────────────────────────────
Commit blocked: the change introduces secrets or production-identifiable
information. Redact it (use generic placeholders like *.internal,
@example.com, CHANGE-ME), keep real secrets in untracked .env files, or
— for a genuine false positive — append "# pragma: allowlist secret" to
the line. See scripts/check_secrets.sh.
────────────────────────────────────────────────────────────────────
MSG
  exit 1
fi

exit 0
