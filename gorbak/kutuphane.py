"""Dosya tarama ve hasta / çalışma / seri / görüntü düzeni.

Ağ kullanılmaz. Zip dosyaları geçici bir klasöre açılır ve program kapanınca silinir.
"""
from __future__ import annotations

import datetime as _dt
import os
import re
import shutil
import tempfile
import time
import uuid
import zipfile
from dataclasses import dataclass, field

import pydicom

# --- Sabitler -----------------------------------------------------------------

SOP_DIZIN = "1.2.840.10008.1.3.10"  # DICOMDIR
SOP_PDF = "1.2.840.10008.5.1.4.1.1.104.1"  # DICOM içine gömülü PDF
SOP_SR_ONEK = "1.2.840.10008.5.1.4.1.1.88."  # yapılandırılmış rapor

DICOM_UZANTI = {".dcm", ".dicom", ".dic", ".ima", ".img", ""}
RESIM_UZANTI = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
PDF_UZANTI = {".pdf"}
ZIP_UZANTI = {".zip"}

# Öğe türleri
T_DICOM = "dicom"  # piksel verisi olan DICOM
T_DICOM_PDF = "dicom_pdf"
T_SR = "sr"
T_DICOM_DIGER = "dicom_diger"  # görüntüsüz DICOM (plan, doz vb.)
T_RESIM = "resim"
T_PDF = "pdf"

GORUNTULU_TURLER = {T_DICOM, T_DICOM_PDF, T_RESIM, T_PDF}

MODALITE_ADI = {
    "CR": "Röntgen (CR)",
    "DX": "Röntgen (DX)",
    "DR": "Röntgen (DR)",
    "RG": "Röntgen (RG)",
    "US": "Ultrason (US)",
    "CT": "BT (CT)",
    "MR": "MR",
    "MG": "Mamografi (MG)",
    "XA": "Anjiyografi (XA)",
    "RF": "Floroskopi (RF)",
    "NM": "Nükleer tıp (NM)",
    "PT": "PET (PT)",
    "OT": "Diğer (OT)",
    "SC": "Ekran görüntüsü (SC)",
    "SR": "Rapor (SR)",
    "DOC": "Belge",
    "IO": "Diş röntgeni (IO)",
    "PX": "Panoramik diş (PX)",
    "ES": "Endoskopi (ES)",
    "XC": "Fotoğraf (XC)",
    "RTDOSE": "Radyoterapi dozu",
    "RTPLAN": "Radyoterapi planı",
    "RTSTRUCT": "Radyoterapi yapısı",
    "ECG": "EKG",
}


def modalite_adi(kod: str) -> str:
    kod = (kod or "").upper()
    if not kod:
        return "Bilinmiyor"
    return MODALITE_ADI.get(kod, kod)


def tarih_bicimle(d: str) -> str:
    """'20221215' -> '15.12.2022'."""
    d = (d or "").strip()
    if len(d) >= 8 and d[:8].isdigit():
        return f"{d[6:8]}.{d[4:6]}.{d[0:4]}"
    return d


def saat_bicimle(s: str) -> str:
    s = (s or "").strip()
    if len(s) >= 4 and s[:4].isdigit():
        return f"{s[0:2]}:{s[2:4]}"
    return ""


def kisi_adi(deger) -> str:
    """DICOM kişi adını 'Ad Soyad' biçimine çevirir."""
    if deger is None:
        return ""
    metin = str(deger).strip()
    if not metin:
        return ""
    if "^" in metin:
        parcalar = [p.strip() for p in metin.split("=")[0].split("^")]
        soyad = parcalar[0] if len(parcalar) > 0 else ""
        ad = parcalar[1] if len(parcalar) > 1 else ""
        orta = parcalar[2] if len(parcalar) > 2 else ""
        return " ".join(p for p in (ad, orta, soyad) if p)
    return metin


def guvenli_ad(metin: str, uzunluk: int = 80) -> str:
    """Dosya / klasör adı olarak güvenli metin."""
    metin = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(metin or "")).strip(" .")
    metin = re.sub(r"\s+", " ", metin)
    return (metin[:uzunluk].strip(" .")) or "adsiz"


# --- Geçici klasör ------------------------------------------------------------

_GECICI_KOK = os.path.join(tempfile.gettempdir(), "gor-bak")
_OTURUM_KLASORU: str | None = None


