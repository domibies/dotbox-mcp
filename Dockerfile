FROM python:3.11-slim

# Install Docker CLI (needed to communicate with host daemon via socket)
# Note: Only the CLI is needed, not the daemon
RUN apt-get update && apt-get install -y \
    docker.io \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files first (for Docker layer caching)
COPY pyproject.toml uv.lock ./

# Install Python dependencies
RUN uv sync --frozen --no-dev

# Copy source code
COPY src ./src
COPY README.md ./

# Create non-root user and add to docker group for socket access
RUN useradd -m -u 1000 dotbox && \
    groupadd -g 999 docker || true && \
    usermod -aG docker dotbox && \
    chown -R dotbox:dotbox /app

USER dotbox

# MCP servers use stdio transport (stdin/stdout communication)
ENTRYPOINT ["uv", "run", "python", "-m", "src.server"]
