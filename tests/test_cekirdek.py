"""Çekirdek sınamaları: pydicom'un örnek dosyalarıyla tarama, görüntü ve dışa aktarma.

Çalıştırma:  python -m pytest tests  (ya da)  python tests/test_cekirdek.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pydicom  # noqa: E402
from pydicom.data import get_testdata_file  # noqa: E402

from gorbak import disari as D  # noqa: E402
from gorbak import goruntu as G  # noqa: E402
from gorbak import kutuphane as K  # noqa: E402

ORNEK = os.path.join(os.path.dirname(pydicom.__file__), "data", "test_files")


def _kopya(klasor, *adlar):
    os.makedirs(klasor, exist_ok=True)
    for ad in adlar:
        shutil.copy(os.path.join(ORNEK, ad), klasor)


def test_tarama_ve_cizim():
    with tempfile.TemporaryDirectory() as t:
        _kopya(os.path.join(t, "a"), "CT_small.dcm", "MR_small.dcm", "JPGExtended.dcm", "MR_small_RLE.dcm",
               "JPEG2000.dcm", "SC_rgb_rle_2frame.dcm", "examples_palette.dcm", "reportsi.dcm",
               "examples_ybr_color.dcm", "no_meta.dcm")
        # uzantısız DICOM (CD gibi)
        shutil.copy(os.path.join(ORNEK, "CT_small.dcm"), os.path.join(t, "a", "IM000001"))
        # zip içindeki DICOM
        with zipfile.ZipFile(os.path.join(t, "paket.zip"), "w") as z:
            z.write(os.path.join(ORNEK, "MR_small_jpeg_ls_lossless.dcm"), "ic/klasor/IMG1")
            z.write(os.path.join(ORNEK, "rtdose.dcm"), "../kacak/rtdose.dcm")  # zip-slip denemesi
        kut = K.Kutuphane()
        sonuc = kut.ekle([os.path.join(t, "a"), os.path.join(t, "paket.zip")])
        assert not sonuc.hatalar, sonuc.hatalar
        ogeler = kut.tum_ogeler()
        # MR_small kopyaları ve IM000001 aynı SOP UID'yi taşır: bir kez listelenir
        assert sonuc.eklenen >= 8, sonuc
        assert sonuc.tekrar >= 1
        turler = {o.tur for o in ogeler}
        assert K.T_DICOM in turler and K.T_SR in turler
        for o in ogeler:
            if o.tur != K.T_DICOM:
                continue
            kaynak = G.kaynak_ac(o)
            s, g = kaynak.varsayilan_pencere()
            for k in range(kaynak.kare_sayisi):
                dizi = kaynak.ciz(k, s, g)
                assert dizi.dtype.name == "uint8" and dizi.size > 0, o.yol
        assert "rapor" in G.sr_html(next(o.yol for o in ogeler if o.tur == K.T_SR)).lower()
        # zip-slip: dosya oturum klasörünün dışına çıkmamalı
        assert not os.path.exists(os.path.join(tempfile.gettempdir(), "kacak", "rtdose.dcm"))
    K.gecicileri_temizle(eskiler_de=False)


def test_ct_pencere_ve_disari_aktarma():
    with tempfile.TemporaryDirectory() as t:
        _kopya(os.path.join(t, "giris"), "CT_small.dcm", "SC_rgb_rle_2frame.dcm", "reportsi.dcm")
        kut = K.Kutuphane()
        kut.ekle([os.path.join(t, "giris")])
        ogeler = kut.tum_ogeler()
        ct = next(o for o in ogeler if o.seri.modalite == "CT")
        kaynak = G.kaynak_ac(ct)
        dusuk, yuksek = kaynak.deger_araligi()
        assert dusuk < 0 < yuksek  # Hounsfield'e çevrilmiş
        cikti = os.path.join(t, "cikti")
        os.makedirs(cikti)
        dizi = kaynak.ciz(0, 40, 400)
        D.resim_kaydet(dizi, os.path.join(cikti, "ct.png"))
        D.resim_kaydet(dizi, os.path.join(cikti, "ct.jpg"))
        sayfa, hata = D.pdf_olustur(ogeler, os.path.join(cikti, "calisma.pdf"))
        assert not hata, hata
        assert sayfa >= 1 + 1 + 2  # kapak + CT + 2 kare
        adet, hata = D.orijinalleri_kopyala(ogeler, os.path.join(cikti, "orijinal"))
        assert adet == len(ogeler) and not hata
        adet, hata = D.calisma_resimleri_kaydet(ogeler, os.path.join(cikti, "png"), "PNG")
        assert adet == 3 and not hata, (adet, hata)
        kopya = [os.path.join(k, d) for k, _, ds in os.walk(os.path.join(cikti, "orijinal")) for d in ds]
        assert all(pydicom.dcmread(p).SOPInstanceUID for p in kopya)
        for ad in ("ct.png", "ct.jpg", "calisma.pdf"):
            assert os.path.getsize(os.path.join(cikti, ad)) > 1000


def test_belge_calismaya_baglanir():
    from PIL import Image

    with tempfile.TemporaryDirectory() as t:
        klasor = os.path.join(t, "cd")
        _kopya(klasor, "CT_small.dcm")
        Image.new("L", (64, 64), 128).save(os.path.join(klasor, "rapor.png"))
        kut = K.Kutuphane()
        kut.ekle([klasor])
        ct = next(o for o in kut.tum_ogeler() if o.tur == K.T_DICOM)
        belge = next(o for o in kut.tum_ogeler() if o.tur == K.T_RESIM)
        assert belge.calisma is ct.calisma


if __name__ == "__main__":
    for ad, f in list(globals().items()):
        if ad.startswith("test_") and callable(f):
            f()
            print("geçti:", ad)