def oturum_klasoru() -> str:
    global _OTURUM_KLASORU
    if _OTURUM_KLASORU is None:
        os.makedirs(_GECICI_KOK, exist_ok=True)
        _OTURUM_KLASORU = os.path.join(_GECICI_KOK, f"oturum-{os.getpid()}-{uuid.uuid4().hex[:8]}")
        os.makedirs(_OTURUM_KLASORU, exist_ok=True)
    return _OTURUM_KLASORU


def gecicileri_temizle(eskiler_de: bool = True) -> None:
    """Bu oturumun açılmış zip klasörünü, istenirse bir günden eski oturumları siler."""
    global _OTURUM_KLASORU
    if _OTURUM_KLASORU and os.path.isdir(_OTURUM_KLASORU):
        shutil.rmtree(_OTURUM_KLASORU, ignore_errors=True)
    _OTURUM_KLASORU = None
    if eskiler_de and os.path.isdir(_GECICI_KOK):
        sinir = time.time() - 24 * 3600
        for ad in os.listdir(_GECICI_KOK):
            yol = os.path.join(_GECICI_KOK, ad)
            try:
                if os.path.isdir(yol) and os.path.getmtime(yol) < sinir:
                    shutil.rmtree(yol, ignore_errors=True)
            except OSError:
                pass


def zip_ac(yol: str) -> str:
    """Zip'i oturum klasörüne güvenli biçimde açar, açılan klasörü döndürür."""
    hedef = os.path.join(oturum_klasoru(), "zip-" + uuid.uuid4().hex[:10])
    os.makedirs(hedef, exist_ok=True)
    with zipfile.ZipFile(yol) as z:
        for bilgi in z.infolist():
            if bilgi.is_dir():
                continue
            if bilgi.flag_bits & 0x1:
                raise RuntimeError("Zip şifreli; önce şifresini çözüp açın.")
            ad = bilgi.filename.replace("\\", "/")
            parcalar = [p for p in ad.split("/") if p not in ("", ".", "..")]
            if not parcalar:
                continue
            parcalar = [guvenli_ad(p, 120) for p in parcalar]
            dosya = os.path.join(hedef, *parcalar)
            os.makedirs(os.path.dirname(dosya), exist_ok=True)
            with z.open(bilgi) as kaynak, open(dosya, "wb") as cikti:
                shutil.copyfileobj(kaynak, cikti)
    return hedef


# --- Veri modeli --------------------------------------------------------------


@dataclass
class Oge:
    yol: str
    tur: str
    ad: str
    sira: int = 0
    kare_sayisi: int = 1
    sop_uid: str = ""
    kesit_konumu: float | None = None
    seri: "Seri | None" = field(default=None, repr=False)

    @property
    def calisma(self) -> "Calisma | None":
        return self.seri.calisma if self.seri else None


@dataclass
class Seri:
    anahtar: str
    numara: int | None
    aciklama: str
    modalite: str
    ogeler: list[Oge] = field(default_factory=list)
    calisma: "Calisma | None" = field(default=None, repr=False)

    def baslik(self) -> str:
        parcalar = []
        if self.numara is not None:
            parcalar.append(f"Seri {self.numara}")
        if self.aciklama:
            parcalar.append(self.aciklama)
        if not parcalar:
            parcalar.append(modalite_adi(self.modalite))
        return " · ".join(parcalar)

    def sirali_ogeler(self) -> list[Oge]:
        def anahtar(o: Oge):
            return (o.sira if o.sira else 10**9, o.kesit_konumu if o.kesit_konumu is not None else 0.0, o.ad)

        return sorted(self.ogeler, key=anahtar)


@dataclass
class Calisma:
    anahtar: str
    tarih: str  # YYYYMMDD
    saat: str
    aciklama: str
    kurum: str
    seriler: dict[str, Seri] = field(default_factory=dict)
    hasta: "Hasta | None" = field(default=None, repr=False)

    def modaliteler(self) -> list[str]:
        kodlar = []
        for s in self.seriler.values():
            if s.modalite and s.modalite not in kodlar and s.modalite != "DOC":
                kodlar.append(s.modalite)
        if not kodlar and self.seriler:
            kodlar = ["DOC"]
        return kodlar

    def modalite_metni(self) -> str:
        return ", ".join(self.modaliteler()) or "?"

    def baslik(self) -> str:
        parcalar = [tarih_bicimle(self.tarih) or "Tarihsiz", self.modalite_metni()]
        if self.aciklama:
            parcalar.append(self.aciklama)
        return " · ".join(parcalar)

    def sirali_seriler(self) -> list[Seri]:
        return sorted(
            self.seriler.values(),
            key=lambda s: (s.modalite == "DOC", s.numara if s.numara is not None else 10**9, s.aciklama),
        )

    def tum_ogeler(self) -> list[Oge]:
        sonuc = []
        for s in self.sirali_seriler():
            sonuc.extend(s.sirali_ogeler())
        return sonuc


