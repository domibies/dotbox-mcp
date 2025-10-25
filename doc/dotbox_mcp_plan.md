# dotbox-mcp - Implementation Plan

## Project Overview

An MCP server that manages Docker containers running .NET workloads, enabling Claude to:
- Execute C# code snippets and full projects
- Test different .NET versions (8, 9, 10 RC2)
- Host HTTP endpoints for API testing
- Handle file uploads/downloads
- Manage container lifecycle

**Server Name**: `dotbox_mcp`
**Language**: Python (using FastMCP)
**Transport**: stdio (for local Claude Desktop integration)

---

## Phase 1: Agent-Centric Design

### Core Workflows

1. **Quick Snippet Testing**
   - User: "Test this LINQ expression with .NET 8"
   - Flow: Create temp container → Execute snippet → Return output → Cleanup

2. **Project Development**
   - User: "Create a minimal API with two endpoints"
   - Flow: Create project → Add files → Build → Run → Expose endpoints → Test

3. **Version Comparison**
   - User: "Does this work differently in .NET 8 vs 10?"
   - Flow: Run in parallel containers → Compare outputs → Report differences

4. **Package Testing**
   - User: "Show me how to use Dapper with SQL Server"
   - Flow: Create project → Add packages → Generate sample code → Run

5. **Web Endpoint Hosting**
   - User: "Host this API and test the /health endpoint"
   - Flow: Create project → Start server → Map ports → Return URL → Test endpoint

### Tool Design Philosophy

**Build for complete workflows, not raw Docker commands:**
- ❌ `docker_run` - too low-level
- ✅ `execute_csharp_snippet` - complete workflow for quick tests
- ✅ `create_dotnet_project` - sets up proper project structure
- ✅ `host_web_api` - handles project + build + run + port mapping

**Optimize for limited context:**
- Default to "concise" output (first 50 lines of errors)
- Support `detail_level` parameter: "concise" | "full"
- Use human-readable names: "dotnet8-webapi-abc123" not container IDs
- Return structured JSON with clear status indicators

**Actionable error messages:**
- ❌ "Build failed" 
- ✅ "Build failed: Missing package System.Text.Json. Try adding: <PackageReference Include='System.Text.Json' Version='8.0.0' />"
- ❌ "Container start failed"
- ✅ "Container start failed: Port 5000 already in use. Suggestion: Use the 'port' parameter to specify a different port (e.g., 5001)"

---

## Phase 2: Tool Selection & Design

### Core Tools (Priority 1)

#### 1. `dotnet_execute_snippet`
**Purpose**: Execute a C# code snippet quickly without project setup
**Input**:
- `code: str` - C# code to execute (supports top-level statements)
- `dotnet_version: "8" | "9" | "10-rc2"` - .NET version to use
- `packages: List[str]` - NuGet packages to include (e.g., ["Newtonsoft.Json"])
- `detail_level: "concise" | "full"` - Output detail level
**Output**: Execution result (stdout, stderr, exit code)
**Annotations**: readOnlyHint=true, destructiveHint=false, openWorldHint=true

#### 2. `dotnet_create_project`
**Purpose**: Create a new .NET project with proper structure
**Input**:
- `project_name: str` - Name for the project
- `template: "console" | "webapi" | "classlib" | "worker"` - Project template
- `dotnet_version: "8" | "9" | "10-rc2"` - .NET version
- `packages: List[str]` - Initial packages to add
**Output**: Project ID, file structure, next steps
**Annotations**: readOnlyHint=false, destructiveHint=false, idempotentHint=false

#### 3. `dotnet_add_file`
**Purpose**: Add or update a file in the project
**Input**:
- `project_id: str` - Project identifier
- `file_path: str` - Relative path (e.g., "Controllers/WeatherController.cs")
- `content: str` - File content
- `overwrite: bool` - Whether to overwrite existing file
**Output**: Success status, file path
**Annotations**: readOnlyHint=false, destructiveHint=false, idempotentHint=true

#### 4. `dotnet_build_project`
**Purpose**: Build a .NET project
**Input**:
- `project_id: str` - Project identifier
- `configuration: "Debug" | "Release"` - Build configuration
- `detail_level: "concise" | "full"` - Error output detail
**Output**: Build status, errors/warnings, build artifacts location
**Annotations**: readOnlyHint=true, destructiveHint=false, idempotentHint=true

