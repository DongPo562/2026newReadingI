"""
floating_ui.py - 主入口模块
包含: FloatingBall（悬浮球主窗口）

拆分后的模块依赖关系:
widgets.py → audio_player.py → ui_services.py → list_panel.py/review_window.py/word_game.py → floating_ui.py
"""

import sys
import time
import socket
from PyQt6.QtWidgets import QApplication, QWidget, QMenu
from PyQt6.QtCore import Qt, QPoint, QPropertyAnimation, QEasingCurve, QRect
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QLinearGradient, QPainterPath, QAction, QCursor
from config_loader import app_config
from db_manager import DatabaseManager
from audio_player import AudioPlayer
from ui_services import CommandServer, ConsistencyChecker
from list_panel import ListPanel
from word_game import WordGameWindow


class FloatingBall(QWidget):
    def __init__(self):
        super().__init__()
        start_t = time.time()
        print("[Startup] FloatingBall initializing...")
        self.db_manager = DatabaseManager()
        self.db_manager.init_db()
        self.consistency_checker = ConsistencyChecker(self.db_manager)
        self.consistency_checker.start()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.diameter = app_config.ui_ball_diameter
        self.setFixedSize(self.diameter, self.diameter)
        last_pos = app_config.ui_last_position
        if last_pos:
            self.move(last_pos[0], last_pos[1])
        else:
            screen_geo = QApplication.primaryScreen().geometry()
            self.move(screen_geo.width() - self.diameter - 50, (screen_geo.height() - self.diameter) // 2)
        self.dragging = False
        self.drag_position = QPoint()
        self.player = AudioPlayer()
        self.panel = ListPanel(self.player, self, self.db_manager)
        self.panel.game_requested.connect(self.open_game_window)
        self.anim = QPropertyAnimation(self.panel, b"geometry")
        self.anim.setDuration(app_config.ui_animation_duration)
        self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.game_window = None
        self.cmd_server = CommandServer()
        self.cmd_server.file_saved_signal.connect(self.panel.on_auto_play_signal)
        self.cmd_server.stop_playback_signal.connect(self.player.stop)
        self.cmd_server.start()
        print(f"[Startup] FloatingBall init done in {time.time() - start_t:.4f}s")

    def open_game_window(self, text):
        if self.game_window:
            self.game_window.close()
            self.game_window = None
        self.game_window = WordGameWindow(text, self)
        self.game_window.show()
        self.game_window.raise_()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, self.diameter, self.diameter)
        gradient.setColorAt(0.0, QColor("#66BB6A"))
        gradient.setColorAt(1.0, QColor("#43A047"))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, self.diameter, self.diameter)
        painter.setPen(QPen(QColor("white"), 2))
        path = QPainterPath()
        cx, cy = self.diameter / 2, self.diameter / 2
        s = self.diameter / 45.0
        path.moveTo(cx - 5*s, cy - 8*s)
        path.cubicTo(cx + 8*s, cy - 12*s, cx + 10*s, cy + 5*s, cx + 2*s, cy + 10*s)
        path.cubicTo(cx - 2*s, cy + 12*s, cx - 6*s, cy + 8*s, cx - 6*s, cy + 5*s)
        path.moveTo(cx - 2*s, cy - 4*s)
        path.cubicTo(cx + 3*s, cy - 4*s, cx + 4*s, cy + 2*s, cx + 1*s, cy + 4*s)
        painter.drawPath(path)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        self.raise_()

    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() & Qt.MouseButton.LeftButton:
            new_pos = event.globalPosition().toPoint() - self.drag_position
            self.move(new_pos)
            if self.panel.isVisible():
                self.update_panel_position()
            self.raise_()
            event.accept()

    def mouseReleaseEvent(self, event):
        if self.dragging:
            self.dragging = False
            app_config.ui_last_position = (self.x(), self.y())

    def enterEvent(self, event):
        if not self.dragging:
            self.expand_panel()
        super().enterEvent(event)

    def leaveEvent(self, event):
        cursor_pos = QCursor.pos()
        if self.panel.isVisible():
            if self.panel.is_menu_open:
                super().leaveEvent(event)
                return
            if not self.panel.geometry().contains(cursor_pos):
                self.collapse_panel()
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.player.toggle_playback()
            event.accept()
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        refresh_action = QAction("刷新列表", self)
        refresh_action.triggered.connect(lambda: self.panel.refresh_list(True))
        exit_action = QAction("退出程序", self)
        exit_action.triggered.connect(self.exit_application)
        menu.addAction(refresh_action)
        menu.addAction(exit_action)
        menu.exec(event.globalPos())

    def exit_application(self):
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect(('127.0.0.1', 65433))
            client.sendall(b"EXIT")
            client.close()
        except Exception as e:
            print(f"Failed to send exit signal to main app: {e}")
        QApplication.instance().quit()

    def expand_panel(self):
        if self.panel.isVisible():
            self.raise_()
            return
        target_width = app_config.ui_panel_width
        target_height = app_config.ui_panel_max_height
        ball_geo = self.geometry()
        target_x = ball_geo.x() + self.diameter - target_width
        target_y = ball_geo.y() + self.diameter - target_height
        start_rect = QRect(ball_geo.x(), ball_geo.y(), self.diameter, self.diameter)
        end_rect = QRect(target_x, target_y, target_width, target_height)
        self.panel.setGeometry(start_rect)
        self.panel.show()
        self.anim.setStartValue(start_rect)
        self.anim.setEndValue(end_rect)
        self.anim.start()
        self.raise_()

    def collapse_panel(self):
        if not self.panel.isVisible():
            return
        ball_geo = self.geometry()
        start_rect = self.panel.geometry()
        end_rect = QRect(ball_geo.x(), ball_geo.y(), self.diameter, self.diameter)
        self.anim.setStartValue(start_rect)
        self.anim.setEndValue(end_rect)
        self.anim.finished.connect(self._on_collapse_finished)
        self.anim.start()
        self.raise_()

    def _on_collapse_finished(self):
        self.panel.hide()
        try:
            self.anim.finished.disconnect(self._on_collapse_finished)
        except:
            pass
        self.raise_()

    def update_panel_position(self):
        if self.panel.isVisible():
            target_width = self.panel.width()
            target_height = self.panel.height()
            ball_geo = self.geometry()
            target_x = ball_geo.x() + self.diameter - target_width
            target_y = ball_geo.y() + self.diameter - target_height
            self.panel.move(target_x, target_y)
            self.raise_()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FloatingBall()
    window.show()
    sys.exit(app.exec())