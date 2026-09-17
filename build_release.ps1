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

Write-Host "NexusLauncher $AppVersion - build onefile portatil"

Write-Host "Limpando build anterior..."
foreach ($path in @("build", "dist")) {
    $fullPath = Join-Path $ProjectRoot $path
    if (Test-Path -LiteralPath $fullPath) {
        Remove-Item -LiteralPath $fullPath -Recurse -Force
    }
}

Write-Host "Validando PyInstaller..."
& $PythonExe -m PyInstaller --version | Out-Null

Write-Host "Gerando NexusLauncher.exe (onefile)..."
& $PythonExe -m PyInstaller --noconfirm (Join-Path $ProjectRoot "NexusLauncher.spec")

$OutputExe = Join-Path $ProjectRoot "dist\NexusLauncher.exe"
if (-not (Test-Path $OutputExe)) {
    throw "Build falhou: NexusLauncher.exe nao foi gerado em dist\."
}

$SizeMb = [math]::Round((Get-Item $OutputExe).Length / 1MB, 1)
Write-Host "Build concluido: dist\NexusLauncher.exe ($SizeMb MB)"
Write-Host "O exe e portatil: nao precisa de Git, Python nem instalacao."
