#!/usr/bin/env bash
# Bump patch version in version.json files before commit.
# Usage: bash scripts/bump-version.sh [bidcopilot|cvcopilot|both]
# Default: auto-detect based on staged files.

set -e
TODAY=$(date +%Y-%m-%d)

bump_file() {
  local file="$1"
  if [ ! -f "$file" ]; then return; fi

  local current
  current=$(grep '"version"' "$file" | head -1 | sed 's/.*"\([0-9]*\.[0-9]*\.[0-9]*\)".*/\1/')
  if [ -z "$current" ]; then return; fi

  local major minor patch
  IFS='.' read -r major minor patch <<< "$current"
  patch=$((patch + 1))
  local new_version="${major}.${minor}.${patch}"

  # Use portable sed (works on both macOS and Linux)
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/\"version\": \"${current}\"/\"version\": \"${new_version}\"/" "$file"
    sed -i '' "s/\"build\": \"[0-9-]*\"/\"build\": \"${TODAY}\"/" "$file"
  else
    sed -i "s/\"version\": \"${current}\"/\"version\": \"${new_version}\"/" "$file"
    sed -i "s/\"build\": \"[0-9-]*\"/\"build\": \"${TODAY}\"/" "$file"
  fi

  echo "  $file: $current -> $new_version"
}

TARGET="${1:-auto}"

if [ "$TARGET" = "auto" ]; then
  # Check staged files to decide what to bump
  STAGED=$(git diff --cached --name-only 2>/dev/null || echo "")
  if echo "$STAGED" | grep -q "^CVCopilot/"; then
    echo "Bumping CVCopilot versions..."
    bump_file "CVCopilot/frontend/src/version.json"
    bump_file "CVCopilot/backend/version.json"
  fi
  if echo "$STAGED" | grep -q "^bidcopilot/\|^pyproject.toml\|^config/"; then
    echo "Bumping BidCopilot version..."
    bump_file "version.json"
  fi
elif [ "$TARGET" = "cvcopilot" ]; then
  echo "Bumping CVCopilot versions..."
  bump_file "CVCopilot/frontend/src/version.json"
  bump_file "CVCopilot/backend/version.json"
elif [ "$TARGET" = "bidcopilot" ]; then
  echo "Bumping BidCopilot version..."
  bump_file "version.json"
elif [ "$TARGET" = "both" ]; then
  echo "Bumping all versions..."
  bump_file "CVCopilot/frontend/src/version.json"
  bump_file "CVCopilot/backend/version.json"
  bump_file "version.json"
fi
