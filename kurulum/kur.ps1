# gör-bak kurulumu: programı kullanıcı klasörüne kopyalar, Masaüstü ve Başlat menüsüne kısayol ekler.
# Yönetici izni gerekmez. İnternete bağlanmaz.
$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'gör-bak kurulumu'

function Yaz($metin, $renk = 'Gray') { Write-Host $metin -ForegroundColor $renk }

try {
    $kok = Split-Path -Parent $PSScriptRoot
    $kaynak = Join-Path $kok 'program'
    $exeKaynak = Join-Path $kaynak 'gor-bak.exe'
    if (-not (Test-Path $exeKaynak)) {
        Yaz 'Program dosyaları bulunamadı.' Red
        Yaz 'Zip dosyasını önce bir klasöre çıkarın (sağ tık > Tümünü ayıkla), sonra Kur.cmd dosyasına çift tıklayın.' Yellow
        exit 1
    }

    $hedef = Join-Path $env:LOCALAPPDATA 'Programs\gor-bak'
    Yaz ''
    Yaz '  gör-bak kuruluyor' White
    Yaz "  Konum: $hedef"
    Yaz ''

    $calisan = Get-Process -Name 'gor-bak' -ErrorAction SilentlyContinue
    if ($calisan) {
        Yaz 'gör-bak açık. Kuruluma devam etmek için kapatılıyor…' Yellow
        $calisan | Stop-Process -Force
        Start-Sleep -Milliseconds 800
    }

    if (Test-Path $hedef) { Remove-Item -LiteralPath $hedef -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $hedef | Out-Null
    Copy-Item -Path (Join-Path $kaynak '*') -Destination $hedef -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'kaldir.ps1') -Destination $hedef -Force
    # İnternetten indirilen zip'in "engellendi" işaretini kaldır
    Get-ChildItem -LiteralPath $hedef -Recurse -File | Unblock-File

    $exe = Join-Path $hedef 'gor-bak.exe'
    $kaldir = Join-Path $hedef 'kaldir.ps1'
    $psYolu = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $kabuk = New-Object -ComObject WScript.Shell

    function Kisayol($yol, $hedefDosya, $argumanlar, $aciklama) {
        $k = $kabuk.CreateShortcut($yol)
        $k.TargetPath = $hedefDosya
        if ($argumanlar) { $k.Arguments = $argumanlar }
        $k.WorkingDirectory = $hedef
        $k.IconLocation = "$exe,0"
        $k.Description = $aciklama
        $k.Save()
    }

    $masaustu = [Environment]::GetFolderPath('Desktop')
    $baslat = Join-Path ([Environment]::GetFolderPath('Programs')) 'gör-bak'
    New-Item -ItemType Directory -Force -Path $baslat | Out-Null
    Kisayol (Join-Path $masaustu 'gör-bak.lnk') $exe $null 'Radyoloji görüntülerini aç ve kaydet'
    Kisayol (Join-Path $baslat 'gör-bak.lnk') $exe $null 'Radyoloji görüntülerini aç ve kaydet'
    Kisayol (Join-Path $baslat 'gör-bak kaldır.lnk') $psYolu "-NoProfile -ExecutionPolicy Bypass -File `"$kaldir`"" 'gör-bak programını kaldır'

    # Ayarlar > Uygulamalar listesinde görünsün
    $anahtar = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\gor-bak'
    New-Item -Path $anahtar -Force | Out-Null
    $boyut = [int]((Get-ChildItem -LiteralPath $hedef -Recurse -File | Measure-Object Length -Sum).Sum / 1KB)
    $degerler = @{
        DisplayName     = 'gör-bak'
        DisplayVersion  = '1.0.0'
        Publisher       = 'gör-bak'
        DisplayIcon     = "$exe,0"
        InstallLocation = $hedef
        UninstallString = "`"$psYolu`" -NoProfile -ExecutionPolicy Bypass -File `"$kaldir`""
    }
    foreach ($ad in $degerler.Keys) { New-ItemProperty -Path $anahtar -Name $ad -Value $degerler[$ad] -PropertyType String -Force | Out-Null }
    New-ItemProperty -Path $anahtar -Name 'EstimatedSize' -Value $boyut -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $anahtar -Name 'NoModify' -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $anahtar -Name 'NoRepair' -Value 1 -PropertyType DWord -Force | Out-Null

    Yaz '  Kurulum tamamlandı.' Green
    Yaz '  Masaüstündeki ve Başlat menüsündeki "gör-bak" kısayoluyla açabilirsiniz.'
    Yaz ''
    if ($env:GORBAK_SESSIZ -ne '1') { Start-Process -FilePath $exe }
    exit 0
}
catch {
    Yaz ''
    Yaz "Kurulum tamamlanamadı: $($_.Exception.Message)" Red
    exit 1
}
