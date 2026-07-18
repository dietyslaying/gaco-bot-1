# Deploy gaco-bot to Alwaysdata over SSH/SCP from Windows.
# Usage:
#   .\scripts\deploy-alwaysdata.ps1
#   $env:ALWAYSDATA_SSH = "chad@ssh-chad.alwaysdata.net"; .\scripts\deploy-alwaysdata.ps1

$ErrorActionPreference = "Stop"
$HostName = if ($env:ALWAYSDATA_SSH) { $env:ALWAYSDATA_SSH } else { "chad@ssh-chad.alwaysdata.net" }
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$RemoteDir = "gaco-bot"

Write-Host "Deploying $Root -> ${HostName}:~/$RemoteDir"

# Ensure remote dir
ssh $HostName "mkdir -p ~/$RemoteDir/logs ~/$RemoteDir/data"

# Sync code (exclude secrets, venv, caches, backups dumps)
$excludes = @(
  "--exclude=.git",
  "--exclude=.venv",
  "--exclude=venv",
  "--exclude=__pycache__",
  "--exclude=*.pyc",
  "--exclude=.env",
  "--exclude=backups/*.sqlite",
  "--exclude=backups/*.sql",
  "--exclude=logs"
)

# Prefer rsync if available; else tar over ssh
$rsync = Get-Command rsync -ErrorAction SilentlyContinue
if ($rsync) {
  & rsync -avz --delete @excludes "$Root/" "${HostName}:~/$RemoteDir/"
} else {
  Write-Host "rsync not found — using tar+ssh"
  $tarArgs = @(
    "-czf", "-",
    "--exclude=.git", "--exclude=.venv", "--exclude=venv",
    "--exclude=__pycache__", "--exclude=.env",
    "--exclude=backups/*.sqlite", "--exclude=backups/*.sql",
    "-C", $Root, "."
  )
  # Git bash tar if present
  $tar = Get-Command tar -ErrorAction SilentlyContinue
  if (-not $tar) { throw "Need tar or rsync installed" }
  & tar @tarArgs | ssh $HostName "mkdir -p ~/$RemoteDir && tar -xzf - -C ~/$RemoteDir"
}

ssh $HostName "chmod +x ~/$RemoteDir/scripts/alwaysdata/*.sh; bash ~/$RemoteDir/scripts/alwaysdata/setup.sh"
Write-Host ""
Write-Host "Code deployed. If .env is not on the server yet:"
Write-Host "  scp .env ${HostName}:~/$RemoteDir/.env"
Write-Host "Then:"
Write-Host "  ssh $HostName 'bash ~/$RemoteDir/scripts/alwaysdata/start-bot.sh'"
Write-Host "  ssh $HostName 'bash ~/$RemoteDir/scripts/alwaysdata/install-cron.sh'"
