FROM mcr.microsoft.com/dotnet/sdk:9.0-alpine

# Install bash and curl for debugging
RUN apk add --no-cache bash curl

# Set working directory
WORKDIR /workspace

# Create non-root user for security
RUN adduser -D -u 1000 sandbox

# Give ownership of workspace to sandbox user
RUN chown -R sandbox:sandbox /workspace

# Switch to non-root user
USER sandbox

# Set default command to keep container running
CMD ["tail", "-f", "/dev/null"]
