"""gör-bak ana penceresi (PySide6)."""
from __future__ import annotations

import html
import math
import os
import sys
import traceback
from collections import OrderedDict

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSettings, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (QAction, QBrush, QColor, QFont, QIcon, QImage, QKeySequence, QPainter, QPen, QPixmap)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMainWindow, QMenu, QMessageBox, QProgressDialog, QSlider, QSpinBox,
                               QSplitter, QStackedWidget, QStyle, QTabWidget, QTextBrowser, QToolBar, QToolButton,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from . import AD, SURUM
from . import disari as D
from . import goruntu as G
from . import kutuphane as K
from .etiketler import etiket_adi

ROL = Qt.ItemDataRole.UserRole


# --- Yardım metinleri ----------------------------------------------------------

HOSGELDIN_HTML = f"""
<div style="font-family:Segoe UI; color:#d8dde3; margin:28px">
<h1 style="color:#ffffff; font-weight:600">{AD}</h1>
<p style="font-size:12pt">Röntgen, MR, BT, ultrason ve diğer radyoloji görüntülerinizi bu bilgisayarda açıp
ayrıntılı inceleyin, sonra PNG, JPG ya da PDF olarak kaydedin. İnternete bağlanmaz; dosyalarınız hiçbir yere gönderilmez.</p>
<p style="font-size:13pt">
<a href="ac:dosya" style="color:#6fb6ff">Dosya aç</a> (DICOM, zip, JPG, PNG, PDF) &nbsp;·&nbsp;
<a href="ac:klasor" style="color:#6fb6ff">Klasör ya da CD/DVD aç</a></p>
<p>Dosyaları bu pencereye sürükleyip bırakabilirsiniz.</p>
<h3 style="color:#ffffff">Kullanım</h3>
<ul>
<li><b>Fare tekerleği</b>: yakınlaştır / uzaklaştır &nbsp; · &nbsp; <b>Sol tuşla sürükle</b>: kaydır</li>
<li><b>Sağ tuşla sürükle</b>: parlaklık / kontrast (pencere-seviye). Sağa-sola genişlik, yukarı-aşağı seviye.</li>
<li><b>Ok tuşları, Page Up/Down</b> ya da <b>Shift + tekerlek</b>: MR/BT kesitleri ve ultrason kareleri arasında gezin</li>
<li><b>Boşluk</b>: kareleri oynat / durdur &nbsp; · &nbsp; <b>Çift tık</b> ya da <b>F</b>: ekrana sığdır &nbsp; · &nbsp; <b>1</b>: gerçek boyut</li>
<li><b>M</b>: ölçüm cetveli (piksel aralığı biliniyorsa mm) &nbsp; · &nbsp; <b>I</b>: tersine çevir &nbsp; · &nbsp; <b>R</b>: ayarları sıfırla</li>
</ul>
<h3 style="color:#ffffff">e-Nabız'da görüntü açılmıyorsa</h3>
<p>Yardım menüsündeki <a href="yardim:enabiz" style="color:#6fb6ff">e-Nabız görüntüsü açılmıyorsa</a> başlığına bakın.</p>
</div>
"""

ENABIZ_HTML = """
<h2>e-Nabız'da görüntü açılmıyorsa</h2>
<p><b>"Hastaneye erişim sorunu nedeniyle radyolojik görüntünüze ulaşılamamaktadır"</b> mesajı, görüntünün
hastanenin kendi görüntü arşivinde (PACS) durduğunu ve e-Nabız'ın o an bu arşive ulaşamadığını gösterir.
Görüntü sizin bilgisayarınızda ya da e-Nabız'da değildir. Bu yüzden gör-bak dahil hiçbir program onu oradan çekemez.</p>
<h3>Yapabilecekleriniz</h3>
<ol>
<li><b>Açılan çalışmaları hemen indirin.</b> Teleradyoloji ekranında görüntü yükleniyorsa disk (kaydet) düğmesiyle
indirin. İnen dosyayı (zip, DICOM ya da resim) gör-bak'ta <i>Dosya aç</i> ile açın.</li>
<li><b>Hastaneden isteyin.</b> Radyoloji birimine ya da hasta hakları birimine başvurup çalışmayı
<b>CD/DVD ya da DICOM dosyası</b> olarak, raporu da çıktı ya da PDF olarak isteyin. CD'yi gör-bak'ta
<i>Klasör ya da CD/DVD aç</i> ile açın.</li>
<li><b>Daha sonra yeniden deneyin.</b> Erişim sorunu bazen hastane tarafındaki geçici bir kesintiden kaynaklanır.</li>
</ol>
<h3>"Rapor bulunmamaktadır" yazıyorsa</h3>
<p>Rapor e-Nabız'a gönderilmemiştir. gör-bak rapor üretmez. Raporu hastaneden isteyin, gelen PDF'i ya da fotoğrafı
gör-bak'ta açın. Görüntülerle aynı klasördeyse aynı çalışmanın altında listelenir.</p>
"""


# --- Arka plan tarama ---------------------------------------------------------


class TaramaIsi(QThread):
    ilerleme = Signal(int, int, str)
    bitti = Signal(object)

    def __init__(self, kutuphane: K.Kutuphane, yollar):
        super().__init__()
        self.kutuphane = kutuphane
        self.yollar = list(yollar)
        self._iptal = False

    def iptal_et(self):
        self._iptal = True

    def run(self):
        try:
            sonuc = self.kutuphane.ekle(self.yollar, lambda a, b, c: self.ilerleme.emit(a, b, c), lambda: self._iptal)
        except Exception as e:  # noqa: BLE001
            sonuc = K.TaramaSonucu(hatalar=[f"Beklenmeyen hata: {e}"])
        self.bitti.emit(sonuc)


# --- Görüntü alanı ------------------------------------------------------------


