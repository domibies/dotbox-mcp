#!/bin/bash
set -e

echo "Building .NET sandbox Docker images..."

# Build .NET 8 image
echo "Building dotnet-sandbox:8..."
docker build -t dotnet-sandbox:8 -f dotnet-8.dockerfile .

# Build .NET 9 image
echo "Building dotnet-sandbox:9..."
docker build -t dotnet-sandbox:9 -f dotnet-9.dockerfile .

# Build .NET 10 RC2 image (using 9.0 as placeholder)
echo "Building dotnet-sandbox:10-rc2..."
docker build -t dotnet-sandbox:10-rc2 -f dotnet-10-rc2.dockerfile .

echo "All images built successfully!"
echo ""
echo "Available images:"
docker images | grep dotnet-sandbox
