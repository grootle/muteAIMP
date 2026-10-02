import sys
import threading
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSlider,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .core import monitor_thread_main
from .utils import APP_NAME, get_state, stop_event, store

SVG_PATH = Path(__file__).resolve().parent.parent / 'MuteAIMP.svg'

ORANGE = '#F57C00'
ORANGE_HOVER = '#FF8A1F'
ORANGE_DARK = '#D96500'
THEME = f"""
QWidget {{
    font-family: 'Segoe UI';
    color: #EEF1F4;
    font-size: 10pt;
}}
QWidget#surface {{
    background: #11151A;
}}
QFrame#card {{
    background: #191F26;
    border: 1px solid #2A323B;
    border-radius: 16px;
}}
QLabel#title {{
    font-size: 19px;
    font-weight: 700;
}}
QLabel#subtitle, QLabel#muted {{
    color: #9AA4AE;
}}
QLabel#section {{
    color: #89939E;
    font-size: 9px;
    font-weight: 700;
}}
QLabel#state {{
    font-size: 20px;
    font-weight: 700;
}}
QLabel#pill {{
    background: #3A2617;
    color: #FFB66F;
    border: 1px solid #6A4323;
    border-radius: 9px;
    padding: 4px 8px;
    font-size: 9px;
    font-weight: 700;
}}
QPushButton {{
    background: #252D36;
    border: 1px solid #303A45;
    border-radius: 11px;
    padding: 8px 11px;
}}
QPushButton:hover {{ background: #2D3742; }}
QPushButton#primary {{
    background: {ORANGE};
    border: 1px solid {ORANGE};
    color: white;
    font-weight: 700;
}}
QPushButton#primary:hover {{ background: {ORANGE_HOVER}; }}
QLineEdit, QComboBox {{
    background: #151A20;
    border: 1px solid #303943;
    border-radius: 9px;
    padding: 7px 9px;
}}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {ORANGE}; }}
QSlider::groove:horizontal {{
    height: 5px;
    background: #303943;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ORANGE};
    width: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}
QCheckBox::indicator {{ width: 18px; height: 18px; }}
QCheckBox::indicator:unchecked {{
    border: 1px solid #59636E;
    border-radius: 6px;
    background: #171C22;
}}
QCheckBox::indicator:checked {{
    border: 1px solid {ORANGE};
    border-radius: 6px;
    background: {ORANGE};
}}
QListWidget {{
    background: #151A20;
    border: 1px solid #303943;
    border-radius: 10px;
    padding: 4px;
}}
QListWidget::item {{ padding: 7px; border-radius: 7px; }}
QListWidget::item:selected {{ background: #3A2617; color: #FFD0A7; }}
QTabWidget::pane {{ border: 0; }}
QTabBar::tab {{
    padding: 9px 14px;
    color: #9AA4AE;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: #FFB66F;
    border-bottom: 2px solid {ORANGE};
}}
"""


def clamp(value, low, high):
    return max(low, min(high, value))


def load_svg_icon(svg_path):
    """Load and render an SVG into a multi-size QIcon"""

    svg_path = Path(svg_path)

    # Check whether the file exists
    if not svg_path.is_file():
        raise FileNotFoundError(
            f'SVG file not found: {svg_path}'
        )

    # Read SVG contents explicitly.
    svg_data = QByteArray(svg_path.read_bytes())

    renderer = QSvgRenderer(svg_data)

    if not renderer.isValid():
        raise ValueError(
            f'Qt could not parse SVG: {svg_path}\n'
            'Try the simplified SVG format'
        )

    icon = QIcon()

    # Render several sizes for different display contexts.
    for size in (16, 20, 24, 32, 48, 64, 128):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform
        )

        renderer.render(
            painter,
            QRectF(0, 0, size, size)
        )

        painter.end()

        icon.addPixmap(pixmap)

    return icon


