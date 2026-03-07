#!/bin/bash

# Check if a commit message is provided
if [ -z "$1" ]; then
  echo "Error: Please provide a commit message."
  exit 1
fi

# Add all changes
git add .

# Commit with the provided message
git commit -m "$1"

# Pull the latest changes before pushing
git pull --rebase origin main

# Push changes to the main branch
git push -u origin main
#./git_push.sh myapp