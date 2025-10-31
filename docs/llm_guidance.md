# LLM Guidance for dotbox-mcp

> **Note:** This document is maintained for future reference and potential MCP prompts implementation. It contains detailed UX patterns that are condensed to 1-2 line reminders in tool descriptions.

This document provides behavioral guidance for LLMs using the dotbox-mcp server. These patterns ensure excellent user experience when executing .NET code and managing Docker containers.

## Table of Contents
1. [User Feedback Patterns](#user-feedback-patterns)
2. [Artifact Creation Workflows](#artifact-creation-workflows)
3. [Output Visualization Requirements](#output-visualization-requirements)
4. [URL Formatting for Clickability](#url-formatting-for-clickability)
5. [NuGet Package Usage Guidelines](#nuget-package-usage-guidelines)
6. [Port Access: Container vs Host](#port-access-container-vs-host)
7. [Common .NET CLI Commands](#common-net-cli-commands)

---

## User Feedback Patterns

### Why Feedback Matters
Tool calls are collapsed in Claude's UI, so users **cannot see the code you're writing**. You must show them the interesting parts inline.

### Required Communication Pattern

Between tool calls, provide:
1. **Status message** - what you're doing
2. **Code snippet** - show the KEY/INTERESTING part (5-15 lines, not full files)
3. **Explanation** - why this matters or what it demonstrates
4. **Result summary** - what happened

### Example - Good (Engaging)

```
Let me create a service that uses TimeProvider for time-dependent logic:

```csharp
public class SubscriptionService
{
    private readonly TimeProvider _timeProvider;

    public SubscriptionService(TimeProvider timeProvider)
    {
        _timeProvider = timeProvider;  // Injectable for testing!
    }

    public bool IsSubscriptionActive(DateTime start, int days)
    {
        var expiration = start.AddDays(days);
        return _timeProvider.GetUtcNow().UtcDateTime < expiration;
    }
}
```

This demonstrates the key pattern: inject TimeProvider instead of using DateTime.Now directly.

[tool call to write file]

✓ Service created successfully
```

### Example - Bad (User Sees Nothing)

```
Creating subscription service...
[tool call]
✓ Service created
```

### What to Show

- ✅ Key method signatures
- ✅ Interesting language features being demonstrated
- ✅ Novel patterns or techniques
- ✅ The "aha!" moment of your code
- ❌ Boilerplate or full file dumps
- ❌ Just status messages without code

---

## Artifact Creation Workflows

### For Code Files (.cs, .csproj, etc.)

**Recommended workflow when writing .NET code:**

1. **FIRST** create an artifact to display the code with syntax highlighting
2. **THEN** call `dotnet_write_file` to write that code to the container
3. Confirm the file was written successfully

This creates a better visual experience for users to review code before writing.

**Exception:** For simple config files or one-liners, skip the artifact.

### For Snippet Execution

**Recommended workflow for `dotnet_execute_snippet`:**

1. **FIRST** create a C# code artifact to display the code cleanly
2. **THEN** call `dotnet_execute_snippet` to execute that code
3. Show the execution results
4. **IF output is formatted** (see next section), create artifact with output

**Exception:** For very simple one-liners like `Console.WriteLine("Hello");`, execute directly.

---

## Output Visualization Requirements

### When to Create Output Artifacts

**CRITICAL:** When executing code that produces visual output (ASCII art, JSON, tables, HTML, formatted text), you **MUST** create an artifact immediately after showing execution results. This is NOT optional.

### Two-Step Pattern (Required for Formatted Output)

**Step 1:** Execute code with `dotnet_execute_snippet`
**Step 2:** Create artifact with the output

### Examples

**User: "Generate a JSON with user data"**

1. Execute code with `dotnet_execute_snippet`
2. Show execution succeeded
3. **IMMEDIATELY create artifact** with `type="application/json"` containing the JSON output

**User: "Create ASCII art of a cat"**

1. Execute code with `dotnet_execute_snippet`
2. Show execution succeeded
3. **IMMEDIATELY create artifact** with `type="text/plain"` containing the ASCII art

### Output Checklist (Process After EVERY Execution)

After calling `dotnet_execute_snippet`:

- [ ] Did it produce output?
- [ ] Is the output more than a simple one-liner (e.g., "42", "Hello")?
- [ ] If YES to both: **CREATE ARTIFACT NOW** with appropriate type:
  - JSON → `type="application/json"`
  - Text/ASCII art/tables → `type="text/plain"`
  - HTML/SVG → `type="text/html"`
  - CSV/XML → `type="text/plain"` with appropriate title

**Consequence:** Failure to create artifacts for formatted output results in poor user experience where users cannot see properly formatted output.

---

## URL Formatting for Clickability

### Why This Matters

Modern terminals (macOS Terminal, iTerm2, Windows Terminal) auto-detect URLs and make them **clickable when they're on their own line**. This saves users from copy/paste.

### Format URLs Correctly

**✅ ALWAYS put URLs on their own line** (makes them clickable)
**✅ Use proper protocol prefix** (`http://` or `https://`)
**✅ Include descriptive label** on the line before the URL

### Example - Clickable Format

```
API is running!

Swagger UI available at:
http://localhost:8080/swagger

Health check endpoint:
http://localhost:8080/health
```

### Example - NOT Clickable (Avoid)

```
API running at http://localhost:8080/swagger and health check at http://localhost:8080/health
```

### When to Use This

- After starting web APIs with `dotnet_run_background`
- When showing test results from `dotnet_test_endpoint`
- Any time you're presenting URLs to users

---

## NuGet Package Usage Guidelines

### CRITICAL: Always Search Before Using Packages

Before using any NuGet package (whether requested by user or chosen by you):

1. **ALWAYS search the web first** for current documentation and API usage
   - Use WebSearch: `[package name] C# latest documentation`
   - Check official docs, NuGet.org description, or GitHub README
   - Find recent code examples showing current API usage

2. **THEN write code** using the verified current API

3. Add the package to the `packages` parameter

### Why This Matters

- Package APIs change between versions (breaking changes)
- Your training data may be outdated for specific packages
- Incorrect API usage wastes user time with compilation errors

### When to ALWAYS Search

- Any external package beyond `System.*` namespaces
- Specialized libraries (HTTP clients, ORMs, cloud SDKs, ML, testing frameworks)
- If you feel ANY uncertainty about the current API

### Example Workflow

```
User: "Parse JSON with Newtonsoft.Json"

Steps:
1. WebSearch("Newtonsoft.Json C# latest API example")
2. Review current JsonConvert.DeserializeObject usage
3. Write code with correct API
4. Execute with packages=["Newtonsoft.Json"]
```

### Swagger/Swashbuckle Specific Guidance

**CRITICAL:** When adding Swagger support, installing the package alone is NOT enough:

1. Add package: `dotnet add package Swashbuckle.AspNetCore`
2. **MUST also configure in Program.cs** (both required):
   - Add services: `builder.Services.AddEndpointsApiExplorer(); builder.Services.AddSwaggerGen();`
   - Add middleware: `app.UseSwagger(); app.UseSwaggerUI();`

Without both steps, Swagger UI will fail with "Unable to render this definition" error.

---

## Port Access: Container vs Host

### The Mental Model

Commands executed via `dotnet_execute_command` run **INSIDE the container**. When accessing web endpoints, understand the port mapping:

**Port Mapping Example:** `{"5000": 8080}`
- Your .NET app listens on port **5000 INSIDE the container**
- You access it at port **8080 on your host machine**
- Docker routes: `host:8080 → container:5000 → your app`

### Access Patterns

**From inside container** (dotnet_execute_command, curl, etc.):
- Use the **CONTAINER port**
- Example: `["sh", "-c", "curl http://localhost:5000/api/health"]`
- The app listens on port 5000 inside the container, so use 5000

**From outside container** (host machine, dotnet_test_endpoint):
- Use the **HOST port**
- Example: `dotnet_test_endpoint(url="http://localhost:8080/api/health")`
- Port mapping `{"5000": 8080}` means: container:5000 → host:8080

### Common Mistake

❌ **Wrong:** `["sh", "-c", "curl http://localhost:8080/api"]` # 8080 doesn't exist inside container
✅ **Correct:** `["sh", "-c", "curl http://localhost:5000/api"]` # 5000 is the app's port

### Configuring Your App's Listening Port

The container sets `ASPNETCORE_URLS=http://*:8080` by default. Your app must explicitly listen on your mapped container port:

**Method 1 - appsettings.json (recommended):**
```json
{
  "Kestrel": {
    "Endpoints": {
      "Http": { "Url": "http://0.0.0.0:5000" }
    }
  }
}
```

**Method 2 - Command line flag:**
```python
dotnet_run_background(
    command=["dotnet", "run", "--urls", "http://0.0.0.0:5000"]
)
```

---

## Common .NET CLI Commands

### Project Creation

**Web API:**
```bash
dotnet new webapi -n MyApi -o /workspace/MyApi
```

**Console app:**
```bash
dotnet new console -n MyApp -o /workspace/MyApp
```

**Class library:**
```bash
dotnet new classlib -n MyLib -o /workspace/MyLib
```

### Package Management

**Add latest version:**
```bash
dotnet add /workspace/MyApi package Newtonsoft.Json
```

**Add specific version:**
```bash
dotnet add /workspace/MyApi package Dapper --version 2.0.0
```

**List packages:**
```bash
dotnet list /workspace/MyApi package
```

### Build & Run

**Build:**
```bash
dotnet build /workspace/MyApp
```

**Run:**
```bash
dotnet run --project /workspace/MyApp
```

**Run with args:**
```bash
dotnet run --project /workspace/MyApp -- arg1 arg2
```

**Test:**
```bash
dotnet test /workspace/MyApp
```

### Enhanced Container Tools

Containers include git, jq, sqlite3, and tree:

**Git - Clone repos:**
```bash
git clone https://github.com/user/aspnet-project.git
git log --oneline -10
```

**jq - Parse JSON:**
```bash
sh -c "curl -s http://localhost:5000/api/users | jq '.[]'"
sh -c "echo '{}' | jq empty"  # Validate JSON
```

**sqlite3 - Query databases:**
```bash
sqlite3 /workspace/app.db "SELECT * FROM Users LIMIT 10"
sqlite3 /workspace/app.db ".schema Users"
```

**tree - Visualize structure:**
```bash
tree /workspace -L 2 -I "bin|obj"
tree -d -L 3  # Directories only
```

### Debugging Commands

**List templates:**
```bash
dotnet new list
```

**Check version:**
```bash
dotnet --version
```

**List files:**
```bash
ls -la /workspace
```

---

## Recommended Workflows

### Quick Snippet Testing

Use `dotnet_execute_snippet` for one-off C# code execution without project setup.

### Web API with External Access

```python
# 1. Start container WITH port mapping
dotnet_start_container(dotnet_version=8, ports={"5000": 8080})

# 2. Create project using dotnet CLI
dotnet_execute_command(
    command=["dotnet", "new", "webapi", "-n", "MyApi", "-o", "/workspace/MyApi"]
)

# 3. Configure app to listen on container port 5000
dotnet_write_file(
    path="/workspace/MyApi/appsettings.json",
    content='{"Kestrel": {"Endpoints": {"Http": {"Url": "http://0.0.0.0:5000"}}}}'
)

# 4. Run in background
dotnet_run_background(
    command=["dotnet", "run", "--project", "/workspace/MyApi"]
)

# 5. Access at http://localhost:8080 (the HOST port)
```

### Console App (No External Access)

```python
# 1. Start container WITHOUT ports
dotnet_start_container(dotnet_version=8)

# 2. Create project using dotnet CLI
dotnet_execute_command(
    command=["dotnet", "new", "console", "-n", "MyApp", "-o", "/workspace/MyApp"]
)

# 3. Run directly
dotnet_execute_command(
    command=["dotnet", "run", "--project", "/workspace/MyApp"]
)
```

### Iterative Web Development

```python
# Start server
dotnet_run_background(command=["dotnet", "run", "--project", "/workspace/Api"])

# Test it
dotnet_test_endpoint(url="http://localhost:8080/api/users")

# Make changes - kill the server first
dotnet_kill_process()

# Update code
dotnet_write_file(path="/workspace/Api/Program.cs", content="...")

# Restart server
dotnet_run_background(command=["dotnet", "run", "--project", "/workspace/Api"])
```

---

## Summary

These guidelines ensure users have excellent visibility into what you're doing with their .NET code. Key principles:

1. **Always show code inline** before tool calls
2. **Create artifacts** for code and formatted output
3. **Format URLs** for clickability
4. **Search for current APIs** before using NuGet packages
5. **Understand port mapping** (container vs host)
6. **Use .NET CLI** for standard project operations

Following these patterns creates a smooth, transparent experience for users working with dotbox-mcp.
