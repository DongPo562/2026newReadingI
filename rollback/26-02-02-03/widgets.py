"""
widgets.py - 基础UI组件
包含: ToggleSwitch, ClickableLabel
"""

from PyQt6.QtWidgets import QWidget, QLabel
from PyQt6.QtCore import Qt, QPoint, QPropertyAnimation, QEasingCurve, pyqtSignal, pyqtProperty
from PyQt6.QtGui import QPainter, QColor
from config_loader import app_config

class ToggleSwitch(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, parent=None, width=50, height=26):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._checked = False
        self._thumb_radius = height // 2 - 2
        self._thumb_pos = 2.0
        self._anim = QPropertyAnimation(self, b"thumb_pos", self)
        self._anim.setDuration(250)
        self._anim.setEasingCurve(QEasingCurve.Type.OutQuad)

    @pyqtProperty(float)
    def thumb_pos(self):
        return self._thumb_pos

    @thumb_pos.setter
    def thumb_pos(self, pos):
        self._thumb_pos = pos
        self.update()

    def setChecked(self, checked):
        if self._checked != checked:
            self._checked = checked
            self.toggled.emit(checked)
        target = self.width() - self._thumb_radius * 2 - 2 if self._checked else 2.0
        if abs(self._thumb_pos - target) > 0.1:
            self._anim.stop()
            self._anim.setStartValue(self._thumb_pos)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self.update()

    def isChecked(self):
        return self._checked

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track_opacity = 0.9 if self._checked else 0.5
        track_color = QColor(app_config.ui_play_button_color) if self._checked else QColor("#757575")
        p.setBrush(track_color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), self.height() / 2, self.height() / 2)
        p.setBrush(QColor("white"))
        p.drawEllipse(QPoint(int(self._thumb_pos + self._thumb_radius), int(self.height() / 2)), 
            self._thumb_radius, self._thumb_radius)

class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)