# CLAUDE.md

Claude Code guidance for this repository.

## Project Overview

**dotbox-mcp**: MCP server managing Docker containers for .NET workloads. Enables LLMs to execute C# code, test .NET versions (8, 9, 10 RC2), host HTTP endpoints, manage container lifecycles.

- **Language**: Python (FastMCP framework)
- **Transport**: stdio (Claude Desktop integration)
- **Container Management**: Docker SDK for Python

## Core Architecture

**Agent-centric workflows** - Tools provide complete end-to-end functionality, not low-level Docker commands.

### Design Principles

1. **Workflow-Complete Tools**: Each tool handles full workflow (create → execute → cleanup)
2. **Context Optimization**: Default concise output (first 50 lines), full detail via `detail_level` parameter
3. **Actionable Errors**: Error messages include specific suggestions (missing packages, port conflicts)
4. **Human-Readable Naming**: Containers named "dotnet8-webapi-abc123" not raw IDs

### Core Workflows

1. **Quick Snippet Testing**: Execute C# without project setup
2. **Project Development**: Create, build, run complete .NET projects
3. **Version Comparison**: Run code across multiple .NET versions in parallel
4. **Web Endpoint Hosting**: Host APIs, expose accessible URLs
5. **Package Testing**: Test NuGet packages with sample code

## Development Principles (CRITICAL)

### Git Workflow (STRICT RULES)
- ✅ **ALWAYS** work on feature branches (never commit directly to main)
- ✅ Create PRs for all changes
- ✅ Wait for CI to pass before merging
- ❌ **NEVER** commit directly to main
- ❌ **NEVER** push to main without PR

### Test-Driven Development
- Write tests FIRST, then implementation
- **NEVER commit code with failing tests** (hard rule)
- Red → Green → Refactor cycle
- >90% coverage for new code

### Code Quality
- Pass ruff linting (no warnings)
- Pass mypy strict type checking
- Follow DRY principles

### Commit Standards
- Conventional commit format: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `ci:`, `perf:`
- One logical change per commit
- Include test changes with implementation
- **NO AI attribution** (no "Generated with Claude Code" or "Co-Authored-By: Claude")

### Branch Naming
- `feature/description` - New features
- `fix/description` - Bug fixes
- `refactor/description` - Refactoring
- `docs/description` - Documentation
- `chore/description` - Maintenance

### macOS Paths
- Claude Desktop config: `~/Library/Application\ Support/Claude/claude_desktop_config.json`
- Escape spaces with backslashes in bash commands

## Project Structure

```
src/
├── server.py           # Main MCP server (FastMCP)
├── docker_manager.py   # Docker container management
├── project_manager.py  # .NET project file management
├── executor.py         # Build & execution logic
├── formatter.py        # Output formatting (25k char limit)
├── error_enhancer.py   # Error message enhancement
└── models.py           # Pydantic input/output models
docker/
├── dotnet-{8,9,10-rc2}.dockerfile
└── build-images.sh
tests/
├── test_*.py           # Unit tests (mocked Docker)
└── test_e2e_integration.py  # E2E tests (real Docker)
.github/workflows/
├── ci.yml              # CI/CD pipeline
└── release-please.yml  # Automated releases
```

## Tool Implementation Pattern

```python
class ExecuteSnippetInput(BaseModel):
    code: str = Field(..., description="C# code to execute")
    dotnet_version: DotNetVersion = Field(default="8")
    response_format: ResponseFormat = Field(default="markdown")

@mcp.tool()
async def dotnet_execute_snippet(input: ExecuteSnippetInput) -> str:
    """Execute a C# code snippet quickly without project setup."""
    # Returns Markdown or JSON
```

### Response Formats

**Default: Markdown** (30-50% more context-efficient than JSON, better readability)

```markdown
# Execution Result ✓
**Runtime:** .NET 8.0.0 (1.2s)
## Output
Hello, World!
```

**Optional: JSON** - Add `"response_format": "json"` for programmatic processing or backward compatibility.

**Note:** Markdown output may include status emojis (✓/✗) for visual clarity.

## Security & Resource Management

**Container Isolation:**
- Resource limits (CPU, memory) via Docker
- Read-only filesystem except `/workspace`
- Non-root user
- Auto-cleanup after 1 hour idle

**Resource Limits:**
- Max 5 concurrent containers
- Max 10 projects per session
- 30s default execution timeout
- No Docker socket access from containers

## Docker Images

**Sandbox images** (.NET SDK):
- `dotnet-sandbox:8` - .NET 8 SDK
- `dotnet-sandbox:9` - .NET 9 SDK
- `dotnet-sandbox:10-rc2` - .NET 10 RC2 SDK

**Server image**:
- `dotbox-mcp:dev` - MCP server for Docker-based testing

Build: `./scripts/build-docker-dev.sh` (all images) or `cd docker && ./build-images.sh` (sandbox only)

**Switch Claude Desktop config**:
- `./scripts/toggle-claude-config.py dev` - Run from source (uv)
- `./scripts/toggle-claude-config.py docker` - Run in Docker (dotbox-mcp:dev)
- `./scripts/toggle-claude-config.py production` - Use published GHCR images
- `./scripts/toggle-claude-config.py` - Toggle between dev/docker

## Development Workflow

### Setup
```bash
uv sync                        # Install dependencies
cd docker && ./build-images.sh # Build Docker images (for E2E tests)
```

### Standard Workflow
```bash
# 1. Create feature branch
git checkout main && git pull
git checkout -b feature/your-feature-name

# 2. TDD cycle: write test → implement → pass → refactor
uv run pytest -v -m "not e2e"

# 3. Commit with conventional format
git add .
git commit -m "feat: your feature description"

# 4. Push and create PR
git push -u origin feature/your-feature-name
gh pr create --title "feat: your feature" --body "Description"

# 5. CI runs (lint + unit tests) - must pass before merge
# 6. After merge to main, E2E tests run automatically
```

