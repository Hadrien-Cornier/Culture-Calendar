#!/usr/bin/env bash
# scripts/gitnexus_workflow.sh — Run the GitNexus analyze + wiki workflow
#
# Prerequisites:
#   npm install   (installs gitnexus@1.6.1 into node_modules/)
#
# For wiki generation, set one of:
#   export OPENAI_API_KEY=sk-...           (OpenAI)
#   export GITNEXUS_API_KEY=sk-...         (OpenRouter or compatible)
#
# Or pass a custom endpoint:
#   GITNEXUS_BASE_URL=https://openrouter.ai/api/v1
#   GITNEXUS_MODEL=minimax/minimax-m2.5
#
# Usage:
#   ./scripts/gitnexus_workflow.sh           # analyze only
#   ./scripts/gitnexus_workflow.sh --wiki    # analyze + wiki
#   ./scripts/gitnexus_workflow.sh --force   # force full re-index

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GITNEXUS="$REPO_ROOT/node_modules/.bin/gitnexus"
FORCE_FLAG=""
RUN_WIKI=false

for arg in "$@"; do
  case "$arg" in
    --wiki)   RUN_WIKI=true ;;
    --force)  FORCE_FLAG="--force" ;;
  esac
done

echo "=== GitNexus Workflow ==="
echo "Repo: $REPO_ROOT"
echo "Version: $($GITNEXUS --version)"
echo ""

# Step 1: Analyze
echo "--- Step 1: analyze ---"
$GITNEXUS analyze $FORCE_FLAG "$REPO_ROOT"

# Step 2: Status check
echo ""
echo "--- Step 2: status ---"
$GITNEXUS status

# Step 3: Wiki (optional, requires API key)
if [ "$RUN_WIKI" = true ]; then
  echo ""
  echo "--- Step 3: wiki ---"
  WIKI_ARGS="--provider openai"

  # Base URL: OpenAI by default, override with GITNEXUS_BASE_URL
  # NOTE: gitnexus default base URL is openrouter.ai — must explicitly set OpenAI URL
  BASE_URL="${GITNEXUS_BASE_URL:-https://api.openai.com/v1}"
  WIKI_ARGS="$WIKI_ARGS --base-url $BASE_URL"

  # Model
  MODEL="${GITNEXUS_MODEL:-gpt-4o-mini}"
  WIKI_ARGS="$WIKI_ARGS --model $MODEL"

  # API key (GITNEXUS_API_KEY > OPENAI_API_KEY)
  if [ -n "${GITNEXUS_API_KEY:-}" ]; then
    WIKI_ARGS="$WIKI_ARGS --api-key $GITNEXUS_API_KEY"
  elif [ -n "${OPENAI_API_KEY:-}" ]; then
    WIKI_ARGS="$WIKI_ARGS --api-key $OPENAI_API_KEY"
  else
    echo "ERROR: No API key found. Set OPENAI_API_KEY or GITNEXUS_API_KEY and retry."
    echo "  export OPENAI_API_KEY=sk-..."
    echo "  $0 --wiki"
    exit 1
  fi
  $GITNEXUS wiki $FORCE_FLAG $WIKI_ARGS "$REPO_ROOT"

  # Verify wiki output
  WIKI_DIR="$REPO_ROOT/.gitnexus/wiki"
  if [ -d "$WIKI_DIR" ] && [ -n "$(ls -A "$WIKI_DIR" 2>/dev/null)" ]; then
    echo ""
    echo "✅ Wiki artifacts verified:"
    ls "$WIKI_DIR"
  else
    echo "WARNING: Wiki directory is empty or missing: $WIKI_DIR"
    exit 1
  fi
else
  echo ""
  echo "Skipping wiki (pass --wiki to enable; requires API key)."
fi

echo ""
echo "✅ Workflow complete."
