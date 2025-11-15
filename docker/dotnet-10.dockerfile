FROM mcr.microsoft.com/dotnet/sdk:10.0-alpine

# Install LLM-usable CLI tools
RUN apk add --no-cache \
    bash \
    curl \
    git \
    jq \
    tree \
    sqlite \
    ca-certificates \
    tzdata

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
