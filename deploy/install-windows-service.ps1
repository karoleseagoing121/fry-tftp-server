# Install Fry TFTP Server as a Windows Service
# Run as Administrator

$ServiceName = "FryTftpServer"
$DisplayName = "Fry TFTP Server"
$ExePath = "$PSScriptRoot\..\target\release\fry-tftp-server.exe"
$Arguments = "--headless"

# Check if running as admin
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Error "Please run this script as Administrator"
    exit 1
}

# Stop existing service if running
$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    if ($existing.Status -eq "Running") {
        Stop-Service -Name $ServiceName -Force
    }
    sc.exe delete $ServiceName
    Start-Sleep -Seconds 2
}

# Create the service
New-Service -Name $ServiceName `
    -DisplayName $DisplayName `
    -Description "Cross-platform high-performance TFTP server" `
    -BinaryPathName "`"$ExePath`" $Arguments" `
    -StartupType Automatic

# Add firewall rule
$ruleName = "Fry TFTP Server (UDP 69)"
$existingRule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if (-not $existingRule) {
    New-NetFirewallRule -DisplayName $ruleName `
        -Direction Inbound `
        -Protocol UDP `
        -LocalPort 69 `
        -Action Allow `
        -Profile Any
}

Write-Host "Service '$ServiceName' installed. Start with: Start-Service $ServiceName"
