import shutil
import subprocess
import sys
import threading
import winreg
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSignalBlocker, QSize, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .core import monitor_thread_main
from .logging_setup import APP_NAME, configure_logging
from .utils import get_state, stop_event, store

try:
    import winreg
except ImportError:  # pragma: no cover - the app targets Windows
    winreg = None

SVG_PATH = Path(__file__).resolve().parent.parent / 'MuteAIMP.svg'
logger = configure_logging()

ORANGE = '#F57C00'
ORANGE_HOVER = '#FF8A1F'
ORANGE_DARK = '#D96500'

STARTUP_REGISTRY_PATH = r'Software\Microsoft\Windows\CurrentVersion\Run'
STARTUP_VALUE_NAME = 'MuteAIMP'

THEME = f"""
QWidget {{
    font-family: 'Segoe UI';
    color: #EEF1F4;
    font-size: 10pt;
}}
QWidget#surface {{
    background: #11151A;
    border: none;
}}
QDialog {{
    background: #11151A;
}}
QTabWidget::pane {{
    background: #11151A;
    border: 0;
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
QWidget#settingsPage {{
    background: #11151A;
}}
QFrame#flyoutPanel {{
    background: #11151A;
    border: 1px solid #2A323B;
    border-radius: 16px;
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
QPushButton:disabled {{
    color: #68727D;
    border-color: #29313A;
}}
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
QComboBox QAbstractItemView {{
    background: #191F26;
    color: #EEF1F4;
    selection-background-color: #3A2617;
    selection-color: #FFD0A7;
    border: 1px solid #303943;
    outline: 0;
}}
QSlider::groove:horizontal {{
    height: 5px;
    background: #303943;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ORANGE};
    width: 16px;
    margin: -5px 0;
    border-radius: 5px;
}}
QCheckBox {{ spacing: 8px; }}
QCheckBox:disabled {{ color: #68727D; }}
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
QCheckBox::indicator:disabled {{
    border-color: #48515B;
    background: #252B32;
}}
QListWidget {{
    background: #151A20;
    border: 1px solid #303943;
    border-radius: 10px;
    padding: 4px;
    outline: 0;
}}
QListWidget::item {{ padding: 3px 6px; border-radius: 7px; }}
QListWidget::item:selected {{ background: #3A2617; color: #FFD0A7; }}
QListWidget#externalList {{
    background: transparent;
    border: none;
    padding: 0;
}}
QListWidget#externalList::item {{
    padding: 2px 4px;
    border-radius: 5px;
}}
QListWidget#externalList::item:selected {{
    background: transparent;
    color: #EEF1F4;
}}
QListWidget#externalList QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 1px;
}}
QListWidget#externalList QScrollBar::handle:vertical {{
    background: #59636E;
    border-radius: 3px;
    min-height: 16px;
}}
QListWidget#externalList QScrollBar::add-line:vertical,
QListWidget#externalList QScrollBar::sub-line:vertical {{
    height: 0;
}}
QListWidget#externalList QScrollBar::add-page:vertical,
QListWidget#externalList QScrollBar::sub-page:vertical {{ background: transparent; }}
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
QTabBar::tab:hover:!selected {{ color: #D6DCE2; }}
"""


def clamp(value, low, high):
    """Clamp a numeric value to an inclusive range"""
    return max(low, min(high, value))


def load_svg_icon(svg_path):
    """Load and render an SVG into a multi-size QIcon"""

    svg_path = Path(svg_path)

    # Check whether the file exists
    if not svg_path.is_file():
        msg = f'SVG file not found: {svg_path}'
        logger.error(msg)
        raise FileNotFoundError(msg)

    # Read SVG contents explicitly
    svg_data = QByteArray(svg_path.read_bytes())

    renderer = QSvgRenderer(svg_data)

    if not renderer.isValid():
        msg = f'Qt could not parse SVG: {svg_path}. Try simplifying the SVG file.'
        logger.error(msg)
        raise ValueError(msg)

    icon = QIcon()

    # Provide several raster sizes for tray, title bar, and taskbar use
    for size in (16, 20, 24, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing,
            True
        )
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform,
            True
        )

        renderer.render(
            painter,
            QRectF(0, 0, size, size)
        )

        painter.end()

        icon.addPixmap(pixmap)

    return icon


