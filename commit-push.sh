#!/bin/bash
set -e

# Check if there are changes to commit
if [ -z "$(git status --porcelain)" ]; then
  echo "No changes to commit"
  exit 0
fi

# Stage all changes first so diff --cached works
git add .

# Generate commit message using Claude CLI
echo "Generating commit message..."
MESSAGE=$(git diff --cached --stat | claude --print "Generate a brief git commit message (max 50 chars) for these changes. Output ONLY the message, no quotes or prefixes.")

# Commit with generated message
git commit -m "$MESSAGE"

# Push to current branch
git push

echo "Changes committed and pushed"
