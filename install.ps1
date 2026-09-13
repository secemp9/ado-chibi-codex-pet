[CmdletBinding()]
param(
    [switch]$Force,
    [string]$CodexHome
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PackageDir = Join-Path $RepoRoot "pet/ado"

if (-not $CodexHome) {
    if ($env:CODEX_HOME) {
        $CodexHome = $env:CODEX_HOME
    }
    else {
        $CodexHome = Join-Path $HOME ".codex"
    }
}

$TargetDir = Join-Path $CodexHome "pets/ado"
$ChecksumLine = Get-Content (Join-Path $RepoRoot "SHA256SUMS") |
    Where-Object { $_ -match "\s+pet/ado/spritesheet\.webp$" } |
    Select-Object -First 1

if (-not $ChecksumLine) {
    throw "The spritesheet checksum is missing from SHA256SUMS."
}

$ExpectedHash = ($ChecksumLine -split "\s+")[0].ToLowerInvariant()
$ActualHash = (Get-FileHash (Join-Path $PackageDir "spritesheet.webp") -Algorithm SHA256).Hash.ToLowerInvariant()

if ($ActualHash -ne $ExpectedHash) {
    throw "Spritesheet checksum verification failed."
}

if (Test-Path -LiteralPath $TargetDir) {
    if (-not $Force) {
        throw "Ado is already installed at $TargetDir. Run ./install.ps1 -Force to back it up and replace it."
    }

    $Timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $BackupRoot = Join-Path $CodexHome "pet-backups"
    $BackupDir = Join-Path $BackupRoot "ado.backup.$Timestamp"
    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
    Move-Item -LiteralPath $TargetDir -Destination $BackupDir
    Write-Host "Backed up the previous installation to $BackupDir"
}

New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PackageDir "pet.json") -Destination $TargetDir
Copy-Item -LiteralPath (Join-Path $PackageDir "spritesheet.webp") -Destination $TargetDir

Write-Host "Installed Ado at $TargetDir"
Write-Host "Open Codex > Settings > Pets > Refresh, then select Ado."

