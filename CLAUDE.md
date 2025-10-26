# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**dotbox-mcp** is a Model Context Protocol (MCP) server that manages Docker containers running .NET workloads. It enables LLMs to execute C# code, test different .NET versions (8, 9, 10 RC2), host HTTP endpoints, and manage container lifecycles.

- **Language**: Python (using FastMCP framework)
- **Transport**: stdio (for local Claude Desktop integration)
- **Container Management**: Docker SDK for Python

## Core Architecture

The server is designed around **agent-centric workflows** rather than low-level Docker commands. Tools provide complete end-to-end functionality for common tasks.

### Key Design Principles

1. **Workflow-Complete Tools**: Each tool handles a complete workflow (e.g., `execute_csharp_snippet` handles container creation, execution, and cleanup)
2. **Context Optimization**: Default to concise output (first 50 lines) with optional full detail via `detail_level` parameter
3. **Actionable Errors**: Enhanced error messages include specific suggestions (e.g., missing packages, port conflicts)
4. **Human-Readable Naming**: Containers use descriptive names like "dotnet8-webapi-abc123" not raw IDs

### Development Principles

**CRITICAL: These principles MUST be followed strictly**

**Git Workflow:**
- ✅ Always work on feature branches
- ✅ Create PRs for all changes
- ❌ NEVER commit directly to main
- ❌ NEVER push to main without PR

1. **Test-Driven Development (TDD)**:
   - Write tests FIRST, then implementation
   - All tests must pass before committing
   - **NEVER commit code with failing tests** - this is a hard rule
   - Red → Green → Refactor cycle

2. **Code Quality**:
   - All code must pass ruff linting (no warnings)
   - All code must pass mypy strict type checking
   - Maintain high test coverage (>90% for new code)
   - Follow DRY principles - no code duplication

3. **Commit Standards**:
   - Use conventional commit format (feat:, fix:, docs:, etc.)
   - Only commit when all tests pass
   - One logical change per commit
   - Include test changes with implementation changes
   - **Do NOT include AI attribution** (no "Generated with Claude Code" or "Co-Authored-By: Claude")

4. **Git Workflow**:
   - **ALWAYS work on feature branches** - never commit directly to main
   - Create PRs for all changes
   - Wait for CI to pass before merging
   - Use squash or rebase merge to keep main clean
   - Delete branch after merge

5. **Testing Standards**:
   - Unit tests for all components
   - Integration tests for end-to-end workflows
   - Mock external dependencies (Docker, HTTP calls)
   - Test both success and failure paths

### Core Workflows

1. **Quick Snippet Testing**: Execute C# code without project setup
2. **Project Development**: Create, build, run complete .NET projects
3. **Version Comparison**: Run code across multiple .NET versions in parallel
4. **Web Endpoint Hosting**: Host APIs and expose accessible URLs
5. **Package Testing**: Test NuGet packages with sample code

## Project Structure

```
dotbox_mcp/
├── src/
│   ├── server.py              # Main MCP server with FastMCP
│   ├── docker_manager.py      # Docker container management
│   ├── project_manager.py     # .NET project file management
│   ├── executor.py            # Build & execution logic
│   ├── formatter.py           # Output formatting (25k char limit)
│   ├── error_enhancer.py      # Error message enhancement
│   └── models.py              # Pydantic input/output models
├── docker/
│   ├── dotnet-8.dockerfile
│   ├── dotnet-9.dockerfile
│   ├── dotnet-10-rc2.dockerfile
│   └── build-images.sh
├── tests/
│   ├── test_executor.py
│   ├── test_project_manager.py
│   ├── test_integration.py
│   └── test_e2e_integration.py # Real E2E tests with Docker
├── .github/
│   ├── workflows/
│   │   ├── ci.yml             # CI/CD pipeline
│   │   └── release-please.yml # Automated release management
│   └── dependabot.yml         # Automated dependency updates
├── CHANGELOG.md               # Auto-generated changelog
└── examples/                   # Usage examples
```

## Tool Implementation Pattern

All MCP tools follow this structure:

