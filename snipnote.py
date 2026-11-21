#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SnipNote - Windows 画面キャプチャ + その場で書き込み（注釈）ツール

  python snipnote.py              1回だけキャプチャして終了（ショートカット起動向け）
  python snipnote.py --tray       タスクトレイに常駐し、PrintScreen キーで起動
  python snipnote.py --tray --hotkey ctrl+shift+a   ホットキーを変更

操作:
  ドラッグ            範囲選択（クリックだけ → そのモニター全体）
  ツールバー / キー    S:選択移動  P:ペン  H:蛍光  L:直線  A:矢印  R:矩形
                      E:楕円  T:文字  N:番号  M:モザイク
  Ctrl+Z / Ctrl+Y     元に戻す / やり直し
  Enter または Ctrl+C クリップボードへコピーして閉じる
  Ctrl+S              PNG保存(＋コピー)して閉じる
  Ctrl+Shift+S        保存先を指定して保存
  Esc / 右クリック    キャンセル
"""
import sys
import os
import datetime
import argparse

os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")

from PyQt5.QtCore import (Qt, QRect, QPoint, QPointF, QRectF, QLineF, QTimer,
                          QAbstractNativeEventFilter, pyqtSignal)
from PyQt5.QtGui import (QPixmap, QPainter, QPen, QColor, QBrush, QFont,
                         QGuiApplication, QIcon, QPainterPath, QPolygonF,
                         QFontMetrics, QRegion)
import updater
from PyQt5.QtWidgets import (QApplication, QWidget, QToolButton, QHBoxLayout,
                             QLineEdit, QFileDialog, QSystemTrayIcon, QMenu,
                             QAction, QSlider, QFrame, QButtonGroup, QLabel, QGridLayout)

APP_NAME = "SnipNote"
__version__ = "1.1.0"
DEFAULT_HOTKEY = "printscreen"

TOOLS = [  # (id, ラベル, ツールチップ, キー)
    ("select", "選択", "範囲の選択・移動 (S)", Qt.Key_S),
    ("pen", "ペン", "フリーハンド (P)", Qt.Key_P),
    ("highlight", "蛍光", "マーカー (H)", Qt.Key_H),
    ("line", "直線", "直線 (L)", Qt.Key_L),
    ("arrow", "矢印", "矢印 (A)", Qt.Key_A),
    ("rect", "矩形", "四角 (R)", Qt.Key_R),
    ("ellipse", "楕円", "楕円 (E)", Qt.Key_E),
    ("text", "文字", "テキスト (T)", Qt.Key_T),
    ("number", "番号", "連番バッジ (N)", Qt.Key_N),
    ("mosaic", "モザイク", "モザイク・個人情報隠し (M)", Qt.Key_M),
]
COLORS = ["#ff3b30", "#ff9500", "#ffd60a", "#34c759",
          "#007aff", "#af52de", "#000000", "#ffffff"]


# ----------------------------------------------------------------------------
# 図形データと描画
# ----------------------------------------------------------------------------
class Shape:
    def __init__(self, kind, color, width, pts=None, text=None, number=None):
        self.kind = kind
        self.color = QColor(color)
        self.width = width
        self.pts = pts or []
        self.text = text
        self.number = number


def _arrow_head(p1, p2, size):
    line = QLineF(QPointF(p1), QPointF(p2))
    if line.length() == 0:
        return None
    base = line.pointAt(max(0.0, 1 - size / line.length()))
    n = line.normalVector().unitVector()
    dx, dy = (n.dx() * size * 0.45, n.dy() * size * 0.45)
    return QPolygonF([QPointF(p2), base + QPointF(dx, dy), base - QPointF(dx, dy)])


def draw_shape(p, s, base):
    """painter p の座標系はスクリーンショット座標。base は元画像(モザイク用)。"""
    if not s.pts:
        return
    p.save()
    pen = QPen(s.color, s.width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    k = s.kind

    if k == "pen":
        path = QPainterPath(QPointF(s.pts[0]))
        for q in s.pts[1:]:
            path.lineTo(QPointF(q))
        p.drawPath(path)

    elif k == "highlight":
        c = QColor(s.color)
        c.setAlpha(110)
        p.setPen(QPen(c, s.width * 4, Qt.SolidLine, Qt.FlatCap, Qt.RoundJoin))
        p.setCompositionMode(QPainter.CompositionMode_Multiply)
        path = QPainterPath(QPointF(s.pts[0]))
        for q in s.pts[1:]:
            path.lineTo(QPointF(q))
        p.drawPath(path)

    elif k in ("line", "arrow") and len(s.pts) >= 2:
        a, b = s.pts[0], s.pts[-1]
        p.drawLine(a, b)
        if k == "arrow":
            head = _arrow_head(a, b, 12 + s.width * 3)
            if head:
                p.setBrush(QBrush(s.color))
                p.drawPolygon(head)

    elif k in ("rect", "ellipse") and len(s.pts) >= 2:
        r = QRect(s.pts[0], s.pts[-1]).normalized()
        if k == "rect":
            p.drawRect(r)
        else:
            p.drawEllipse(r)

    elif k == "mosaic" and len(s.pts) >= 2:
        r = QRect(s.pts[0], s.pts[-1]).normalized().intersected(base.rect())
        if r.width() > 1 and r.height() > 1:
            block = 6 + s.width * 2
            src = base.copy(r)
            small = src.scaled(max(1, r.width() // block), max(1, r.height() // block),
                               Qt.IgnoreAspectRatio, Qt.FastTransformation)
            p.setRenderHint(QPainter.SmoothPixmapTransform, False)
            p.drawPixmap(r, small.scaled(r.size(), Qt.IgnoreAspectRatio, Qt.FastTransformation))

    elif k == "text" and s.text:
        f = text_font(s.width)
        p.setFont(f)
        # 読みやすさのため白い縁取り
        path = QPainterPath()
        path.addText(QPointF(s.pts[0]), f, s.text)
        p.setPen(QPen(QColor(255, 255, 255, 200), 3))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(s.color))
        p.drawPath(path)

    elif k == "number":
        r = 10 + s.width * 2
        c = QPointF(s.pts[0])
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.setBrush(QBrush(s.color))
        p.drawEllipse(c, r, r)
        f = QFont()
        f.setBold(True)
        f.setPixelSize(int(r * 1.2))
        p.setFont(f)
        p.setPen(QColor(255, 255, 255) if s.color.lightness() < 160 else QColor(0, 0, 0))
        p.drawText(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), Qt.AlignCenter, str(s.number))

    p.restore()


def text_font(width):
    f = QFont()
    f.setBold(True)
    f.setPixelSize(14 + width * 4)
    return f


def rect_between(a, b):
    """2点を対角とする矩形（QRect(a, b) と違い、幅=|dx| になる）"""
    x1, x2 = sorted((a.x(), b.x()))
    y1, y2 = sorted((a.y(), b.y()))
    return QRect(x1, y1, x2 - x1, y2 - y1)


# ----------------------------------------------------------------------------
# スクリーンショット（全モニター）
# ----------------------------------------------------------------------------
def grab_virtual_desktop():
    screens = QGuiApplication.screens()
    vg = QRect()
    for s in screens:
        vg = vg.united(s.geometry())
    canvas = QPixmap(vg.size())
    canvas.fill(Qt.black)
    p = QPainter(canvas)
    for s in screens:
        pm = s.grabWindow(0)
        g = s.geometry()
        if pm.size() != g.size():  # DPI差などでサイズが違う場合は合わせる
            pm = pm.scaled(g.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        p.drawPixmap(g.topLeft() - vg.topLeft(), pm)
    p.end()
    return canvas, vg


# ----------------------------------------------------------------------------
# UI部品
# ----------------------------------------------------------------------------
class TextInput(QLineEdit):
    committed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, parent, color, width):
        super().__init__(parent)
        self.setFont(text_font(width))
        self.apply_color(QColor(color))
        self.setMinimumWidth(160)
        self.returnPressed.connect(lambda: self.committed.emit(self.text()))

    def apply_color(self, color):
        self.setStyleSheet(
            "QLineEdit{background:rgba(255,255,255,200);color:%s;border:1px dashed #666;padding:2px;}"
            % color.name())

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.cancelled.emit()
            return
        super().keyPressEvent(e)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        if self.isVisible():
            self.committed.emit(self.text())


class Toolbar(QFrame):
    def __init__(self, overlay):
        super().__init__(overlay)
        self.ov = overlay
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame{background:#2b2b2b;border:1px solid #555;border-radius:6px;}
            QToolButton{color:#eee;background:transparent;border:1px solid transparent;
                        border-radius:4px;padding:4px 7px;font-size:12px;}
            QToolButton:hover{background:#444;}
            QToolButton:checked{background:#0a84ff;color:white;}
            QToolButton#color{min-width:18px;max-width:18px;min-height:18px;max-height:18px;
                              padding:0;border:2px solid #2b2b2b;border-radius:9px;}
            QToolButton#color:checked{border:2px solid white;}
            QLabel{color:#ccc;font-size:11px;}
        """)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(6, 4, 6, 4)
        self.grid.setHorizontalSpacing(3)
        self.grid.setVerticalSpacing(4)
        self.row1, self.row2, self.row3 = [], [], []   # 画面幅が足りない時は2〜3段にする

        self.tool_group = QButtonGroup(self)
        self.tool_btns = {}
        for tid, label, tip, _ in TOOLS:
            b = QToolButton(self)
            b.setText(label)
            b.setToolTip(tip)
            b.setCheckable(True)
            b.clicked.connect(lambda _c, t=tid: self.ov.set_tool(t))
            self.tool_group.addButton(b)
            self.tool_btns[tid] = b
            self.row1.append(b)

        self.row2.append(self._sep())
        self.color_group = QButtonGroup(self)
        self.color_btns = {}
        for c in COLORS:
            b = QToolButton(self)
            b.setObjectName("color")
            b.setCheckable(True)
            b.setToolTip(c)
            b.setStyleSheet("QToolButton#color{background:%s;}" % c)
            b.clicked.connect(lambda _c, col=c: self.ov.set_color(col))
            self.color_group.addButton(b)
            self.color_btns[c] = b
            self.row2.append(b)

        self.row2.append(self._sep())
        self.slider = QSlider(Qt.Horizontal, self)
        self.slider.setRange(1, 12)
        self.slider.setFixedWidth(70)
        self.slider.setToolTip("線の太さ / 文字サイズ")
        self.slider.valueChanged.connect(self.ov.set_width)
        self.row2.append(self.slider)

        self.row3.append(self._sep())
        for text, tip, cb in [
            ("↶", "元に戻す (Ctrl+Z)", self.ov.undo),
            ("↷", "やり直し (Ctrl+Y)", self.ov.redo_),
            ("コピー", "クリップボードへコピーして閉じる (Enter / Ctrl+C)", lambda: self.ov.finish(copy=True)),
            ("保存", "PNG保存して閉じる (Ctrl+S)", lambda: self.ov.finish(copy=True, save=True)),
            ("✕", "キャンセル (Esc)", self.ov.cancel),
        ]:
            b = QToolButton(self)
            b.setText(text)
            b.setToolTip(tip)
            b.clicked.connect(cb)
            self.row3.append(b)

        self.rows = 0
        self.set_rows(1)
        self.adjustSize()
        self.hide()

    def set_rows(self, n):
        if n == self.rows:
            return
        self.rows = n
        groups = [self.row1, self.row2, self.row3]
        for g in groups:
            for w in g:
                self.grid.removeWidget(w)
                w.hide()
        if n == 1:
            lines = [self.row1 + self.row2 + self.row3]
        elif n == 2:
            lines = [self.row1, self.row2 + self.row3]
        else:
            lines = [self.row1, self.row2, self.row3]
        for r, line in enumerate(lines):
            col = 0
            for i, w in enumerate(line):
                if i == 0 and isinstance(w, QFrame) and w.frameShape() == QFrame.VLine:
                    continue  # 行頭の区切り線は表示しない
                self.grid.addWidget(w, r, col)
                w.show()
                col += 1
        self.grid.activate()
        self.adjustSize()

    def _sep(self):
        f = QFrame(self)
        f.setFrameShape(QFrame.VLine)
        f.setStyleSheet("color:#555;")
        return f

    def sync(self):
        self.tool_btns[self.ov.tool].setChecked(True)
        b = self.color_btns.get(self.ov.color.name())
        if b:
            b.setChecked(True)
        self.slider.blockSignals(True)
        self.slider.setValue(self.ov.width)
        self.slider.blockSignals(False)

    def place(self, sel, bounds):
        for n in (1, 2, 3):
            self.set_rows(n)
            if self.sizeHint().width() + 8 <= bounds.width():
                break
        self.adjustSize()
        w, h = self.width(), self.height()
        x = sel.center().x() - w // 2
        x = max(bounds.left() + 4, min(x, bounds.right() - w - 4))
        if sel.bottom() + 8 + h <= bounds.bottom():
            y = sel.bottom() + 8
        elif sel.top() - 8 - h >= bounds.top():
            y = sel.top() - 8 - h
        else:
            y = sel.bottom() - h - 8
        self.move(x, y)