class GoruntuAlani(QGraphicsView):
    pencere_surukle = Signal(float, float)  # dx, dy (piksel)
    kare_kaydir = Signal(int)
    sigdir_istendi = Signal()
    olcum_degisti = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.resim = QGraphicsPixmapItem()
        self.resim.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scene().addItem(self.resim)
        self.setBackgroundBrush(QBrush(QColor(0, 0, 0)))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.koseler = ["", "", "", ""]  # sol üst, sağ üst, sol alt, sağ alt
        self._sag_baslangic = None
        self.olcum_modu = False
        self.olcum: tuple[QPointF, QPointF] | None = None
        self._olcum_suruyor = False
        self.piksel_araligi = None
        self.keskin_piksel = False
        self.boyut = (0, 0)

    def goster(self, dizi: np.ndarray, yeni: bool):
        dizi = np.ascontiguousarray(dizi)
        y, x = dizi.shape[:2]
        if dizi.ndim == 2:
            img = QImage(dizi.data, x, y, dizi.strides[0], QImage.Format.Format_Grayscale8)
        else:
            img = QImage(dizi.data, x, y, dizi.strides[0], QImage.Format.Format_RGB888)
        self.resim.setPixmap(QPixmap.fromImage(img.copy()))
        boyut_degisti = (x, y) != self.boyut
        self.boyut = (x, y)
        self.scene().setSceneRect(QRectF(0, 0, x, y))
        if yeni or boyut_degisti:
            self.olcum = None
            self.sigdir()
        self.viewport().update()

    def temizle(self):
        self.resim.setPixmap(QPixmap())
        self.boyut = (0, 0)
        self.olcum = None
        self.koseler = ["", "", "", ""]

    def sigdir(self):
        if self.boyut[0] == 0:
            return
        self.resetTransform()
        self.fitInView(self.resim, Qt.AspectRatioMode.KeepAspectRatio)
        self._yumusatma_guncelle()

    def gercek_boyut(self):
        self.resetTransform()
        self._yumusatma_guncelle()

    def yakinlik(self) -> float:
        return self.transform().m11()

    def _yumusatma_guncelle(self):
        keskin = self.keskin_piksel and self.yakinlik() > 1.5
        mod = Qt.TransformationMode.FastTransformation if keskin else Qt.TransformationMode.SmoothTransformation
        self.resim.setTransformationMode(mod)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, not keskin)
        self.viewport().update()

    def yakinlastir(self, carpan: float):
        yeni = self.yakinlik() * carpan
        if 0.02 < yeni < 64:
            self.scale(carpan, carpan)
            self._yumusatma_guncelle()

    # olaylar
    def wheelEvent(self, e):
        adim = e.angleDelta().y() / 120.0
        if adim == 0:
            return
        if e.modifiers() & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier):
            self.kare_kaydir.emit(-1 if adim > 0 else 1)
            return
        self.yakinlastir(1.18 ** adim)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            self._sag_baslangic = e.position()
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            e.accept()
            return
        if e.button() == Qt.MouseButton.LeftButton and self.olcum_modu and self.boyut[0]:
            p = self.mapToScene(e.position().toPoint())
            self.olcum = (p, p)
            self._olcum_suruyor = True
            self.viewport().update()
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._sag_baslangic is not None:
            fark = e.position() - self._sag_baslangic
            self._sag_baslangic = e.position()
            self.pencere_surukle.emit(fark.x(), fark.y())
            e.accept()
            return
        if self._olcum_suruyor and self.olcum:
            self.olcum = (self.olcum[0], self.mapToScene(e.position().toPoint()))
            self.viewport().update()
            self.olcum_degisti.emit()
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton and self._sag_baslangic is not None:
            self._sag_baslangic = None
            self.unsetCursor()
            e.accept()
            return
        if e.button() == Qt.MouseButton.LeftButton and self._olcum_suruyor:
            self._olcum_suruyor = False
            self.olcum_degisti.emit()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.sigdir_istendi.emit()
            return
        super().mouseDoubleClickEvent(e)

    def contextMenuEvent(self, e):
        e.accept()  # sağ tuş pencere-seviye için

    def olcum_metni(self) -> str:
        if not self.olcum:
            return ""
        a, b = self.olcum
        dx, dy = b.x() - a.x(), b.y() - a.y()
        if self.piksel_araligi:
            sat, sut = self.piksel_araligi
            mm = math.hypot(dx * sut, dy * sat)
            return f"{mm:.1f} mm" if mm < 100 else f"{mm / 10:.2f} cm"
        return f"{math.hypot(dx, dy):.0f} piksel"

    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        if self.olcum:
            a, b = self.olcum
            painter.save()
            kalem = QPen(QColor(255, 210, 0), 0)
            kalem.setCosmetic(True)
            kalem.setWidthF(1.6)
            painter.setPen(kalem)
            painter.drawLine(a, b)
            painter.restore()
        painter.save()
        painter.resetTransform()
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        yazi = QFont("Segoe UI", 9)
        painter.setFont(yazi)
        alan = self.viewport().rect().adjusted(10, 8, -10, -8)
        hizalar = [
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
        ]
        for metin, hiza in zip(self.koseler, hizalar):
            if not metin:
                continue
            painter.setPen(QColor(0, 0, 0, 200))
            painter.drawText(alan.translated(1, 1), hiza, metin)
            painter.setPen(QColor(235, 235, 235))
            painter.drawText(alan, hiza, metin)
        if self.olcum:
            a, b = self.olcum
            p = self.mapFromScene(b)
            painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            m = self.olcum_metni()
            painter.setPen(QColor(0, 0, 0, 220))
            painter.drawText(p.x() + 9, p.y() - 7, m)
            painter.setPen(QColor(255, 210, 0))
            painter.drawText(p.x() + 8, p.y() - 8, m)
        painter.restore()


# --- Etiket paneli ------------------------------------------------------------


