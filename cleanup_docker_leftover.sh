#!/bin/bash

# Stop and remove all running and stopped containers
echo "Stopping and removing all Docker containers..."
docker stop $(docker ps -q) 2>/dev/null
docker rm -f $(docker ps -a -q) 2>/dev/null

# Remove all unused Docker images
echo "Removing all unused Docker images..."
docker rmi -f $(docker images -a -q) 2>/dev/null

# Remove all unused Docker networks
echo "Removing all unused Docker networks..."
docker network rm $(docker network ls -q) 2>/dev/null

# Remove all dangling volumes
echo "Removing all dangling Docker volumes..."
docker volume rm $(docker volume ls -qf dangling=true) 2>/dev/null

# Remove all Docker system cache
echo "Cleaning up Docker system..."
docker system prune -a --volumes -f

echo "Docker cleanup completed!"

