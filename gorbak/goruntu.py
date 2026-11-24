"""Piksel verisini ekrana uygun 8 bitlik görüntüye çevirme (pencere / seviye)."""
from __future__ import annotations

import html
import io

import numpy as np
import pydicom
from pydicom.pixels import apply_color_lut, apply_modality_lut
from pydicom.uid import ExplicitVRBigEndian, ExplicitVRLittleEndian, ImplicitVRLittleEndian

from . import kutuphane as K

# Hazır pencere ayarları: (ad, seviye, genişlik). BT için Hounsfield birimi.
HAZIR_PENCERELER = [
    ("BT · Akciğer", -600, 1500),
    ("BT · Mediasten / yumuşak doku", 40, 400),
    ("BT · Karın", 50, 350),
    ("BT · Kemik", 400, 1800),
    ("BT · Beyin", 40, 80),
    ("BT · İnme (beyin, dar)", 35, 40),
]


def pencerele(degerler: np.ndarray, seviye: float, genislik: float) -> np.ndarray:
    genislik = max(float(genislik), 1e-6)
    alt = float(seviye) - genislik / 2.0
    cikti = (degerler.astype(np.float32, copy=False) - alt) * (255.0 / genislik)
    np.clip(cikti, 0, 255, out=cikti)
    return cikti.astype(np.uint8)


def _transfer_duzelt(ds) -> None:
    """Dosya başlığı eksik DICOM'larda aktarım sözdizimini tahmin eder."""
    meta = getattr(ds, "file_meta", None)
    if meta is None:
        meta = pydicom.dataset.FileMetaDataset()
        ds.file_meta = meta
    if "TransferSyntaxUID" not in meta:
        try:
            ortuk, kucuk = ds.original_encoding
        except Exception:  # noqa: BLE001
            ortuk, kucuk = True, True
        if ortuk:
            meta.TransferSyntaxUID = ImplicitVRLittleEndian
        elif kucuk:
            meta.TransferSyntaxUID = ExplicitVRLittleEndian
        else:
            meta.TransferSyntaxUID = ExplicitVRBigEndian


def _ilk_sayi(deger):
    if deger is None:
        return None
    try:
        if isinstance(deger, (str, bytes)):
            return float(deger)
        if hasattr(deger, "__len__"):
            return float(deger[0]) if len(deger) else None
        return float(deger)
    except (TypeError, ValueError):
        return None


class Kaynak:
    """Ortak arayüz: kare sayısı, renk, varsayılan pencere, kare çizimi."""

    kare_sayisi: int = 1
    renkli: bool = False
    ters_varsayilan: bool = False
    piksel_araligi: tuple[float, float] | None = None  # (satır, sütun) mm
    kare_hizi: float | None = None  # saniyede kare
    ds = None

    def kare(self, i: int) -> np.ndarray:  # pragma: no cover - arayüz
        raise NotImplementedError

    def varsayilan_pencere(self) -> tuple[float, float]:
        return 127.5, 255.0

    def deger_araligi(self) -> tuple[float, float]:
        return 0.0, 255.0

    def ciz(self, i: int, seviye: float, genislik: float, ters: bool = False) -> np.ndarray:
        v = self.kare(i)
        cikti = pencerele(v, seviye, genislik)
        if ters != self.ters_varsayilan:
            cikti = 255 - cikti
        return np.ascontiguousarray(cikti)


