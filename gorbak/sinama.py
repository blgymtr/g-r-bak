"""Öz sınama: gor-bak.exe <dosyalar> --sinama-cikti <klasör>

Kurulu programın gerçek arayüzüyle dosyaları açar, ilk görüntüyü gösterir, ekranda görüneni PNG / JPG,
çalışmayı PDF olarak kaydeder, orijinalleri kopyalar ve pencerenin ekran görüntüsünü alır.
Sonuç <klasör>/sinama.txt dosyasına yazılır. Çıkış kodu: 0 başarılı, 1 hata.
"""
from __future__ import annotations

import os
import time
import traceback

from . import disari as D
from . import kutuphane as K


def _bekle(app, sn=0.3):
    son = time.time() + sn
    while time.time() < son:
        app.processEvents()
        time.sleep(0.02)


def oz_sinama(app, pencere, yollar, klasor) -> int:
    os.makedirs(klasor, exist_ok=True)
    rapor: list[str] = []
    basarili = True

    def yaz(satir):
        rapor.append(satir)

    try:
        pencere.resize(1400, 860)
        _bekle(app, 0.5)
        sonuc = pencere.kutuphane.ekle(yollar)
        pencere.agaci_kur()
        yaz(f"Tarama: {sonuc.eklenen} eklendi, {sonuc.tekrar} tekrar, {sonuc.atlanan} atlandı, {len(sonuc.hatalar)} hata")
        for h in sonuc.hatalar:
            yaz("  HATA " + h)
        ogeler = pencere.kutuphane.tum_ogeler()
        goruntulu = [o for o in ogeler if o.tur in K.GORUNTULU_TURLER]
        if not goruntulu:
            raise RuntimeError("Görüntü bulunamadı")

        # her görüntüyü aç (çözücülerin pakette olduğunu doğrular)
        acilan = 0
        for o in goruntulu:
            pencere.ogeyi_ac(o)
            _bekle(app, 0.05)
            if pencere.kaynak is not None and pencere.oge is o:
                acilan += 1
                yaz(f"  AÇILDI {o.seri.modalite if o.seri else ''} {os.path.basename(o.yol)} "
                    f"({pencere.kaynak.kare_sayisi} kare, {pencere.alan.boyut[0]}x{pencere.alan.boyut[1]})")
            else:
                basarili = False
                yaz(f"  AÇILAMADI {os.path.basename(o.yol)}")
        yaz(f"Açılan görüntü: {acilan}/{len(goruntulu)}")

        # ekranda bir CT/MR göster, pencere ayarını değiştir, çok kareliyse ikinci kareye geç
        tercih = next((o for o in goruntulu if o.seri and o.seri.modalite in ("CT", "MR")), goruntulu[0])
        pencere.ogeyi_ac(tercih)
        if tercih.seri and tercih.seri.modalite == "CT":
            pencere.pencere_ayarla(40, 400)
        _bekle(app, 0.4)
        cok_kareliler = [o for o in goruntulu if o.kare_sayisi > 1]
        cok = max(cok_kareliler, key=lambda o: o.kare_sayisi) if cok_kareliler else None

        cikti = {}
        cikti["goruntu.png"] = pencere.goruntuyu_kaydet("PNG", os.path.join(klasor, "goruntu.png"))
        cikti["goruntu.jpg"] = pencere.goruntuyu_kaydet("JPG", os.path.join(klasor, "goruntu.jpg"))
        pencere.grab().save(os.path.join(klasor, "pencere.png"))
        cikti["pencere.png"] = os.path.join(klasor, "pencere.png")

        calisma = tercih.calisma
        sayfa, hata = D.pdf_olustur(calisma.tum_ogeler(), os.path.join(klasor, "calisma.pdf"),
                                    pencere._pencere_kayitlari)
        yaz(f"PDF: {sayfa} sayfa, {len(hata)} hata")
        cikti["calisma.pdf"] = os.path.join(klasor, "calisma.pdf")
        adet, hata = D.orijinalleri_kopyala(ogeler, os.path.join(klasor, "orijinal"))
        yaz(f"Orijinal kopya: {adet}/{len(ogeler)} dosya, {len(hata)} hata")
        if adet != len(ogeler):
            basarili = False

        if cok is not None:
            pencere.ogeyi_ac(cok)
            pencere.kareye_git(1)
            _bekle(app, 0.3)
            yaz(f"Çok kareli: {os.path.basename(cok.yol)} -> {pencere.kare_etiketi.text()}")
            cikti["kare2.png"] = pencere.goruntuyu_kaydet("PNG", os.path.join(klasor, "kare2.png"))
            pencere.grab().save(os.path.join(klasor, "pencere_cok_kare.png"))

        for ad, yol in cikti.items():
            boyut = os.path.getsize(yol) if yol and os.path.isfile(yol) else 0
            yaz(f"Çıktı {ad}: {boyut} bayt")
            if boyut < 500:
                basarili = False
    except Exception:  # noqa: BLE001
        basarili = False
        yaz(traceback.format_exc())

    yaz("SONUÇ: " + ("BAŞARILI" if basarili else "HATALI"))
    with open(os.path.join(klasor, "sinama.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(rapor) + "\n")
    pencere.close()
    K.gecicileri_temizle(eskiler_de=False)
    return 0 if basarili else 1
