#!/bin/bash

set -e # exit on error

if [ -z "$1" ]; then
  echo "Error: No version specified."
  echo "Usage: ./release.sh v1.2.3"
  exit 1
fi

# check that version starts with 'v' followed by numbers and dots otherwise the action won't run
if ! [[ $1 =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Error: Version must start with 'v' followed by numbers and dots (e.g., v1.2.3)."
  exit 1
fi

VERSION=$1
COMPOSE_FILE="docker-compose.yml"

echo "Starting release of version $VERSION..."

if ! git diff-index --quiet HEAD --; then
    echo "❌ Error: Working directory is not clean. Please commit or stash your changes."
    exit 1
    # happens if there are uncommitted changes
fi

echo "Working directory is clean."

sed -i -E "s|(image: ghcr.io/dragon863/myrunshaw-[a-z-]+):v[0-9]+\.[0-9]+\.[0-9]+|\1:$VERSION|g" $COMPOSE_FILE # bumps version in docker-compose.yml

echo "Updated '$COMPOSE_FILE' to use image tag '$VERSION'."

git add $COMPOSE_FILE
git commit -m "chore: Release version $VERSION"
echo "Committed version bump."

# tag it on git so the action can pick it up
git tag $VERSION
echo "Created git tag '$VERSION'."

git push origin main
git push origin $VERSION
echo "Pushed commit and tag to origin."
echo "🎉 Done! The actions build should now be processing: https://github.com/Dragon863/myrunshaw-backend/actions/workflows/docker-image.yml"