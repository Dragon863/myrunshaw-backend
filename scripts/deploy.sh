#!/bin/bash

# Update local repository with latest changes from main branch
git pull origin main
docker compose pull

# Start services in detached mode, and remove unused containers
# (the --remove-orphans flag removes containers for services not defined in the current compose file)
docker compose up -d --remove-orphans