# ----------------------------------------------------------------------------
# オーバーレイ（全画面に半透明で被せ、その上で選択・描画）
# ----------------------------------------------------------------------------
class Overlay(QWidget):
    def __init__(self, shot, vgeo, save_dir, on_done):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setGeometry(vgeo)
        self.vgeo = vgeo
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.setFocusPolicy(Qt.StrongFocus)

        self.shot = shot
        self.save_dir = save_dir
        self.on_done = on_done

        self.phase = "select"           # select -> edit
        self.sel = QRect()
        self.origin = None
        self.move_origin = None
        self.move_start_sel = None

        self.shapes = []
        self.redo_stack = []
        self.cur = None
        self.tool = "pen"
        self.color = QColor(COLORS[0])
        self.width_ = 3
        self.counter = 1
        self.text_input = None
        self.mouse_pos = QPoint(-1, -1)

        self.toolbar = Toolbar(self)
        self.toolbar.sync()

    # ---- 設定 ----
    def set_tool(self, t):
        self.commit_text()
        self.tool = t
        self.setCursor(Qt.ArrowCursor if t == "select" else Qt.CrossCursor)
        self.toolbar.sync()

    def set_color(self, c):
        self.color = QColor(c)
        if self.text_input:
            self.text_input.apply_color(self.color)
        self.toolbar.sync()

    def set_width(self, w):
        self.width_ = int(w)

    @property
    def width(self):
        return self.width_

    # ---- 編集操作 ----
    def undo(self):
        self.commit_text()
        if self.shapes:
            s = self.shapes.pop()
            self.redo_stack.append(s)
            if s.kind == "number":
                self.counter = max(1, self.counter - 1)
            self.update()

    def redo_(self):
        if self.redo_stack:
            s = self.redo_stack.pop()
            self.shapes.append(s)
            if s.kind == "number":
                self.counter += 1
            self.update()

    def add_shape(self, s):
        self.shapes.append(s)
        self.redo_stack.clear()
        self.update()

    # ---- テキスト入力 ----
    def begin_text(self, pos):
        self.commit_text()
        ti = TextInput(self, self.color, self.width_)
        fm = QFontMetrics(ti.font())
        ti.move(pos.x(), pos.y() - fm.ascent() - 3)
        ti.show()
        ti.setFocus()
        anchor = QPoint(pos)
        ti.committed.connect(lambda t, a=anchor: self._text_done(t, a))
        ti.cancelled.connect(self._text_cancel)
        self.text_input = ti

    def _text_done(self, text, anchor):
        ti, self.text_input = self.text_input, None
        if ti:
            ti.hide()
            ti.deleteLater()
        if text.strip():
            self.add_shape(Shape("text", self.color, self.width_, [anchor], text=text))
        self.setFocus()

    def _text_cancel(self):
        ti, self.text_input = self.text_input, None
        if ti:
            ti.hide()
            ti.deleteLater()
        self.setFocus()

    def commit_text(self):
        if self.text_input:
            self.text_input.committed.emit(self.text_input.text())

    # ---- マウス ----
    def mousePressEvent(self, e):
        pos = e.pos()
        if e.button() == Qt.RightButton:
            self.cancel()
            return
        if e.button() != Qt.LeftButton:
            return
        if self.text_input:
            self.commit_text()
            return

        if self.phase == "select" or (self.tool == "select" and not self.sel.contains(pos)):
            self.phase = "select"
            self.toolbar.hide()
            self.origin = pos
            self.sel = QRect(pos, pos)
            self.update()
            return

        if self.tool == "select":
            self.move_origin = pos
            self.move_start_sel = QRect(self.sel)
            return

        if not self.sel.contains(pos):
            return

        if self.tool == "text":
            self.begin_text(pos)
        elif self.tool == "number":
            self.add_shape(Shape("number", self.color, self.width_, [pos], number=self.counter))
            self.counter += 1
        else:
            self.cur = Shape(self.tool, self.color, self.width_, [pos])
        self.update()

    def mouseMoveEvent(self, e):
        pos = e.pos()
        self.mouse_pos = pos
        if self.origin is not None:
            self.sel = rect_between(self.origin, pos)
        elif self.move_origin is not None:
            d = pos - self.move_origin
            r = self.move_start_sel.translated(d)
            # 画面外へ出ないよう制限
            r.moveLeft(max(0, min(r.left(), self.width_px() - r.width())))
            r.moveTop(max(0, min(r.top(), self.height_px() - r.height())))
            self.sel = r
        elif self.cur is not None:
            if self.cur.kind in ("pen", "highlight"):
                self.cur.pts.append(pos)
            else:
                if len(self.cur.pts) == 1:
                    self.cur.pts.append(pos)
                else:
                    self.cur.pts[-1] = pos
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        pos = e.pos()
        if self.origin is not None:
            self.origin = None
            if self.sel.width() < 4 or self.sel.height() < 4:
                # クリックのみ: そのモニター全体を選択
                scr = QGuiApplication.screenAt(pos + self.vgeo.topLeft())
                g = scr.geometry() if scr else self.vgeo
                self.sel = g.translated(-self.vgeo.topLeft())
            self.phase = "edit"
            if self.tool == "select":
                self.set_tool("pen")
            self.toolbar.place(self.sel, self.rect())
            self.toolbar.show()
            self.toolbar.raise_()
        elif self.move_origin is not None:
            self.move_origin = None
            self.toolbar.place(self.sel, self.rect())
        elif self.cur is not None:
            s, self.cur = self.cur, None
            if len(s.pts) >= 2 or s.kind in ("pen", "highlight"):
                if len(s.pts) == 1:
                    s.pts.append(s.pts[0] + QPoint(1, 0))
                self.add_shape(s)
        self.update()

    def mouseDoubleClickEvent(self, e):
        if self.phase == "edit" and self.tool == "select" and self.sel.contains(e.pos()):
            self.finish(copy=True)

    def width_px(self):
        return self.rect().width()

    def height_px(self):
        return self.rect().height()

    # ---- キー ----
    def keyPressEvent(self, e):
        k, m = e.key(), e.modifiers()
        ctrl = bool(m & Qt.ControlModifier)
        shift = bool(m & Qt.ShiftModifier)
        if k == Qt.Key_Escape:
            self.cancel()
        elif k in (Qt.Key_Return, Qt.Key_Enter):
            if self.phase == "edit":
                self.finish(copy=True)
        elif ctrl and k == Qt.Key_C and self.phase == "edit":
            self.finish(copy=True)
        elif ctrl and k == Qt.Key_S and self.phase == "edit":
            self.finish(copy=True, save=True, ask_path=shift)
        elif ctrl and k == Qt.Key_Z:
            self.redo_() if shift else self.undo()
        elif ctrl and k == Qt.Key_Y:
            self.redo_()
        elif not ctrl and self.phase == "edit":
            for tid, _, _, key in TOOLS:
                if k == key:
                    self.set_tool(tid)
                    break
        else:
            super().keyPressEvent(e)

    # ---- 描画 ----
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.drawPixmap(0, 0, self.shot)

        # 選択外を暗くする
        dim = QRegion(self.rect())
        if not self.sel.isNull():
            dim = dim.subtracted(QRegion(self.sel))
        p.save()
        p.setClipRegion(dim)
        p.fillRect(self.rect(), QColor(0, 0, 0, 120))
        p.restore()

        # 図形（選択範囲内にクリップ）
        if not self.sel.isNull():
            p.save()
            p.setClipRect(self.sel)
            for s in self.shapes:
                draw_shape(p, s, self.shot)
            if self.cur:
                draw_shape(p, self.cur, self.shot)
            p.restore()

            # 選択枠とサイズ表示
            p.setPen(QPen(QColor("#0a84ff"), 1, Qt.SolidLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(self.sel.adjusted(0, 0, -1, -1))
            label = "%d × %d" % (self.sel.width(), self.sel.height())
            f = QFont()
            f.setPixelSize(12)
            p.setFont(f)
            fm = QFontMetrics(f)
            tw = fm.horizontalAdvance(label) + 10
            ty = self.sel.top() - 22 if self.sel.top() >= 24 else self.sel.top() + 4
            tx = max(0, min(self.sel.left(), self.width_px() - tw))
            p.fillRect(QRect(tx, ty, tw, 18), QColor(0, 0, 0, 170))
            p.setPen(Qt.white)
            p.drawText(QRect(tx, ty, tw, 18), Qt.AlignCenter, label)
        elif self.phase == "select" and self.mouse_pos.x() >= 0:
            # 選択前は十字ガイド
            p.setPen(QPen(QColor(255, 255, 255, 120), 1, Qt.DashLine))
            p.drawLine(self.mouse_pos.x(), 0, self.mouse_pos.x(), self.height_px())
            p.drawLine(0, self.mouse_pos.y(), self.width_px(), self.mouse_pos.y())
            p.setPen(Qt.white)
            p.fillRect(QRect(20, 20, 420, 26), QColor(0, 0, 0, 160))
            p.drawText(QRect(20, 20, 420, 26), Qt.AlignCenter,
                       "ドラッグで範囲選択 / クリックで画面全体 / Esc でキャンセル")
        p.end()

    # ---- 出力 ----
    def render_result(self):
        out = self.shot.copy(self.sel)
        p = QPainter(out)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(-self.sel.topLeft())
        p.setClipRect(self.sel)
        for s in self.shapes:
            draw_shape(p, s, self.shot)
        p.end()
        return out

    def default_path(self):
        os.makedirs(self.save_dir, exist_ok=True)
        name = datetime.datetime.now().strftime("snip_%Y%m%d_%H%M%S.png")
        return os.path.join(self.save_dir, name)

    def finish(self, copy=True, save=False, ask_path=False):
        self.commit_text()
        if self.sel.isNull() or self.sel.width() < 1 or self.sel.height() < 1:
            return
        out = self.render_result()
        path = None
        if save:
            path = self.default_path()
            if ask_path:
                self.toolbar.hide()
                path, _ = QFileDialog.getSaveFileName(self, "保存", path, "PNG (*.png);;JPEG (*.jpg)")
                if not path:
                    self.toolbar.show()
                    return
            out.save(path)
        if copy:
            QApplication.clipboard().setPixmap(out)
        self.hide()
        self.on_done(path, copy)
        self.close()

    def cancel(self):
        if self.text_input:
            self._text_cancel()
            return
        self.hide()
        self.on_done(None, False)
        self.close()


# ----------------------------------------------------------------------------
# Windows グローバルホットキー
# ----------------------------------------------------------------------------
MODS = {"ctrl": 0x0002, "control": 0x0002, "alt": 0x0001, "shift": 0x0004, "win": 0x0008}
VKS = {"printscreen": 0x2C, "prtsc": 0x2C, "space": 0x20, "insert": 0x2D}
for _i in range(1, 13):
    VKS["f%d" % _i] = 0x6F + _i


def parse_hotkey(text):
    mods, vk = 0x4000, None  # MOD_NOREPEAT
    for part in text.lower().replace(" ", "").split("+"):
        if part in MODS:
            mods |= MODS[part]
        elif part in VKS:
            vk = VKS[part]
        elif len(part) == 1 and part.isalnum():
            vk = ord(part.upper())
        else:
            raise ValueError("不明なキー: %s" % part)
    if vk is None:
        raise ValueError("キーが指定されていません: %s" % text)
    return mods, vk


class HotkeyFilter(QAbstractNativeEventFilter):
    """RegisterHotKey 方式: WM_HOTKEY を受け取る"""
    WM_HOTKEY = 0x0312

    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, event_type, message):
        if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            import ctypes.wintypes
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == self.WM_HOTKEY:
                QTimer.singleShot(0, self.callback)
                return True, 0
        return False, 0


class Hotkey:
    """
    グローバルホットキー。
    1) RegisterHotKey を試す
    2) 失敗（Snipping Tool 等が PrtSc を先取りしている）なら
       低レベルキーボードフック (WH_KEYBOARD_LL) で同じキーを横取りする
    """

    def __init__(self, app, hotkey_text, callback):
        import ctypes
        import ctypes.wintypes as wt
        self.app = app
        self.callback = callback
        self.mods, self.vk = parse_hotkey(hotkey_text)
        self.method = None
        self.hook = None
        self.user32 = ctypes.windll.user32
        self.ctypes, self.wt = ctypes, wt

        self.filter = HotkeyFilter(callback)
        app.installNativeEventFilter(self.filter)
        if self.user32.RegisterHotKey(None, 1, self.mods, self.vk):
            self.method = "RegisterHotKey"
            return
        self._install_hook()

    def _install_hook(self):
        ctypes, wt = self.ctypes, self.wt
        WH_KEYBOARD_LL = 13
        WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
        LRESULT = ctypes.c_ssize_t
        HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)

        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                        ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_void_p)]

        u = self.user32
        u.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
        u.SetWindowsHookExW.restype = wt.HHOOK
        u.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
        u.CallNextHookEx.restype = LRESULT
        u.UnhookWindowsHookEx.argtypes = [wt.HHOOK]
        u.GetAsyncKeyState.argtypes = [ctypes.c_int]
        u.GetAsyncKeyState.restype = ctypes.c_short

        need_ctrl = bool(self.mods & 0x0002)
        need_alt = bool(self.mods & 0x0001)
        need_shift = bool(self.mods & 0x0004)
        need_win = bool(self.mods & 0x0008)

        def down(vk):
            return bool(u.GetAsyncKeyState(vk) & 0x8000)

        def proc(n_code, w_param, l_param):
            if n_code == 0 and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if kb.vkCode == self.vk:
                    if (down(0x11) == need_ctrl and down(0x12) == need_alt and
                            down(0x10) == need_shift and
                            (down(0x5B) or down(0x5C)) == need_win):
                        QTimer.singleShot(0, self.callback)
                        return 1  # 他アプリ(OneDrive等)へ渡さない
            return u.CallNextHookEx(self.hook, n_code, w_param, l_param)

        self._proc = HOOKPROC(proc)  # GC されないよう保持
        self.hook = u.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        if not self.hook:
            raise OSError("ホットキーを登録できません（RegisterHotKey もフックも失敗）")
        self.method = "KeyboardHook"

    def release(self):
        if self.method == "RegisterHotKey":
            self.user32.UnregisterHotKey(None, 1)
        elif self.hook:
            self.user32.UnhookWindowsHookEx(self.hook)
            self.hook = None


