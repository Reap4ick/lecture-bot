$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Get-PowerIndex([string]$text, [string]$kind) {
    $match = [regex]::Match($text, "Current $kind Power Setting Index:\s*0x([0-9a-fA-F]+)")
    if (-not $match.Success) { throw "Could not read $kind power setting" }
    return [Convert]::ToInt32($match.Groups[1].Value, 16)
}

$schemeLine = (& powercfg /getactivescheme | Out-String)
$schemeMatch = [regex]::Match($schemeLine, '([0-9a-fA-F-]{36})')
if (-not $schemeMatch.Success) { throw 'Could not detect active Windows power scheme' }
$scheme = $schemeMatch.Groups[1].Value
$query = (& powercfg /q $scheme SUB_BUTTONS LIDACTION | Out-String)
$oldLidAc = Get-PowerIndex $query 'AC'
$oldLidDc = Get-PowerIndex $query 'DC'

$standbyQuery = (& powercfg /q $scheme SUB_SLEEP STANDBYIDLE | Out-String)
$oldStandbyAc = Get-PowerIndex $standbyQuery 'AC'
$oldStandbyDc = Get-PowerIndex $standbyQuery 'DC'

$backup = Join-Path $env:TEMP 'lecture-bot-power-backup.json'
@{
    scheme = $scheme
    lidAc = $oldLidAc
    lidDc = $oldLidDc
    standbyAc = $oldStandbyAc
    standbyDc = $oldStandbyDc
} | ConvertTo-Json | Set-Content -LiteralPath $backup -Encoding UTF8

$changed = $false
try {
    & powercfg /setacvalueindex $scheme SUB_BUTTONS LIDACTION 0 | Out-Null
    & powercfg /setdcvalueindex $scheme SUB_BUTTONS LIDACTION 0 | Out-Null
    & powercfg /setacvalueindex $scheme SUB_SLEEP STANDBYIDLE 0 | Out-Null
    & powercfg /setdcvalueindex $scheme SUB_SLEEP STANDBYIDLE 0 | Out-Null
    & powercfg /S $scheme | Out-Null
    $changed = $true
    Write-Host 'Lecture Bot power mode enabled: no sleep and lid close does nothing.'

    $python = Start-Process -FilePath 'python' -ArgumentList 'app.py' -WorkingDirectory $PSScriptRoot -PassThru
    Start-Sleep -Seconds 3
    Start-Process 'http://127.0.0.1:5000'
    $python.WaitForExit()
    if ($python.ExitCode -ne 0) { Write-Host "Lecture Bot exited with code $($python.ExitCode)." }
}
finally {
    if ($changed) {
        & powercfg /setacvalueindex $scheme SUB_BUTTONS LIDACTION $oldLidAc | Out-Null
        & powercfg /setdcvalueindex $scheme SUB_BUTTONS LIDACTION $oldLidDc | Out-Null
        & powercfg /setacvalueindex $scheme SUB_SLEEP STANDBYIDLE $oldStandbyAc | Out-Null
        & powercfg /setdcvalueindex $scheme SUB_SLEEP STANDBYIDLE $oldStandbyDc | Out-Null
        & powercfg /S $scheme | Out-Null
        Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
        Write-Host 'Previous Windows power settings restored.'
    }
}
