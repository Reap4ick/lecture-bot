$ErrorActionPreference = 'Stop'
$backup = Join-Path $env:TEMP 'lecture-bot-power-backup.json'
if (-not (Test-Path -LiteralPath $backup)) {
    Write-Host 'No Lecture Bot power backup found; nothing to restore.'
    exit 0
}
$data = Get-Content -LiteralPath $backup -Raw | ConvertFrom-Json
$scheme = [string]$data.scheme
& powercfg /setacvalueindex $scheme SUB_BUTTONS LIDACTION ([int]$data.lidAc) | Out-Null
& powercfg /setdcvalueindex $scheme SUB_BUTTONS LIDACTION ([int]$data.lidDc) | Out-Null
& powercfg /setacvalueindex $scheme SUB_SLEEP STANDBYIDLE ([int]$data.standbyAc) | Out-Null
& powercfg /setdcvalueindex $scheme SUB_SLEEP STANDBYIDLE ([int]$data.standbyDc) | Out-Null
& powercfg /S $scheme | Out-Null
Remove-Item -LiteralPath $backup -Force
Write-Host 'Previous Windows power settings restored.'