```python
# Input validation with Pydantic
class ExecuteSnippetInput(BaseModel):
    code: str = Field(..., description="C# code to execute")
    dotnet_version: DotNetVersion = Field(default="8")
    detail_level: DetailLevel = Field(default="concise")

# Tool implementation
@mcp.tool()
async def dotnet_execute_snippet(input: ExecuteSnippetInput) -> str:
    """Execute a C# code snippet quickly without project setup."""
    # Returns JSON string with standardized format
```

### Standardized Response Format

```python
# Success
{
    "status": "success",
    "data": {...},
    "metadata": {
        "execution_time_ms": 1234,
        "container_id": "...",
        "dotnet_version": "8.0.0"
    }
}

# Error
{
    "status": "error",
    "error": {
        "type": "BuildError",
        "message": "...",
        "suggestions": ["...", "..."]
    }
}
```

## Security & Resource Management

### Container Isolation
- Resource limits (CPU, memory) enforced via Docker
- Read-only filesystem except `/workspace`
- Non-root user inside containers
- Auto-cleanup after 1 hour idle timeout

### Resource Limits
- Max 5 concurrent containers
- Max 10 projects per session
- 30 second default execution timeout
- No Docker socket access from containers

## Docker Image Management

Three base images (Alpine-based for minimal size):
- `dotnet-sandbox:8` - .NET 8 SDK
- `dotnet-sandbox:9` - .NET 9 SDK
- `dotnet-sandbox:10-rc2` - .NET 10 RC2 SDK

Build all images:
```bash
cd docker && ./build-images.sh
```

## Development Workflow

**IMPORTANT: Always work on feature branches and create PRs - NEVER push directly to main.**

### Setup
```bash
# Install dependencies (uv)
uv sync

# Build Docker images (for E2E tests)
cd docker && ./build-images.sh
```

### Branch-Based Development (REQUIRED)

**Standard Workflow:**
```bash
# 1. Create feature branch from main
git checkout main
git pull origin main
git checkout -b feature/your-feature-name

# 2. Make changes following TDD
#    - Write failing test
#    - Implement feature
#    - Make test pass
#    - Refactor
#    - Run: uv run pytest -v -m "not e2e"

# 3. Commit changes with conventional commits
git add .
git commit -m "feat: add your feature description"

# 4. Push branch and create PR
git push -u origin feature/your-feature-name
# Then create PR via GitHub UI or gh CLI

# 5. CI runs automatically (lint + unit tests)
# 6. After PR approval and merge, E2E tests run on main
```

**Branch Naming Conventions:**
- `feature/description` - New features
- `fix/description` - Bug fixes
- `refactor/description` - Code refactoring
- `docs/description` - Documentation changes
- `chore/description` - Maintenance tasks

**When to Create a PR:**
- After completing a feature slice (tests passing)
- When you want code review
- Before merging to main (always)
- Never push directly to main

**Creating PRs with gh CLI:**
```bash
# After pushing your branch
gh pr create --title "feat: your feature" --body "Description of changes"

# Or use interactive mode
gh pr create

# View PR status
gh pr status

# Merge after approval
gh pr merge --squash
```

### Testing

**Test Strategy:**
- **Unit tests**: Run automatically (mocked Docker) - fast feedback
- **E2E tests**: Run ONLY when explicitly needed to validate a functional slice
  - Requires Docker images built
  - Actually executes C# code in real containers
  - Slower but provides true end-to-end validation

```bash
# Run unit tests only (fast, default for development)
uv run pytest -v -m "not e2e"

# Run with coverage (unit tests only)
uv run pytest --cov=src --cov-report=term-missing -m "not e2e"

# Run E2E tests (ONLY when validating a functional slice)
# Requires: cd docker && ./build-images.sh
uv run pytest -v -m e2e

# Run ALL tests (unit + E2E)
uv run pytest -v
```

**When to run E2E tests:**
- After completing a significant feature slice
- Before creating a release
- When making changes to executor or Docker integration
- NOT during normal TDD red-green-refactor cycles

### Running the Server
```bash
# Standard MCP stdio server
uv run python -m src.server

# With debug logging
DEBUG=1 uv run python -m src.server
```

## Core Components

### DockerContainerManager (`docker_manager.py`)
- `create_container()` - Create/start container with mounted volume
- `execute_command()` - Execute command in container, return (stdout, stderr, exit_code)
- `stop_container()` - Stop and remove container
- `list_containers()` - List all active sandbox containers

