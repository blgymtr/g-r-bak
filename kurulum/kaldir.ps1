# gör-bak kaldırma: program klasörünü, kısayolları ve Uygulamalar kaydını siler.
# Kaydettiğiniz PNG / JPG / PDF ve DICOM kopyalarına dokunmaz.
$ErrorActionPreference = 'Continue'
$hedef = Join-Path $env:LOCALAPPDATA 'Programs\gor-bak'

Write-Host ''
Write-Host '  gör-bak kaldırılıyor' -ForegroundColor White
Get-Process -Name 'gor-bak' -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500

$masaustu = [Environment]::GetFolderPath('Desktop')
$baslat = Join-Path ([Environment]::GetFolderPath('Programs')) 'gör-bak'
Remove-Item -LiteralPath (Join-Path $masaustu 'gör-bak.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $baslat -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\gor-bak' -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path 'HKCU:\Software\gor-bak' -Recurse -Force -ErrorAction SilentlyContinue
Set-Location $env:TEMP
Remove-Item -LiteralPath $hedef -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $env:TEMP 'gor-bak') -Recurse -Force -ErrorAction SilentlyContinue

Write-Host '  gör-bak kaldırıldı. Kaydettiğiniz dosyalar yerinde duruyor.' -ForegroundColor Green
Write-Host ''
if ($env:GORBAK_SESSIZ -ne '1') { Start-Sleep -Seconds 3 }
