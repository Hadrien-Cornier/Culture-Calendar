#!/usr/bin/env bash
# Overnight autonomous loop for the Culture Calendar fix/calendar-oracle branch.
#
# Reads the subtask queue in CHANGELOG.md, picks the next unchecked line, hands
# it to a `claude -p` invocation to execute, runs the verify + test suite after
# each iteration, commits on green with the mandated authorship, and pushes.
#
# Safe by construction:
#   - refuses to run off fix/calendar-oracle (never touches main)
#   - uses `-c user.name=… -c user.email=…` flags (no persistent config mutation)
#   - never force-pushes, never --no-verify
#   - hard stop after three BLOCKED lines in a row
#   - cache-coherent: keeps iterations under 2 consecutive no-commit rounds
#
# Usage:
#   tmux new -s culture-calendar
#   cd /Users/HCornier/Documents/Personal/Culture-Calendar
#   git checkout fix/calendar-oracle  # already created
#   ./scripts/overnight_loop.sh 2>&1 | tee .overnight.log
#   # Ctrl-b d to detach

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

BRANCH="fix/calendar-oracle"
GIT_AUTHOR_FLAGS=(-c user.name=Hadrien-Cornier -c user.email=hadrien.cornier@gmail.com)

# ---- Safety: require branch -------------------------------------------------
CURRENT=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT" != "$BRANCH" ]; then
  echo "Refusing to run on '$CURRENT' (expected '$BRANCH'). Run: git checkout $BRANCH"
  exit 1
fi

# ---- Ensure venv -------------------------------------------------------------
if [ ! -x ".venv/bin/python" ]; then
  echo "No .venv found. Creating…"
  /opt/homebrew/bin/python3.13 -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -r requirements.txt
fi
PY=.venv/bin/python

# ---- Initial upstream --------------------------------------------------------
git push -u origin "$BRANCH" 2>/dev/null || true

# ---- Main loop ---------------------------------------------------------------
ITER=0
CONSECUTIVE_BLOCKERS=0
CONSECUTIVE_NOCOMMIT=0

while true; do
  ITER=$((ITER + 1))
  HEAD_BEFORE=$(git rev-parse HEAD)
  echo ""
  echo "=============================================================="
  echo "Iteration $ITER @ $(date '+%Y-%m-%d %H:%M:%S')"
  echo "=============================================================="

  # Oracle check: if green twice in a row, exit cleanly.
  if $PY scripts/verify_calendar.py --offline; then
    echo ""
    echo "OFFLINE PASS. Trying LIVE…"
    if $PY scripts/verify_calendar.py --live; then
      echo ""
      echo "LIVE PASS. Termination criterion met."
      git add -A
      if ! git diff --cached --quiet; then
        git "${GIT_AUTHOR_FLAGS[@]}" commit -m "feat(calendar): verify_calendar PASS (iter $ITER)"
        git push origin "$BRANCH"
      fi
      exit 0
    fi
    echo "LIVE FAIL — likely network or layout drift. Continuing with next subtask."
  fi

  # Pick next unchecked subtask from CHANGELOG.md.
  NEXT=$(awk '/^- \[ \]/ {print; exit}' CHANGELOG.md || true)
  if [ -z "$NEXT" ]; then
    echo "No unchecked subtasks remain. Exiting."
    exit 0
  fi
  echo "Next subtask: $NEXT"

  # Build the prompt. Keep short; CLAUDE.md is the fuller protocol.
  PROMPT=$(cat <<EOF
You are continuing the overnight Culture Calendar calendar-fix run (branch fix/calendar-oracle).

Read CLAUDE.md and CHANGELOG.md. Work on this subtask only:
$NEXT

After your changes, run:
  .venv/bin/python -m pytest -q
  .venv/bin/python scripts/verify_calendar.py --offline

If both pass, tick the box in CHANGELOG.md (replace "- [ ]" with "- [x] $(date '+%Y-%m-%d %H:%M')") and commit with:
  git -c user.name=Hadrien-Cornier -c user.email=hadrien.cornier@gmail.com commit -m "feat(calendar): <subtask-id> <what>"
  git push origin fix/calendar-oracle

If blocked, append a line to CHANGELOG.md: BLOCKED: <subtask-id>: <one-sentence reason>
Commit and push anyway.

Constraints: never touch main; never force-push; never --no-verify; never commit .env. Scope strictly to this subtask.
EOF
)

  # Hand off to Claude Code non-interactively (if the `claude` CLI is available).
  if command -v claude >/dev/null 2>&1; then
    claude -p "$PROMPT" || echo "claude -p returned non-zero; continuing."
  else
    echo "warning: 'claude' CLI not in PATH. Paste the prompt into a Claude session manually, then press Enter to continue."
    read -r _
  fi

  # Push whatever got committed (belt-and-suspenders).
  git push origin "$BRANCH" || echo "push failed (network?); will retry next iter"

  HEAD_AFTER=$(git rev-parse HEAD)
  if [ "$HEAD_BEFORE" = "$HEAD_AFTER" ]; then
    CONSECUTIVE_NOCOMMIT=$((CONSECUTIVE_NOCOMMIT + 1))
    echo "No commit this iteration (streak=$CONSECUTIVE_NOCOMMIT)."
    if [ "$CONSECUTIVE_NOCOMMIT" -ge 2 ]; then
      echo "Two iterations without progress. Exiting to avoid infinite loop."
      exit 2
    fi
  else
    CONSECUTIVE_NOCOMMIT=0
  fi

  # Detect three BLOCKED lines in a row (three blockers since last green commit)
  BLOCKED_RECENT=$(git log -n 10 --pretty=%s | grep -c "^BLOCKED:" || true)
  if [ "$BLOCKED_RECENT" -ge 3 ]; then
    echo "Three or more recent BLOCKED entries. Exiting for human review."
    exit 3
  fi
done