### ProjectManager (`project_manager.py`)
- `create_project_workspace()` - Create project directory structure
- `add_file()` - Add/update files in project
- `get_project_path()` - Get absolute path to project
- `cleanup_project()` - Remove project directory

### DotNetExecutor (`executor.py`)
- `build_project()` - Build .NET project, return parsed results
- `run_snippet()` - Execute C# code snippet with top-level statements
- `host_web_app()` - Start web app in container

### OutputFormatter (`formatter.py`)
- Enforces 25,000 character MCP limit
- Supports `detail_level`: "concise" (first 50 lines) or "full"
- Parses MSBuild output into structured errors

### ErrorEnhancer (`error_enhancer.py`)
- Parses common C# compiler errors (CS0246, CS0103, etc.)
- Adds actionable suggestions (missing using directives, package references)

## Error Handling Categories

1. **User Input Errors**: Clear validation messages via Pydantic
2. **Build Errors**: Parse MSBuild output, add suggestions
3. **Runtime Errors**: Capture exceptions, timeouts, OOM
4. **Infrastructure Errors**: Docker unavailable, port conflicts, disk space
5. **Resource Limits**: Too many containers, quota exceeded

## CI/CD & Automation

### GitHub Actions CI Strategy

**PR Workflow (branch → PR → main):**

1. **On PR Creation/Update** (fast feedback ~1 min):
   - Linting (ruff)
   - Type checking (mypy)
   - Unit tests with mocked Docker
   - Coverage reporting to Codecov
   - **Must pass before merge allowed**

2. **After PR Merge to Main** (post-merge validation ~5 min):
   - E2E integration tests with real Docker containers
   - Builds all .NET Docker images (8, 9, 10 RC2)
   - Full end-to-end workflow validation
   - **Alerts if E2E tests fail after merge**

3. **Manual Trigger** (`workflow_dispatch`):
   - Run E2E tests on demand for any branch
   - Useful for validating major changes before PR

**Protection Rules:**
- Main branch requires PR (no direct commits)
- PR requires passing CI checks
- At least 1 approval recommended (for team projects)

### Dependabot Configuration

Automated dependency updates via `.github/dependabot.yml`:

**Python Dependencies** (weekly on Monday):
- Groups dev dependencies (pytest, ruff, mypy) together
- Groups production dependencies (mcp, pydantic, httpx, docker) together
- Limits to 5 open PRs to reduce noise
- Conventional commit format: `chore(deps): update ...`

**GitHub Actions** (weekly on Monday):
- Groups all action updates together
- Limits to 3 open PRs
- Conventional commit format: `chore(ci): update ...`

**Handling Dependabot PRs:**
1. CI automatically runs on Dependabot PRs (unit tests only)
2. Review changes and merge if tests pass
3. E2E tests run after merge to main
4. Rollback if E2E tests fail

## Release Management

### Semantic Versioning Strategy

**Version Format:** `MAJOR.MINOR.PATCH[-prerelease]`

**Version Semantics:**
- **MAJOR** (0→1, 1→2): Breaking changes in tool signatures, removed tools, incompatible API changes
- **MINOR** (0.1→0.2): New tools, new features, backward-compatible enhancements
- **PATCH** (0.1.0→0.1.1): Bug fixes, documentation, performance improvements (no new features)

**Pre-1.0 Development:**
- While `0.x.y`, breaking changes allowed in MINOR bumps
- `0.x` = unstable API, rapid iteration phase
- `1.0.0` = stable API, backward compatibility guaranteed

**Example Version History:**
```
0.1.0 → Initial version
0.2.0 → Add execute_snippet, create_project tools
0.3.0 → Add web hosting, package management
0.4.0 → Add project inspection tools
...
0.9.0 → Feature complete, testing phase
1.0.0-rc.1 → Release candidate
1.0.0 → Stable release! 🎉
1.0.1 → Bug fix (no new features)
1.1.0 → New tool added (backward compatible)
2.0.0 → Breaking API change
```

### Automated Release Process (release-please)

**How It Works:**

1. **Daily Development** - Merge PRs to main (version stays unchanged)
   ```bash
   # Multiple PRs merged:
   feat: add new tool    → version stays 0.1.0
   fix: bug in executor  → version stays 0.1.0
   feat: add another tool → version stays 0.1.0
   ```