@dataclass
class Hasta:
    anahtar: str
    ad: str
    kimlik: str
    dogum: str
    cinsiyet: str
    calismalar: dict[str, Calisma] = field(default_factory=dict)

    def baslik(self) -> str:
        ad = self.ad or "Adı bilinmeyen hasta"
        return f"{ad} ({self.kimlik})" if self.kimlik else ad

    def sirali_calismalar(self) -> list[Calisma]:
        return sorted(self.calismalar.values(), key=lambda c: (c.tarih or "", c.saat or ""), reverse=True)


@dataclass
class TaramaSonucu:
    eklenen: int = 0
    tekrar: int = 0
    atlanan: int = 0
    hatalar: list[str] = field(default_factory=list)
    iptal: bool = False


# --- Tarama -------------------------------------------------------------------


def _dicom_mu(yol: str) -> bool:
    try:
        with open(yol, "rb") as f:
            bas = f.read(132)
        return len(bas) == 132 and bas[128:132] == b"DICM"
    except OSError:
        return False


def _ilk(deger, varsayilan=None):
    if deger is None:
        return varsayilan
    try:
        if isinstance(deger, (list, tuple)) or hasattr(deger, "__getitem__") and not isinstance(deger, (str, bytes)):
            return deger[0] if len(deger) else varsayilan
    except Exception:
        pass
    return deger


def _sayi(deger) -> int | None:
    try:
        if deger is None or str(deger).strip() == "":
            return None
        return int(float(str(deger)))
    except (TypeError, ValueError):
        return None


