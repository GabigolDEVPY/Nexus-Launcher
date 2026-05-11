Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}

$ConstantsPath = Join-Path $ProjectRoot "core\constants.py"
$VersionMatch = Select-String -Path $ConstantsPath -Pattern 'APP_VERSION\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $VersionMatch) {
    throw "Nao foi possivel localizar APP_VERSION em core/constants.py"
}
$AppVersion = $VersionMatch.Matches[0].Groups[1].Value

Write-Host "Limpando build anterior..."
foreach ($path in @("build", "dist", "dist-installer")) {
    $fullPath = Join-Path $ProjectRoot $path
    if (Test-Path -LiteralPath $fullPath) {
        Remove-Item -LiteralPath $fullPath -Recurse -Force
    }
}

Write-Host "Validando PyInstaller..."
& $PythonExe -m PyInstaller --version | Out-Null

$PortableGitDir = Join-Path $ProjectRoot "vendor\PortableGit"
if (Test-Path $PortableGitDir) {
    Write-Host "PortableGit encontrado e sera embutido no build."
}
else {
    Write-Warning "PortableGit nao encontrado em vendor\\PortableGit."
    Write-Warning "Sem ele, o app instalado ainda dependera do Git do sistema."
}

Write-Host "Gerando build onedir..."
& $PythonExe -m PyInstaller --noconfirm (Join-Path $ProjectRoot "NexusLauncher.spec")

$InstallerScript = Join-Path $ProjectRoot "installer\NexusLauncher.iss"
$IsccCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
$RegistryInstallLocation = $null
try {
    $RegistryInstallLocation = (
        Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1' -ErrorAction Stop
    ).InstallLocation
}
catch {
}

if ($RegistryInstallLocation) {
    $IsccCandidates += (Join-Path $RegistryInstallLocation "ISCC.exe")
}

$IsccPath = $IsccCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

if ($IsccPath) {
    Write-Host "Gerando instalador..."
    & $IsccPath "/DMyAppVersion=$AppVersion" $InstallerScript
    Write-Host "Instalador criado em dist-installer."
}
else {
    Write-Warning "Inno Setup nao encontrado. O build da pasta foi gerado em dist\\NexusLauncher."
    Write-Warning "Instale o Inno Setup 6 para compilar installer\\NexusLauncher.iss."
}

Write-Host "Build concluido."
