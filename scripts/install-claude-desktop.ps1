# dotbox-mcp installer for Windows (Claude Desktop)
# Usage: irm https://raw.githubusercontent.com/domibies/dotbox-mcp/main/scripts/install-claude-desktop.ps1 | iex

$ErrorActionPreference = 'Stop'

Write-Host 'dotbox-mcp installer for Windows' -ForegroundColor Cyan
Write-Host ''

# 1. Check if Docker Desktop is installed and running
$dockerPaths = @(
    "${env:ProgramFiles}\Docker\Docker\resources\bin\docker.exe",
    "${env:ProgramFiles(x86)}\Docker\Docker\resources\bin\docker.exe"
)

$dockerExePath = $null
foreach ($path in $dockerPaths) {
    if (Test-Path $path) {
        $dockerExePath = $path
        break
    }
}

if (-not $dockerExePath) {
    Write-Host '[ERROR] Docker Desktop not found' -ForegroundColor Red
    Write-Host ''
    Write-Host 'Install Docker Desktop for Windows:'
    Write-Host '  https://docs.docker.com/desktop/install/windows-install/' -ForegroundColor Cyan
    Write-Host ''
    Write-Host 'After installing Docker Desktop, start it and re-run this installer.'
    return
}

Write-Host '[OK] Docker Desktop found' -ForegroundColor Green

# 2. Check if Docker daemon TCP port (2375) is enabled
try {
    $response = Invoke-WebRequest -Uri 'http://localhost:2375/version' -TimeoutSec 2 -ErrorAction Stop
    Write-Host '[OK] Docker TCP port 2375 enabled' -ForegroundColor Green
} catch {
    Write-Host '[ERROR] Docker TCP port 2375 is not enabled' -ForegroundColor Red
    Write-Host ''
    Write-Host 'Enable Docker daemon TCP access:'
    Write-Host '  1. Open Docker Desktop'
    Write-Host '  2. Go to Settings > General'
    Write-Host '  3. Enable "Expose daemon on tcp://localhost:2375 without TLS"'
    Write-Host '  4. Click "Apply & Restart"'
    Write-Host '  5. Re-run this installer'
    Write-Host ''
    Write-Host '[WARNING] This exposes Docker API without authentication. Only enable on trusted networks.' -ForegroundColor Yellow
    return
}

# 3. Check if Claude Desktop is installed
$claudeDesktopPaths = @(
    "$env:LOCALAPPDATA\AnthropicClaude\Claude.exe",
    "$env:LOCALAPPDATA\Programs\Claude\Claude.exe",
    "$env:ProgramFiles\AnthropicClaude\Claude.exe",
    "$env:ProgramFiles\Claude\Claude.exe"
)

$claudeDesktopInstalled = $false
foreach ($path in $claudeDesktopPaths) {
    if (Test-Path $path) {
        $claudeDesktopInstalled = $true
        break
    }
}

if (-not $claudeDesktopInstalled) {
    Write-Host '[WARNING] Claude Desktop not found' -ForegroundColor Yellow
    Write-Host ''
    Write-Host 'Install Claude Desktop from:'
    Write-Host '  https://claude.ai/download' -ForegroundColor Cyan
    Write-Host ''
    Write-Host 'You can continue with this installer, but you will need Claude Desktop to use dotbox-mcp.'
    Write-Host ''
    $response = Read-Host 'Continue anyway? (y/N)'
    if ($response -ne 'y' -and $response -ne 'Y') {
        Write-Host 'Installation cancelled.'
        return
    }
}

Write-Host '[OK] Claude Desktop found' -ForegroundColor Green

# 4. Claude Desktop config path (Windows)
$configPath = Join-Path $env:APPDATA 'Claude\claude_desktop_config.json'

# 5. Check if already installed (idempotency)
$alreadyInstalled = $false
if (Test-Path $configPath) {
    try {
        $config = Get-Content $configPath -Raw -ErrorAction Stop | ConvertFrom-Json
        if ($config.mcpServers.'dotbox-mcp') {
            $alreadyInstalled = $true
        }
    } catch {
        Write-Host '[WARNING] Existing config file has invalid JSON, will recreate' -ForegroundColor Yellow
    }
}