#### 5. `dotnet_run_project`
**Purpose**: Run a console application or worker service
**Input**:
- `project_id: str` - Project identifier
- `args: List[str]` - Command-line arguments
- `timeout_seconds: int` - Max execution time (default: 30)
- `detail_level: "concise" | "full"` - Output detail
**Output**: Execution result (stdout, stderr, exit code)
**Annotations**: readOnlyHint=true, destructiveHint=false, openWorldHint=true

#### 6. `dotnet_host_api`
**Purpose**: Host a web API and return the accessible URL
**Input**:
- `project_id: str` - Project identifier
- `port: Optional[int]` - Host port (auto-assigned if not specified)
- `environment: Dict[str, str]` - Environment variables
**Output**: Container ID, accessible URL (http://localhost:PORT), status
**Annotations**: readOnlyHint=false, destructiveHint=false, openWorldHint=true

#### 7. `dotnet_test_endpoint`
**Purpose**: Make HTTP request to a hosted endpoint
**Input**:
- `url: str` - Full URL to test
- `method: "GET" | "POST" | "PUT" | "DELETE"` - HTTP method
- `headers: Optional[Dict[str, str]]` - Request headers
- `body: Optional[str]` - Request body (JSON)
**Output**: Response status, headers, body
**Annotations**: readOnlyHint=true, destructiveHint=false, openWorldHint=true

#### 8. `dotnet_list_containers`
**Purpose**: List all active .NET sandbox containers
**Output**: List of containers with IDs, projects, status, ports
**Annotations**: readOnlyHint=true, destructiveHint=false, openWorldHint=false

#### 9. `dotnet_stop_container`
**Purpose**: Stop and remove a specific container
**Input**:
- `container_id: str` - Container identifier or project_id
**Output**: Success status
**Annotations**: readOnlyHint=false, destructiveHint=true, idempotentHint=true

#### 10. `dotnet_cleanup_all`
**Purpose**: Stop and remove all sandbox containers
**Output**: Number of containers cleaned up
**Annotations**: readOnlyHint=false, destructiveHint=true, idempotentHint=true

### Utility Tools (Priority 2)

#### 11. `dotnet_get_project_files`
**Purpose**: List all files in a project
**Input**:
- `project_id: str` - Project identifier
**Output**: File tree with sizes
**Annotations**: readOnlyHint=true

#### 12. `dotnet_read_file`
**Purpose**: Read content of a file in a project
**Input**:
- `project_id: str` - Project identifier
- `file_path: str` - Relative file path
**Output**: File content
**Annotations**: readOnlyHint=true

#### 13. `dotnet_add_package`
**Purpose**: Add a NuGet package to a project
**Input**:
- `project_id: str` - Project identifier
- `package_name: str` - Package name
- `version: Optional[str]` - Package version (latest if not specified)
**Output**: Success status, package info
**Annotations**: readOnlyHint=false, destructiveHint=false

---

## Phase 3: Shared Utilities Design

### Docker Management Layer

```python
class DockerContainerManager:
    """Manages Docker containers for .NET sandboxes."""
    
    async def create_container(
        self,
        dotnet_version: str,
        project_id: str,
        working_dir: Path,
        port_mapping: Optional[Dict[int, int]] = None
    ) -> str:
        """Create and start a container with mounted volume."""
        
    async def execute_command(
        self,
        container_id: str,
        command: List[str],
        timeout: int = 30
    ) -> Tuple[str, str, int]:
        """Execute command in container, return (stdout, stderr, exit_code)."""
        
    async def stop_container(self, container_id: str) -> None:
        """Stop and remove a container."""
        
    async def list_containers(self) -> List[ContainerInfo]:
        """List all active sandbox containers."""
```

### Project Management Layer

```python
class ProjectManager:
    """Manages .NET project files and structure."""
    
    def create_project_workspace(
        self,
        project_id: str,
        template: str,
        dotnet_version: str
    ) -> Path:
        """Create project directory structure."""
        
    def add_file(
        self,
        project_id: str,
        file_path: str,
        content: str
    ) -> None:
        """Add or update a file in the project."""
        
    def get_project_path(self, project_id: str) -> Path:
        """Get absolute path to project directory."""
        
    def cleanup_project(self, project_id: str) -> None:
        """Remove project directory and all files."""
```

### Build & Execution Layer

```python
class DotNetExecutor:
    """Handles .NET build and execution operations."""
    
    async def build_project(
        self,
        container_id: str,
        project_path: str,
        configuration: str
    ) -> BuildResult:
        """Build a .NET project, return parsed results."""
        
    async def run_snippet(
        self,
        code: str,
        dotnet_version: str,
        packages: List[str]
    ) -> ExecutionResult:
        """Execute a C# code snippet with top-level statements."""
        
    async def host_web_app(
        self,
        container_id: str,
        project_path: str,
        port: int
    ) -> HostResult:
        """Start web app in container."""
```

### Output Formatting Layer

```python
class OutputFormatter:
    """Formats tool outputs for optimal LLM consumption."""
    
    CHARACTER_LIMIT = 25000  # Standard MCP limit
    
    def format_build_output(
        self,
        errors: List[str],
        warnings: List[str],
        detail_level: str
    ) -> str:
        """Format build output, truncating if needed."""
        
    def format_execution_output(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        detail_level: str
    ) -> str:
        """Format execution results with clear sections."""
        
    def parse_msbuild_errors(
        self,
        raw_output: str
    ) -> List[BuildError]:
        """Parse MSBuild output into structured errors."""
```

### Error Message Enhancement

```python
class ErrorEnhancer:
    """Enhances error messages with actionable suggestions."""
    
    COMMON_ERRORS = {
        "CS0246": {
            "pattern": r"The type or namespace name '(\w+)' could not be found",
            "suggestion": "Missing using directive or assembly reference. Try adding 'using {namespace};' or package reference."
        },
        "CS0103": {
            "pattern": r"The name '(\w+)' does not exist",
            "suggestion": "Undefined identifier. Check spelling and ensure all necessary using directives are included."
        },
        # More common errors...
    }
    
    def enhance_error(self, error: str) -> str:
        """Add helpful suggestions to error messages."""
```

---

## Phase 4: Input/Output Design

### Input Validation Models (Pydantic)

```python
from pydantic import BaseModel, Field, field_validator, ConfigDict
from enum import Enum
from typing import Optional, List, Dict

class DotNetVersion(str, Enum):
    V8 = "8"
    V9 = "9"
    V10_RC2 = "10-rc2"

class ProjectTemplate(str, Enum):
    CONSOLE = "console"
    WEBAPI = "webapi"
    CLASSLIB = "classlib"
    WORKER = "worker"

class DetailLevel(str, Enum):
    CONCISE = "concise"
    FULL = "full"

class ExecuteSnippetInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    
    code: str = Field(
        ...,
        description="C# code to execute (supports top-level statements)",
        min_length=1,
        max_length=50000
    )
    dotnet_version: DotNetVersion = Field(
        default=DotNetVersion.V8,
        description=".NET version: '8', '9', or '10-rc2'"
    )
    packages: List[str] = Field(
        default_factory=list,
        description="NuGet packages to include (e.g., ['Newtonsoft.Json', 'Dapper'])",
        max_items=20
    )
    detail_level: DetailLevel = Field(
        default=DetailLevel.CONCISE,
        description="Output detail: 'concise' (first 50 lines) or 'full' (complete output)"
    )
    
    @field_validator('packages')
    @classmethod
    def validate_packages(cls, v: List[str]) -> List[str]:
        # Validate package name format
        for pkg in v:
            if not pkg or len(pkg) > 100:
                raise ValueError(f"Invalid package name: {pkg}")
        return v

class CreateProjectInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    
    project_name: str = Field(
        ...,
        description="Project name (alphanumeric, hyphens, underscores)",
        pattern=r'^[a-zA-Z0-9_-]+$',
        min_length=1,
        max_length=50
    )
    template: ProjectTemplate = Field(
        description="Project template: 'console', 'webapi', 'classlib', or 'worker'"
    )
    dotnet_version: DotNetVersion = Field(
        default=DotNetVersion.V8,
        description=".NET version: '8', '9', or '10-rc2'"
    )
    packages: List[str] = Field(
        default_factory=list,
        description="Initial NuGet packages to add",
        max_items=20
    )

# Similar models for other tools...
```

### Response Format Standards

All tools return JSON strings with this structure:

```python
# Success Response
{
    "status": "success",
    "data": {
        # Tool-specific data
    },
    "metadata": {
        "execution_time_ms": 1234,
        "container_id": "dotnet8-console-abc123",
        "dotnet_version": "8.0.0"
    }
}

# Error Response
{
    "status": "error",
    "error": {
        "type": "BuildError",
        "message": "Build failed with 3 errors",
        "details": "...",
        "suggestions": [
            "Add missing using directive: using System.Text.Json;",
            "Install package: dotnet add package System.Text.Json"
        ]
    },
    "metadata": {
        "execution_time_ms": 1234,
        "container_id": "dotnet8-console-abc123"
    }
}

# Truncated Response
{
    "status": "success",
    "data": {
        "output": "... (truncated)",
        "truncated": true,
        "truncation_message": "Output truncated from 50000 to 25000 characters. Use detail_level='full' for complete output."
    }
}
```

---

## Phase 5: Security & Safety Considerations

### Container Isolation
- Use Docker's resource limits (CPU, memory)
- No network access by default (unless web hosting)
- Read-only filesystem except for /workspace
- Non-root user inside container
- Auto-cleanup after timeout (default: 1 hour idle)

### Code Safety
- No direct file system access outside /workspace
- Timeout enforcement on all executions (default: 30s)
- Maximum container count per session (default: 10)
- No access to Docker socket from within containers

### Rate Limiting
- Max 5 concurrent containers
- Max 100 executions per hour
- Max 10 projects per session

---

## Phase 6: Error Handling Strategy

### Error Categories

1. **User Input Errors** (return clear validation messages)
   - Invalid code syntax
   - Invalid package names
   - Invalid project names

2. **Build Errors** (parse MSBuild output, add suggestions)
   - Missing references
   - Compilation errors
   - Package restore failures

3. **Runtime Errors** (capture and format)
   - Exceptions during execution
   - Timeouts
   - Out of memory

4. **Infrastructure Errors** (provide recovery steps)
   - Docker daemon not available
   - Port conflicts
   - Disk space issues
   - Network errors

5. **Resource Limits** (inform user of constraints)
   - Too many containers
   - Container creation failed
   - Quota exceeded

### Error Message Template

```python
def format_error(error_type: str, details: str, suggestions: List[str]) -> str:
    return json.dumps({
        "status": "error",
        "error": {
            "type": error_type,
            "message": details,
            "suggestions": suggestions
        }
    })

# Example usage:
format_error(
    "BuildError",
    "Build failed: CS0246 - The type 'JsonSerializer' could not be found",
    [
        "Add using directive: using System.Text.Json;",
        "Or install package: dotnet add package System.Text.Json",
        "Make sure you're targeting .NET 8+ for this namespace"
    ]
)
```

---

## Phase 7: Docker Image Strategy

### Base Images

Create custom images with pre-installed .NET SDKs:

```dockerfile
# dotnet-sandbox-8.dockerfile
FROM mcr.microsoft.com/dotnet/sdk:8.0-alpine
RUN apk add --no-cache bash curl
WORKDIR /workspace
RUN adduser -D -u 1000 sandbox
USER sandbox

# dotnet-sandbox-9.dockerfile
FROM mcr.microsoft.com/dotnet/sdk:9.0-alpine
RUN apk add --no-cache bash curl
WORKDIR /workspace
RUN adduser -D -u 1000 sandbox
USER sandbox

# dotnet-sandbox-10-rc2.dockerfile
FROM mcr.microsoft.com/dotnet/sdk:10.0-rc.2-alpine
RUN apk add --no-cache bash curl
WORKDIR /workspace
RUN adduser -D -u 1000 sandbox
USER sandbox
```

### Build Script

```bash
#!/bin/bash
docker build -t dotnet-sandbox:8 -f dotnet-sandbox-8.dockerfile .
docker build -t dotnet-sandbox:9 -f dotnet-sandbox-9.dockerfile .
docker build -t dotnet-sandbox:10-rc2 -f dotnet-sandbox-10-rc2.dockerfile .
```

---

## Phase 8: Implementation Structure

### Project Structure

```
dotbox_mcp/
├── src/
│   ├── __init__.py
│   ├── server.py              # Main MCP server with FastMCP
│   ├── docker_manager.py      # Docker container management
│   ├── project_manager.py     # .NET project management
│   ├── executor.py            # Build & execution logic
│   ├── formatter.py           # Output formatting
│   ├── error_enhancer.py      # Error message enhancement
│   └── models.py              # Pydantic models
├── docker/
│   ├── dotnet-8.dockerfile
│   ├── dotnet-9.dockerfile
│   ├── dotnet-10-rc2.dockerfile
│   └── build-images.sh
├── tests/
│   ├── test_executor.py
│   ├── test_project_manager.py
│   └── test_integration.py
├── examples/
│   ├── snippet_execution.py
│   ├── webapi_hosting.py
│   └── version_comparison.py
├── pyproject.toml
├── README.md
└── .gitignore
```

### Key Dependencies

```toml
[project]
name = "dotbox-mcp"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "mcp>=1.0.0",
    "pydantic>=2.0.0",
    "httpx>=0.27.0",
    "docker>=7.0.0",  # Python Docker SDK
]
```

---

## Phase 9: Testing Strategy

### Unit Tests
- Test each utility function independently
- Mock Docker operations
- Test Pydantic validation
- Test error parsing

### Integration Tests
- Test full workflow: create → build → run → cleanup
- Test error scenarios (build failures, timeouts)
- Test concurrent operations
- Test cleanup mechanisms

### Manual Testing Scenarios
1. Execute simple "Hello World" snippet
2. Create web API and test endpoint
3. Test with invalid code (should return helpful errors)
4. Test concurrent executions
5. Test cleanup after timeout
6. Test version comparison

---

## Phase 10: Documentation Requirements

### Tool Documentation (Auto-generated from docstrings)
Each tool includes:
- Clear description of what it does
- When to use it vs alternatives
- Input parameters with examples
- Output format
- Common errors and solutions
- Usage examples

### README.md
- Overview and use cases
- Installation instructions
- Docker setup requirements
- Configuration options
- Security considerations
- Troubleshooting guide

### Examples Directory
- Common workflow examples
- Error handling patterns
- Advanced usage scenarios

---

## Implementation Priorities

### MVP (Phase 1) - Core Tools
1. `dotnet_execute_snippet` - Quick testing
2. `dotnet_create_project` - Project setup
3. `dotnet_build_project` - Build functionality
4. `dotnet_run_project` - Execution
5. `dotnet_cleanup_all` - Resource management

**Goal**: Enable basic "execute C# code" workflow

### Phase 2 - Web Hosting
6. `dotnet_host_api` - Start web servers
7. `dotnet_test_endpoint` - Test HTTP endpoints
8. `dotnet_stop_container` - Individual cleanup
9. `dotnet_list_containers` - Container visibility

**Goal**: Enable web API testing workflow

### Phase 3 - File Management
10. `dotnet_add_file` - File manipulation
11. `dotnet_get_project_files` - Project inspection
12. `dotnet_read_file` - File reading
13. `dotnet_add_package` - Package management

**Goal**: Enable complex project development

### Phase 4 - Polish
- Error message enhancement
- Performance optimization
- Comprehensive testing
- Documentation completion

---

## Success Metrics

1. **Workflow Completion**: Claude can successfully complete all 5 core workflows
2. **Error Quality**: Error messages are actionable and helpful
3. **Performance**: < 5 seconds for snippet execution, < 10 seconds for project build
4. **Reliability**: No orphaned containers, proper cleanup
5. **Usability**: Clear tool descriptions enable Claude to choose right tools

---

## Next Steps

1. Set up Python project structure
2. Build Docker images for .NET 6, 8, 9
3. Implement core utilities (DockerManager, ProjectManager)
4. Implement MVP tools (execute_snippet, create_project, build, run, cleanup)
5. Write integration tests
6. Test with Claude Desktop
7. Iterate based on real usage

---

## Open Questions for Discussion

1. **Workspace Location**: Where should project files be stored on host? `/tmp/dotnet-sandbox/` or configurable?
2. **Persistence**: Should projects persist between sessions or auto-cleanup on server restart?
3. **Network Access**: Allow outbound HTTP by default for package restore, or require explicit flag?
4. **Resource Limits**: Default limits for CPU/memory per container?
5. **Logging**: How verbose should logging be? Store logs per-project?
6. **Authentication**: Any need for API keys or auth to external services?