def windows_prtsc_snipping_enabled():
    """Windows の「PrintScreen で Snipping Tool を開く」設定が ON か"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Keyboard") as k:
            val, _ = winreg.QueryValueEx(k, "PrintScreenKeyForSnippingEnabled")
            return int(val) == 1
    except Exception:
        return False


# ----------------------------------------------------------------------------
# アプリ本体
# ----------------------------------------------------------------------------
def make_icon():
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#0a84ff"), 6))
    p.setBrush(QColor(255, 255, 255, 230))
    p.drawRoundedRect(8, 12, 48, 40, 6, 6)
    p.setPen(QPen(QColor("#ff3b30"), 6, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(18, 42, 46, 22)
    p.end()
    return QIcon(pm)


class SnipNote:
    def __init__(self, app, save_dir, tray=False, hotkey=DEFAULT_HOTKEY, auto_update=True):
        self.app = app
        self.save_dir = save_dir
        self.tray_mode = tray
        self.overlay = None
        self.tray = None
        self.hotkey = hotkey
        self.updater = updater.AutoUpdater(__version__, lambda: self.overlay is not None, parent=app)
        self.updater.status.connect(self._notify)
        self.updater.quit_requested.connect(self.app.quit)
        if tray:
            self._setup_tray()
            if auto_update:
                self.updater.start()

    def _notify(self, title, msg, warning):
        if self.tray:
            self.tray.showMessage(title, msg,
                                  QSystemTrayIcon.Warning if warning else QSystemTrayIcon.Information, 6000)

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(make_icon(), self.app)
        menu = QMenu()
        a = QAction("キャプチャ (%s)" % self.hotkey.upper(), menu)
        a.triggered.connect(self.capture)
        menu.addAction(a)
        b = QAction("保存フォルダを開く", menu)
        b.triggered.connect(lambda: os.startfile(self.save_dir) if hasattr(os, "startfile") else None)
        menu.addAction(b)
        menu.addSeparator()
        v = QAction("バージョン %s%s" % (__version__, "" if updater.is_frozen() else " (ソース実行)"), menu)
        v.setEnabled(False)
        menu.addAction(v)
        c = QAction("今すぐ更新を確認", menu)
        c.triggered.connect(lambda: self.updater.check(manual=True))
        menu.addAction(c)
        au = QAction("自動更新", menu)
        au.setCheckable(True)
        au.setChecked(self.updater.enabled)
        au.setEnabled(updater.is_frozen())
        au.toggled.connect(lambda on: setattr(self.updater, "enabled", on))
        menu.addAction(au)
        menu.addSeparator()
        q = QAction("終了", menu)
        q.triggered.connect(self.app.quit)
        menu.addAction(q)
        self.tray.setContextMenu(menu)
        self.tray.messageClicked.connect(self.updater.open_download_page)
        self.tray.setToolTip("%s - %s でキャプチャ" % (APP_NAME, self.hotkey.upper()))
        self.tray.activated.connect(lambda r: self.capture() if r == QSystemTrayIcon.Trigger else None)
        self.tray.show()
        if sys.platform == "win32":
            try:
                self.hk = Hotkey(self.app, self.hotkey, self.capture)
                self.app.aboutToQuit.connect(self.hk.release)
                self.tray.setToolTip("%s - %s でキャプチャ (%s)" % (APP_NAME, self.hotkey.upper(), self.hk.method))
            except Exception as ex:
                self.tray.showMessage(APP_NAME, str(ex), QSystemTrayIcon.Warning, 8000)
            if self.hotkey == "printscreen" and windows_prtsc_snipping_enabled():
                self.tray.showMessage(
                    APP_NAME,
                    "Windows の「PrintScreen キーで画面キャプチャを開く」が ON です。\n"
                    "Snipping Tool と競合する場合は 設定 > アクセシビリティ > キーボード で OFF にしてください。",
                    QSystemTrayIcon.Warning, 10000)

    def capture(self):
        if self.overlay is not None:
            return
        shot, vg = grab_virtual_desktop()
        self.overlay = Overlay(shot, vg, self.save_dir, self._done)
        self.overlay.destroyed.connect(self._cleared)
        self.overlay.show()
        self.overlay.raise_()
        self.overlay.activateWindow()
        self.overlay.setFocus()

    def _cleared(self):
        self.overlay = None

    def _done(self, path, copied):
        if self.tray:
            if path:
                self.tray.showMessage(APP_NAME, "保存しました: %s" % path, QSystemTrayIcon.Information, 3000)
            elif copied:
                self.tray.showMessage(APP_NAME, "クリップボードにコピーしました", QSystemTrayIcon.Information, 1500)
        if not self.tray_mode:
            # クリップボードへの受け渡しを完了させてから終了
            QTimer.singleShot(400, self.app.quit)
        else:
            self.updater.try_install()  # 更新待ちがあればここで実行


def main():
    ap = argparse.ArgumentParser(description="画面キャプチャ＋その場で注釈")
    ap.add_argument("--tray", action="store_true", help="タスクトレイに常駐してホットキー待機")
    ap.add_argument("--hotkey", default=DEFAULT_HOTKEY,
                    help="常駐時のホットキー (既定: printscreen。例: ctrl+shift+a, win+shift+f9)")
    ap.add_argument("--dir", default=os.path.join(os.path.expanduser("~"), "Pictures", "Screenshots"),
                    help="保存先フォルダ")
    ap.add_argument("--no-update", action="store_true", help="自動更新の確認を行わない")
    ap.add_argument("--version", action="version", version="%s %s" % (APP_NAME, __version__))
    args = ap.parse_args()

    QApplication.setAttribute(Qt.AA_DisableHighDpiScaling, True)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    app.setApplicationVersion(__version__)
    sn = SnipNote(app, args.dir, tray=args.tray, hotkey=args.hotkey, auto_update=not args.no_update)
    if not args.tray:
        QTimer.singleShot(50, sn.capture)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