### Testing

**Unit tests** (fast, mocked Docker):
```bash
uv run pytest -v -m "not e2e"                              # Run tests
uv run pytest --cov=src --cov-report=term-missing -m "not e2e"  # With coverage
```

**E2E tests** (slow, real Docker - run when validating functional slices):
```bash
cd docker && ./build-images.sh  # Build images first
uv run pytest -v -m e2e         # Run E2E tests
```

**When to run E2E:**
- After completing significant feature slice
- Before creating release
- When changing executor or Docker integration
- NOT during normal TDD cycles

### Running Server
```bash
uv run python -m src.server   # Standard MCP stdio server
DEBUG=1 uv run python -m src.server  # With debug logging
```

## Core Components

**DockerContainerManager** (`docker_manager.py`): `create_container()`, `execute_command()`, `stop_container()`, `list_containers()`

**ProjectManager** (`project_manager.py`): `create_project_workspace()`, `add_file()`, `get_project_path()`, `cleanup_project()`

**DotNetExecutor** (`executor.py`): `build_project()`, `run_snippet()`, `host_web_app()`

**OutputFormatter** (`formatter.py`): Enforces 25k char MCP limit, supports `detail_level` (concise/full), parses MSBuild output

**ErrorEnhancer** (`error_enhancer.py`): Parses C# compiler errors (CS0246, CS0103, etc.), adds actionable suggestions

## Error Handling

1. **User Input**: Pydantic validation messages
2. **Build Errors**: Parsed MSBuild output with suggestions
3. **Runtime Errors**: Exceptions, timeouts, OOM
4. **Infrastructure**: Docker unavailable, port conflicts, disk space
5. **Resource Limits**: Too many containers, quota exceeded

## CI/CD Strategy

### PR Workflow

**On PR creation/update** (~1 min):
- Linting (ruff), type checking (mypy)
- Unit tests (mocked Docker)
- Coverage reporting (Codecov)
- **Must pass before merge**

**After merge to main** (~5 min):
- E2E tests with real Docker containers
- Builds all .NET images (8, 9, 10 RC2)
- Alerts if E2E fails

**Manual trigger**: Run E2E on any branch via `workflow_dispatch`

**Protection rules**: Main requires PR + passing CI

### Dependabot

**Python deps** (weekly Monday): Groups dev/prod separately, limits to 5 PRs, format: `chore(deps): update ...`

**GitHub Actions** (weekly Monday): Groups all actions, limits to 3 PRs, format: `chore(ci): update ...`

**Handle Dependabot PRs**: CI runs unit tests → merge if pass → E2E runs on main → rollback if E2E fails

## Release Management

### Semantic Versioning

`MAJOR.MINOR.PATCH[-prerelease]`

- **MAJOR**: Breaking changes (tool signatures, removed tools)
- **MINOR**: New tools/features (backward-compatible)
- **PATCH**: Bug fixes, docs, performance (no new features)
- **Pre-1.0**: Breaking changes allowed in MINOR bumps

### Automated Releases (release-please)

1. **Daily dev**: Merge PRs to main (version unchanged)
2. **Release Please bot**: Runs on every push to main
   - Analyzes commits since last release
   - Determines version bump: `feat:` → MINOR, `fix:` → PATCH, `feat!:` or `BREAKING CHANGE:` → MAJOR
   - Creates/updates Release PR with version bump + CHANGELOG
3. **Review Release PR**: Check CHANGELOG, verify version
4. **Merge Release PR**: Auto-creates git tag + GitHub Release

### Conventional Commits

```bash
feat: add execute snippet tool          # MINOR bump
fix: handle timeout correctly            # PATCH bump
feat!: change tool input schema          # MAJOR bump
docs/refactor/perf/test/chore/ci: ...   # No version bump (in CHANGELOG)
```

### When to Release

- Significant features complete (2-3 new tools)
- Breaking changes (ASAP)
- Critical bug fixes (immediate patch)
- Regular cadence (weekly/bi-weekly if changes exist)
- Before demos/presentations

**Frequency**: Pre-1.0: every 1-2 weeks; Post-1.0: monthly for features, immediate for critical bugs

### Manual Release (if needed)

```bash
# Bump version in pyproject.toml, update CHANGELOG.md
git add pyproject.toml CHANGELOG.md
git commit -m "chore(release): 0.2.0"
git tag v0.2.0
git push origin main --tags
gh release create v0.2.0 --generate-notes
```

### Release Checklist

- [ ] Version correct (follows SemVer)
- [ ] CHANGELOG accurate
- [ ] CI passing (unit + E2E)
- [ ] Docs updated if API changed
- [ ] Breaking changes documented + migration guide

## MCP Tool Inventory

### MVP (Phase 1)
`dotnet_execute_snippet`, `dotnet_create_project`, `dotnet_build_project`, `dotnet_run_project`, `dotnet_cleanup_all`

### Phase 2
`dotnet_host_api`, `dotnet_test_endpoint`, `dotnet_list_containers`, `dotnet_stop_container`

### Phase 3
`dotnet_add_file`, `dotnet_add_package`, `dotnet_get_project_files`, `dotnet_read_file`

## Testing Strategy

**Unit tests**: Mock Docker, test Pydantic validation, error parsing
**Integration tests**: Full workflows (create → build → run → cleanup), error scenarios, concurrency, cleanup
**Manual scenarios**: Hello World snippet, web API, invalid code errors, concurrent executions, timeout cleanup, version comparison
