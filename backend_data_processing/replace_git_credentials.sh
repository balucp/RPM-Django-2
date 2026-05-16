#!/bin/bash

# Load environment variables from .env file
set -a
source .env.dev
set +a

# Define the requirements file
REQUIREMENTS_FILE="requirements.txt"

# Check if the requirements file exists
if [[ ! -f $REQUIREMENTS_FILE ]]; then
  echo "$REQUIREMENTS_FILE not found!"
  exit 1
fi

# Escape special characters in credentials
ESCAPED_USERNAME=$(printf '%s' "$GIT_USERNAME" | sed 's/[&/\]/\\&/g')
ESCAPED_TOKEN=$(printf '%s' "$GIT_TOKEN" | sed 's/[&/\]/\\&/g')

# Replace ${GIT_USERNAME} and ${GIT_TOKEN} in-place
sed -i "s|\${GIT_USERNAME}|$ESCAPED_USERNAME|g" "$REQUIREMENTS_FILE"
sed -i "s|\${GIT_TOKEN}|$ESCAPED_TOKEN|g" "$REQUIREMENTS_FILE"

echo "Git credentials replaced in $REQUIREMENTS_FILE"