class Kutuphane:
    def __init__(self) -> None:
        self.hastalar: dict[str, Hasta] = {}
        self._sop_kumesi: set[str] = set()
        self._yol_kumesi: set[str] = set()

    # -- sorgu --
    def bos_mu(self) -> bool:
        return not self.hastalar

    def sirali_hastalar(self) -> list[Hasta]:
        return sorted(self.hastalar.values(), key=lambda h: (h.anahtar.startswith("~"), h.ad.lower()))

    def tum_ogeler(self) -> list[Oge]:
        return [o for h in self.sirali_hastalar() for c in h.sirali_calismalar() for o in c.tum_ogeler()]

    def temizle(self) -> None:
        self.hastalar.clear()
        self._sop_kumesi.clear()
        self._yol_kumesi.clear()

    # -- tarama --
    def dosyalari_topla(self, yollar, sonuc: TaramaSonucu, derinlik: int = 0) -> list[str]:
        dosyalar: list[str] = []
        for yol in yollar:
            yol = os.path.abspath(yol)
            if os.path.isdir(yol):
                for kok, _, adlar in os.walk(yol):
                    for ad in sorted(adlar):
                        dosyalar.extend(self._dosya_ya_da_zip(os.path.join(kok, ad), sonuc, derinlik))
            elif os.path.isfile(yol):
                if os.path.basename(yol).upper() == "DICOMDIR":
                    # CD / DVD: DICOMDIR'in bulunduğu klasörün tamamı taranır
                    dosyalar.extend(self.dosyalari_topla([os.path.dirname(yol)], sonuc, derinlik))
                else:
                    dosyalar.extend(self._dosya_ya_da_zip(yol, sonuc, derinlik))
            else:
                sonuc.hatalar.append(f"Bulunamadı: {yol}")
        # sırayı koruyarak tekrarları at
        gorulen = set()
        tekil = []
        for d in dosyalar:
            k = os.path.normcase(d)
            if k not in gorulen:
                gorulen.add(k)
                tekil.append(d)
        return tekil

    def _dosya_ya_da_zip(self, yol: str, sonuc: TaramaSonucu, derinlik: int) -> list[str]:
        uzanti = os.path.splitext(yol)[1].lower()
        if uzanti in ZIP_UZANTI:
            if derinlik >= 3:
                sonuc.atlanan += 1
                return []
            try:
                if not zipfile.is_zipfile(yol):
                    sonuc.hatalar.append(f"Bozuk zip: {os.path.basename(yol)}")
                    return []
                klasor = zip_ac(yol)
            except Exception as e:  # noqa: BLE001
                sonuc.hatalar.append(f"Zip açılamadı ({os.path.basename(yol)}): {e}")
                return []
            return self.dosyalari_topla([klasor], sonuc, derinlik + 1)
        return [yol]

    def ekle(self, yollar, ilerleme=None, iptal_mi=None) -> TaramaSonucu:
        sonuc = TaramaSonucu()
        dosyalar = self.dosyalari_topla(list(yollar), sonuc)
        dicom_disi: list[str] = []
        dicom_klasor_calisma: dict[str, set[str]] = {}
        kokler = [os.path.abspath(y) if os.path.isdir(y) else os.path.dirname(os.path.abspath(y)) for y in yollar]

        toplam = len(dosyalar)
        for i, yol in enumerate(dosyalar):
            if iptal_mi and iptal_mi():
                sonuc.iptal = True
                break
            if ilerleme and (i % 5 == 0 or i == toplam - 1):
                ilerleme(i + 1, toplam, os.path.basename(yol))
            anahtar = os.path.normcase(os.path.abspath(yol))
            if anahtar in self._yol_kumesi:
                sonuc.tekrar += 1
                continue
            uzanti = os.path.splitext(yol)[1].lower()
            ad_buyuk = os.path.basename(yol).upper()
            if ad_buyuk == "DICOMDIR":
                sonuc.atlanan += 1
                continue
            try:
                if uzanti in RESIM_UZANTI or uzanti in PDF_UZANTI:
                    if _dicom_mu(yol):
                        durum = self._dicom_ekle(yol, sonuc, dicom_klasor_calisma, kokler)
                    else:
                        dicom_disi.append(yol)
                        continue
                elif _dicom_mu(yol) or uzanti in DICOM_UZANTI or uzanti[1:].isdigit():
                    durum = self._dicom_ekle(yol, sonuc, dicom_klasor_calisma, kokler)
                else:
                    sonuc.atlanan += 1
                    continue
            except Exception as e:  # noqa: BLE001
                sonuc.hatalar.append(f"{os.path.basename(yol)}: {e}")
                continue
            if durum:
                self._yol_kumesi.add(anahtar)

        for yol in dicom_disi:
            self._belge_ekle(yol, sonuc, dicom_klasor_calisma)
            self._yol_kumesi.add(os.path.normcase(os.path.abspath(yol)))
        return sonuc

    def _dicom_ekle(self, yol, sonuc, klasor_calisma, kokler) -> bool:
        sihirli = _dicom_mu(yol)
        try:
            ds = pydicom.dcmread(yol, stop_before_pixels=True, force=True)
        except Exception as e:  # noqa: BLE001
            if sihirli:
                sonuc.hatalar.append(f"{os.path.basename(yol)}: okunamadı ({e})")
            else:
                sonuc.atlanan += 1
            return False

        sop_sinif = str(ds.get("SOPClassUID", "") or "")
        if not sihirli and not (sop_sinif or "StudyInstanceUID" in ds or "Rows" in ds):
            sonuc.atlanan += 1
            return False
        if sop_sinif == SOP_DIZIN or "DirectoryRecordSequence" in ds:
            sonuc.atlanan += 1
            return False

        sop_uid = str(ds.get("SOPInstanceUID", "") or "")
        if sop_uid and sop_uid in self._sop_kumesi:
            sonuc.tekrar += 1
            return False

        modalite = str(ds.get("Modality", "") or "").upper()
        kare = _sayi(ds.get("NumberOfFrames")) or 1
        sira = _sayi(ds.get("InstanceNumber")) or 0
        if sop_sinif == SOP_PDF:
            tur = T_DICOM_PDF
            baslik = str(ds.get("DocumentTitle", "") or "") or "Rapor (PDF)"
        elif sop_sinif.startswith(SOP_SR_ONEK):
            tur = T_SR
            baslik = "Rapor (yapılandırılmış)"
            modalite = modalite or "SR"
        elif "Rows" in ds and "Columns" in ds:
            tur = T_DICOM
            baslik = f"Görüntü {sira}" if sira else "Görüntü"
            if kare > 1:
                baslik += f" ({kare} kare)"
        else:
            tur = T_DICOM_DIGER
            baslik = f"{modalite_adi(modalite)} (görüntüsüz)"

        kesit = None
        try:
            if "SliceLocation" in ds:
                kesit = float(ds.SliceLocation)
            elif "ImagePositionPatient" in ds:
                kesit = float(ds.ImagePositionPatient[2])
        except Exception:  # noqa: BLE001
            kesit = None

        # hasta
        hasta_adi = kisi_adi(ds.get("PatientName"))
        hasta_kimlik = str(ds.get("PatientID", "") or "").strip()
        h_anahtar = f"{hasta_kimlik}|{hasta_adi.lower()}" if (hasta_adi or hasta_kimlik) else "~bilinmeyen"
        hasta = self.hastalar.get(h_anahtar)
        if hasta is None:
            hasta = Hasta(
                anahtar=h_anahtar,
                ad=hasta_adi,
                kimlik=hasta_kimlik,
                dogum=str(ds.get("PatientBirthDate", "") or ""),
                cinsiyet=str(ds.get("PatientSex", "") or ""),
            )
            self.hastalar[h_anahtar] = hasta

        # çalışma
        tarih = str(ds.get("StudyDate", "") or ds.get("SeriesDate", "") or ds.get("ContentDate", "") or "")
        c_uid = str(ds.get("StudyInstanceUID", "") or "")
        c_anahtar = c_uid or f"yok|{tarih}|{modalite}"
        calisma = hasta.calismalar.get(c_anahtar)
        if calisma is None:
            calisma = Calisma(
                anahtar=c_anahtar,
                tarih=tarih,
                saat=str(ds.get("StudyTime", "") or ""),
                aciklama=str(ds.get("StudyDescription", "") or "").strip(),
                kurum=str(ds.get("InstitutionName", "") or "").strip(),
                hasta=hasta,
            )
            hasta.calismalar[c_anahtar] = calisma

        # seri
        s_uid = str(ds.get("SeriesInstanceUID", "") or "")
        s_no = _sayi(ds.get("SeriesNumber"))
        s_anahtar = s_uid or f"{c_anahtar}|{modalite}|{s_no}"
        seri = calisma.seriler.get(s_anahtar)
        if seri is None:
            seri = Seri(
                anahtar=s_anahtar,
                numara=s_no,
                aciklama=str(ds.get("SeriesDescription", "") or "").strip(),
                modalite=modalite,
                calisma=calisma,
            )
            calisma.seriler[s_anahtar] = seri

        oge = Oge(yol=yol, tur=tur, ad=baslik, sira=sira, kare_sayisi=kare, sop_uid=sop_uid,
                  kesit_konumu=kesit, seri=seri)
        seri.ogeler.append(oge)
        if sop_uid:
            self._sop_kumesi.add(sop_uid)
        sonuc.eklenen += 1

        # aynı klasördeki belgeleri bu çalışmaya bağlayabilmek için klasör -> çalışma eşlemesi
        klasor = os.path.normcase(os.path.dirname(os.path.abspath(yol)))
        kok_kume = {os.path.normcase(k) for k in kokler}
        while True:
            klasor_calisma.setdefault(klasor, set()).add(f"{h_anahtar}\n{c_anahtar}")
            if klasor in kok_kume:
                break
            ust = os.path.dirname(klasor)
            if ust == klasor:
                break
            klasor = ust
        return True

    def _belge_ekle(self, yol, sonuc, klasor_calisma) -> None:
        uzanti = os.path.splitext(yol)[1].lower()
        tur = T_PDF if uzanti in PDF_UZANTI else T_RESIM
        klasor = os.path.normcase(os.path.dirname(os.path.abspath(yol)))
        eslesen = klasor_calisma.get(klasor, set())
        calisma = None
        if len(eslesen) == 1:
            h_anahtar, c_anahtar = next(iter(eslesen)).split("\n", 1)
            calisma = self.hastalar[h_anahtar].calismalar[c_anahtar]
        if calisma is None:
            hasta = self.hastalar.get("~belgeler")
            if hasta is None:
                hasta = Hasta(anahtar="~belgeler", ad="Diğer dosyalar (JPG, PNG, PDF)", kimlik="", dogum="", cinsiyet="")
                self.hastalar["~belgeler"] = hasta
            c_anahtar = "klasor|" + klasor
            calisma = hasta.calismalar.get(c_anahtar)
            if calisma is None:
                try:
                    mt = _dt.datetime.fromtimestamp(os.path.getmtime(yol)).strftime("%Y%m%d")
                except OSError:
                    mt = ""
                calisma = Calisma(anahtar=c_anahtar, tarih=mt, saat="",
                                  aciklama=os.path.basename(os.path.dirname(yol)) or "Klasör", kurum="", hasta=hasta)
                hasta.calismalar[c_anahtar] = calisma
        seri = calisma.seriler.get("belgeler")
        if seri is None:
            seri = Seri(anahtar="belgeler", numara=None, aciklama="Dosyalar ve raporlar", modalite="DOC", calisma=calisma)
            calisma.seriler["belgeler"] = seri
        seri.ogeler.append(Oge(yol=yol, tur=tur, ad=os.path.basename(yol), seri=seri))
        sonuc.eklenen += 1
