FROM mcr.microsoft.com/dotnet/sdk:9.0-alpine

# Install bash and curl for debugging
RUN apk add --no-cache bash curl

# Set working directory
WORKDIR /workspace

# Create non-root user for security
RUN adduser -D -u 1000 sandbox

# Switch to non-root user
USER sandbox

# Note: .NET 10 RC2 image may not be available yet, using 9.0 as placeholder
# Update to actual .NET 10 RC2 image when available

# Set default command to keep container running
CMD ["tail", "-f", "/dev/null"]
