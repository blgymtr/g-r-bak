"""Dışa aktarma: PNG / JPG, PDF ve orijinal DICOM kopyası."""
from __future__ import annotations

import datetime as _dt
import os
import shutil

import numpy as np

from . import AD, SURUM
from . import goruntu as G
from . import kutuphane as K

A4 = (595.0, 842.0)
KENAR = 36.0


def _font_yolu() -> str | None:
    fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    for ad in ("arial.ttf", "segoeui.ttf", "calibri.ttf", "tahoma.ttf", "verdana.ttf"):
        yol = os.path.join(fonts, ad)
        if os.path.isfile(yol):
            return yol
    return None


def resim_kaydet(dizi: np.ndarray, yol: str) -> None:
    uzanti = os.path.splitext(yol)[1].lower()
    bicim = "JPEG" if uzanti in (".jpg", ".jpeg") else "PNG"
    with open(yol, "wb") as f:
        f.write(G.resim_baytlari(dizi, bicim))


def oge_dosya_adi(oge: K.Oge, kare: int | None = None, uzanti: str = ".png") -> str:
    c = oge.calisma
    parcalar = []
    if c is not None:
        parcalar.append(c.tarih or "tarihsiz")
        parcalar.append(oge.seri.modalite or "dosya")
    if oge.seri and oge.seri.numara is not None:
        parcalar.append(f"S{oge.seri.numara}")
    if oge.tur in (K.T_RESIM, K.T_PDF):
        parcalar.append(os.path.splitext(os.path.basename(oge.yol))[0])
    else:
        parcalar.append(f"G{oge.sira:04d}" if oge.sira else os.path.splitext(os.path.basename(oge.yol))[0])
    if kare is not None:
        parcalar.append(f"K{kare + 1:03d}")
    return K.guvenli_ad("_".join(parcalar), 120) + uzanti


def _benzersiz(yol: str) -> str:
    if not os.path.exists(yol):
        return yol
    kok, uzanti = os.path.splitext(yol)
    i = 2
    while os.path.exists(f"{kok} ({i}){uzanti}"):
        i += 1
    return f"{kok} ({i}){uzanti}"


def calisma_resimleri_kaydet(ogeler, klasor: str, bicim: str = "PNG", ilerleme=None, iptal_mi=None) -> tuple[int, list[str]]:
    """Öğelerin her karesini varsayılan pencereyle PNG / JPG olarak kaydeder."""
    uzanti = ".jpg" if bicim.upper() in ("JPG", "JPEG") else ".png"
    os.makedirs(klasor, exist_ok=True)
    adet, hatalar = 0, []
    isler = [o for o in ogeler if o.tur in K.GORUNTULU_TURLER]
    for n, oge in enumerate(isler):
        if iptal_mi and iptal_mi():
            break
        if ilerleme:
            ilerleme(n + 1, len(isler), oge.ad)
        try:
            kaynak = G.kaynak_ac(oge)
            seviye, genislik = kaynak.varsayilan_pencere()
            for k in range(kaynak.kare_sayisi):
                dizi = kaynak.ciz(k, seviye, genislik)
                ad = oge_dosya_adi(oge, k if kaynak.kare_sayisi > 1 else None, uzanti)
                resim_kaydet(dizi, _benzersiz(os.path.join(klasor, ad)))
                adet += 1
        except Exception as e:  # noqa: BLE001
            hatalar.append(f"{oge.ad}: {e}")
    return adet, hatalar