class ToggleSwitch(QCheckBox):
    def __init__(self, checked=False, parent=None):
        super().__init__(parent)

        self.setText('')
        self.setTristate(False)
        self.setChecked(checked)
        self.setFixedSize(52, 30)

        self.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.setFocusPolicy(
            Qt.FocusPolicy.StrongFocus
        )

        self.setAccessibleName('Automatic monitoring')
        self.setToolTip('Enable or disable automatic monitoring')

        self.accent_color = QColor(ORANGE)

    def sizeHint(self):
        return QSize(52, 30)

    def hitButton(self, pos):
        # Make the whole switch clickable
        return self.rect().contains(pos)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing,
            True
        )

        # Track
        track = QRectF(1, 3, 50, 24)

        if not self.isEnabled():
            track_color = QColor('#ADB3BB')
            thumb_color = QColor('#E6E8EB')
        elif self.isChecked():
            track_color = QColor(self.accent_color)
            thumb_color = QColor('#FFFFFF')
        else:
            track_color = QColor('#89919B')
            thumb_color = QColor('#FFFFFF')

        # Slightly brighten the track on hover
        if self.underMouse() and self.isEnabled():
            if self.isChecked():
                track_color = track_color.lighter(108)
            else:
                track_color = track_color.lighter(112)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track, 12, 12)

        # Thumb
        diameter = 18
        thumb_y = (self.height() - diameter) / 2

        if self.isChecked():
            thumb_x = self.width() - diameter - 5
        else:
            thumb_x = 5

        thumb = QRectF(
            thumb_x,
            thumb_y,
            diameter,
            diameter,
        )

        painter.setBrush(thumb_color)
        painter.drawEllipse(thumb)

        # Keyboard-focus indicator
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(
                QPen(
                    self.accent_color,
                    1.5
                )
            )
            painter.drawRoundedRect(
                QRectF(0.5, 2.5, 51, 25),
                13,
                13
            )

        painter.end()

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)