def resolve_muteaimp_launcher() -> Path:
    """Find the installed muteaimp entry-point executable"""
    launcher = shutil.which('muteaimp')

    if launcher:
        return Path(launcher).resolve()

    # Fall back to the executable used to launch this process
    current = Path(sys.argv[0])

    if current.is_file():
        return current.resolve()

    msg = 'Could not locate the installed muteaimp launcher'
    logger.error(msg)
    raise FileNotFoundError(msg)


def is_startup_enabled():
    """Check whether MuteAIMP is registered to start at user logon"""
    if winreg is None:
        return False

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            STARTUP_REGISTRY_PATH,
            0,
            winreg.KEY_READ,
        ) as key:
            value, _ = winreg.QueryValueEx(key, STARTUP_VALUE_NAME)
            return bool(value)

    except FileNotFoundError:
        return False
    except OSError:
        logger.exception('[STARTUP] Could not read startup setting')
        return False


def set_startup_enabled(enabled: bool):
    """Enable or disable MuteAIMP at Windows user logon"""
    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER,
        STARTUP_REGISTRY_PATH
    ) as key:
        if enabled:
            launcher = resolve_muteaimp_launcher()

            # Quote the absolute path, including paths with spaces
            command = subprocess.list2cmdline([str(launcher)])

            winreg.SetValueEx(
                key,
                STARTUP_VALUE_NAME,
                0,
                winreg.REG_SZ,
                command
            )
        else:
            try:
                winreg.DeleteValue(key, STARTUP_VALUE_NAME)
            except FileNotFoundError:
                pass