class EtiketPaneli(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        dikey = QVBoxLayout(self)
        dikey.setContentsMargins(4, 4, 4, 4)
        self.ara = QLineEdit()
        self.ara.setPlaceholderText("Etiketlerde ara (ad, numara ya da değer)…")
        self.ara.setClearButtonEnabled(True)
        self.ara.textChanged.connect(self._suz)
        self.agac = QTreeWidget()
        self.agac.setHeaderLabels(["Etiket", "Ad", "VR", "Değer"])
        self.agac.setUniformRowHeights(True)
        self.agac.setAlternatingRowColors(True)
        self.agac.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.agac.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        dikey.addWidget(self.ara)
        dikey.addWidget(self.agac)
        self._ds = None

    def doldur(self, ds):
        self.agac.clear()
        self._ds = ds
        if ds is None:
            QTreeWidgetItem(self.agac, ["", "Bu dosyada DICOM etiketi yok.", "", ""])
            return
        meta = getattr(ds, "file_meta", None)
        if meta is not None and len(meta):
            ust = QTreeWidgetItem(self.agac, ["(0002,xxxx)", "Dosya başlığı", "", ""])
            self._ekle(meta, ust)
        self._ekle(ds, self.agac.invisibleRootItem())
        for i, g in enumerate((110, 240, 40)):
            self.agac.setColumnWidth(i, g)
        self._suz(self.ara.text())

    def _ekle(self, ds, ust):
        for el in ds:
            etiket = f"({el.tag.group:04X},{el.tag.element:04X})"
            ad = etiket_adi(el)
            if el.VR == "SQ":
                dugum = QTreeWidgetItem(ust, [etiket, ad, "SQ", f"{len(el.value)} öğe"])
                for i, alt in enumerate(el.value):
                    alt_dugum = QTreeWidgetItem(dugum, ["", f"Öğe {i + 1}", "", ""])
                    self._ekle(alt, alt_dugum)
                continue
            if el.tag in (0x7FE00010, 0x7FE00008, 0x7FE00009) or el.VR in ("OB", "OW", "OF", "OD", "OL", "UN", "OV"):
                try:
                    uzunluk = len(el.value) if el.value is not None else 0
                except Exception:  # noqa: BLE001
                    uzunluk = 0
                deger = f"<ikili veri, {uzunluk:,} bayt>".replace(",", ".")
            else:
                try:
                    deger = str(el.value)
                except Exception:  # noqa: BLE001
                    deger = repr(el.value)
                if len(deger) > 300:
                    deger = deger[:300] + "…"
            dugum = QTreeWidgetItem(ust, [etiket, ad, str(el.VR), deger])
            dugum.setToolTip(3, deger)

    def _suz(self, metin):
        metin = (metin or "").strip().lower()

        def uygun(d: QTreeWidgetItem) -> bool:
            gorunur_alt = False
            for i in range(d.childCount()):
                if uygun(d.child(i)):
                    gorunur_alt = True
            kendi = not metin or any(metin in d.text(s).lower() for s in range(4))
            d.setHidden(not (kendi or gorunur_alt))
            if metin and gorunur_alt:
                d.setExpanded(True)
            return kendi or gorunur_alt

        kok = self.agac.invisibleRootItem()
        for i in range(kok.childCount()):
            uygun(kok.child(i))


# --- Ana pencere --------------------------------------------------------------


class AnaPencere(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(AD)
        self.resize(1400, 860)
        self.setAcceptDrops(True)
        self.ayarlar = QSettings("gor-bak", "gor-bak")
        self.kutuphane = K.Kutuphane()
        self._onbellek: OrderedDict[str, G.Kaynak] = OrderedDict()
        self._is: TaramaIsi | None = None
        self._ilerleme: QProgressDialog | None = None

        # görüntüleme durumu
        self.yigin: list[tuple[K.Oge, int]] = []
        self.konum = 0
        self.seviye, self.genislik, self.ters = 127.5, 255.0, False
        self.netlestir = False
        self.kaynak: G.Kaynak | None = None
        self.oge: K.Oge | None = None
        self._son_dizi: np.ndarray | None = None
        self._pencere_kayitlari: dict[str, tuple[float, float, bool]] = {}

        self.oynatici = QTimer(self)
        self.oynatici.timeout.connect(lambda: self.kareye_git(self.konum + 1, dongu=True))

        self._arayuz_kur()
        self._eylemler_kur()
        self._durum_guncelle()

    # ---------------- kurulum ----------------
    def _arayuz_kur(self):
        self.agac = QTreeWidget()
        self.agac.setHeaderLabels(["Hasta / çalışma / seri", "Adet"])
        self.agac.setColumnWidth(0, 300)
        self.agac.header().setStretchLastSection(False)
        self.agac.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.agac.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.agac.currentItemChanged.connect(self._agac_secildi)
        self.agac.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.agac.customContextMenuRequested.connect(self._agac_menusu)
        self.agac.setMinimumWidth(240)

        # orta alan
        self.alan = GoruntuAlani()
        self.alan.pencere_surukle.connect(self._pencere_surukle)
        self.alan.kare_kaydir.connect(lambda d: self.kareye_git(self.konum + d))
        self.alan.sigdir_istendi.connect(self.alan.sigdir)
        self.alan.olcum_degisti.connect(self._durum_guncelle)

        self.btn_onceki = QToolButton(text="◀")
        self.btn_oynat = QToolButton(text="▶  Oynat")
        self.btn_sonraki = QToolButton(text="▶")
        self.btn_onceki.setToolTip("Önceki kare / kesit (←)")
        self.btn_sonraki.setToolTip("Sonraki kare / kesit (→)")
        self.btn_oynat.setToolTip("Oynat / durdur (Boşluk)")
        self.btn_onceki.clicked.connect(lambda: self.kareye_git(self.konum - 1))
        self.btn_sonraki.clicked.connect(lambda: self.kareye_git(self.konum + 1))
        self.btn_oynat.clicked.connect(self.oynat_durdur)
        self.kaydirici = QSlider(Qt.Orientation.Horizontal)
        self.kaydirici.valueChanged.connect(lambda v: self.kareye_git(v) if v != self.konum else None)
        self.kare_etiketi = QLabel("")
        self.kare_etiketi.setMinimumWidth(130)
        self.hiz = QSpinBox()
        self.hiz.setRange(1, 60)
        self.hiz.setValue(10)
        self.hiz.setSuffix(" kare/sn")
        self.hiz.valueChanged.connect(self._hiz_degisti)
        cubuk = QWidget()
        yatay = QHBoxLayout(cubuk)
        yatay.setContentsMargins(6, 2, 6, 2)
        for w in (self.btn_onceki, self.btn_oynat, self.btn_sonraki):
            yatay.addWidget(w)
        yatay.addWidget(self.kaydirici, 1)
        yatay.addWidget(self.kare_etiketi)
        yatay.addWidget(self.hiz)
        self.kare_cubugu = cubuk

        goruntu_sayfasi = QWidget()
        dikey = QVBoxLayout(goruntu_sayfasi)
        dikey.setContentsMargins(0, 0, 0, 0)
        dikey.setSpacing(0)
        dikey.addWidget(self.alan, 1)
        dikey.addWidget(cubuk)

        self.hosgeldin = QTextBrowser()
        self.hosgeldin.setOpenLinks(False)
        self.hosgeldin.anchorClicked.connect(self._baglanti)
        self.hosgeldin.setHtml(HOSGELDIN_HTML)
        self.hosgeldin.setStyleSheet("QTextBrowser{background:#15181c;border:none}")

        self.metin_sayfasi = QTextBrowser()
        self.metin_sayfasi.setStyleSheet("QTextBrowser{background:#fbfbfb;color:#111;border:none;padding:16px}")

        self.yigin_alani = QStackedWidget()
        self.yigin_alani.addWidget(self.hosgeldin)  # 0
        self.yigin_alani.addWidget(goruntu_sayfasi)  # 1
        self.yigin_alani.addWidget(self.metin_sayfasi)  # 2

        # sağ panel
        self.bilgi = QTextBrowser()
        self.bilgi.setOpenExternalLinks(False)
        self.etiketler = EtiketPaneli()
        self.sag = QTabWidget()
        self.sag.addTab(self.bilgi, "Bilgi")
        self.sag.addTab(self.etiketler, "DICOM etiketleri")
        self.sag.setMinimumWidth(280)

        bolucu = QSplitter()
        bolucu.addWidget(self.agac)
        bolucu.addWidget(self.yigin_alani)
        bolucu.addWidget(self.sag)
        bolucu.setStretchFactor(0, 0)
        bolucu.setStretchFactor(1, 1)
        bolucu.setStretchFactor(2, 0)
        bolucu.setSizes([320, 780, 340])
        self.setCentralWidget(bolucu)
        self.statusBar().showMessage("Hazır. Dosya ya da klasör açın.")

    def _eylem(self, ad, tetik, kisayol=None, ipucu=None, simge=None, isaretli=None):
        e = QAction(ad, self)
        if kisayol:
            e.setShortcut(QKeySequence(kisayol))
            e.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        if ipucu:
            e.setToolTip(ipucu)
            e.setStatusTip(ipucu)
        if simge is not None:
            e.setIcon(self.style().standardIcon(simge))
        if isaretli is not None:
            e.setCheckable(True)
            e.setChecked(isaretli)
            e.toggled.connect(tetik)
        else:
            e.triggered.connect(tetik)
        self.addAction(e)
        return e

    def _eylemler_kur(self):
        SP = QStyle.StandardPixmap
        self.e_dosya = self._eylem("Dosya aç…", self.dosya_ac, "Ctrl+O", "DICOM, zip, JPG, PNG ya da PDF aç",
                                   SP.SP_DialogOpenButton)
        self.e_klasor = self._eylem("Klasör ya da CD/DVD aç…", self.klasor_ac, "Ctrl+Shift+O",
                                    "Bir klasörü ya da hastane CD'sini baştan sona tara", SP.SP_DirOpenIcon)
        self.e_temizle = self._eylem("Listeyi temizle", self.listeyi_temizle)
        self.e_cikis = self._eylem("Çıkış", self.close, "Ctrl+Q")

        self.e_png = self._eylem("Bu görüntüyü PNG olarak kaydet…", lambda: self.goruntuyu_kaydet("PNG"), "Ctrl+S",
                                 "Ekranda gördüğünüz ayarlarla, tam çözünürlükte", SP.SP_DialogSaveButton)
        self.e_jpg = self._eylem("Bu görüntüyü JPG olarak kaydet…", lambda: self.goruntuyu_kaydet("JPG"))
        self.e_pdf_tek = self._eylem("Bu görüntüyü PDF olarak kaydet…", self.goruntuyu_pdf)
        self.e_pdf_calisma = self._eylem("Seçili çalışmayı PDF olarak kaydet…", lambda: self.secimi_pdf("calisma"),
                                         "Ctrl+P")
        self.e_png_calisma = self._eylem("Seçili çalışmanın görüntülerini PNG olarak kaydet…",
                                         lambda: self.secimi_resim("calisma", "PNG"))
        self.e_jpg_calisma = self._eylem("Seçili çalışmanın görüntülerini JPG olarak kaydet…",
                                         lambda: self.secimi_resim("calisma", "JPG"))
        self.e_orijinal = self._eylem("Orijinal dosyaları (DICOM) kaydet…", lambda: self.secimi_orijinal("calisma"),
                                      "Ctrl+Shift+S")
        self.e_orijinal_tum = self._eylem("Tüm listenin orijinallerini kaydet…", lambda: self.secimi_orijinal("tum"))

        self.e_sigdir = self._eylem("Ekrana sığdır", self.alan.sigdir, "F", simge=None)
        self.e_gercek = self._eylem("Gerçek boyut (1:1)", self.alan.gercek_boyut, "1")
        self.e_yakin = self._eylem("Yakınlaştır", lambda: self.alan.yakinlastir(1.25), "+")
        self.e_uzak = self._eylem("Uzaklaştır", lambda: self.alan.yakinlastir(0.8), "-")
        self.e_ters = self._eylem("Tersine çevir", self._ters_degisti, "I", isaretli=False)
        self.e_sifirla = self._eylem("Pencere-seviyeyi sıfırla", self.pencereyi_sifirla, "R")
        self.e_otomatik = self._eylem("Otomatik pencere (tam aralık)", self.otomatik_pencere, "A")
        self.e_olcum = self._eylem("Ölçüm cetveli", self._olcum_degisti, "M", isaretli=False)
        self.e_net = self._eylem("Netleştir", self._net_degisti, "N", isaretli=False)
        self.e_keskin = self._eylem("Büyütünce pikselleri keskin göster", self._keskin_degisti, isaretli=False)
        self.e_tam = self._eylem("Tam ekran", self._tam_ekran, "F11")
        self._eylem("Önceki kare", lambda: self.kareye_git(self.konum - 1), "Left")
        self._eylem("Sonraki kare", lambda: self.kareye_git(self.konum + 1), "Right")
        self._eylem("Önceki kare ", lambda: self.kareye_git(self.konum - 1), "Up")
        self._eylem("Sonraki kare ", lambda: self.kareye_git(self.konum + 1), "Down")
        self._eylem("10 kare geri", lambda: self.kareye_git(self.konum - 10), "PgUp")
        self._eylem("10 kare ileri", lambda: self.kareye_git(self.konum + 10), "PgDown")
        self._eylem("İlk kare", lambda: self.kareye_git(0), "Home")
        self._eylem("Son kare", lambda: self.kareye_git(len(self.yigin) - 1), "End")
        self._eylem("Oynat / durdur", self.oynat_durdur, "Space")

        self.e_yardim = self._eylem("Nasıl kullanılır", self.yardim_goster, "F1")
        self.e_enabiz = self._eylem("e-Nabız görüntüsü açılmıyorsa", self.enabiz_goster)
        self.e_hakkinda = self._eylem(f"{AD} hakkında", self.hakkinda)

        m = self.menuBar()
        dosya = m.addMenu("&Dosya")
        for e in (self.e_dosya, self.e_klasor):
            dosya.addAction(e)
        dosya.addSeparator()
        dosya.addAction(self.e_temizle)
        dosya.addSeparator()
        dosya.addAction(self.e_cikis)

        disa = m.addMenu("Dışa &aktar")
        for e in (self.e_png, self.e_jpg, self.e_pdf_tek):
            disa.addAction(e)
        disa.addSeparator()
        for e in (self.e_pdf_calisma, self.e_png_calisma, self.e_jpg_calisma):
            disa.addAction(e)
        disa.addSeparator()
        disa.addAction(self.e_orijinal)
        disa.addAction(self.e_orijinal_tum)

        gor = m.addMenu("&Görünüm")
        for e in (self.e_sigdir, self.e_gercek, self.e_yakin, self.e_uzak):
            gor.addAction(e)
        gor.addSeparator()
        for e in (self.e_sifirla, self.e_otomatik, self.e_ters):
            gor.addAction(e)
        hazir = gor.addMenu("Hazır pencereler (BT)")
        for ad, s, g in G.HAZIR_PENCERELER:
            hazir.addAction(f"{ad}  (S {s} / G {g})", lambda s=s, g=g: self.pencere_ayarla(s, g))
        gor.addSeparator()
        for e in (self.e_olcum, self.e_net, self.e_keskin):
            gor.addAction(e)
        gor.addSeparator()
        gor.addAction(self.e_tam)

        yardim = m.addMenu("&Yardım")
        for e in (self.e_yardim, self.e_enabiz):
            yardim.addAction(e)
        yardim.addSeparator()
        yardim.addAction(self.e_hakkinda)

        arac = QToolBar("Araçlar")
        arac.setMovable(False)
        arac.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(arac)
        arac.addAction(self.e_dosya)
        arac.addAction(self.e_klasor)
        arac.addSeparator()
        kaydet = QToolButton()
        kaydet.setText("Kaydet / dışa aktar")
        kaydet.setIcon(self.style().standardIcon(SP.SP_DialogSaveButton))
        kaydet.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        kaydet.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        kaydet.setMenu(disa)
        arac.addWidget(kaydet)
        arac.addSeparator()
        self.hazir_kutu = QComboBox()
        self.hazir_kutu.addItem("Pencere: varsayılan")
        self.hazir_kutu.addItem("Pencere: otomatik (tam aralık)")
        for ad, s, g in G.HAZIR_PENCERELER:
            self.hazir_kutu.addItem(ad)
        self.hazir_kutu.setToolTip("Parlaklık / kontrast için hazır ayarlar. Sağ tuşla sürükleyerek de ayarlayabilirsiniz.")
        self.hazir_kutu.activated.connect(self._hazir_secildi)
        arac.addWidget(self.hazir_kutu)
        for e in (self.e_sigdir, self.e_gercek, self.e_ters, self.e_olcum, self.e_net):
            arac.addAction(e)
        arac.addSeparator()
        arac.addAction(self.e_enabiz)

    # ---------------- dosya açma ----------------
    def _son_klasor(self) -> str:
        return self.ayarlar.value("son_klasor", os.path.expanduser("~"))

    def dosya_ac(self):
        yollar, _ = QFileDialog.getOpenFileNames(
            self, "Dosya aç", self._son_klasor(),
            "Desteklenen dosyalar (*.dcm *.dicom *.dic *.ima *.zip *.jpg *.jpeg *.png *.bmp *.tif *.tiff *.pdf DICOMDIR *);;"
            "DICOM (*.dcm *.dicom *.dic *.ima DICOMDIR);;Zip (*.zip);;Resim (*.jpg *.jpeg *.png *.bmp *.tif *.tiff);;"
            "PDF (*.pdf);;Tüm dosyalar (*)")
        if yollar:
            self.ayarlar.setValue("son_klasor", os.path.dirname(yollar[0]))
            self.yukle(yollar)

    def klasor_ac(self):
        klasor = QFileDialog.getExistingDirectory(self, "Klasör ya da CD/DVD seçin", self._son_klasor())
        if klasor:
            self.ayarlar.setValue("son_klasor", klasor)
            self.yukle([klasor])

    def yukle(self, yollar, esli: bool = False):
        if self._is is not None:
            return
        if esli:
            sonuc = self.kutuphane.ekle(yollar)
            self._yukleme_bitti(sonuc)
            return
        self._ilerleme = QProgressDialog("Dosyalar taranıyor…", "Durdur", 0, 0, self)
        self._ilerleme.setWindowTitle(AD)
        self._ilerleme.setWindowModality(Qt.WindowModality.WindowModal)
        self._ilerleme.setMinimumDuration(300)
        self._is = TaramaIsi(self.kutuphane, yollar)
        self._is.ilerleme.connect(self._ilerleme_guncelle)
        self._is.bitti.connect(self._yukleme_bitti)
        self._ilerleme.canceled.connect(self._is.iptal_et)
        QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        self._is.start()

    def _ilerleme_guncelle(self, a, b, ad):
        if self._ilerleme is not None:
            self._ilerleme.setMaximum(b)
            self._ilerleme.setValue(a)
            self._ilerleme.setLabelText(f"Dosyalar taranıyor… {a}/{b}\n{ad}")

    def _yukleme_bitti(self, sonuc: K.TaramaSonucu):
        if self._is is not None:
            QApplication.restoreOverrideCursor()
            self._is.wait()
            self._is = None
            if self._ilerleme is not None:
                self._ilerleme.close()
                self._ilerleme = None
        self.agaci_kur()
        mesaj = f"{sonuc.eklenen} dosya eklendi"
        if sonuc.tekrar:
            mesaj += f", {sonuc.tekrar} tekrar atlandı"
        if sonuc.atlanan:
            mesaj += f", {sonuc.atlanan} desteklenmeyen dosya atlandı"
        if sonuc.iptal:
            mesaj += " (tarama durduruldu)"
        self.statusBar().showMessage(mesaj + ".", 12000)
        if sonuc.hatalar:
            kutu = QMessageBox(self)
            kutu.setIcon(QMessageBox.Icon.Warning)
            kutu.setWindowTitle(AD)
            kutu.setText(f"{mesaj}. {len(sonuc.hatalar)} dosya açılamadı.")
            kutu.setDetailedText("\n".join(sonuc.hatalar[:500]))
            kutu.exec()
        elif sonuc.eklenen == 0 and not sonuc.iptal:
            QMessageBox.information(self, AD, "Açılabilecek görüntü bulunamadı.\n\nDesteklenenler: DICOM (.dcm, uzantısız, "
                                    "DICOMDIR), zip, JPG, PNG, BMP, TIFF ve PDF.")
        if self.oge is None:
            self._ilk_goruntuyu_sec()

    def listeyi_temizle(self):
        self.oynatici.stop()
        self.kutuphane.temizle()
        self._onbellek.clear()
        self._pencere_kayitlari.clear()
        self.yigin, self.konum, self.oge, self.kaynak = [], 0, None, None
        self.agac.clear()
        self.alan.temizle()
        self.etiketler.doldur(None)
        self.bilgi.clear()
        self.yigin_alani.setCurrentIndex(0)
        K.gecicileri_temizle(eskiler_de=False)
        self._durum_guncelle()

    # ---------------- ağaç ----------------
    def agaci_kur(self):
        self.agac.blockSignals(True)
        secili = self.oge
        self.agac.clear()
        bulunan = None
        kalin = QFont()
        kalin.setBold(True)
        for h in self.kutuphane.sirali_hastalar():
            hd = QTreeWidgetItem(self.agac, [h.baslik(), str(len(h.calismalar))])
            hd.setData(0, ROL, h)
            hd.setFont(0, kalin)
            hd.setToolTip(0, h.baslik())
            for c in h.sirali_calismalar():
                cd = QTreeWidgetItem(hd, [c.baslik(), str(sum(len(s.ogeler) for s in c.seriler.values()))])
                cd.setData(0, ROL, c)
                cd.setToolTip(0, c.baslik() + (f"\n{c.kurum}" if c.kurum else ""))
                for s in c.sirali_seriler():
                    sd = QTreeWidgetItem(cd, [s.baslik(), str(len(s.ogeler))])
                    sd.setData(0, ROL, s)
                    sd.setToolTip(0, f"{modalite_tam(s.modalite)} · {s.baslik()}")
                    for o in s.sirali_ogeler():
                        od = QTreeWidgetItem(sd, [o.ad, str(o.kare_sayisi) if o.kare_sayisi > 1 else ""])
                        od.setData(0, ROL, o)
                        od.setToolTip(0, o.yol)
                        if o is secili:
                            bulunan = od
                cd.setExpanded(len(h.calismalar) <= 6)
            hd.setExpanded(True)
        if bulunan is not None:
            self.agac.setCurrentItem(bulunan)
        self.agac.blockSignals(False)

    def _ilk_goruntuyu_sec(self):
        kok = self.agac.invisibleRootItem()
        yigin = [kok.child(i) for i in range(kok.childCount())]
        while yigin:
            d = yigin.pop(0)
            nesne = d.data(0, ROL)
            if isinstance(nesne, K.Oge) and nesne.tur in K.GORUNTULU_TURLER | {K.T_SR}:
                self.agac.setCurrentItem(d)
                return
            yigin[0:0] = [d.child(i) for i in range(d.childCount())]

    def _secili_nesne(self):
        d = self.agac.currentItem()
        return d.data(0, ROL) if d is not None else None

    def _agac_secildi(self, simdiki, _onceki):
        if simdiki is None:
            return
        nesne = simdiki.data(0, ROL)
        oge = None
        if isinstance(nesne, K.Oge):
            oge = nesne
        elif isinstance(nesne, K.Seri):
            ogeler = nesne.sirali_ogeler()
            oge = ogeler[0] if ogeler else None
        elif isinstance(nesne, K.Calisma):
            ogeler = nesne.tum_ogeler()
            oge = next((o for o in ogeler if o.tur in K.GORUNTULU_TURLER), ogeler[0] if ogeler else None)
        elif isinstance(nesne, K.Hasta):
            calismalar = nesne.sirali_calismalar()
            if calismalar:
                ogeler = calismalar[0].tum_ogeler()
                oge = next((o for o in ogeler if o.tur in K.GORUNTULU_TURLER), None)
        if oge is not None and (self.oge is None or oge is not self.oge):
            self.ogeyi_ac(oge)
        self._bilgi_guncelle(nesne)

    def _agac_menusu(self, konum):
        d = self.agac.itemAt(konum)
        if d is None:
            return
        self.agac.setCurrentItem(d)
        menu = QMenu(self)
        menu.addAction("PDF olarak kaydet…", lambda: self.secimi_pdf("secili"))
        menu.addAction("Görüntüleri PNG olarak kaydet…", lambda: self.secimi_resim("secili", "PNG"))
        menu.addAction("Görüntüleri JPG olarak kaydet…", lambda: self.secimi_resim("secili", "JPG"))
        menu.addSeparator()
        menu.addAction("Orijinal dosyaları kaydet…", lambda: self.secimi_orijinal("secili"))
        nesne = d.data(0, ROL)
        if isinstance(nesne, K.Oge):
            menu.addSeparator()
            menu.addAction("Dosyanın bulunduğu klasörü aç", lambda: _klasoru_ac(os.path.dirname(nesne.yol)))
        menu.exec(self.agac.viewport().mapToGlobal(konum))

    # ---------------- görüntüleme ----------------
    def _kaynak(self, oge: K.Oge) -> G.Kaynak:
        if oge.yol in self._onbellek:
            self._onbellek.move_to_end(oge.yol)
            return self._onbellek[oge.yol]
        kaynak = G.kaynak_ac(oge)
        self._onbellek[oge.yol] = kaynak
        while len(self._onbellek) > 64:
            self._onbellek.popitem(last=False)
        return kaynak

    def ogeyi_ac(self, oge: K.Oge):
        self.oynatici.stop()
        self._oynat_dugmesi()
        if oge.tur == K.T_SR:
            self.oge, self.kaynak, self.yigin = oge, None, []
            try:
                self.metin_sayfasi.setHtml(G.sr_html(oge.yol))
                import pydicom
                self.etiketler.doldur(pydicom.dcmread(oge.yol, force=True))
            except Exception as e:  # noqa: BLE001
                self.metin_sayfasi.setHtml(f"<p>Rapor okunamadı: {html.escape(str(e))}</p>")
            self.yigin_alani.setCurrentIndex(2)
            self._durum_guncelle()
            return
        if oge.tur == K.T_DICOM_DIGER:
            self.oge, self.kaynak, self.yigin = oge, None, []
            import pydicom
            try:
                self.etiketler.doldur(pydicom.dcmread(oge.yol, stop_before_pixels=True, force=True))
            except Exception:  # noqa: BLE001
                self.etiketler.doldur(None)
            self.metin_sayfasi.setHtml("<h3>Bu DICOM dosyasında görüntü yok.</h3>"
                                       "<p>İçeriğini sağdaki <b>DICOM etiketleri</b> sekmesinde görebilirsiniz.</p>")
            self.sag.setCurrentWidget(self.etiketler)
            self.yigin_alani.setCurrentIndex(2)
            self._durum_guncelle()
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            kaynak = self._kaynak(oge)
        except Exception as e:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            self.oge, self.kaynak, self.yigin = oge, None, []
            self.metin_sayfasi.setHtml(f"<h3>Bu görüntü açılamadı.</h3><p>{html.escape(str(e))}</p>"
                                       "<p>Etiketler yine de sağda gösterilir.</p>")
            try:
                import pydicom
                self.etiketler.doldur(pydicom.dcmread(oge.yol, stop_before_pixels=True, force=True))
            except Exception:  # noqa: BLE001
                self.etiketler.doldur(None)
            self.yigin_alani.setCurrentIndex(2)
            self._durum_guncelle()
            return
        QApplication.restoreOverrideCursor()

        # yığın: çok kareliyse kareler; değilse serideki tek kareli görüntüler (MR / BT kesitleri)
        eski_yigin_serisi = self.yigin[0][0].seri if self.yigin else None
        if kaynak.kare_sayisi > 1:
            yigin = [(oge, k) for k in range(kaynak.kare_sayisi)]
            konum = 0
        else:
            kardesler = [o for o in (oge.seri.sirali_ogeler() if oge.seri else [oge])
                         if o.tur in (K.T_DICOM, K.T_RESIM) and o.kare_sayisi <= 1]
            if oge not in kardesler:
                kardesler = [oge]
            yigin = [(o, 0) for o in kardesler]
            konum = kardesler.index(oge)
        ayni_seri = (kaynak.kare_sayisi <= 1 and eski_yigin_serisi is not None and eski_yigin_serisi is oge.seri
                     and len(yigin) > 1 and self.yigin and self.yigin[0][1] == 0 and self.kaynak is not None)
        self.yigin = yigin
        self.konum = konum
        if kaynak.kare_hizi:
            self.hiz.blockSignals(True)
            self.hiz.setValue(int(round(min(60, max(1, kaynak.kare_hizi)))))
            self.hiz.blockSignals(False)
        if not ayni_seri:
            kayit = self._pencere_kayitlari.get(oge.sop_uid or oge.yol)
            if kayit:
                self.seviye, self.genislik, self.ters = kayit
            else:
                (self.seviye, self.genislik), self.ters = kaynak.varsayilan_pencere(), False
            self.e_ters.blockSignals(True)
            self.e_ters.setChecked(self.ters)
            self.e_ters.blockSignals(False)
            self.hazir_kutu.setCurrentIndex(0)
        self.yigin_alani.setCurrentIndex(1)
        self._ciz(yeni=not ayni_seri)

    def kareye_git(self, i: int, dongu: bool = False):
        if not self.yigin:
            return
        n = len(self.yigin)
        if dongu:
            i %= n
        i = max(0, min(n - 1, i))
        if i == self.konum and self.kaynak is not None and self.oge is self.yigin[i][0]:
            self._kaydirici_guncelle()
            return
        self.konum = i
        self._ciz(yeni=False)

    def _ciz(self, yeni: bool):
        oge, kare = self.yigin[self.konum]
        try:
            kaynak = self._kaynak(oge)
        except Exception as e:  # noqa: BLE001
            self.statusBar().showMessage(f"Açılamadı: {e}", 8000)
            return
        oge_degisti = oge is not self.oge
        self.oge, self.kaynak = oge, kaynak
        dizi = kaynak.ciz(kare, self.seviye, self.genislik, self.ters)
        if self.netlestir:
            dizi = G.netlestir(dizi)
        self._son_dizi = dizi
        self.alan.piksel_araligi = kaynak.piksel_araligi
        self.alan.goster(dizi, yeni)
        if oge_degisti or yeni:
            self.etiketler.doldur(kaynak.ds)
            self._agacta_isaretle(oge)
        self._kaydirici_guncelle()
        self._durum_guncelle()

    def _agacta_isaretle(self, oge):
        d = self.agac.currentItem()
        if d is not None and d.data(0, ROL) is oge:
            return
        if d is not None and isinstance(d.data(0, ROL), (K.Seri, K.Calisma, K.Hasta)) and not self.oynatici.isActive():
            # kullanıcı seri / çalışma seçtiyse seçim yerinde kalsın
            if self.yigin and self.yigin[0][1] != 0:
                return
        bul = self.agac.findItems(oge.ad, Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive, 0)
        for aday in bul:
            if aday.data(0, ROL) is oge:
                self.agac.blockSignals(True)
                self.agac.setCurrentItem(aday)
                self.agac.blockSignals(False)
                self._bilgi_guncelle(oge)
                return

    def _kaydirici_guncelle(self):
        n = len(self.yigin)
        self.kaydirici.blockSignals(True)
        self.kaydirici.setRange(0, max(0, n - 1))
        self.kaydirici.setValue(self.konum)
        self.kaydirici.blockSignals(False)
        cok = n > 1
        for w in (self.btn_onceki, self.btn_oynat, self.btn_sonraki, self.kaydirici, self.hiz):
            w.setEnabled(cok)
        if cok:
            tur = "Kare" if self.yigin[0][1] != 0 or (self.kaynak and self.kaynak.kare_sayisi > 1) else "Kesit"
            if self.oge and self.oge.tur in (K.T_PDF, K.T_DICOM_PDF):
                tur = "Sayfa"
            self.kare_etiketi.setText(f"{tur} {self.konum + 1} / {n}")
        else:
            self.kare_etiketi.setText("Tek görüntü")

    def _durum_guncelle(self):
        a = self.alan
        if self.kaynak is None or self.oge is None or not self.yigin:
            a.koseler = ["", "", "", ""]
            a.viewport().update()
            return
        oge = self.oge
        c = oge.calisma
        h = c.hasta if c else None
        sol_ust = []
        if h and not h.anahtar.startswith("~"):
            sol_ust.append(h.ad or "Adı yok")
            ek = []
            if h.kimlik:
                ek.append(h.kimlik)
            if h.dogum:
                ek.append("D: " + K.tarih_bicimle(h.dogum))
            if h.cinsiyet:
                ek.append({"M": "Erkek", "F": "Kadın"}.get(h.cinsiyet, h.cinsiyet))
            if ek:
                sol_ust.append(" · ".join(ek))
        sag_ust = []
        if c:
            sag_ust.append(f"{K.tarih_bicimle(c.tarih)} {K.saat_bicimle(c.saat)}".strip())
            if c.aciklama:
                sag_ust.append(c.aciklama)
            if c.kurum:
                sag_ust.append(c.kurum)
        if oge.seri:
            sag_ust.append(f"{modalite_tam(oge.seri.modalite)} · {oge.seri.baslik()}")
        sol_alt = []
        if len(self.yigin) > 1:
            sol_alt.append(self.kare_etiketi.text())
        sol_alt.append(oge.ad)
        if a.boyut[0]:
            sol_alt.append(f"{a.boyut[0]} × {a.boyut[1]} piksel")
        sag_alt = []
        if not self.kaynak.renkli:
            sag_alt.append(f"Seviye {self.seviye:.0f} · Genişlik {self.genislik:.0f}")
        sag_alt.append(f"Yakınlık %{a.yakinlik() * 100:.0f}")
        if a.olcum:
            sag_alt.append("Ölçüm: " + a.olcum_metni())
        a.koseler = ["\n".join(sol_ust), "\n".join(sag_ust), "\n".join(sol_alt), "\n".join(sag_alt)]
        a.viewport().update()

    def _bilgi_guncelle(self, nesne):
        satir = []

        def ekle(ad, deger):
            if deger:
                satir.append(f"<tr><td style='color:#666;padding-right:10px'>{html.escape(ad)}</td>"
                             f"<td>{html.escape(str(deger))}</td></tr>")

        oge = nesne if isinstance(nesne, K.Oge) else None
        seri = nesne if isinstance(nesne, K.Seri) else (oge.seri if oge else None)
        calisma = nesne if isinstance(nesne, K.Calisma) else (seri.calisma if seri else None)
        hasta = nesne if isinstance(nesne, K.Hasta) else (calisma.hasta if calisma else None)
        if hasta and not hasta.anahtar.startswith("~"):
            satir.append("<tr><td colspan=2><b>Hasta</b></td></tr>")
            ekle("Ad", hasta.ad)
            ekle("Hasta no", hasta.kimlik)
            ekle("Doğum tarihi", K.tarih_bicimle(hasta.dogum))
            ekle("Cinsiyet", {"M": "Erkek", "F": "Kadın", "O": "Diğer"}.get(hasta.cinsiyet, hasta.cinsiyet))
            ekle("Çalışma sayısı", len(hasta.calismalar))
        if calisma:
            satir.append("<tr><td colspan=2><br><b>Çalışma</b></td></tr>")
            ekle("Tarih", f"{K.tarih_bicimle(calisma.tarih)} {K.saat_bicimle(calisma.saat)}".strip())
            ekle("Tür", ", ".join(modalite_tam(m) for m in calisma.modaliteler()))
            ekle("Açıklama", calisma.aciklama)
            ekle("Kurum", calisma.kurum)
            ekle("Seri sayısı", len(calisma.seriler))
        if seri:
            satir.append("<tr><td colspan=2><br><b>Seri</b></td></tr>")
            ekle("Seri", seri.baslik())
            ekle("Tür", modalite_tam(seri.modalite))
            ekle("Dosya sayısı", len(seri.ogeler))
        if oge:
            satir.append("<tr><td colspan=2><br><b>Dosya</b></td></tr>")
            ekle("Ad", oge.ad)
            if oge.kare_sayisi > 1:
                ekle("Kare sayısı", oge.kare_sayisi)
            if self.kaynak is not None and oge is self.oge and self.kaynak.piksel_araligi:
                pa = self.kaynak.piksel_araligi
                ekle("Piksel aralığı", f"{pa[0]:.3f} × {pa[1]:.3f} mm")
            ekle("Konum", oge.yol)
        self.bilgi.setHtml("<table style='font-family:Segoe UI;font-size:9.5pt'>" + "".join(satir) + "</table>")

    # pencere-seviye
    def _pencere_surukle(self, dx, dy):
        if self.kaynak is None:
            return
        alt, ust = self.kaynak.deger_araligi()
        olcek = max((ust - alt) / 600.0, 0.25)
        self.genislik = max(1.0, self.genislik + dx * olcek * 2)
        self.seviye = self.seviye - dy * olcek
        self.hazir_kutu.setCurrentIndex(0)
        self._pencere_kaydet()
        self._ciz(yeni=False)

    def pencere_ayarla(self, seviye, genislik):
        if self.kaynak is None:
            return
        self.seviye, self.genislik = float(seviye), float(genislik)
        self._pencere_kaydet()
        self._ciz(yeni=False)

    def _pencere_kaydet(self):
        if self.oge is not None:
            self._pencere_kayitlari[self.oge.sop_uid or self.oge.yol] = (self.seviye, self.genislik, self.ters)

    def pencereyi_sifirla(self):
        if self.kaynak is None:
            return
        self.seviye, self.genislik = self.kaynak.varsayilan_pencere()
        self.ters = False
        self.e_ters.blockSignals(True)
        self.e_ters.setChecked(False)
        self.e_ters.blockSignals(False)
        self.hazir_kutu.setCurrentIndex(0)
        if self.oge is not None:
            self._pencere_kayitlari.pop(self.oge.sop_uid or self.oge.yol, None)
        self._ciz(yeni=False)
        self.alan.sigdir()
        self._durum_guncelle()

    def otomatik_pencere(self):
        if isinstance(self.kaynak, G.DicomKaynak):
            s, g = self.kaynak.otomatik_pencere(self.yigin[self.konum][1])
            self.pencere_ayarla(s, g)

    def _hazir_secildi(self, i):
        if self.kaynak is None:
            return
        if i == 0:
            s, g = self.kaynak.varsayilan_pencere()
            self.pencere_ayarla(s, g)
        elif i == 1:
            self.otomatik_pencere()
        else:
            _, s, g = G.HAZIR_PENCERELER[i - 2]
            self.pencere_ayarla(s, g)

    def _ters_degisti(self, acik):
        self.ters = bool(acik)
        self._pencere_kaydet()
        if self.kaynak is not None:
            self._ciz(yeni=False)

    def _olcum_degisti(self, acik):
        self.alan.olcum_modu = bool(acik)
        self.alan.setDragMode(QGraphicsView.DragMode.NoDrag if acik else QGraphicsView.DragMode.ScrollHandDrag)
        self.alan.setCursor(Qt.CursorShape.CrossCursor if acik else Qt.CursorShape.ArrowCursor)
        if not acik:
            self.alan.olcum = None
            self.alan.unsetCursor()
        self.statusBar().showMessage(
            "Ölçüm: görüntü üzerinde sol tuşla çizgi çekin." if acik else "Ölçüm kapandı.", 6000)
        self._durum_guncelle()

    def _net_degisti(self, acik):
        self.netlestir = bool(acik)
        if self.kaynak is not None:
            self._ciz(yeni=False)

    def _keskin_degisti(self, acik):
        self.alan.keskin_piksel = bool(acik)
        self.alan._yumusatma_guncelle()

    def _tam_ekran(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    # oynatma
    def oynat_durdur(self):
        if len(self.yigin) <= 1:
            return
        if self.oynatici.isActive():
            self.oynatici.stop()
        else:
            self.oynatici.start(int(1000 / max(1, self.hiz.value())))
        self._oynat_dugmesi()

    def _oynat_dugmesi(self):
        self.btn_oynat.setText("❚❚  Durdur" if self.oynatici.isActive() else "▶  Oynat")

    def _hiz_degisti(self, v):
        if self.oynatici.isActive():
            self.oynatici.setInterval(int(1000 / max(1, v)))

    # ---------------- dışa aktarma ----------------
    def _kayit_yolu(self, baslik, ad, suzgec) -> str | None:
        klasor = self.ayarlar.value("son_kayit", os.path.join(os.path.expanduser("~"), "Desktop"))
        yol, _ = QFileDialog.getSaveFileName(self, baslik, os.path.join(klasor, ad), suzgec)
        if yol:
            self.ayarlar.setValue("son_kayit", os.path.dirname(yol))
        return yol or None

    def _kayit_klasoru(self, baslik) -> str | None:
        klasor = self.ayarlar.value("son_kayit", os.path.join(os.path.expanduser("~"), "Desktop"))
        yol = QFileDialog.getExistingDirectory(self, baslik, klasor)
        if yol:
            self.ayarlar.setValue("son_kayit", yol)
        return yol or None

    def _gorunen_dizi(self) -> np.ndarray | None:
        if self.kaynak is None or not self.yigin:
            return None
        oge, kare = self.yigin[self.konum]
        dizi = self.kaynak.ciz(kare, self.seviye, self.genislik, self.ters)
        return G.netlestir(dizi) if self.netlestir else dizi

    def goruntuyu_kaydet(self, bicim: str, yol: str | None = None) -> str | None:
        dizi = self._gorunen_dizi()
        if dizi is None:
            QMessageBox.information(self, AD, "Önce bir görüntü açın.")
            return None
        oge, kare = self.yigin[self.konum]
        uzanti = ".jpg" if bicim == "JPG" else ".png"
        ad = D.oge_dosya_adi(oge, kare if self.kaynak.kare_sayisi > 1 else None, uzanti)
        if yol is None:
            yol = self._kayit_yolu(f"Görüntüyü {bicim} olarak kaydet", ad,
                                   "JPG (*.jpg)" if bicim == "JPG" else "PNG (*.png)")
            if not yol:
                return None
        try:
            D.resim_kaydet(dizi, yol)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, AD, f"Kaydedilemedi:\n{e}")
            return None
        self.statusBar().showMessage(f"Kaydedildi: {yol}", 10000)
        return yol

    def goruntuyu_pdf(self):
        if self.oge is None or self.kaynak is None:
            QMessageBox.information(self, AD, "Önce bir görüntü açın.")
            return
        yol = self._kayit_yolu("Görüntüyü PDF olarak kaydet", D.oge_dosya_adi(self.oge, None, ".pdf"), "PDF (*.pdf)")
        if not yol:
            return
        self._pencere_kaydet()
        self._arkaplanda("PDF hazırlanıyor…",
                         lambda il, ip: D.pdf_olustur([self.oge], yol, self._pencere_kayitlari, il, ip, kapak=False),
                         lambda r: f"PDF kaydedildi ({r[0]} sayfa): {yol}")

    def _secim_ogeleri(self, kapsam: str) -> list[K.Oge]:
        if kapsam == "tum":
            return self.kutuphane.tum_ogeler()
        nesne = self._secili_nesne()
        if kapsam == "calisma" and isinstance(nesne, (K.Oge, K.Seri)):
            nesne = nesne.calisma
        if isinstance(nesne, K.Oge):
            return [nesne]
        if isinstance(nesne, K.Seri):
            return nesne.sirali_ogeler()
        if isinstance(nesne, K.Calisma):
            return nesne.tum_ogeler()
        if isinstance(nesne, K.Hasta):
            return [o for c in nesne.sirali_calismalar() for o in c.tum_ogeler()]
        if self.oge is not None and self.oge.calisma is not None:
            return self.oge.calisma.tum_ogeler()
        return []

    def _secim_adi(self, ogeler) -> str:
        c = ogeler[0].calisma if ogeler else None
        if c is None:
            return "gor-bak"
        return K.guvenli_ad(f"{c.tarih} {c.modalite_metni()} {c.aciklama}".strip(), 80)

    def secimi_pdf(self, kapsam: str, yol: str | None = None):
        ogeler = self._secim_ogeleri(kapsam)
        if not ogeler:
            QMessageBox.information(self, AD, "Önce listeden bir çalışma seçin.")
            return
        kare_toplam = sum(o.kare_sayisi for o in ogeler if o.tur in (K.T_DICOM, K.T_RESIM))
        if kare_toplam > 400 and yol is None:
            yanit = QMessageBox.question(self, AD, f"Bu seçim yaklaşık {kare_toplam} sayfalık bir PDF olacak. Devam edilsin mi?")
            if yanit != QMessageBox.StandardButton.Yes:
                return
        if yol is None:
            yol = self._kayit_yolu("PDF olarak kaydet", self._secim_adi(ogeler) + ".pdf", "PDF (*.pdf)")
            if not yol:
                return
        self._pencere_kaydet()
        return self._arkaplanda("PDF hazırlanıyor…",
                                lambda il, ip: D.pdf_olustur(ogeler, yol, self._pencere_kayitlari, il, ip),
                                lambda r: f"PDF kaydedildi ({r[0]} sayfa): {yol}")

    def secimi_resim(self, kapsam: str, bicim: str):
        ogeler = self._secim_ogeleri(kapsam)
        if not ogeler:
            QMessageBox.information(self, AD, "Önce listeden bir çalışma seçin.")
            return
        klasor = self._kayit_klasoru(f"Görüntülerin {bicim} olarak kaydedileceği klasörü seçin")
        if not klasor:
            return
        hedef = os.path.join(klasor, self._secim_adi(ogeler))
        self._arkaplanda(f"{bicim} dosyaları yazılıyor…",
                         lambda il, ip: D.calisma_resimleri_kaydet(ogeler, hedef, bicim, il, ip),
                         lambda r: f"{r[0]} görüntü kaydedildi: {hedef}")

    def secimi_orijinal(self, kapsam: str):
        ogeler = self._secim_ogeleri(kapsam)
        if not ogeler:
            QMessageBox.information(self, AD, "Kaydedilecek dosya yok.")
            return
        klasor = self._kayit_klasoru("Orijinal dosyaların kopyalanacağı klasörü seçin")
        if not klasor:
            return
        self._arkaplanda("Dosyalar kopyalanıyor…",
                         lambda il, ip: D.orijinalleri_kopyala(ogeler, klasor, il, ip),
                         lambda r: f"{r[0]} orijinal dosya kopyalandı: {klasor}")

    def _arkaplanda(self, baslik, is_, basari_metni, esli: bool = False):
        """Uzun dışa aktarmaları ilerleme penceresiyle çalıştırır (aynı iş parçacığında, arayüz canlı kalır)."""
        ilerleme = QProgressDialog(baslik, "Durdur", 0, 0, self)
        ilerleme.setWindowTitle(AD)
        ilerleme.setWindowModality(Qt.WindowModality.WindowModal)
        ilerleme.setMinimumDuration(400)
        iptal = {"var": False}
        ilerleme.canceled.connect(lambda: iptal.__setitem__("var", True))

        def il(a, b, ad):
            ilerleme.setMaximum(b)
            ilerleme.setValue(a)
            ilerleme.setLabelText(f"{baslik} {a}/{b}\n{ad}")
            QApplication.processEvents()

        QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        try:
            sonuc = is_(il, lambda: iptal["var"])
        except Exception as e:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            ilerleme.close()
            if not esli:
                QMessageBox.warning(self, AD, f"İşlem tamamlanamadı:\n{e}")
            return None
        QApplication.restoreOverrideCursor()
        ilerleme.close()
        mesaj = basari_metni(sonuc)
        if iptal["var"]:
            mesaj += " (durduruldu, eksik olabilir)"
        self.statusBar().showMessage(mesaj, 15000)
        hatalar = sonuc[1] if isinstance(sonuc, tuple) and len(sonuc) > 1 else []
        if not esli:
            if hatalar:
                kutu = QMessageBox(self)
                kutu.setIcon(QMessageBox.Icon.Warning)
                kutu.setWindowTitle(AD)
                kutu.setText(mesaj + f"\n\n{len(hatalar)} dosya atlandı.")
                kutu.setDetailedText("\n".join(hatalar))
                kutu.exec()
            else:
                QMessageBox.information(self, AD, mesaj)
        return sonuc

    # ---------------- yardım ----------------
    def _baglanti(self, url):
        hedef = url.toString()
        if hedef == "ac:dosya":
            self.dosya_ac()
        elif hedef == "ac:klasor":
            self.klasor_ac()
        elif hedef == "yardim:enabiz":
            self.enabiz_goster()

    def _html_penceresi(self, baslik, icerik, genislik=640, yukseklik=560):
        d = QDialog(self)
        d.setWindowTitle(baslik)
        d.resize(genislik, yukseklik)
        v = QVBoxLayout(d)
        t = QTextBrowser()
        t.setOpenExternalLinks(False)
        t.setHtml(f"<div style='font-family:Segoe UI;font-size:10pt'>{icerik}</div>")
        v.addWidget(t)
        b = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        b.button(QDialogButtonBox.StandardButton.Close).setText("Kapat")
        b.rejected.connect(d.reject)
        v.addWidget(b)
        d.exec()

    def enabiz_goster(self):
        self._html_penceresi("e-Nabız görüntüsü açılmıyorsa", ENABIZ_HTML)

    def yardim_goster(self):
        icerik = HOSGELDIN_HTML.replace("color:#d8dde3", "color:#111").replace("color:#ffffff", "color:#111")
        icerik = icerik.replace("color:#6fb6ff", "color:#0a58ca")
        self._html_penceresi("Nasıl kullanılır", icerik, 760, 640)

    def hakkinda(self):
        QMessageBox.about(self, f"{AD} hakkında",
                          f"<b>{AD} {SURUM}</b><br>Yerel radyoloji görüntüleyici.<br><br>"
                          "DICOM, DICOMDIR (CD/DVD), zip, JPG, PNG, BMP, TIFF ve PDF açar; PNG, JPG ve PDF "
                          "olarak dışa aktarır, orijinal DICOM'u kopyalar.<br><br>"
                          "İnternete bağlanmaz. Zip dosyaları geçici olarak açılır ve program kapanınca silinir.<br><br>"
                          "Bu program tıbbi tanı aracı değildir; tanı için hekiminize ve orijinal görüntülere başvurun.")

    # ---------------- sürükle-bırak ve kapanış ----------------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        yollar = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if yollar:
            self.yukle(yollar)

    def closeEvent(self, e):
        self.oynatici.stop()
        if self._is is not None:
            self._is.iptal_et()
            self._is.wait(3000)
        K.gecicileri_temizle(eskiler_de=False)
        super().closeEvent(e)


def modalite_tam(kod: str) -> str:
    return K.modalite_adi(kod)


def _klasoru_ac(klasor: str):
    try:
        os.startfile(klasor)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


def koyu_tema(app: QApplication):
    from PySide6.QtGui import QPalette

    app.setStyle("Fusion")
    p = QPalette()
    renkler = {
        QPalette.ColorRole.Window: QColor(37, 40, 45),
        QPalette.ColorRole.WindowText: QColor(225, 228, 232),
        QPalette.ColorRole.Base: QColor(26, 28, 32),
        QPalette.ColorRole.AlternateBase: QColor(33, 36, 40),
        QPalette.ColorRole.ToolTipBase: QColor(50, 54, 60),
        QPalette.ColorRole.ToolTipText: QColor(235, 235, 235),
        QPalette.ColorRole.Text: QColor(225, 228, 232),
        QPalette.ColorRole.Button: QColor(45, 49, 55),
        QPalette.ColorRole.ButtonText: QColor(225, 228, 232),
        QPalette.ColorRole.Highlight: QColor(42, 110, 187),
        QPalette.ColorRole.HighlightedText: QColor(255, 255, 255),
        QPalette.ColorRole.Link: QColor(111, 182, 255),
        QPalette.ColorRole.PlaceholderText: QColor(140, 145, 150),
    }
    for rol, renk in renkler.items():
        p.setColor(rol, renk)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(110, 114, 120))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(110, 114, 120))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(110, 114, 120))
    app.setPalette(p)
    app.setStyleSheet("QTextBrowser#bilgi{background:#1a1c20}")


def kaynak_yolu(goreli: str) -> str:
    taban = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(taban, goreli)


def calistir(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    sinama_klasoru = None
    if "--sinama-cikti" in argv:
        i = argv.index("--sinama-cikti")
        sinama_klasoru = argv[i + 1]
        del argv[i:i + 2]
    yollar = [a for a in argv[1:] if not a.startswith("-")]

    K.gecicileri_temizle(eskiler_de=True)
    app = QApplication(argv[:1])
    app.setApplicationName(AD)
    app.setApplicationDisplayName(AD)
    simge = kaynak_yolu(os.path.join("varliklar", "gor-bak.ico"))
    if os.path.isfile(simge):
        app.setWindowIcon(QIcon(simge))
    koyu_tema(app)
    pencere = AnaPencere()
    pencere.show()
    if sinama_klasoru:
        from .sinama import oz_sinama

        return oz_sinama(app, pencere, yollar, sinama_klasoru)
    if yollar:
        QTimer.singleShot(100, lambda: pencere.yukle(yollar))
    return app.exec()