class TrayFlyout(QWidget):
    WIDTH = 390
    HEIGHT = 300

    def __init__(self, app_controller):
        super().__init__(
            None,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        self.controller = app_controller
        self.setObjectName('surface')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(self.WIDTH, self.HEIGHT)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        self.panel = QFrame()
        self.panel.setObjectName('card')
        root.addWidget(self.panel)

        content = QVBoxLayout(self.panel)
        content.setContentsMargins(18, 17, 18, 15)
        content.setSpacing(10)

        monitor_card = QFrame()
        monitor_card.setObjectName('card')
        ml = QHBoxLayout(monitor_card)
        ml.setContentsMargins(14, 12, 12, 12)
        monitor_text = QVBoxLayout()
        monitor_text.setSpacing(3)
        h = QLabel('Automatic monitoring')
        h.setFont(QFont('Segoe UI', 11, QFont.Weight.Bold))
        self.monitor_desc = QLabel('Pause AIMP when another app becomes active')
        self.monitor_desc.setObjectName('muted')
        self.monitor_desc.setWordWrap(True)
        monitor_text.addWidget(h)
        monitor_text.addWidget(self.monitor_desc)
        self.monitor_switch = ToggleSwitch(store.snapshot().enabled)
        self.monitor_switch.toggled.connect(self.on_monitor_toggle)
        ml.addLayout(monitor_text, 1)
        ml.addWidget(self.monitor_switch)
        content.addWidget(monitor_card)

        external_card = QFrame()
        external_card.setObjectName('card')
        el = QVBoxLayout(external_card)
        el.setContentsMargins(14, 10, 14, 10)
        sec2 = QLabel('ACTIVE EXTERNAL SOURCES')
        sec2.setObjectName('section')
        self.external_label = QLabel('None')
        self.external_label.setObjectName('muted')
        self.external_label.setWordWrap(True)
        self.external_label.setMaximumHeight(62)
        el.addWidget(sec2)
        el.addWidget(self.external_label)
        content.addWidget(external_card)

        status = QHBoxLayout()
        self.status_label = QLabel('Starting...')
        self.status_label.setObjectName('muted')
        status.addWidget(self.status_label, 1)
        content.addLayout(status)

        footer = QHBoxLayout()
        self.settings_button = QPushButton('⚙  Settings')
        self.settings_button.clicked.connect(self.controller.show_settings)
        self.exit_button = QPushButton('Exit')
        self.exit_button.clicked.connect(self.controller.shutdown)
        footer.addWidget(self.settings_button)
        footer.addWidget(self.exit_button)
        content.addLayout(footer)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(250)

    def on_monitor_toggle(self):
        store.update(enabled=self.monitor_switch.isChecked())

    def refresh(self):
        settings = store.snapshot()
        if self.monitor_switch.isChecked() != settings.enabled:
            self.monitor_switch.setChecked(settings.enabled)

        s = get_state()
        sources = s['external_sources']
        if sources:
            text = '\n'.join(f'•  {x}' for x in sources[:4])
            if len(sources) > 4:
                text += f'\n•  +{len(sources) - 4} more'
            self.external_label.setText(text)
        else:
            self.external_label.setText('None')

        self.status_label.setText(s['status'])
        self.status_label.setToolTip(s['status'])

    def show_near_tray(self, tray_icon):
        rect = tray_icon.geometry()
        anchor = rect.center() if rect.isValid() else QApplication.primaryScreen().availableGeometry().center()
        screen = QApplication.screenAt(anchor) or QApplication.primaryScreen()
        area = screen.availableGeometry()

        x = anchor.x() - self.width() // 2
        y = anchor.y() - self.height() - 10

        if y < area.top() + 6:
            y = anchor.y() + 10

        x = clamp(x, area.left() + 6, area.right() - self.width() - 6)
        y = clamp(y, area.top() + 6, area.bottom() - self.height() - 6)

        self.move(int(x), int(y))
        self.show()
        self.raise_()
        self.activateWindow()

    def toggle(self, tray_icon):
        if self.isVisible():
            self.hide()
        else:
            self.show_near_tray(tray_icon)


class SettingsDialog(QDialog):
    def __init__(self, controller):
        super().__init__(None)
        self.controller = controller
        self.setWindowTitle(f'{APP_NAME} Settings')
        self.setMinimumSize(720, 610)
        self.resize(760, 660)

        main = QVBoxLayout(self)
        main.setContentsMargins(24, 22, 24, 20)
        main.setSpacing(14)

        tabs = QTabWidget()
        main.addWidget(tabs, 1)
        tabs.addTab(self.general_tab(), 'General')
        tabs.addTab(self.rules_tab(), 'App Rules')

        close = QPushButton('Done')
        close.setObjectName('primary')
        close.setFixedHeight(42)
        close.clicked.connect(self.hide)
        main.addWidget(close)
        
        self.setStyleSheet(THEME)

    def general_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 10, 4, 4)
        layout.setSpacing(12)

        detection = QFrame()
        detection.setObjectName('card')
        dl = QVBoxLayout(detection)
        dl.setContentsMargins(16, 14, 16, 14)
        dl.setSpacing(9)
        sec = QLabel('DETECTION')
        sec.setObjectName('section')
        dl.addWidget(sec)

        row = QHBoxLayout()
        row.addWidget(QLabel('Trigger source'))
        self.trigger_combo = QComboBox()
        self.trigger_combo.addItem('Audio activity', 'audio')
        self.trigger_combo.addItem('Media activity (not depend on sound)', 'media')
        current = store.snapshot().trigger_mode
        idx = self.trigger_combo.findData(current)
        self.trigger_combo.setCurrentIndex(idx if idx >= 0 else 1)
        self.trigger_combo.currentIndexChanged.connect(
            lambda _: store.update(trigger_mode=self.trigger_combo.currentData())
        )
        row.addWidget(self.trigger_combo, 1)
        dl.addLayout(row)

        threshold_row = QHBoxLayout()
        threshold_row.addWidget(QLabel('Sound threshold'))
        self.threshold_value = QLabel()
        threshold_row.addStretch(1)
        threshold_row.addWidget(self.threshold_value)
        dl.addLayout(threshold_row)

        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(-100, -5)
        self.threshold_slider.setValue(store.snapshot().sound_threshold_dbfs)
        self.threshold_slider.valueChanged.connect(self.on_threshold)
        dl.addWidget(self.threshold_slider)

        hint = QLabel('Lower values are more sensitive. This is a peak level in dBFS, not the Windows volume slider.')
        hint.setObjectName('muted')
        hint.setWordWrap(True)
        dl.addWidget(hint)

        interval_row = QHBoxLayout()
        interval_row.addWidget(QLabel('Check interval'))
        self.interval_value = QLabel()
        interval_row.addStretch(1)
        interval_row.addWidget(self.interval_value)
        dl.addLayout(interval_row)

        self.interval_slider = QSlider(Qt.Orientation.Horizontal)
        self.interval_slider.setRange(250, 2000)
        self.interval_slider.setSingleStep(50)
        self.interval_slider.setValue(store.snapshot().check_interval_ms)
        self.interval_slider.valueChanged.connect(self.on_interval)
        dl.addWidget(self.interval_slider)

        resume_row = QHBoxLayout()
        self.resume_external = QCheckBox('Resume AIMP after external audio/media ends')
        self.resume_external.setChecked(store.snapshot().resume_after_external)
        self.resume_external.toggled.connect(lambda v: store.update(resume_after_external=v))
        resume_row.addWidget(self.resume_external)
        dl.addLayout(resume_row)

        delay_row = QHBoxLayout()
        delay_row.addWidget(QLabel('Resume delay'))
        self.delay_value = QLabel()
        delay_row.addStretch(1)
        delay_row.addWidget(self.delay_value)
        dl.addLayout(delay_row)

        self.delay_slider = QSlider(Qt.Orientation.Horizontal)
        self.delay_slider.setRange(0, 5000)
        self.delay_slider.setSingleStep(100)
        self.delay_slider.setValue(store.snapshot().resume_delay_ms)
        self.delay_slider.valueChanged.connect(self.on_delay)
        dl.addWidget(self.delay_slider)

        layout.addWidget(detection)

        volume = QFrame()
        volume.setObjectName('card')
        vl = QVBoxLayout(volume)
        vl.setContentsMargins(16, 14, 16, 14)
        sec2 = QLabel('AIMP VOLUME ZERO')
        sec2.setObjectName('section')
        vl.addWidget(sec2)

        self.zero_check = QCheckBox('Pause AIMP when its own volume reaches 0% or is muted')
        self.zero_check.setChecked(store.snapshot().pause_when_aimp_volume_zero)
        self.zero_check.toggled.connect(lambda v: store.update(pause_when_aimp_volume_zero=v))
        vl.addWidget(self.zero_check)

        self.zero_resume = QCheckBox('Resume AIMP automatically when its volume is raised again')
        self.zero_resume.setChecked(store.snapshot().resume_when_aimp_volume_restored)
        self.zero_resume.toggled.connect(lambda v: store.update(resume_when_aimp_volume_restored=v))
        vl.addWidget(self.zero_resume)

        volume_note = QLabel("This uses AIMP's own player volume/mute state, not the Windows master speaker volume.")
        volume_note.setObjectName('muted')
        volume_note.setWordWrap(True)
        vl.addWidget(volume_note)

        layout.addWidget(volume)
        layout.addStretch(1)

        self.refresh_labels()
        return page

    def rules_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 10, 4, 4)
        layout.setSpacing(12)

        card = QFrame()
        card.setObjectName('card')
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(8)

        sec = QLabel('APP FILTER MODE')
        sec.setObjectName('section')
        cl.addWidget(sec)

        self.filter_combo = QComboBox()
        self.filter_combo.addItem('All detected apps', 'all')
        self.filter_combo.addItem('All except blacklist', 'blacklist')
        self.filter_combo.addItem('Only whitelist', 'whitelist')
        mode = store.snapshot().filter_mode
        idx = self.filter_combo.findData(mode)
        self.filter_combo.setCurrentIndex(max(idx, 0))
        self.filter_combo.currentIndexChanged.connect(
            lambda _: store.update(filter_mode=self.filter_combo.currentData())
        )
        cl.addWidget(self.filter_combo)

        note = QLabel(
            'Rules use case-insensitive partial matching. Examples: chrome.exe, spotify, vlc. '
            f'In whitelist mode only listed apps can trigger {APP_NAME}.'
        )
        note.setObjectName('muted')
        note.setWordWrap(True)
        cl.addWidget(note)
        layout.addWidget(card)

        lists = QHBoxLayout()
        self.whitelist_widget = self.make_rule_list(
            'WHITELIST',
            'Apps allowed to trigger AIMP pause',
            store.snapshot().whitelist,
            'whitelist',
        )
        self.blacklist_widget = self.make_rule_list(
            'BLACKLIST',
            'Apps ignored when they play media/audio',
            store.snapshot().blacklist,
            'blacklist',
        )
        lists.addWidget(self.whitelist_widget[0])
        lists.addWidget(self.blacklist_widget[0])
        layout.addLayout(lists, 1)

        return page

    def make_rule_list(self, title, description, entries, list_type):
        card = QFrame()
        card.setObjectName('card')
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)

        heading = QLabel(title)
        heading.setObjectName('section')
        layout.addWidget(heading)

        d = QLabel(description)
        d.setObjectName('muted')
        d.setWordWrap(True)
        layout.addWidget(d)

        widget = QListWidget()
        for entry in entries:
            widget.addItem(entry)
        layout.addWidget(widget, 1)

        add_row = QHBoxLayout()
        edit = QLineEdit()
        edit.setPlaceholderText('e.g. chrome.exe')
        add = QPushButton('Add')
        remove = QPushButton('Remove')
        add.setObjectName('primary')
        add_row.addWidget(edit, 1)
        add_row.addWidget(add)
        layout.addLayout(add_row)
        layout.addWidget(remove)

        def sync():
            values = [widget.item(i).text().strip() for i in range(widget.count())]
            values = list(dict.fromkeys(v for v in values if v))
            store.update(**{list_type: values})

        def add_rule():
            value = edit.text().strip()
            if not value:
                return
            if not any(widget.item(i).text().casefold() == value.casefold() for i in range(widget.count())):
                widget.addItem(value)
                edit.clear()
                sync()

        def remove_rule():
            for item in widget.selectedItems():
                widget.takeItem(widget.row(item))
            sync()

        add.clicked.connect(add_rule)
        edit.returnPressed.connect(add_rule)
        remove.clicked.connect(remove_rule)

        return card, widget, edit

    def on_threshold(self, value):
        store.update(sound_threshold_dbfs=value)
        self.refresh_labels()

    def on_interval(self, value):
        store.update(check_interval_ms=value)
        self.refresh_labels()

    def on_delay(self, value):
        store.update(resume_delay_ms=value)
        self.refresh_labels()

    def refresh_labels(self):
        if hasattr(self, 'threshold_value'):
            self.threshold_value.setText(f'{self.threshold_slider.value()} dBFS')
        if hasattr(self, 'interval_value'):
            self.interval_value.setText(f'{self.interval_slider.value()} ms')
        if hasattr(self, 'delay_value'):
            self.delay_value.setText(f'{self.delay_slider.value()} ms')


class ApplicationController:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName(APP_NAME)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setStyle('Fusion')

        self.settings_dialog = None
        self.tray = QSystemTrayIcon(
            load_svg_icon(SVG_PATH),
            self.app
        )
        self.tray.setToolTip(APP_NAME)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

        self.flyout = TrayFlyout(self)

        self.monitor_thread = threading.Thread(
            target=monitor_thread_main,
            name=f'{APP_NAME}-monitor',
            daemon=True,
        )
        self.monitor_thread.start()
        
        self.flyout.setStyleSheet(THEME)
        if self.settings_dialog is not None:
            self.settings_dialog.setStyleSheet(THEME)

    def on_tray_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.Context,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.flyout.toggle(self.tray)

    def show_settings(self):
        self.flyout.hide()
        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(self)
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def shutdown(self):
        stop_event.set()
        self.flyout.hide()
        self.tray.hide()
        if self.settings_dialog is not None:
            self.settings_dialog.close()
        self.app.quit()

    def run(self):
        return self.app.exec()