class ToggleSwitch(QCheckBox):
    """A compact orange custom-painted switch based on QCheckBox"""

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)

        self.setText('')
        self.setTristate(False)
        self.setChecked(checked)
        self.setFixedSize(52, 30)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.setAccessibleName('Automatic monitoring')
        self.setToolTip('Enable or disable automatic monitoring')

        self.accent_color = QColor(ORANGE)

    def sizeHint(self):
        return QSize(52, 30)

    def hitButton(self, pos):
        # Make the entire switch area clickable
        return self.rect().contains(pos)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing,
            True
        )

        # Draw the switch track
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

        # Add a subtle hover highlight
        if self.underMouse() and self.isEnabled():
            track_color = track_color.lighter(108 if self.isChecked() else 112)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track, 12, 12)

        # Draw the circular thumb at the current position
        diameter = 18
        thumb_y = (self.height() - diameter) / 2
        thumb_x = (
            self.width() - diameter - 5
            if self.isChecked()
            else 5
        )

        painter.setBrush(thumb_color)
        painter.drawEllipse(
            QRectF(
                thumb_x,
                thumb_y,
                diameter,
                diameter
            )
        )

        # Draw a focus ring for keyboard navigation
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
    HEIGHT = 320

    def __init__(self, app_controller):
        super().__init__(
            None,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        self.controller = app_controller
        self._last_external_sources = None

        self.setObjectName('surface')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setWindowIcon(self.controller.app_icon)

        root = QVBoxLayout(self)
        # Fill the popup
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.panel = QFrame()
        self.panel.setObjectName('flyoutPanel')
        root.addWidget(self.panel)

        content = QVBoxLayout(self.panel)
        content.setContentsMargins(18, 17, 18, 15)
        content.setSpacing(10)

        # Automatic monitoring card
        monitor_card = QFrame()
        monitor_card.setObjectName('card')
        ml = QHBoxLayout(monitor_card)
        ml.setContentsMargins(14, 12, 12, 12)
        ml.setSpacing(12)
        monitor_text = QVBoxLayout()
        monitor_text.setSpacing(3)

        heading = QLabel('Automatic monitoring')
        heading.setFont(QFont('Segoe UI', 11, QFont.Weight.Bold))
        self.monitor_desc = QLabel('Pause AIMP when another app becomes active')
        self.monitor_desc.setObjectName('muted')
        self.monitor_desc.setWordWrap(True)
        monitor_text.addWidget(heading)
        monitor_text.addWidget(self.monitor_desc)
        self.monitor_switch = ToggleSwitch(store.snapshot().enabled)
        self.monitor_switch.toggled.connect(self.on_monitor_toggle)
        ml.addLayout(monitor_text, 1)
        ml.addWidget(self.monitor_switch)
        content.addWidget(monitor_card)

        # External sources card with a scrollable list
        external_card = QFrame()
        external_card.setObjectName('card')

        # Keep the external sources card at a stable size
        external_card.setFixedHeight(106)

        el = QVBoxLayout(external_card)
        el.setContentsMargins(14, 10, 14, 10)
        el.setSpacing(5)

        # Anchor the heading to the top of the card
        el.setAlignment(Qt.AlignmentFlag.AlignTop)

        sec2 = QLabel('ACTIVE EXTERNAL SOURCES')
        sec2.setObjectName('section')
        sec2.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        sec2.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sec2.setFixedHeight(16)

        self.external_list = QListWidget()
        self.external_list.setObjectName('externalList')

        # Keep the list viewport stable and scroll when necessary
        self.external_list.setFixedHeight(62)
        self.external_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.external_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.external_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        el.addWidget(sec2, 0, Qt.AlignmentFlag.AlignTop)
        el.addWidget(self.external_list)
        content.addWidget(external_card)

        # Current status row
        status = QHBoxLayout()
        self.status_label = QLabel('Starting...')
        self.status_label.setObjectName('muted')
        self.status_label.setWordWrap(False)
        status.addWidget(self.status_label, 1)
        content.addLayout(status)

        # Footer buttons
        footer = QHBoxLayout()
        self.settings_button = QPushButton('⚙  Settings')
        self.settings_button.clicked.connect(self.controller.show_settings)

        self.exit_button = QPushButton('Exit')
        self.exit_button.clicked.connect(self.controller.shutdown)

        footer.addWidget(self.settings_button)
        footer.addStretch(1)
        footer.addWidget(self.exit_button)
        content.addLayout(footer)

        # Refresh visible state periodically
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(250)

        self.refresh()

    def on_monitor_toggle(self, checked):
        # Persist the switch state immediately
        store.update(enabled=bool(checked))

    def _refresh_external_sources(self, sources):
        """Update the source list only when its contents changed"""
        normalized = tuple(sources)

        if normalized == self._last_external_sources:
            return

        self._last_external_sources = normalized
        self.external_list.clear()

        if not normalized:
            item = QListWidgetItem('None')
            item.setForeground(QBrush(QColor('#9AA4AE')))
            self.external_list.addItem(item)
            visible_rows = 1
        else:
            for source in normalized:
                item = QListWidgetItem(f'•  {source}')
                self.external_list.addItem(item)

            # Show up to three rows; additional entries are scrollable
            visible_rows = min(len(normalized), 3)

        self.external_list.doItemsLayout()
        row_height = self.external_list.sizeHintForRow(0)
        if row_height <= 0:
            row_height = 22

        target_height = min(
            76,
            max(25, visible_rows * row_height + 5)
        )
        self.external_list.setFixedHeight(target_height)
        self.external_list.scrollToTop()

    def refresh(self):
        settings = store.snapshot()
        if self.monitor_switch.isChecked() != settings.enabled:
            blocker = QSignalBlocker(self.monitor_switch)
            self.monitor_switch.setChecked(settings.enabled)
            del blocker

        current_state = get_state()
        sources = current_state['external_sources']

        self._refresh_external_sources(sources)

        self.status_label.setText(current_state['status'])
        self.status_label.setToolTip(current_state['status'])

    def show_near_tray(self, tray_icon):
        """Position the popup near the tray icon, inside its work area"""
        rect = tray_icon.geometry()
        anchor = rect.center() if rect.isValid() else QCursor.pos()
        screen = QApplication.screenAt(anchor) or QApplication.primaryScreen()

        if screen is None:
            self.show()
            self.raise_()
            self.activateWindow()
            return

        area = screen.availableGeometry()

        x = anchor.x() - self.width() // 2
        y = anchor.y() - self.height() - 8

        # If there is not enough room above the tray, open below it
        if y < area.top() + 6:
            y = anchor.y() + 8

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
        self.setWindowIcon(controller.app_icon)
        self.setMinimumSize(720, 650)
        self.resize(760, 700)

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

    @staticmethod
    def _opacity_effect(widget, enabled=True):
        """Attach an opacity effect used for disabled setting groups"""
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(1.0 if enabled else 0.42)
        widget.setGraphicsEffect(effect)
        return effect

    @staticmethod
    def _set_faded_enabled(widget, effect, enabled):
        """Enable a control and visually dim it when unavailable"""
        widget.setEnabled(enabled)
        effect.setOpacity(1.0 if enabled else 0.42)

    def general_tab(self):
        page = QWidget()
        page.setObjectName('settingsPage')
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 10, 4, 4)
        layout.setSpacing(12)

        current = store.snapshot()

        # Startup option
        startup_card = QFrame()
        startup_card.setObjectName('card')

        startup_layout = QHBoxLayout(startup_card)
        startup_layout.setContentsMargins(16, 11, 16, 11)
        startup_layout.setSpacing(12)

        startup_text = QVBoxLayout()
        startup_text.setSpacing(3)

        self.startup_check = QCheckBox(f'Start {APP_NAME} with Windows')
        self.startup_check.setChecked(is_startup_enabled())
        self.startup_check.toggled.connect(self.on_startup_toggled)

        startup_hint = QLabel('Launch in the background when you sign in to Windows.')
        startup_hint.setObjectName('muted')
        startup_hint.setWordWrap(True)

        startup_text.addWidget(self.startup_check)
        startup_text.addWidget(startup_hint)
        startup_layout.addLayout(startup_text, 1)
        layout.addWidget(startup_card)

        # Detection settings
        detection = QFrame()
        detection.setObjectName('card')

        dl = QVBoxLayout(detection)
        dl.setContentsMargins(16, 14, 16, 14)
        dl.setSpacing(9)

        sec = QLabel('DETECTION')
        sec.setObjectName('section')
        dl.addWidget(sec)

        # Trigger source selector
        trigger_row = QHBoxLayout()
        trigger_row.addWidget(QLabel('Trigger source'))

        self.trigger_combo = QComboBox()
        self.trigger_combo.addItem('Audio activity', 'audio')
        self.trigger_combo.addItem('Media activity (independent of sound)', 'media')

        idx = self.trigger_combo.findData(current.trigger_mode)
        self.trigger_combo.setCurrentIndex(idx if idx >= 0 else 1)
        self.trigger_combo.currentIndexChanged.connect(self.on_trigger_mode_changed)

        trigger_row.addWidget(self.trigger_combo, 1)
        dl.addLayout(trigger_row)

        # Sound threshold group; disabled for media mode
        self.threshold_container = QWidget()
        self.threshold_container.setObjectName('conditionalGroup')

        threshold_layout = QVBoxLayout(self.threshold_container)
        threshold_layout.setContentsMargins(0, 0, 0, 0)
        threshold_layout.setSpacing(6)

        threshold_row = QHBoxLayout()
        threshold_row.addWidget(QLabel('Sound threshold'))

        self.threshold_value = QLabel()
        threshold_row.addStretch(1)
        threshold_row.addWidget(self.threshold_value)
        threshold_layout.addLayout(threshold_row)

        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(-100, -5)
        self.threshold_slider.setValue(current.sound_threshold_dbfs)
        self.threshold_slider.valueChanged.connect(self.on_threshold)
        threshold_layout.addWidget(self.threshold_slider)

        threshold_hint = QLabel(
            'Lower values are more sensitive. This is a peak level in dBFS, '
            'not the Windows volume slider.'
        )
        threshold_hint.setObjectName('muted')
        threshold_hint.setWordWrap(True)
        threshold_layout.addWidget(threshold_hint)

        self.threshold_effect = self._opacity_effect(self.threshold_container)
        dl.addWidget(self.threshold_container)

        # Check interval
        interval_row = QHBoxLayout()
        interval_row.addWidget(QLabel('Check interval'))

        self.interval_value = QLabel()
        interval_row.addStretch(1)
        interval_row.addWidget(self.interval_value)
        dl.addLayout(interval_row)

        self.interval_slider = QSlider(Qt.Orientation.Horizontal)
        self.interval_slider.setRange(250, 2000)
        self.interval_slider.setSingleStep(50)
        self.interval_slider.setValue(current.check_interval_ms)
        self.interval_slider.valueChanged.connect(self.on_interval)
        dl.addWidget(self.interval_slider)

        # External-resume checkbox
        self.resume_external = QCheckBox('Resume AIMP after external audio/media ends')
        self.resume_external.setChecked(current.resume_after_external)
        self.resume_external.toggled.connect(self.on_resume_external_toggled)
        dl.addWidget(self.resume_external)

        # Resume delay group; dimmed and disabled when the checkbox is off
        self.resume_delay_container = QWidget()
        self.resume_delay_container.setObjectName('conditionalGroup')

        delay_layout = QVBoxLayout(self.resume_delay_container)
        delay_layout.setContentsMargins(0, 0, 0, 0)
        delay_layout.setSpacing(6)

        delay_row = QHBoxLayout()
        delay_row.addWidget(QLabel('Resume delay'))

        self.delay_value = QLabel()
        delay_row.addStretch(1)
        delay_row.addWidget(self.delay_value)
        delay_layout.addLayout(delay_row)

        self.delay_slider = QSlider(Qt.Orientation.Horizontal)
        self.delay_slider.setRange(0, 5000)
        self.delay_slider.setSingleStep(100)
        self.delay_slider.setValue(current.resume_delay_ms)
        self.delay_slider.valueChanged.connect(self.on_delay)
        delay_layout.addWidget(self.delay_slider)

        self.resume_delay_effect = self._opacity_effect(
            self.resume_delay_container,
            current.resume_after_external
        )
        self._set_faded_enabled(
            self.resume_delay_container,
            self.resume_delay_effect,
            current.resume_after_external
        )
        dl.addWidget(self.resume_delay_container)

        layout.addWidget(detection)

        # AIMP volume-zero settings
        volume = QFrame()
        volume.setObjectName('card')

        vl = QVBoxLayout(volume)
        vl.setContentsMargins(16, 14, 16, 14)
        vl.setSpacing(8)

        sec2 = QLabel('AIMP VOLUME ZERO')
        sec2.setObjectName('section')
        vl.addWidget(sec2)

        self.zero_check = QCheckBox('Pause AIMP when its own volume reaches 0% or is muted')
        self.zero_check.setChecked(current.pause_when_aimp_volume_zero)
        self.zero_check.toggled.connect(self.on_zero_check_toggled)
        vl.addWidget(self.zero_check)

        self.zero_resume = QCheckBox('Resume AIMP automatically when its volume is raised again')
        self.zero_resume.setChecked(current.resume_when_aimp_volume_restored)
        self.zero_resume.toggled.connect(
            lambda value: store.update(
                resume_when_aimp_volume_restored=bool(value)
            )
        )
        vl.addWidget(self.zero_resume)

        self.zero_resume_effect = self._opacity_effect(
            self.zero_resume,
            current.pause_when_aimp_volume_zero
        )
        self._set_faded_enabled(
            self.zero_resume,
            self.zero_resume_effect,
            current.pause_when_aimp_volume_zero
        )

        volume_note = QLabel(
            "This uses AIMP's own player volume/mute state, "
            "not the Windows master speaker volume."
        )
        volume_note.setObjectName('muted')
        volume_note.setWordWrap(True)
        vl.addWidget(volume_note)

        layout.addWidget(volume)
        layout.addStretch(1)

        self.refresh_labels()
        self.update_conditional_controls()

        # Keep all General settings reachable on smaller displays
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def rules_tab(self):
        page = QWidget()
        page.setObjectName('settingsPage')

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
        self.filter_combo.currentIndexChanged.connect(self.on_filter_mode_changed)
        cl.addWidget(self.filter_combo)

        note = QLabel(
            'Rules use case-insensitive partial matching. '
            'Examples: chrome.exe, spotify, vlc. '
            f'In whitelist mode only listed apps can trigger {APP_NAME}.'
        )
        note.setObjectName('muted')
        note.setWordWrap(True)
        cl.addWidget(note)

        layout.addWidget(card)

        lists = QHBoxLayout()
        lists.setSpacing(12)

        self.whitelist_widget = self.make_rule_list(
            'WHITELIST',
            'Apps allowed to trigger AIMP pause',
            store.snapshot().whitelist,
            'whitelist'
        )
        self.blacklist_widget = self.make_rule_list(
            'BLACKLIST',
            'Apps ignored when they play media/audio',
            store.snapshot().blacklist,
            'blacklist'
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
        layout.setSpacing(8)

        heading = QLabel(title)
        heading.setObjectName('section')
        layout.addWidget(heading)

        description_label = QLabel(description)
        description_label.setObjectName('muted')
        description_label.setWordWrap(True)
        layout.addWidget(description_label)

        widget = QListWidget()
        widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        widget.setAlternatingRowColors(False)

        for entry in entries:
            widget.addItem(entry)

        layout.addWidget(widget, 1)

        add_row = QHBoxLayout()
        add_row.setSpacing(6)

        edit = QLineEdit()
        edit.setPlaceholderText('e.g. chrome.exe')

        add = QPushButton('Add')
        add.setObjectName('primary')

        remove = QPushButton('Remove')

        add_row.addWidget(edit, 1)
        add_row.addWidget(add)
        layout.addLayout(add_row)
        layout.addWidget(remove)

        def sync():
            values = [
                widget.item(i).text().strip()
                for i in range(widget.count())
            ]

            values = list(
                dict.fromkeys(
                    value
                    for value in values
                    if value
                )
            )

            store.update(
                **{list_type: values}
            )

        def add_rule():
            value = edit.text().strip()
            if not value:
                return

            exists = any(
                widget.item(i).text().casefold()
                == value.casefold()
                for i in range(widget.count())
            )

            if not exists:
                widget.addItem(value)
                edit.clear()
                sync()

        def remove_rule():
            for item in widget.selectedItems():
                widget.takeItem(
                    widget.row(item)
                )

            sync()

        add.clicked.connect(add_rule)
        edit.returnPressed.connect(add_rule)
        remove.clicked.connect(remove_rule)

        return card, widget, edit

    # Settings handlers
    def on_startup_toggled(self, enabled):
        """Persist the startup preference in the user's Run registry key"""
        try:
            set_startup_enabled(bool(enabled))
        except Exception as exc:
            # Restore the previous checkbox state if registration fails
            blocker = QSignalBlocker(self.startup_check)
            self.startup_check.setChecked(is_startup_enabled())
            del blocker

            logger.exception('Could not update Windows startup setting')
            QMessageBox.warning(
                self,
                APP_NAME,
                f'Could not update Windows startup setting:\n{exc}'
            )

    def on_trigger_mode_changed(self, index):
        mode = self.trigger_combo.currentData()
        if mode:
            store.update(trigger_mode=mode)
        self.update_conditional_controls()

    def on_filter_mode_changed(self, index):
        mode = self.filter_combo.currentData()
        if mode:
            store.update(filter_mode=mode)

    def on_resume_external_toggled(self, enabled):
        store.update(resume_after_external=bool(enabled))
        self.update_conditional_controls()

    def on_zero_check_toggled(self, enabled):
        store.update(pause_when_aimp_volume_zero=bool(enabled))
        self.update_conditional_controls()

    def update_conditional_controls(self):
        """Enable and dim settings that do not apply to the chosen mode"""
        if hasattr(self, 'threshold_container'):
            mode = self.trigger_combo.currentData()

            # The threshold is relevant when audio detection is enabled
            self._set_faded_enabled(
                self.threshold_container,
                self.threshold_effect,
                mode == 'audio'
            )

        if hasattr(self, 'resume_delay_container'):
            resume_enabled = (self.resume_external.isChecked())

            self._set_faded_enabled(
                self.resume_delay_container,
                self.resume_delay_effect,
                resume_enabled
            )

        if hasattr(self, 'zero_resume'):
            zero_enabled = (self.zero_check.isChecked())

            self._set_faded_enabled(
                self.zero_resume,
                self.zero_resume_effect,
                zero_enabled
            )

    def on_threshold(self, value):
        store.update(sound_threshold_dbfs=int(value))
        self.refresh_labels()

    def on_interval(self, value):
        store.update(check_interval_ms=int(value))
        self.refresh_labels()

    def on_delay(self, value):
        store.update(resume_delay_ms=int(value))
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

        # Set the SVG icon application-wide so dialogs and the taskbar
        # use the same artwork as the system tray.
        try:
            # Load and set the application-wide icon before creating windows
            self.app_icon = load_svg_icon(SVG_PATH)
            self.app.setWindowIcon(self.app_icon)
        except Exception:
            logger.exception('[UI] Could not load application SVG icon')
            self.app_icon = QIcon()
            self.app.setWindowIcon(self.app_icon)

        self.settings_dialog = None
        self.tray = QSystemTrayIcon(self.app_icon, self.app)
        self.tray.setToolTip(APP_NAME)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

        self.flyout = TrayFlyout(self)
        self.flyout.setStyleSheet(THEME)

        self.monitor_thread = threading.Thread(
            target=monitor_thread_main,
            name=f'{APP_NAME}-monitor',
            daemon=True
        )
        self.monitor_thread.start()

    def on_tray_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.Context,
            QSystemTrayIcon.ActivationReason.DoubleClick
        ):
            self.flyout.toggle(self.tray)

    def show_settings(self):
        self.flyout.hide()

        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(self)
            self.settings_dialog.setWindowIcon(self.app_icon)

        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def shutdown(self):
        # Save settings before terminating the application
        store.save()
        stop_event.set()

        self.flyout.hide()
        self.tray.hide()

        if self.settings_dialog is not None:
            self.settings_dialog.close()

        self.app.quit()

    def run(self):
        return self.app.exec()