class DicomKaynak(Kaynak):
    def __init__(self, yol: str):
        ds = pydicom.dcmread(yol, force=True)
        _transfer_duzelt(ds)
        self.ds = ds
        if "PixelData" not in ds and "FloatPixelData" not in ds and "DoubleFloatPixelData" not in ds:
            raise ValueError("Bu DICOM dosyasında görüntü verisi yok.")
        try:
            dizi = ds.pixel_array
        except Exception as e:  # noqa: BLE001
            ts = getattr(ds.file_meta, "TransferSyntaxUID", None)
            ad = ts.name if ts is not None and hasattr(ts, "name") else str(ts)
            raise ValueError(f"Görüntü verisi çözülemedi (sıkıştırma: {ad}). Ayrıntı: {e}") from e

        n = K._sayi(ds.get("NumberOfFrames")) or 1
        ornek = K._sayi(ds.get("SamplesPerPixel")) or 1
        fotometrik = str(ds.get("PhotometricInterpretation", "MONOCHROME2") or "MONOCHROME2").upper()

        if fotometrik == "PALETTE COLOR":
            dizi = apply_color_lut(dizi, ds)
            ornek = 3
        self.renkli = ornek >= 3
        tek_kare_boyut = 3 if self.renkli else 2
        if dizi.ndim == tek_kare_boyut:
            dizi = dizi[np.newaxis, ...]
        if self.renkli and dizi.dtype != np.uint8:
            ust = float(dizi.max()) if dizi.size else 255.0
            if ust > 255:
                dizi = (dizi.astype(np.float32) * (255.0 / ust)).astype(np.uint8)
            else:
                dizi = dizi.astype(np.uint8)
        self._ham = dizi
        self.kare_sayisi = int(dizi.shape[0]) if n >= 1 else 1
        self.ters_varsayilan = fotometrik == "MONOCHROME1"

        # Modality LUT (rescale) - çok kareli gelişmiş nesnelerde ortak gruplardan
        self._egim, self._kesisim, self._lut_dizisi = 1.0, 0.0, False
        if not self.renkli:
            if "ModalityLUTSequence" in ds:
                self._lut_dizisi = True
            else:
                egim = _ilk_sayi(ds.get("RescaleSlope"))
                kesisim = _ilk_sayi(ds.get("RescaleIntercept"))
                if egim is None:
                    try:
                        pv = ds.SharedFunctionalGroupsSequence[0].PixelValueTransformationSequence[0]
                        egim = _ilk_sayi(pv.get("RescaleSlope"))
                        kesisim = _ilk_sayi(pv.get("RescaleIntercept"))
                    except Exception:  # noqa: BLE001
                        pass
                self._egim = egim if egim not in (None, 0) else 1.0
                self._kesisim = kesisim or 0.0

        # Piksel aralığı (ölçüm için)
        aralik = ds.get("PixelSpacing") or ds.get("ImagerPixelSpacing")
        if aralik is None:
            try:
                aralik = ds.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0].PixelSpacing
            except Exception:  # noqa: BLE001
                aralik = None
        if aralik is None and "SequenceOfUltrasoundRegions" in ds:
            try:
                b = ds.SequenceOfUltrasoundRegions[0]
                # birim 3 = cm
                if int(b.PhysicalUnitsXDirection) == 3 and int(b.PhysicalUnitsYDirection) == 3:
                    aralik = [abs(float(b.PhysicalDeltaY)) * 10, abs(float(b.PhysicalDeltaX)) * 10]
            except Exception:  # noqa: BLE001
                aralik = None
        try:
            if aralik is not None and len(aralik) >= 2 and float(aralik[0]) > 0 and float(aralik[1]) > 0:
                self.piksel_araligi = (float(aralik[0]), float(aralik[1]))
        except Exception:  # noqa: BLE001
            self.piksel_araligi = None

        # Kare hızı
        hiz = _ilk_sayi(ds.get("CineRate")) or _ilk_sayi(ds.get("RecommendedDisplayFrameRate"))
        if not hiz:
            ft = _ilk_sayi(ds.get("FrameTime"))
            if ft and ft > 0:
                hiz = 1000.0 / ft
        self.kare_hizi = hiz if hiz and 0 < hiz <= 120 else None

        # Varsayılan pencere
        seviye = _ilk_sayi(ds.get("WindowCenter"))
        genislik = _ilk_sayi(ds.get("WindowWidth"))
        if seviye is None or genislik is None:
            try:
                voi = ds.SharedFunctionalGroupsSequence[0].FrameVOILUTSequence[0]
                seviye = _ilk_sayi(voi.get("WindowCenter"))
                genislik = _ilk_sayi(voi.get("WindowWidth"))
            except Exception:  # noqa: BLE001
                pass
        ilk = self.kare(0)
        alt, ust = float(np.min(ilk)), float(np.max(ilk))
        self._aralik = (alt, ust)
        if self.renkli:
            self._pencere = (127.5, 255.0)
        elif seviye is not None and genislik is not None and genislik > 1:
            self._pencere = (seviye, genislik)
        else:
            self._pencere = self.otomatik_pencere(0)

    def otomatik_pencere(self, i: int) -> tuple[float, float]:
        v = self.kare(i)
        ornek = v[:: max(1, v.shape[0] // 512), :: max(1, v.shape[1] // 512)]
        if self.renkli:
            return 127.5, 255.0
        alt, ust = np.percentile(ornek, [0.5, 99.5])
        if ust - alt < 1:
            alt, ust = float(np.min(v)), float(np.max(v))
        genislik = max(float(ust - alt), 1.0)
        return float(alt + genislik / 2.0), genislik

    def kare(self, i: int) -> np.ndarray:
        i = max(0, min(i, self.kare_sayisi - 1))
        ham = self._ham[i]
        if self.renkli:
            return ham
        if self._lut_dizisi:
            return apply_modality_lut(ham, self.ds).astype(np.float32)
        if self._egim == 1.0 and self._kesisim == 0.0:
            return ham
        return ham.astype(np.float32) * self._egim + self._kesisim

    def varsayilan_pencere(self):
        return self._pencere

    def deger_araligi(self):
        return self._aralik


class ResimKaynak(Kaynak):
    """JPG / PNG / BMP / TIFF."""

    def __init__(self, yol: str):
        from PIL import Image, ImageOps, ImageSequence

        kareler = []
        with Image.open(yol) as resim:
            for sayfa in ImageSequence.Iterator(resim):
                sayfa = ImageOps.exif_transpose(sayfa)
                if sayfa.mode in ("1", "L", "LA", "P") and not (sayfa.mode == "P" and "transparency" in sayfa.info):
                    if sayfa.mode == "P":
                        sayfa = sayfa.convert("RGB")
                    else:
                        sayfa = sayfa.convert("L")
                elif sayfa.mode in ("I", "I;16", "I;16B", "F"):
                    sayfa = sayfa.convert("F")
                else:
                    sayfa = sayfa.convert("RGB")
                kareler.append(np.array(sayfa))
        ilk = kareler[0]
        self.renkli = ilk.ndim == 3
        if not self.renkli and all(k.shape == ilk.shape for k in kareler):
            self._kareler = kareler
        else:
            self._kareler = [k if k.ndim == 3 else np.stack([k] * 3, axis=-1) for k in kareler]
            self.renkli = True
        self.kare_sayisi = len(self._kareler)
        alt, ust = float(np.min(ilk)), float(np.max(ilk))
        if ilk.dtype == np.uint8 or self.renkli:
            self._aralik = (0.0, 255.0)
            self._pencere = (127.5, 255.0)
        else:
            self._aralik = (alt, ust)
            self._pencere = ((alt + ust) / 2.0, max(ust - alt, 1.0))

    def kare(self, i: int) -> np.ndarray:
        return self._kareler[max(0, min(i, self.kare_sayisi - 1))]

    def varsayilan_pencere(self):
        return self._pencere

    def deger_araligi(self):
        return self._aralik


class PdfKaynak(Kaynak):
    """PDF sayfalarını görüntü olarak gösterir (her sayfa bir kare)."""

    renkli = True

    def __init__(self, yol: str | None = None, veri: bytes | None = None, dpi: int = 150):
        import pymupdf

        self._belge = pymupdf.open(stream=veri, filetype="pdf") if veri is not None else pymupdf.open(yol)
        self.kare_sayisi = max(1, self._belge.page_count)
        self._dpi = dpi
        self._onbellek: dict[int, np.ndarray] = {}

    def kare(self, i: int) -> np.ndarray:
        i = max(0, min(i, self.kare_sayisi - 1))
        if i not in self._onbellek:
            sayfa = self._belge.load_page(i)
            pix = sayfa.get_pixmap(dpi=self._dpi, alpha=False)
            dizi = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            if pix.n == 1:
                dizi = np.stack([dizi[..., 0]] * 3, axis=-1)
            self._onbellek[i] = np.ascontiguousarray(dizi[..., :3])
            if len(self._onbellek) > 12:
                self._onbellek.pop(next(iter(self._onbellek)))
        return self._onbellek[i]


def kaynak_ac(oge: K.Oge) -> Kaynak:
    if oge.tur == K.T_DICOM:
        return DicomKaynak(oge.yol)
    if oge.tur == K.T_RESIM:
        return ResimKaynak(oge.yol)
    if oge.tur == K.T_PDF:
        return PdfKaynak(yol=oge.yol)
    if oge.tur == K.T_DICOM_PDF:
        ds = pydicom.dcmread(oge.yol, force=True)
        veri = bytes(ds.EncapsulatedDocument)
        # bazı cihazlar sona tek dolgu baytı ekler
        k = PdfKaynak(veri=veri.rstrip(b"\x00") if veri.endswith(b"\x00") else veri)
        k.ds = ds
        return k
    raise ValueError("Bu dosya türünde görüntü yok.")


def pdf_verisi(oge: K.Oge) -> bytes:
    """Bir PDF ya da DICOM-PDF öğesinin ham PDF baytlarını döndürür."""
    if oge.tur == K.T_PDF:
        with open(oge.yol, "rb") as f:
            return f.read()
    ds = pydicom.dcmread(oge.yol, force=True)
    veri = bytes(ds.EncapsulatedDocument)
    return veri.rstrip(b"\x00") if veri.endswith(b"\x00") else veri


# --- Yapılandırılmış rapor (SR) -----------------------------------------------


def _kod_anlami(seq) -> str:
    try:
        return str(seq[0].CodeMeaning)
    except Exception:  # noqa: BLE001
        return ""


def _sr_dugum(oge, derinlik: int, satirlar: list[str]) -> None:
    ad = _kod_anlami(oge.get("ConceptNameCodeSequence"))
    tur = str(oge.get("ValueType", "") or "")
    deger = ""
    if tur == "TEXT":
        deger = str(oge.get("TextValue", ""))
    elif tur == "CODE":
        deger = _kod_anlami(oge.get("ConceptCodeSequence"))
    elif tur == "NUM":
        try:
            olcum = oge.MeasuredValueSequence[0]
            birim = _kod_anlami(olcum.get("MeasurementUnitsCodeSequence"))
            deger = f"{olcum.NumericValue} {birim}".strip()
        except Exception:  # noqa: BLE001
            deger = ""
    elif tur == "PNAME":
        deger = K.kisi_adi(oge.get("PersonName"))
    elif tur == "DATE":
        deger = K.tarih_bicimle(str(oge.get("Date", "")))
    elif tur == "TIME":
        deger = K.saat_bicimle(str(oge.get("Time", "")))
    elif tur == "DATETIME":
        dt = str(oge.get("DateTime", ""))
        deger = f"{K.tarih_bicimle(dt[:8])} {K.saat_bicimle(dt[8:])}".strip()
    elif tur == "UIDREF":
        deger = str(oge.get("UID", ""))
    girinti = derinlik * 18
    if tur == "CONTAINER":
        if ad:
            boyut = 15 if derinlik == 0 else 13
            satirlar.append(f'<p style="margin:10px 0 4px {girinti}px;font-weight:600;font-size:{boyut}pt">{html.escape(ad)}</p>')
    elif ad or deger:
        metin = html.escape(deger).replace("\n", "<br>")
        if ad:
            satirlar.append(f'<p style="margin:2px 0 2px {girinti}px"><b>{html.escape(ad)}:</b> {metin}</p>')
        else:
            satirlar.append(f'<p style="margin:2px 0 2px {girinti}px">{metin}</p>')
    for alt in oge.get("ContentSequence", []) or []:
        _sr_dugum(alt, derinlik + 1, satirlar)


def sr_html(yol: str) -> str:
    ds = pydicom.dcmread(yol, force=True)
    satirlar = [
        f"<h2>Yapılandırılmış rapor</h2>",
        f"<p><b>Hasta:</b> {html.escape(K.kisi_adi(ds.get('PatientName')))} &nbsp; "
        f"<b>Tarih:</b> {html.escape(K.tarih_bicimle(str(ds.get('ContentDate', '') or ds.get('StudyDate', '') or '')))}</p>",
    ]
    durum = []
    if ds.get("CompletionFlag"):
        durum.append("Tamamlandı" if str(ds.CompletionFlag) == "COMPLETE" else "Tamamlanmadı")
    if ds.get("VerificationFlag"):
        durum.append("Onaylı" if str(ds.VerificationFlag) == "VERIFIED" else "Onaysız")
    if durum:
        satirlar.append(f"<p><i>{' · '.join(durum)}</i></p>")
    satirlar.append("<hr>")
    _sr_dugum(ds, 0, satirlar)
    return "\n".join(satirlar)


def sr_duz_metin(yol: str) -> str:
    """SR içeriğini düz metin olarak (PDF'e eklemek için)."""
    import re as _re

    h = sr_html(yol)
    h = _re.sub(r"<br\s*/?>|</p>|</h2>|<hr>", "\n", h)
    h = _re.sub(r"<[^>]+>", "", h)
    return html.unescape(_re.sub(r"\n{3,}", "\n\n", h)).strip()


def resim_baytlari(dizi: np.ndarray, bicim: str = "PNG", kalite: int = 95) -> bytes:
    from PIL import Image

    resim = Image.fromarray(dizi)
    tampon = io.BytesIO()
    if bicim.upper() in ("JPG", "JPEG"):
        resim.save(tampon, format="JPEG", quality=kalite, subsampling=0)
    else:
        resim.save(tampon, format="PNG", optimize=False)
    return tampon.getvalue()


def netlestir(dizi: np.ndarray, guc: int = 120) -> np.ndarray:
    """Hafif keskinleştirme (unsharp mask). Yalnız görüntülemeyi etkiler."""
    from PIL import Image, ImageFilter

    resim = Image.fromarray(dizi)
    return np.asarray(resim.filter(ImageFilter.UnsharpMask(radius=1.6, percent=guc, threshold=2)))
