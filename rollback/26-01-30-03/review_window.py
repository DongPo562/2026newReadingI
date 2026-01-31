class ReviewToggleSwitch(ToggleSwitch):
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = app_config.review_toggle_colors
        track_color = QColor(colors['on']) if self._checked else QColor(colors['off'])
        p.setBrush(track_color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), self.height() / 2, self.height() / 2)
        p.setBrush(QColor(colors['knob']))
        p.drawEllipse(QPoint(int(self._thumb_pos + self._thumb_radius), int(self.height() / 2)),
            self._thumb_radius, self._thumb_radius)

class ReviewWindow(QWidget):
    def init(self, db_manager, parent=None):
        super().init(parent)
        self.db_manager = db_manager
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        stylesheet = StyleManager.load_stylesheet('review_window.qss')
        self.setStyleSheet(stylesheet)
        self.resize(app_config.review_window_width, app_config.review_window_height)
        pos = app_config.review_last_position
        if pos:
            self.move(pos[0], pos[1])
        else:
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen().geometry()
            self.move(screen.center() - self.rect().center())
        self.dragging = False
        self.drag_position = QPoint()
        self.words = self._load_words_to_review()
        self.current_index = 0
        self.loop_count = 1