if ($alreadyInstalled -and $args -notcontains '--force') {
    Write-Host '[OK] dotbox-mcp already installed' -ForegroundColor Yellow
    Write-Host ''

    # Use direct console input for interactive prompt
    $response = Read-Host 'Do you want to reinstall and update the configuration? (y/N)'

    if ($response -ne 'y' -and $response -ne 'Y') {
        Write-Host 'Installation cancelled. To reinstall later, run with --force flag.'
        return
    }
    Write-Host 'Reinstalling...'
}

# 6. Backup existing config
$configDir = Split-Path $configPath -Parent
if (-not (Test-Path $configDir)) {
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
}

if (Test-Path $configPath) {
    $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $backupPath = "$configPath.backup.$timestamp"
    Copy-Item $configPath $backupPath
    Write-Host ('[OK] Backed up config to: ' + (Split-Path $backupPath -Leaf)) -ForegroundColor Green
}

# 7. Update config (preserves other MCPs)
Write-Host 'Updating Claude Desktop config...'

try {
    # Load or create config
    if (Test-Path $configPath) {
        $config = Get-Content $configPath -Raw | ConvertFrom-Json
    } else {
        $config = [PSCustomObject]@{
            mcpServers = [PSCustomObject]@{}
        }
    }

    # Ensure mcpServers exists
    if (-not $config.mcpServers) {
        $config | Add-Member -MemberType NoteProperty -Name 'mcpServers' -Value ([PSCustomObject]@{}) -Force
    }

    # Add/update dotbox-mcp entry using native Docker
    $dotboxConfig = [PSCustomObject]@{
        command = $dockerExePath
        args = @(
            'run',
            '--rm',
            '-i',
            '--add-host',
            'host.docker.internal:host-gateway',
            '-e',
            'DOCKER_HOST=tcp://host.docker.internal:2375',
            'ghcr.io/domibies/dotbox-mcp:latest'
        )
    }

    # Update or add the dotbox-mcp entry
    if ($config.mcpServers.'dotbox-mcp') {
        $config.mcpServers.'dotbox-mcp' = $dotboxConfig
    } else {
        $config.mcpServers | Add-Member -MemberType NoteProperty -Name 'dotbox-mcp' -Value $dotboxConfig -Force
    }

    # Write config atomically (UTF8 without BOM)
    $tempPath = "$configPath.tmp"
    $json = $config | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText($tempPath, $json, (New-Object System.Text.UTF8Encoding $false))
    Move-Item $tempPath $configPath -Force

    Write-Host '[OK] Config updated' -ForegroundColor Green
} catch {
    Write-Host ('[ERROR] Failed to update config: ' + $_) -ForegroundColor Red
    return
}

# 8. Pull Docker images in parallel
Write-Host ''
Write-Host 'Pulling Docker images (~1GB total, may take a few minutes)...'

$jobs = @(
    Start-Job -ScriptBlock { & $using:dockerExePath pull ghcr.io/domibies/dotbox-mcp:latest 2>&1 | Out-Null }
    Start-Job -ScriptBlock { & $using:dockerExePath pull ghcr.io/domibies/dotbox-mcp/dotnet-sandbox:8 2>&1 | Out-Null }
    Start-Job -ScriptBlock { & $using:dockerExePath pull ghcr.io/domibies/dotbox-mcp/dotnet-sandbox:9 2>&1 | Out-Null }
    Start-Job -ScriptBlock { & $using:dockerExePath pull ghcr.io/domibies/dotbox-mcp/dotnet-sandbox:10 2>&1 | Out-Null }
)

# Wait for all pulls to complete
$jobs | Wait-Job | Out-Null
$jobs | Remove-Job

Write-Host '[OK] Docker images pulled' -ForegroundColor Green

# 9. Show security notice
Write-Host ''
Write-Host '[SECURITY NOTICE]' -ForegroundColor Yellow
Write-Host '  Docker TCP port 2375 exposes Docker API without authentication.'
Write-Host '  Only enable on trusted networks (localhost/private network).'
Write-Host '  dotbox-mcp creates isolated .NET containers for code execution.'
Write-Host '  Review code: https://github.com/domibies/dotbox-mcp'
Write-Host ''

# 10. Success message
Write-Host '[SUCCESS] dotbox-mcp installed successfully!' -ForegroundColor Green
Write-Host ''
Write-Host 'Next steps:'
Write-Host '  1. Restart Claude Desktop'
Write-Host '  2. Try asking: Execute this C# code: Console.WriteLine(DateTime.Now);'
Write-Host ''