class PdfYazici:
    def __init__(self) -> None:
        import pymupdf

        self._pymupdf = pymupdf
        self.belge = pymupdf.open()
        self._font = _font_yolu()

    def _yazi(self, sayfa, nokta, metin, boyut=10.0, renk=(0, 0, 0)):
        if self._font:
            sayfa.insert_font(fontname="trf", fontfile=self._font)
            sayfa.insert_text(nokta, metin, fontname="trf", fontsize=boyut, color=renk)
        else:
            sayfa.insert_text(nokta, metin, fontname="helv", fontsize=boyut, color=renk)

    def _kutu(self, sayfa, dikdortgen, metin, boyut=10.0):
        r = self._pymupdf.Rect(*dikdortgen)
        if self._font:
            sayfa.insert_font(fontname="trf", fontfile=self._font)
            return sayfa.insert_textbox(r, metin, fontname="trf", fontsize=boyut)
        return sayfa.insert_textbox(r, metin, fontname="helv", fontsize=boyut)

    def kapak(self, baslik: str, satirlar: list[str]) -> None:
        sayfa = self.belge.new_page(width=A4[0], height=A4[1])
        self._yazi(sayfa, (KENAR, 70), baslik, 18)
        y = 100.0
        metin = "\n".join(satirlar)
        self._kutu(sayfa, (KENAR, y, A4[0] - KENAR, A4[1] - 80), metin, 10.5)
        alt = (f"{AD} {SURUM} ile {_dt.datetime.now().strftime('%d.%m.%Y %H:%M')} tarihinde bu bilgisayarda oluşturuldu. "
               "Görüntüler ekran kalitesindedir; tanı için orijinal DICOM dosyalarını kullanın.")
        self._kutu(sayfa, (KENAR, A4[1] - 70, A4[0] - KENAR, A4[1] - 30), alt, 8)

    def resim_sayfasi(self, dizi: np.ndarray, ust_yazi: str, alt_yazi: str = "") -> None:
        y, x = dizi.shape[:2]
        yatay = x > y * 1.15
        g, h = (A4[1], A4[0]) if yatay else A4
        sayfa = self.belge.new_page(width=g, height=h)
        # koyu zemin: radyoloji görüntüsü siyah üzerinde daha iyi okunur
        sayfa.draw_rect(sayfa.rect, color=None, fill=(0, 0, 0))
        self._yazi(sayfa, (KENAR / 2, 22), ust_yazi, 9, renk=(1, 1, 1))
        if alt_yazi:
            self._yazi(sayfa, (KENAR / 2, h - 12), alt_yazi, 8, renk=(0.8, 0.8, 0.8))
        alan = self._pymupdf.Rect(KENAR / 2, 30, g - KENAR / 2, h - 24)
        sayfa.insert_image(alan, stream=G.resim_baytlari(dizi, "PNG"), keep_proportion=True)

    def metin_sayfasi(self, baslik: str, metin: str) -> None:
        satirlar = metin.split("\n") or [""]
        r = (KENAR, 70, A4[0] - KENAR, A4[1] - KENAR)
        while satirlar:
            n = len(satirlar)
            while True:
                sayfa = self.belge.new_page(width=A4[0], height=A4[1])
                self._yazi(sayfa, (KENAR, 50), baslik, 14)
                tasma = self._kutu(sayfa, r, "\n".join(satirlar[:n]), 10)
                if tasma >= 0 or n == 1:
                    break
                self.belge.delete_page(-1)  # sığmadı: daha az satırla yeniden dene
                n = max(1, int(n * 0.75))
            satirlar = satirlar[n:]

    def pdf_ekle(self, veri: bytes) -> None:
        kaynak = self._pymupdf.open(stream=veri, filetype="pdf")
        self.belge.insert_pdf(kaynak)
        kaynak.close()

    def kaydet(self, yol: str) -> None:
        self.belge.save(yol, garbage=3, deflate=True)
        self.belge.close()


def _calisma_kapak_satirlari(calismalar) -> list[str]:
    satirlar = []
    hastalar = []
    for c in calismalar:
        if c.hasta and c.hasta not in hastalar:
            hastalar.append(c.hasta)
    for h in hastalar:
        if h.anahtar.startswith("~"):
            continue
        satirlar.append(f"Hasta: {h.ad or '-'}")
        if h.kimlik:
            satirlar.append(f"Hasta no: {h.kimlik}")
        if h.dogum:
            satirlar.append(f"Doğum tarihi: {K.tarih_bicimle(h.dogum)}")
        satirlar.append("")
    for c in calismalar:
        satirlar.append(f"Çalışma: {c.baslik()}")
        if c.kurum:
            satirlar.append(f"   Kurum: {c.kurum}")
        for s in c.sirali_seriler():
            satirlar.append(f"   {s.baslik()} — {len(s.ogeler)} dosya")
        satirlar.append("")
    return satirlar


