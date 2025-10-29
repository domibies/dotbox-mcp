#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "Building Docker images for local development..."
echo ""

# Build sandbox images
echo "=== Building sandbox images ==="
cd docker
./build-images.sh
cd ..

# Build server image
echo ""
echo "=== Building server image ==="
docker build -t dotbox-mcp:dev .

echo ""
echo "✓ All images built successfully:"
echo "  - dotnet-sandbox:8"
echo "  - dotnet-sandbox:9"
echo "  - dotnet-sandbox:10-rc2"
echo "  - dotbox-mcp:dev"
echo ""
echo "Switch to Docker mode: ./scripts/toggle-claude-config.py docker"
