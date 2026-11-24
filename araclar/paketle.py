"""Dağıtım paketini üretir: dagitim/gor-bak-<sürüm>.zip

İçerik:  Kur.cmd · BENIOKU.txt · kurulum/kur.ps1, kaldir.ps1 · program/gor-bak.exe (+ _internal)
Çalıştırma:  python araclar/paketle.py
"""
import os
import shutil
import subprocess
import sys
import zipfile

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)
from gorbak import SURUM  # noqa: E402

AD = f"gor-bak-{SURUM}"
DAGITIM = os.path.join(KOK, "dagitim")
PAKET = os.path.join(DAGITIM, AD)

BENIOKU = f"""gör-bak {SURUM} · yerel radyoloji görüntüleyici
==================================================

KURULUM
1. Bu zip dosyasını bir klasöre çıkarın (sağ tık > Tümünü ayıkla).
2. Kur.cmd dosyasına çift tıklayın.
   Windows "bilinmeyen yayımcı" uyarısı gösterirse "Ek bilgi" > "Yine de çalıştır" deyin.
3. Program şu klasöre kurulur: %LOCALAPPDATA%\\Programs\\gor-bak
   Masaüstüne ve Başlat menüsüne "gör-bak" kısayolu eklenir. Yönetici izni gerekmez.

KALDIRMA
Başlat menüsünde "gör-bak kaldır" kısayolunu ya da Ayarlar > Uygulamalar > gör-bak > Kaldır'ı kullanın.
Kaydettiğiniz dosyalar silinmez.

KURMADAN ÇALIŞTIRMA
program klasöründeki gor-bak.exe dosyasını doğrudan da açabilirsiniz.

NE AÇAR
DICOM (.dcm, uzantısız, CD/DVD'deki DICOMDIR), zip, JPG, PNG, BMP, TIFF, PDF ve DICOM içindeki PDF raporlar.
Röntgen (CR/DX), MR, BT, ultrason (çok kareli), mamografi ve diğerleri.

NE YAPAR
Pencere/seviye (parlaklık-kontrast), yakınlaştırma, kaydırma, kesit ve kare gezinme, oynatma, ölçüm,
DICOM etiketleri; görüntüyü ya da çalışmayı PNG, JPG, PDF olarak kaydetme ve orijinal DICOM'u kopyalama.

GİZLİLİK
İnternete bağlanmaz. Dosyalarınız hiçbir yere gönderilmez. Zip dosyaları geçici olarak açılır
ve program kapanınca silinir.

e-NABIZ'DA GÖRÜNTÜ AÇILMIYORSA
"Hastaneye erişim sorunu" mesajı, görüntünün hastanenin kendi arşivinde durduğunu ve e-Nabız'ın
o an ulaşamadığını gösterir. Hiçbir program görüntüyü oradan çekemez. Görüntü yüklenen çalışmaları
disk (kaydet) düğmesiyle indirin; açılmayanları hastaneden CD/DVD ya da DICOM dosyası olarak isteyin
ya da daha sonra yeniden deneyin.

Bu program tıbbi tanı aracı değildir.
"""


def calistir(*komut):
    print(">", " ".join(komut))
    subprocess.run(komut, cwd=KOK, check=True)


def main():
    py = sys.executable
    calistir(py, os.path.join("araclar", "simge_yap.py"))
    calistir(py, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", os.path.join("build", "dist"),
             "--workpath", os.path.join("build", "is"), "gor-bak.spec")
    program = os.path.join(KOK, "build", "dist", "gor-bak")

    if os.path.isdir(PAKET):
        shutil.rmtree(PAKET)
    os.makedirs(os.path.join(PAKET, "kurulum"))
    shutil.copytree(program, os.path.join(PAKET, "program"))
    shutil.copy(os.path.join(KOK, "kurulum", "Kur.cmd"), PAKET)
    for ad in ("kur.ps1", "kaldir.ps1"):
        shutil.copy(os.path.join(KOK, "kurulum", ad), os.path.join(PAKET, "kurulum"))
    with open(os.path.join(PAKET, "BENIOKU.txt"), "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(BENIOKU)

    zip_yolu = os.path.join(DAGITIM, AD + ".zip")
    if os.path.exists(zip_yolu):
        os.remove(zip_yolu)
    with zipfile.ZipFile(zip_yolu, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for kok, _, dosyalar in os.walk(PAKET):
            for d in sorted(dosyalar):
                tam = os.path.join(kok, d)
                z.write(tam, os.path.relpath(tam, DAGITIM))
    print(f"Paket: {zip_yolu} ({os.path.getsize(zip_yolu) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