def pdf_olustur(ogeler, yol: str, pencere: dict | None = None, ilerleme=None, iptal_mi=None,
                kapak: bool = True) -> tuple[int, list[str]]:
    """Öğelerden tek bir PDF yapar.

    pencere: {sop_uid ya da yol: (seviye, genislik, ters)} - verilirse o öğe bu ayarla çizilir.
    Dönüş: (sayfa sayısı, hatalar)
    """
    pencere = pencere or {}
    yazici = PdfYazici()
    calismalar = []
    for o in ogeler:
        if o.calisma and o.calisma not in calismalar:
            calismalar.append(o.calisma)
    if kapak:
        yazici.kapak(f"{AD} · Radyoloji görüntüleri", _calisma_kapak_satirlari(calismalar))
    hatalar: list[str] = []
    for n, oge in enumerate(ogeler):
        if iptal_mi and iptal_mi():
            break
        if ilerleme:
            ilerleme(n + 1, len(ogeler), oge.ad)
        c = oge.calisma
        ust = " · ".join(p for p in (
            (c.hasta.ad if c and c.hasta and not c.hasta.anahtar.startswith("~") else ""),
            (c.baslik() if c else ""),
            (oge.seri.baslik() if oge.seri else ""),
            oge.ad,
        ) if p)
        try:
            if oge.tur in (K.T_PDF, K.T_DICOM_PDF):
                yazici.pdf_ekle(G.pdf_verisi(oge))
            elif oge.tur == K.T_SR:
                yazici.metin_sayfasi(ust or "Rapor", G.sr_duz_metin(oge.yol))
            elif oge.tur in (K.T_DICOM, K.T_RESIM):
                kaynak = G.kaynak_ac(oge)
                ayar = pencere.get(oge.sop_uid or oge.yol)
                if ayar:
                    seviye, genislik, ters = ayar
                else:
                    (seviye, genislik), ters = kaynak.varsayilan_pencere(), False
                for k in range(kaynak.kare_sayisi):
                    dizi = kaynak.ciz(k, seviye, genislik, ters)
                    alt = f"Seviye {seviye:.0f} · Genişlik {genislik:.0f}" if not kaynak.renkli else ""
                    if kaynak.kare_sayisi > 1:
                        alt = (alt + " · " if alt else "") + f"Kare {k + 1}/{kaynak.kare_sayisi}"
                    yazici.resim_sayfasi(dizi, ust, alt)
        except Exception as e:  # noqa: BLE001
            hatalar.append(f"{oge.ad}: {e}")
    sayfa = yazici.belge.page_count
    if sayfa == 0:
        yazici.belge.close()
        raise ValueError("PDF'e eklenecek görüntü bulunamadı.")
    yazici.kaydet(yol)
    return sayfa, hatalar


def orijinalleri_kopyala(ogeler, klasor: str, ilerleme=None, iptal_mi=None) -> tuple[int, list[str]]:
    """Orijinal dosyaları Hasta / Çalışma / Seri klasör düzeniyle kopyalar (değiştirmeden)."""
    adet, hatalar = 0, []
    for n, oge in enumerate(ogeler):
        if iptal_mi and iptal_mi():
            break
        if ilerleme:
            ilerleme(n + 1, len(ogeler), oge.ad)
        c = oge.calisma
        h = c.hasta if c else None
        hasta_klasoru = K.guvenli_ad(h.baslik() if h else "Hasta", 60)
        calisma_klasoru = K.guvenli_ad(
            f"{c.tarih or 'tarihsiz'} {c.modalite_metni()} {c.aciklama}" if c else "Calisma", 80)
        seri_klasoru = K.guvenli_ad(oge.seri.baslik() if oge.seri else "Seri", 60)
        hedef_klasor = os.path.join(klasor, hasta_klasoru, calisma_klasoru, seri_klasoru)
        os.makedirs(hedef_klasor, exist_ok=True)
        ad = os.path.basename(oge.yol)
        if oge.tur in (K.T_DICOM, K.T_DICOM_PDF, K.T_SR, K.T_DICOM_DIGER) and not ad.lower().endswith(".dcm"):
            ad = (f"G{oge.sira:04d}" if oge.sira else os.path.splitext(ad)[0] or "goruntu") + ".dcm"
        try:
            shutil.copy2(oge.yol, _benzersiz(os.path.join(hedef_klasor, K.guvenli_ad(ad, 120))))
            adet += 1
        except Exception as e:  # noqa: BLE001
            hatalar.append(f"{oge.ad}: {e}")
    return adet, hatalar