2. **Release Please Bot** - Automatically runs on every push to main
   - Analyzes commits since last release
   - Determines version bump based on conventional commits:
     - `feat:` → MINOR bump (0.1.0 → 0.2.0)
     - `fix:` → PATCH bump (0.1.0 → 0.1.1)
     - `feat!:` or `BREAKING CHANGE:` → MAJOR bump (0.x.y → 1.0.0)
   - Creates/updates a **Release PR** with:
     - Version bump in `pyproject.toml`
     - Generated `CHANGELOG.md`
     - Title: `chore(main): release 0.2.0`

3. **Review Release PR** - Developer reviews before merging
   - Check CHANGELOG accuracy
   - Verify version bump is appropriate
   - Can manually edit if needed

4. **Merge Release PR** - Triggers automatic release
   ```bash
   gh pr merge <release-pr-number> --squash
   ```

5. **Automated Post-Merge Actions**
   - Creates git tag (e.g., `v0.2.0`)
   - Creates GitHub Release with changelog
   - (Optional) Publishes to PyPI
   - (Optional) Updates MCP registry

### Conventional Commit Format

**Required for automatic version detection:**

```bash
# Features (MINOR bump)
feat: add execute snippet tool
feat(docker): support custom resource limits

# Bug Fixes (PATCH bump)
fix: handle timeout correctly
fix(executor): parse build errors properly

# Breaking Changes (MAJOR bump - pre-1.0: MINOR)
feat!: change tool input schema
feat: add new parameter
BREAKING CHANGE: removes legacy parameter

# Other types (no version bump, but in CHANGELOG)
docs: update README
refactor: simplify error handling
perf: optimize container creation
test: add E2E tests
chore: update dependencies
ci: improve workflow
```

### When to Release

**Trigger Points:**
- ✅ Significant features complete (2-3 new tools)
- ✅ Breaking changes (release ASAP)
- ✅ Critical bug fixes (patch release immediately)
- ✅ Regular cadence (optional: weekly/bi-weekly if changes exist)
- ✅ Before demos/presentations (stable version)

**Release Frequency:**
- **Pre-1.0**: Every 1-2 weeks (or when ready)
- **Post-1.0**: Monthly for features, immediately for critical bugs

### Manual Release Process (if needed)

**Force a release without waiting for Release Please:**

```bash
# 1. Manually bump version in pyproject.toml
# version = "0.2.0"

# 2. Update CHANGELOG.md manually

# 3. Commit and tag
git add pyproject.toml CHANGELOG.md
git commit -m "chore(release): 0.2.0"
git tag v0.2.0
git push origin main --tags

# 4. Create GitHub Release manually
gh release create v0.2.0 --generate-notes
```

### Release Checklist

Before merging a release PR:
- [ ] Version number is correct (follows SemVer)
- [ ] CHANGELOG.md accurately reflects changes
- [ ] All CI checks passing (unit + E2E tests)
- [ ] Documentation updated if API changed
- [ ] Breaking changes clearly documented
- [ ] Migration guide provided (if breaking changes)

## Implementation Priorities

### MVP (Priority 1)
- `dotnet_execute_snippet` - Quick C# testing
- `dotnet_create_project` - Project setup
- `dotnet_build_project` - Build functionality
- `dotnet_run_project` - Console execution
- `dotnet_cleanup_all` - Resource cleanup

### Phase 2
- `dotnet_host_api` - Web API hosting
- `dotnet_test_endpoint` - HTTP endpoint testing
- `dotnet_list_containers` - Container visibility
- `dotnet_stop_container` - Individual cleanup

### Phase 3
- `dotnet_add_file` - File manipulation
- `dotnet_add_package` - NuGet package management
- `dotnet_get_project_files` - Project inspection
- `dotnet_read_file` - File reading

## Testing Strategy

### Unit Tests
- Mock Docker operations
- Test Pydantic validation
- Test error parsing and enhancement

### Integration Tests
- Full workflows: create → build → run → cleanup
- Error scenarios (build failures, timeouts)
- Concurrent operations
- Cleanup mechanisms

### Manual Testing Scenarios
1. Execute "Hello World" snippet
2. Create web API and test endpoint
3. Test with invalid code (verify helpful errors)
4. Test concurrent executions
5. Verify cleanup after timeout
6. Compare output across .NET versions
