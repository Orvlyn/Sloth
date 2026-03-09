import sys
import os
import json
import time
import threading
import subprocess
import logging
import logging.handlers
import urllib.request
import urllib.error
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Any
from datetime import datetime


# ============================
# BASE DIRECTORY HELPER
# ============================
def get_base_dir() -> str:
    """Return the directory next to Sloth.exe (frozen) or the script file (dev).
    All user data (profiles, backups, logs) is stored here so nothing ends up
    in a temp folder when running as a PyInstaller .exe.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_cached_icon() -> 'QIcon':
    """Download icon from GitHub and cache it locally, or load from cache.
    Falls back to default icon if download fails or cache is empty.
    """
    from PySide6.QtGui import QPixmap, QIcon
    
    base_dir = get_base_dir()
    cache_path = os.path.join(base_dir, '.sloth_icon_cache.ico')
    github_url = 'https://raw.githubusercontent.com/Orvlyn/Sloth/main/sloth.ico'
    
    # Try cache first
    if os.path.exists(cache_path):
        try:
            icon = QIcon(cache_path)
            if not icon.isNull():
                logger.debug(f"Loaded icon from cache: {cache_path}")
                return icon
        except Exception as e:
            logger.debug(f"Failed to load cached icon: {e}")
    
    # Try GitHub download
    try:
        logger.debug(f"Downloading icon from GitHub: {github_url}")
        urllib.request.urlretrieve(github_url, cache_path)
        icon = QIcon(cache_path)
        if not icon.isNull():
            logger.info("Icon downloaded and cached successfully")
            return icon
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        logger.debug(f"Failed to download icon from GitHub: {e}")
    except Exception as e:
        logger.debug(f"Unexpected error downloading icon: {e}")
    
    logger.warning("Could not load icon from cache or GitHub")
    return QIcon()  # Return empty icon if all attempts fail

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QPushButton, QLabel, QStackedWidget, QLineEdit,
    QComboBox, QSlider, QCheckBox, QScrollArea, QSpinBox, QDoubleSpinBox,
    QProgressBar, QListWidget, QListWidgetItem, QFileDialog,
    QMessageBox, QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QTextEdit, QSplitter, QTabWidget, QColorDialog, QButtonGroup, QRadioButton,
    QDialog, QMenu, QSizePolicy, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal, QThread, QSettings, QTimer, QObject, QEvent, QPoint, QUrl, QMimeData
from PySide6.QtGui import QPixmap, QIcon, QColor, QKeySequence, QShortcut, QPainter, QPen, QBrush, QCursor, QFont, QTextDocument, QTextCursor, QDesktopServices, QDrag, QGuiApplication

# ============================
# LOGGING SETUP
# ============================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.handlers.RotatingFileHandler(
            os.path.join(get_base_dir(), 'sloth.log'),
            maxBytes=2 * 1024 * 1024,  # 2 MB
            backupCount=3,
            encoding='utf-8'
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================
# OCR CONFIGURATION
# ============================

def configure_tesseract():
    """Configure Tesseract from expected local install folders near Sloth."""
    try:
        import pytesseract
    except ImportError:
        logger.warning("pytesseract not installed - Skill Check OCR disabled")
        return False

    # Only accept local install locations next to Sloth.exe / script.
    # get_base_dir() resolves correctly for both frozen .exe and development.
    base = get_base_dir()
    possible_paths = [
        os.path.join(base, 'tesseract', 'tesseract.exe'),
        os.path.join(base, 'teseract', 'tesseract.exe'),  # common typo folder name
    ]

    for path in possible_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            logger.info(f"Tesseract found at: {path}")
            return True

    logger.warning("Tesseract not found. Install tesseract.exe at ./teseract/tesseract.exe (or ./tesseract/tesseract.exe)")
    return False

TESSERACT_AVAILABLE = configure_tesseract()

# ============================
# VERSION & UPDATE CHECK
# ============================

APP_VERSION = "1.0.2"
UPDATE_CHECK_URL = "https://raw.githubusercontent.com/Orvlyn/Sloth/main/version.json"


def _check_for_updates(on_result):
    """Fetch latest version from remote JSON in a daemon thread.

    Expects JSON: {"version": "1.1.0", "url": "https://github.com/.../releases/latest"}
    Calls on_result(version, url) only when a newer version is available.
    All network errors are silently swallowed - never blocks or crashes the app.
    """
    try:
        import urllib.request
        import json as _json
        with urllib.request.urlopen(UPDATE_CHECK_URL, timeout=5) as resp:
            data = _json.loads(resp.read().decode())
        latest = data.get("version", "")
        url = data.get("url", "")
        if latest and latest != APP_VERSION:
            on_result(latest, url)
    except Exception as e:
        logger.debug(f"Update check failed: {e}")


# ============================
# THEMES
# ============================

THEMES = {

    # --------------------------------------------------------------
    # NORMAL THEMES (6) - single dominant hue family, tight accent
    # --------------------------------------------------------------

    'midnight': {
        'name': 'Midnight',
        'description': 'Normal: deep indigo foundation, balanced cyan accent',
        'bg_dark': '#0B1020', 'bg_medium': '#141B2D', 'border': '#24314A',
        'hover': '#1B2740', 'accent': '#4CC9F0', 'accent_text': '#04111A',
        'text_primary': '#EAF2FF', 'text_secondary': '#A9BDD8', 'text_disabled': '#62718A',
        'scrollbar': '#1B2740', 'scrollbar_hover': '#2A3C5E'
    },
    'obsidian': {
        'name': 'Obsidian',
        'description': 'Normal: near-black charcoal, single clean teal pop',
        'bg_dark': '#0D0F0F', 'bg_medium': '#171C1C', 'border': '#263030',
        'hover': '#1D2828', 'accent': '#00B4A6', 'accent_text': '#00100E',
        'text_primary': '#E5EFEE', 'text_secondary': '#8AACAA', 'text_disabled': '#476462',
        'scrollbar': '#1D2828', 'scrollbar_hover': '#2D3E3E'
    },
    'monokai': {
        'name': 'Monokai Pro',
        'description': 'Normal: neutral dark charcoal, cool mint-cyan accent',
        'bg_dark': '#232428', 'bg_medium': '#2D2F35', 'border': '#4B4E57',
        'hover': '#3A3E48', 'accent': '#7CE7D0', 'accent_text': '#0F2520',
        'text_primary': '#F2F3F5', 'text_secondary': '#BEC2CC', 'text_disabled': '#7D8493',
        'scrollbar': '#3A3E48', 'scrollbar_hover': '#545A68'
    },
    'cyberpunk': {
        'name': 'Cyberpunk',
        'description': 'Normal: absolute near-black, neon magenta accent - high contrast pop',
        'bg_dark': '#0A0B12', 'bg_medium': '#131625', 'border': '#2C2F45',
        'hover': '#1C2140', 'accent': '#FF4FD8', 'accent_text': '#280727',
        'text_primary': '#E6ECFF', 'text_secondary': '#A8B7DE', 'text_disabled': '#6978A3',
        'scrollbar': '#1C2140', 'scrollbar_hover': '#2C3564'
    },
    'sakura': {
        'name': 'Sakura Night',
        'description': 'Normal: deep plum base, soft orchid-blush accent - tight analogous pink',
        'bg_dark': '#17101E', 'bg_medium': '#231830', 'border': '#4A2D5C',
        'hover': '#35204A', 'accent': '#F4ABCC', 'accent_text': '#280A1C',
        'text_primary': '#F8ECFF', 'text_secondary': '#D0A8C8', 'text_disabled': '#88608A',
        'scrollbar': '#35204A', 'scrollbar_hover': '#502D70'
    },
    'foxfire': {
        'name': 'Foxfire',
        'description': 'Normal: very dark walnut-brown, glowing amber accent - warm analogous',
        'bg_dark': '#110C07', 'bg_medium': '#1E1409', 'border': '#3F2C12',
        'hover': '#2E1E0A', 'accent': '#F09030', 'accent_text': '#220E00',
        'text_primary': '#FFF0DC', 'text_secondary': '#D4A870', 'text_disabled': '#8A6030',
        'scrollbar': '#2E1E0A', 'scrollbar_hover': '#4A2E12'
    },

    # -------------------------------------------------------------------
    # TWO-COLOR THEMES - complementary or split-complementary pairings
    # -------------------------------------------------------------------

    'synthwave': {
        'name': 'Synthwave',
        'description': 'Two-color: deep violet base, electric hot-pink accent - close split-complementary',
        'bg_dark': '#1A1233', 'bg_medium': '#251A45', 'border': '#4B2D7A',
        'hover': '#35235F', 'accent': '#FF6AD5', 'accent_text': '#2A0E2E',
        'text_primary': '#F7EEFF', 'text_secondary': '#CDB9E6', 'text_disabled': '#8D76AF',
        'scrollbar': '#35235F', 'scrollbar_hover': '#55398A'
    },
    'nord': {
        'name': 'Nord Aurora',
        'description': 'Two-color: cool nordic slate-blue, warm amber accent - complementary warmth',
        'bg_dark': '#242933', 'bg_medium': '#2D3442', 'border': '#445063',
        'hover': '#364052', 'accent': '#EBCB8B', 'accent_text': '#1E232B',
        'text_primary': '#E5E9F0', 'text_secondary': '#BCC6D4', 'text_disabled': '#6E7B90',
        'scrollbar': '#364052', 'scrollbar_hover': '#4B5A72'
    },
    'ocean': {
        'name': 'Ocean',
        'description': 'Two-color: deep marine blue, warm coral accent - blue-orange complement',
        'bg_dark': '#0B1B2B', 'bg_medium': '#12314A', 'border': '#1F4A68',
        'hover': '#1A4460', 'accent': '#FF8A7A', 'accent_text': '#2B1210',
        'text_primary': '#E1F2FF', 'text_secondary': '#A9CDE6', 'text_disabled': '#6E9CB9',
        'scrollbar': '#1A4460', 'scrollbar_hover': '#286285'
    },
    'deepspace': {
        'name': 'Deep Space',
        'description': 'Two-color: ultra-dark violet, electric cyan starlight - split-complementary',
        'bg_dark': '#0A0516', 'bg_medium': '#1A0A2E', 'border': '#440066',
        'hover': '#2D1B4E', 'accent': '#00D9FF', 'accent_text': '#001828',
        'text_primary': '#E8D5FF', 'text_secondary': '#B39DDB', 'text_disabled': '#7C6BA8',
        'scrollbar': '#2D1B4E', 'scrollbar_hover': '#441D72'
    },
    'void': {
        'name': 'Void',
        'description': 'Two-color: dark purple-black, vivid mint-green accent - split-complementary',
        'bg_dark': '#090514', 'bg_medium': '#120820', 'border': '#2C1A48',
        'hover': '#1C1038', 'accent': '#00F0A0', 'accent_text': '#001E14',
        'text_primary': '#EAD8FF', 'text_secondary': '#A888CC', 'text_disabled': '#5C4880',
        'scrollbar': '#1C1038', 'scrollbar_hover': '#2E1A55'
    },
    'plum_gold': {
        'name': 'Plum and Gold',
        'description': 'Two-color: deep aubergine-plum base, burnished gold accent - luxury complement',
        'bg_dark': '#14091E', 'bg_medium': '#1F1030', 'border': '#48244A',
        'hover': '#2E1840', 'accent': '#DCA048', 'accent_text': '#22100A',
        'text_primary': '#F2E8FF', 'text_secondary': '#C2A8D8', 'text_disabled': '#7A6090',
        'scrollbar': '#2E1840', 'scrollbar_hover': '#442460'
    },

    # ---------------------------------------------------------------
    # TRICOLOR THEMES - three distinct hue families in one palette
    # ---------------------------------------------------------------

    'aurora': {
        'name': 'Aurora',
        'description': 'Tricolor: deep violet base, arctic-teal mid, rose-pink accent',
        'bg_dark': '#0D0A1E', 'bg_medium': '#0A1A18', 'border': '#1E3830',
        'hover': '#142A24', 'accent': '#F06090', 'accent_text': '#2A0015',
        'text_primary': '#EEE8FF', 'text_secondary': '#90C0B8', 'text_disabled': '#4A7A72',
        'scrollbar': '#142A24', 'scrollbar_hover': '#1E3830'
    },
    'prism': {
        'name': 'Prism',
        'description': 'Tricolor: deep navy base, jade-green mid, golden-amber accent',
        'bg_dark': '#080E1C', 'bg_medium': '#0C1C10', 'border': '#1C3A20',
        'hover': '#102A18', 'accent': '#F0AA30', 'accent_text': '#1E1000',
        'text_primary': '#E8F0FF', 'text_secondary': '#88B0A0', 'text_disabled': '#447060',
        'scrollbar': '#102A18', 'scrollbar_hover': '#1C3A20'
    },
    'tigereye': {
        'name': 'Tiger Eye',
        'description': 'Tricolor: warm amber-black base, deep violet mid, electric teal accent - true triadic',
        'bg_dark': '#0E0C06', 'bg_medium': '#1A1430', 'border': '#342860',
        'hover': '#241E48', 'accent': '#00D8B0', 'accent_text': '#001A16',
        'text_primary': '#FFF8E8', 'text_secondary': '#B0A0D0', 'text_disabled': '#6A5E80',
        'scrollbar': '#241E48', 'scrollbar_hover': '#342860'
    },
    'phosphor': {
        'name': 'Phosphor',
        'description': 'Tricolor: near-black charcoal base, dark military-green mid, electric lime accent',
        'bg_dark': '#07080A', 'bg_medium': '#0C1810', 'border': '#183A18',
        'hover': '#103010', 'accent': '#60FF60', 'accent_text': '#041804',
        'text_primary': '#E0FFE0', 'text_secondary': '#80C880', 'text_disabled': '#408040',
        'scrollbar': '#103010', 'scrollbar_hover': '#1A4818'
    },

    # ------------------------------------------------------------------
    # CUSTOM THEME - colors set by the user in Settings ⚙️ Configure
    # ------------------------------------------------------------------

    'custom': {
        'name': 'Custom',
        'description': 'Your own personalized color scheme. Click "Configure" below to set every color.',
        'bg_dark': '#0B1020', 'bg_medium': '#141B2D', 'border': '#24314A',
        'hover': '#1B2740', 'accent': '#4CC9F0', 'accent_text': '#04111A',
        'text_primary': '#EAF2FF', 'text_secondary': '#A9BDD8', 'text_disabled': '#62718A',
        'scrollbar': '#1B2740', 'scrollbar_hover': '#2A3C5E'
    },
}

def _resolve_theme(theme_name: str, settings=None) -> dict:
    """Return the effective theme dict for *theme_name*.

    For the built-in themes this is simply THEMES[theme_name].
    For 'custom' it starts from the 'custom' defaults and then overlays
    per-key values stored under the "custom_theme/" QSettings prefix.
    Also accepts a QSettings-like object (or None).
    """
    if theme_name == 'custom':
        base = dict(THEMES.get('custom', THEMES['midnight']))
        if settings is not None:
            for k in ('accent', 'accent_text', 'bg_dark', 'bg_medium', 'border', 'hover',
                      'text_primary', 'text_secondary', 'text_disabled',
                      'scrollbar', 'scrollbar_hover'):
                saved = settings.value(f"custom_theme/{k}")
                if saved:
                    base[k] = saved
        return base
    return THEMES.get(theme_name, THEMES['midnight'])


def generate_stylesheet(theme_name='midnight', theme_override=None):
    """Build QSS stylesheet from a theme dict."""
    theme = theme_override if theme_override is not None else THEMES.get(theme_name, THEMES['midnight'])
    
    return f"""
    * {{
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 13px;
    }}
    
    QMainWindow, QWidget, QDialog {{
        background: {theme['bg_dark']};
        color: {theme['text_primary']};
    }}
    
    /* ========== BUTTONS ========== */
    QPushButton {{
        background: {theme['bg_medium']};
        border: 2px solid {theme['border']};
        padding: 8px 16px;
        border-radius: 6px;
        color: {theme['text_primary']};
        min-height: 20px;
        font-weight: 500;
    }}
    
    QPushButton:hover {{
        background: {theme['hover']};
        border: 2px solid {theme['accent']};
    }}
    
    QPushButton:pressed {{
        background: {theme['accent']};
        color: {theme['accent_text']};
        border: 2px solid {theme['accent']};
    }}
    
    QPushButton:disabled {{
        background: {theme['bg_dark']};
        color: {theme['text_disabled']};
        border: 2px solid {theme['border']};
    }}
    
    /* ========== INPUT FIELDS ========== */
    QLineEdit, QTextEdit, QPlainTextEdit {{
        background: {theme['bg_medium']};
        border: 1px solid {theme['border']};
        border-radius: 4px;
        padding: 6px;
        color: {theme['text_primary']};
        selection-background-color: {theme['accent']};
        selection-color: {theme['accent_text']};
    }}
    
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
        border: 2px solid {theme['accent']};
    }}

    QLineEdit[invalid="true"], QComboBox[invalid="true"], QSpinBox[invalid="true"], QDoubleSpinBox[invalid="true"] {{
        border: 2px solid #FF4D4F;
        background: {theme['bg_medium']};
    }}
    
    QSpinBox, QDoubleSpinBox {{
        background: {theme['bg_medium']};
        border: 1px solid {theme['border']};
        border-radius: 4px;
        padding: 4px;
        color: {theme['text_primary']};
    }}
    
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 2px solid {theme['accent']};
    }}
    
    QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        background: {theme['hover']};
        border: 1px solid {theme['border']};
        width: 20px;
    }}
    
    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {{
        background: {theme['accent']};
    }}
    
    /* ========== COMBO BOXES ========== */
    QComboBox {{
        background: {theme['bg_medium']};
        border: 1px solid {theme['border']};
        border-radius: 4px;
        padding: 6px;
        color: {theme['text_primary']};
    }}
    
    QComboBox:hover {{
        border: 2px solid {theme['accent']};
    }}
    
    QComboBox::drop-down {{
        border: none;
        width: 30px;
    }}
    
    QComboBox::down-arrow {{
        image: none;
    }}
    
    /* ========== LISTS & TABLES ========== */
    QListWidget, QTableWidget {{
        background: {theme['bg_medium']};
        border: 1px solid {theme['border']};
        border-radius: 6px;
        color: {theme['text_primary']};
        gridline-color: {theme['border']};
    }}
    
    QListWidget::item:selected, QTableWidget::item:selected {{
        background: {theme['accent']};
        color: {theme['accent_text']};
    }}
    
    QListWidget::item:hover, QTableWidget::item:hover {{
        background: {theme['hover']};
    }}
    
    QHeaderView::section {{
        background: {theme['bg_dark']};
        color: {theme['text_primary']};
        padding: 6px;
        border: none;
        border-right: 1px solid {theme['border']};
        border-bottom: 1px solid {theme['border']};
        font-weight: bold;
    }}
    
    /* ========== CHECKBOXES ========== */
    QCheckBox {{
        spacing: 8px;
        color: {theme['text_primary']};
    }}
    
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border: 2px solid {theme['border']};
        border-radius: 4px;
        background: {theme['bg_medium']};
    }}
    
    QCheckBox::indicator:hover {{
        border: 2px solid {theme['accent']};
    }}
    
    QCheckBox::indicator:checked {{
        background: {theme['accent']};
        border: 2px solid {theme['accent']};
    }}
    
    /* ========== SLIDERS ========== */
    QSlider::groove:horizontal {{
        background: {theme['border']};
        height: 6px;
        border-radius: 3px;
    }}
    
    QSlider::handle:horizontal {{
        background: {theme['accent']};
        width: 18px;
        margin: -6px 0;
        border-radius: 9px;
        border: 1px solid {theme['accent']};
    }}
    
    QSlider::handle:horizontal:hover {{
        background: {theme['accent']};
        border: 2px solid {theme['text_primary']};
    }}
    
    QSlider::sub-page:horizontal {{
        background: {theme['accent']};
        border-radius: 3px;
    }}
    
    /* ========== PROGRESS BARS ========== */
    QProgressBar {{
        background: {theme['bg_medium']};
        border: 1px solid {theme['border']};
        border-radius: 4px;
        text-align: center;
        color: {theme['text_primary']};
        height: 20px;
    }}
    
    QProgressBar::chunk {{
        background: {theme['accent']};
        border-radius: 3px;
    }}
    
    /* ========== GROUP BOXES ========== */
    QGroupBox {{
        border: 2px solid {theme['border']};
        border-radius: 6px;
        margin-top: 12px;
        padding-top: 10px;
        color: {theme['text_primary']};
        font-weight: bold;
    }}
    
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 5px 0 3px;
        color: {theme['accent']};
    }}
    
    /* ========== SCROLLBARS ========== */
    QScrollBar:vertical {{
        background: {theme['bg_medium']};
        border: 1px solid {theme['border']};
        width: 12px;
        border-radius: 6px;
    }}
    
    QScrollBar::handle:vertical {{
        background: {theme['scrollbar']};
        border-radius: 6px;
        min-height: 20px;
    }}
    
    QScrollBar::handle:vertical:hover {{
        background: {theme['scrollbar_hover']};
    }}
    
    QScrollBar::sub-line:vertical, QScrollBar::add-line:vertical {{
        border: none;
        background: none;
    }}

    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: {theme['bg_dark']};
        border-radius: 6px;
    }}
    
    QScrollBar:horizontal {{
        background: {theme['bg_medium']};
        border: 1px solid {theme['border']};
        height: 12px;
        border-radius: 6px;
    }}
    
    QScrollBar::handle:horizontal {{
        background: {theme['scrollbar']};
        border-radius: 6px;
        min-width: 20px;
    }}
    
    QScrollBar::handle:horizontal:hover {{
        background: {theme['scrollbar_hover']};
    }}
    
    QScrollBar::sub-line:horizontal, QScrollBar::add-line:horizontal {{
        border: none;
        background: none;
    }}

    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: {theme['bg_dark']};
        border-radius: 6px;
    }}
    
    /* ========== TABS ========== */
    QTabWidget::pane {{
        border: 1px solid {theme['border']};
        border-radius: 6px;
        background: {theme['bg_dark']};
    }}
    
    QTabBar::tab {{
        background: {theme['bg_medium']};
        border: 1px solid {theme['border']};
        padding: 8px 16px;
        margin-right: 2px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        color: {theme['text_secondary']};
    }}
    
    QTabBar::tab:selected {{
        background: {theme['accent']};
        color: {theme['accent_text']};
        border: 1px solid {theme['accent']};
        font-weight: bold;
    }}
    
    QTabBar::tab:hover {{
        background: {theme['hover']};
    }}
    
    /* ========== LABELS & TEXT ========== */
    QLabel {{
        color: {theme['text_primary']};
    }}
    
    /* ========== TOOLTIPS ========== */
    QToolTip {{
        background: {theme['bg_medium']};
        color: {theme['text_primary']};
        border: 1px solid {theme['accent']};
        border-radius: 4px;
        padding: 4px;
    }}

    /* ========== CONTEXT MENUS ========== */
    QMenu {{
        background: {theme['bg_medium']};
        border: 1px solid {theme['border']};
        border-radius: 6px;
        color: {theme['text_primary']};
        padding: 4px;
    }}

    QMenu::item {{
        padding: 6px 28px 6px 14px;
        border-radius: 4px;
        color: {theme['text_primary']};
        background: transparent;
    }}

    QMenu::item:selected {{
        background: {theme['accent']};
        color: {theme['accent_text']};
    }}

    QMenu::item:disabled {{
        color: {theme['text_disabled']};
    }}

    QMenu::separator {{
        height: 1px;
        background: {theme['border']};
        margin: 4px 8px;
    }}
    
    /* ========== SCROLL AREA ========== */
    QScrollArea {{
        background: {theme['bg_dark']};
        border: 1px solid {theme['border']};
        border-radius: 6px;
    }}
    
    /* ========== SEPARATORS ========== */
    QFrame[frameShape="4"], QFrame[frameShape="5"] {{
        color: {theme['border']};
    }}
    
    /* ========== ACCENT LABELS ========== */
    #AppLogo, #HomePageTitle, #FeatureTitle, #ProfileLabel {{
        color: {theme['accent']};
    }}
    
    /* ========== ADD ACTION BUTTON ========== */
    QPushButton#AddActionBtn {{
        background: {theme['hover']};
        border: 2px solid {theme['border']};
        color: {theme['text_primary']};
        font-weight: bold;
        font-size: 12px;
    }}
    
    QPushButton#AddActionBtn:hover {{
        background: {theme['accent']};
        color: {theme['accent_text']};
        border: 2px solid {theme['accent']};
    }}
    
    QPushButton#AddActionBtn:pressed {{
        background: {theme['bg_dark']};
        color: {theme['accent']};
        border: 2px solid {theme['accent']};
    }}

    /* ========== TEMPLATE BUTTONS ========== */
    QPushButton#TemplateCategoryBtn {{
        text-align: left;
        padding: 4px 8px;
        font-weight: bold;
        font-size: 10px;
        background: {theme['bg_medium']};
        border: 1px solid {theme['border']};
        border-radius: 4px;
        color: {theme['text_primary']};
    }}

    QPushButton#TemplateCategoryBtn:hover {{
        background: {theme['hover']};
        border: 1px solid {theme['accent']};
    }}

    QPushButton#TemplateCategoryBtn:checked {{
        background: {theme['hover']};
        border: 1px solid {theme['accent']};
        color: {theme['text_primary']};
    }}

    QWidget#TemplateCard {{
        background: {theme['bg_medium']};
        border: 2px solid {theme['border']};
        border-radius: 8px;
    }}

    QWidget#TemplateCard:hover {{
        border: 2px solid {theme['accent']};
        background: {theme['hover']};
    }}

    QLabel#TemplateTitle {{
        color: {theme['text_primary']};
        font-size: 12px;
        font-weight: 700;
        background: transparent;
    }}

    QLabel#TemplateSummary {{
        color: {theme['text_secondary']};
        font-size: 10px;
        font-weight: 500;
        background: transparent;
    }}

    QPushButton#TemplateInsertBtn {{
        background: {theme['bg_dark']};
        border: 1px solid {theme['border']};
        border-radius: 6px;
        color: {theme['text_primary']};
        font-size: 11px;
        font-weight: 700;
        padding: 6px 10px;
    }}

    QPushButton#TemplateInsertBtn:hover {{
        background: {theme['accent']};
        color: {theme['accent_text']};
        border: 1px solid {theme['accent']};
    }}
    """


# ============================
# ACTION TEMPLATES - Organized by Game
# ============================

# Helper function to generate inventory drops (useful for OSRS and similar games)
def _generate_inventory_drop(items=27):
    """Generate a sequence of key presses to drop all inventory items (1-27)."""
    return [{"action_type": "key", "key": str(i % 10), "hold_duration": 50, "press_type": "press", "enabled": True} for i in range(1, items + 1)]

ACTION_TEMPLATES = {
    # ====== OSRS (Old School RuneScape) ======
    "OSRS: Copper Mining": [
        {"action_type": "region_watcher", "x": 500, "y": 200, "width": 300, "height": 50, "target_color": "#808080", "tolerance": 25, "check_type": "appears", "description": "Wait for ore depleted", "enabled": True},
        {"action_type": "mouse_move", "x": 640, "y": 300, "relative": False, "duration": 250, "enabled": True},
        {"action_type": "delay", "duration": 1200, "randomize": True, "random_min": 1000, "random_max": 1500, "enabled": True},
        {"action_type": "mouse_click", "x": 640, "y": 300, "button": "left", "clicks": 1, "enabled": True},
        {"action_type": "delay", "duration": 5500, "randomize": True, "random_min": 5000, "random_max": 6000, "enabled": True}
    ],
    
    "OSRS: AFK Fishing": [
        {"action_type": "loop_start", "loop_type": "infinite", "enabled": True},
        {"action_type": "mouse_click", "x": 400, "y": 350, "button": "left", "clicks": 1, "enabled": True},
        {"action_type": "delay", "duration": 5000, "randomize": True, "random_min": 4500, "random_max": 5500, "enabled": True},
        {"action_type": "loop_end", "enabled": True}
    ],
    
    "OSRS: Alching": [
        {"action_type": "loop_start", "count": 0, "enabled": True},
        {"action_type": "key", "key": "f1", "hold_duration": 50, "press_type": "press", "enabled": True},
        {"action_type": "delay", "duration": 200, "randomize": True, "random_min": 150, "random_max": 250, "enabled": True},
        {"action_type": "mouse_click", "x": 800, "y": 500, "button": "left", "clicks": 1, "enabled": True},
        {"action_type": "delay", "duration": 3200, "randomize": True, "random_min": 3000, "random_max": 3400, "enabled": True},
        {"action_type": "loop_end", "enabled": True}
    ],
    
    "OSRS: Inventory Drop": [
        {"action_type": "loop_start", "count": 1, "enabled": True},
        {"action_type": "key", "key": "1", "hold_duration": 50, "press_type": "press", "enabled": True},
        {"action_type": "key", "key": "2", "hold_duration": 50, "press_type": "press", "enabled": True},
        {"action_type": "key", "key": "3", "hold_duration": 50, "press_type": "press", "enabled": True},
        {"action_type": "key", "key": "4", "hold_duration": 50, "press_type": "press", "enabled": True},
        {"action_type": "delay", "duration": 300, "randomize": False, "enabled": True},
        {"action_type": "key", "key": "5", "hold_duration": 50, "press_type": "press", "enabled": True},
        {"action_type": "key", "key": "6", "hold_duration": 50, "press_type": "press", "enabled": True},
        {"action_type": "key", "key": "7", "hold_duration": 50, "press_type": "press", "enabled": True},
        {"action_type": "loop_end", "enabled": True}
    ],
    
    "OSRS: Woodcutting": [
        {"action_type": "region_watcher", "x": 350, "y": 150, "width": 200, "height": 200, "target_color": "#654321", "tolerance": 30, "check_type": "disappears", "description": "Wait for tree depleted", "enabled": True},
        {"action_type": "delay", "duration": 1000, "randomize": True, "random_min": 800, "random_max": 1200, "enabled": True},
        {"action_type": "mouse_move", "x": 450, "y": 250, "relative": False, "duration": 300, "enabled": True},
        {"action_type": "mouse_click", "x": 450, "y": 250, "button": "left", "clicks": 1, "enabled": True},
        {"action_type": "delay", "duration": 3000, "randomize": True, "random_min": 2800, "random_max": 3200, "enabled": True}
    ],
    
    "OSRS: Smithing": [
        {"action_type": "loop_start", "loop_type": "infinite", "enabled": True},
        {"action_type": "key", "key": "space", "hold_duration": 100, "press_type": "press", "enabled": True},
        {"action_type": "delay", "duration": 1500, "randomize": True, "random_min": 1300, "random_max": 1700, "enabled": True},
        {"action_type": "loop_end", "enabled": True}
    ],
    
    "OSRS: Burning Logs": [
        {"action_type": "loop_start", "loop_type": "infinite", "enabled": True},
        {"action_type": "mouse_move", "x": 700, "y": 400, "relative": False, "duration": 200, "enabled": True},
        {"action_type": "mouse_click", "x": 700, "y": 400, "button": "right", "clicks": 1, "enabled": True},
        {"action_type": "delay", "duration": 1000, "randomize": True, "random_min": 800, "random_max": 1200, "enabled": True},
        {"action_type": "key", "key": "b", "hold_duration": 50, "press_type": "press", "enabled": True},
        {"action_type": "delay", "duration": 2500, "randomize": True, "random_min": 2300, "random_max": 2700, "enabled": True},
        {"action_type": "loop_end", "enabled": True}
    ],
    
    # ====== FiveM (GTA V Roleplay) ======
    "FiveM: Auto Cruise": [
        {"action_type": "key", "key": "w", "hold_duration": 500, "press_type": "hold", "enabled": True},
        {"action_type": "delay", "duration": 30000, "randomize": True, "random_min": 25000, "random_max": 35000, "enabled": True},
        {"action_type": "mouse_move", "x": 960, "y": 700, "relative": False, "duration": 500, "enabled": True},
        {"action_type": "key", "key": "s", "hold_duration": 200, "press_type": "press", "enabled": True}
    ],
    
    "FiveM: Click Interaction": [
        {"action_type": "loop_start", "loop_type": "infinite", "enabled": True},
        {"action_type": "key", "key": "e", "hold_duration": 50, "press_type": "press", "enabled": True},
        {"action_type": "delay", "duration": 2000, "randomize": True, "random_min": 1800, "random_max": 2200, "enabled": True},
        {"action_type": "mouse_click", "x": 960, "y": 540, "button": "left", "clicks": 1, "enabled": True},
        {"action_type": "delay", "duration": 500, "randomize": True, "random_min": 400, "random_max": 600, "enabled": True},
        {"action_type": "loop_end", "enabled": True}
    ],
    
    "FiveM: Slot Machine": [
        {"action_type": "loop_start", "count": 50, "enabled": True},
        {"action_type": "key", "key": "e", "hold_duration": 50, "press_type": "press", "enabled": True},
        {"action_type": "delay", "duration": 1500, "randomize": True, "random_min": 1300, "random_max": 1700, "enabled": True},
        {"action_type": "loop_end", "enabled": True}
    ],
    
    "FiveM: Store Robbery": [
        {"action_type": "mouse_click", "x": 960, "y": 540, "button": "left", "clicks": 1, "enabled": True},
        {"action_type": "delay", "duration": 3000, "randomize": True, "random_min": 2500, "random_max": 3500, "enabled": True},
        {"action_type": "key", "key": "e", "hold_duration": 50, "press_type": "press", "enabled": True},
        {"action_type": "delay", "duration": 1000, "randomize": True, "random_min": 800, "random_max": 1200, "enabled": True},
        {"action_type": "mouse_click", "x": 800, "y": 400, "button": "left", "clicks": 1, "enabled": True}
    ],
    
    # ====== Minecraft ======
    "Minecraft: Auto Mine": [
        {"action_type": "loop_start", "loop_type": "infinite", "enabled": True},
        {"action_type": "mouse_click", "x": 960, "y": 540, "button": "left", "clicks": 1, "enabled": True},
        {"action_type": "delay", "duration": 250, "randomize": True, "random_min": 200, "random_max": 300, "enabled": True},
        {"action_type": "loop_end", "enabled": True}
    ],
    
    "Minecraft: Block Builder": [
        {"action_type": "loop_start", "count": 64, "enabled": True},
        {"action_type": "mouse_click", "x": 960, "y": 540, "button": "right", "clicks": 1, "enabled": True},
        {"action_type": "key", "key": "w", "hold_duration": 100, "press_type": "press", "enabled": True},
        {"action_type": "delay", "duration": 120, "randomize": True, "random_min": 100, "random_max": 150, "enabled": True},
        {"action_type": "loop_end", "enabled": True}
    ],
    
    "Minecraft: AFK Fishing": [
        {"action_type": "loop_start", "loop_type": "infinite", "enabled": True},
        {"action_type": "mouse_click", "x": 960, "y": 540, "button": "right", "clicks": 1, "enabled": True},
        {"action_type": "delay", "duration": 18000, "randomize": True, "random_min": 16000, "random_max": 20000, "enabled": True},
        {"action_type": "mouse_click", "x": 960, "y": 540, "button": "left", "clicks": 1, "enabled": True},
        {"action_type": "delay", "duration": 600, "randomize": True, "random_min": 500, "random_max": 700, "enabled": True},
        {"action_type": "loop_end", "enabled": True}
    ],
    
    "Minecraft: Farm Crop": [
        {"action_type": "loop_start", "count": 0, "enabled": True},
        {"action_type": "mouse_click", "x": 960, "y": 540, "button": "left", "clicks": 1, "enabled": True},
        {"action_type": "key", "key": "w", "hold_duration": 150, "press_type": "press", "enabled": True},
        {"action_type": "delay", "duration": 200, "randomize": True, "random_min": 150, "random_max": 250, "enabled": True},
        {"action_type": "loop_end", "enabled": True}
    ],
    
    # ====== World of Warcraft ======
    "WoW: Melee DPS Rotation": [
        {"action_type": "loop_start", "loop_type": "infinite", "enabled": True},
        {"action_type": "key", "key": "1", "hold_duration": 50, "press_type": "press", "enabled": True},
        {"action_type": "delay", "duration": 1500, "randomize": True, "random_min": 1300, "random_max": 1700, "enabled": True},
        {"action_type": "key", "key": "2", "hold_duration": 50, "press_type": "press", "enabled": True},
        {"action_type": "delay", "duration": 2000, "randomize": True, "random_min": 1800, "random_max": 2200, "enabled": True},
        {"action_type": "key", "key": "3", "hold_duration": 50, "press_type": "press", "enabled": True},
        {"action_type": "delay", "duration": 2500, "randomize": True, "random_min": 2300, "random_max": 2700, "enabled": True},
        {"action_type": "loop_end", "enabled": True}
    ],
    
    "WoW: Gathering (Herb/Ore)": [
        {"action_type": "loop_start", "count": 0, "enabled": True},
        {"action_type": "key", "key": "f", "hold_duration": 50, "press_type": "press", "enabled": True},
        {"action_type": "delay", "duration": 3000, "randomize": True, "random_min": 2800, "random_max": 3200, "enabled": True},
        {"action_type": "key", "key": "w", "hold_duration": 300, "press_type": "press", "enabled": True},
        {"action_type": "delay", "duration": 2000, "randomize": True, "random_min": 1800, "random_max": 2200, "enabled": True},
        {"action_type": "loop_end", "enabled": True}
    ],
    
    "WoW: Healing Rotation": [
        {"action_type": "loop_start", "loop_type": "infinite", "enabled": True},
        {"action_type": "key", "key": "4", "hold_duration": 50, "press_type": "press", "enabled": True},
        {"action_type": "delay", "duration": 2000, "randomize": True, "random_min": 1800, "random_max": 2200, "enabled": True},
        {"action_type": "key", "key": "5", "hold_duration": 50, "press_type": "press", "enabled": True},
        {"action_type": "delay", "duration": 2500, "randomize": True, "random_min": 2300, "random_max": 2700, "enabled": True},
        {"action_type": "loop_end", "enabled": True}
    ],
    
    # ====== Valorant / Competitive Shooters ======
    "Valorant: Aim Practice": [
        {"action_type": "loop_start", "count": 10, "enabled": True},
        {"action_type": "mouse_click", "x": 960, "y": 540, "button": "left", "clicks": 1, "enabled": True},
        {"action_type": "delay", "duration": 500, "randomize": True, "random_min": 400, "random_max": 600, "enabled": True},
        {"action_type": "mouse_move", "x": 500, "y": 300, "relative": True, "duration": 200, "enabled": True},
        {"action_type": "delay", "duration": 300, "randomize": True, "random_min": 200, "random_max": 400, "enabled": True},
        {"action_type": "loop_end", "enabled": True}
    ],
    
    "Valorant: Ability Spam": [
        {"action_type": "loop_start", "loop_type": "infinite", "enabled": True},
        {"action_type": "key", "key": "q", "hold_duration": 50, "press_type": "press", "enabled": True},
        {"action_type": "delay", "duration": 800, "randomize": True, "random_min": 700, "random_max": 900, "enabled": True},
        {"action_type": "key", "key": "e", "hold_duration": 50, "press_type": "press", "enabled": True},
        {"action_type": "delay", "duration": 800, "randomize": True, "random_min": 700, "random_max": 900, "enabled": True},
        {"action_type": "loop_end", "enabled": True}
    ],
    
    # ====== General/Utility ======
    "Click Loop": [
        {"action_type": "loop_start", "count": 10, "enabled": True},
        {"action_type": "mouse_click", "x": 960, "y": 540, "button": "left", "clicks": 1, "enabled": True},
        {"action_type": "delay", "duration": 500, "randomize": True, "random_min": 400, "random_max": 600, "enabled": True},
        {"action_type": "loop_end", "enabled": True}
    ],
    
    "Key Spam": [
        {"action_type": "loop_start", "count": 10, "enabled": True},
        {"action_type": "key", "key": "space", "hold_duration": 50, "press_type": "press", "enabled": True},
        {"action_type": "delay", "duration": 100, "randomize": True, "random_min": 80, "random_max": 120, "enabled": True},
        {"action_type": "loop_end", "enabled": True}
    ],
    
    "Wait & Click": [
        {"action_type": "delay", "duration": 1000, "randomize": True, "random_min": 800, "random_max": 1200, "enabled": True},
        {"action_type": "mouse_click", "x": 960, "y": 540, "button": "left", "clicks": 1, "enabled": True},
        {"action_type": "delay", "duration": 500, "randomize": True, "random_min": 400, "random_max": 600, "enabled": True}
    ],
}


# ============================
# MACRO ACTION DATA STRUCTURES
# ============================

@dataclass
class MacroAction:
    """Base class for all macro actions."""
    action_type: str = ""  # Will be set by subclass __post_init__
    enabled: bool = True
    
    def to_dict(self) -> Dict:
        return asdict(self)

    @staticmethod
    def _filter_fields(cls, data: Dict) -> Dict:
        """Return a copy of data containing only keys that are valid fields of cls."""
        import dataclasses
        known = {f.name for f in dataclasses.fields(cls)}
        return {k: v for k, v in data.items() if k in known}

    @staticmethod
    def from_dict(data: Dict) -> 'MacroAction':
        data = dict(data or {})
        action_type = data.get('action_type')

        if action_type == 'mouse_click' and 'click_count' in data and 'clicks' not in data:
            data['clicks'] = data.pop('click_count')

        if action_type == 'key':
            return KeyAction(**MacroAction._filter_fields(KeyAction, data))
        elif action_type == 'mouse_click':
            return MouseClickAction(**MacroAction._filter_fields(MouseClickAction, data))
        elif action_type == 'mouse_move':
            return MouseMoveAction(**MacroAction._filter_fields(MouseMoveAction, data))
        elif action_type == 'delay':
            return DelayAction(**MacroAction._filter_fields(DelayAction, data))
        elif action_type == 'loop_start':
            return LoopStartAction(**MacroAction._filter_fields(LoopStartAction, data))
        elif action_type == 'loop_end':
            return LoopEndAction(**MacroAction._filter_fields(LoopEndAction, data))
        elif action_type == 'pixel_check':
            return PixelCheckAction(**MacroAction._filter_fields(PixelCheckAction, data))
        elif action_type == 'image_match':
            return ImageMatchAction(**MacroAction._filter_fields(ImageMatchAction, data))
        elif action_type == 'region_watcher':
            return RegionColorWatcherAction(**MacroAction._filter_fields(RegionColorWatcherAction, data))
        elif action_type == 'window_focus_check':
            return WindowFocusCheckAction(**MacroAction._filter_fields(WindowFocusCheckAction, data))
        elif action_type == 'run_profile':
            return RunProfileAction(**MacroAction._filter_fields(RunProfileAction, data))
        elif action_type == 'conditional_branch':
            # Use special deserialization for conditional branches (handles nested actions)
            return ConditionalBranchAction.from_dict_conditional(data)
        elif action_type == 'skill_check_digits':
            return SkillCheckDigitsAction(**MacroAction._filter_fields(SkillCheckDigitsAction, data))
        else:
            return MacroAction(**MacroAction._filter_fields(MacroAction, data))

@dataclass
class KeyAction(MacroAction):
    """Keyboard key press action."""
    key: str = "a"
    hold_duration: int = 50  # milliseconds
    press_type: str = "press"  # "press", "hold", "release"
    
    def __post_init__(self):
        self.action_type = "key"

@dataclass
class MouseClickAction(MacroAction):
    """Mouse click action."""
    button: str = "left"  # "left", "right", "middle"
    x: float = 0
    y: float = 0
    relative: bool = False
    pct_screen: bool = False
    clicks: int = 1
    
    def __post_init__(self):
        self.action_type = "mouse_click"

@dataclass
class MouseMoveAction(MacroAction):
    """Mouse movement action."""
    x: float = 0
    y: float = 0
    relative: bool = False
    pct_screen: bool = False
    duration: int = 100  # milliseconds for smooth movement
    
    def __post_init__(self):
        self.action_type = "mouse_move"

@dataclass
class DelayAction(MacroAction):
    """Delay/wait action."""
    duration: int = 1000  # milliseconds
    randomize: bool = False
    random_min: int = 0
    random_max: int = 0
    
    def __post_init__(self):
        self.action_type = "delay"

@dataclass
class LoopStartAction(MacroAction):
    """Start of loop block."""
    loop_type: str = "count"  # "count", "infinite", "time"
    count: int = 10
    duration_seconds: int = 60
    
    def __post_init__(self):
        self.action_type = "loop_start"

@dataclass
class LoopEndAction(MacroAction):
    """End of loop block."""
    
    def __post_init__(self):
        self.action_type = "loop_end"

@dataclass
class PixelCheckAction(MacroAction):
    """Check pixel color at position."""
    x: int = 0
    y: int = 0
    color: str = "#FFFFFF"
    tolerance: int = 10
    wait_for_match: bool = True
    timeout_ms: int = 5000
    poll_interval_ms: int = 30
    action_if_match: str = "continue"  # "continue", "skip_next", "break_loop"
    trigger_macro_name: str = ""  # Macro to run if condition is met
    
    def __post_init__(self):
        self.action_type = "pixel_check"

@dataclass
class ImageMatchAction(MacroAction):
    """Match image template on screen."""
    template_path: str = ""
    confidence: float = 0.8
    region_x: int = 0
    region_y: int = 0
    region_w: int = 1920
    region_h: int = 1080
    action_if_match: str = "continue"
    
    def __post_init__(self):
        self.action_type = "image_match"

@dataclass
class RegionColorWatcherAction(MacroAction):
    """Watch a region for color presence/change. Gaming-focused for health bars, cooldowns, etc."""
    x: int = 0
    y: int = 0
    width: int = 100
    height: int = 20
    target_color: str = "#FF0000"  # e.g., red for health bar
    tolerance: int = 15
    check_type: str = "appears"  # "appears", "disappears", "increases_brightness", "decreases_brightness"
    wait_timeout_ms: int = 5000
    description: str = ""  # e.g., "Watch health bar for red"
    trigger_macro_name: str = ""  # Macro to run if condition is met
    
    def __post_init__(self):
        self.action_type = "region_watcher"

@dataclass
class WindowFocusCheckAction(MacroAction):
    """Check if specific game window is focused before proceeding."""
    window_title_contains: str = ""  # e.g., "RuneScape"
    timeout_ms: int = 1000
    description: str = ""  # e.g., "Verify RuneScape is focused"
    
    def __post_init__(self):
        self.action_type = "window_focus_check"

@dataclass
class RunProfileAction(MacroAction):
    """Run another saved profile by name (nested execution)."""
    profile_name: str = ""

    def __post_init__(self):
        self.action_type = "run_profile"

@dataclass
class ConditionalBranchAction(MacroAction):
    """Conditional branching - IF condition THEN execute if_true_actions ELSE execute if_false_actions."""
    condition_type: str = "pixel_match"  # "pixel_match", "image_match", "region_watch"
    x: int = 0
    y: int = 0
    color: str = "#000000"
    tolerance: int = 15
    template_path: str = ""
    confidence: float = 0.8
    region_x: int = 0
    region_y: int = 0
    region_w: int = 1920
    region_h: int = 1080
    
    # nested action lists for the two execution paths
    if_true_actions: list = None
    if_false_actions: list = None

    # old index-based fields, kept so older saves still load
    if_true_action_index: int = -1
    if_false_action_index: int = 1
    
    description: str = ""
    
    def __post_init__(self):
        self.action_type = "conditional_branch"
        # Initialize nested action lists if not provided
        if self.if_true_actions is None:
            self.if_true_actions = []
        if self.if_false_actions is None:
            self.if_false_actions = []
    
    def to_dict(self) -> Dict:
        """Serialize to dict, converting nested actions to dicts."""
        d = {
            'action_type': self.action_type,
            'enabled': self.enabled,
            'condition_type': self.condition_type,
            'x': self.x,
            'y': self.y,
            'color': self.color,
            'tolerance': self.tolerance,
            'template_path': self.template_path,
            'confidence': self.confidence,
            'region_x': self.region_x,
            'region_y': self.region_y,
            'region_w': self.region_w,
            'region_h': self.region_h,
            'if_true_actions': [a.to_dict() for a in self.if_true_actions] if self.if_true_actions else [],
            'if_false_actions': [a.to_dict() for a in self.if_false_actions] if self.if_false_actions else [],
            'if_true_action_index': self.if_true_action_index,
            'if_false_action_index': self.if_false_action_index,
            'description': self.description
        }
        return d
    
    @staticmethod
    def from_dict_conditional(data: Dict) -> 'ConditionalBranchAction':
        """Deserialize from dict, reconstructing nested actions."""
        from copy import deepcopy
        data = deepcopy(data)
        
        # Reconstruct nested action lists
        if_true_actions = []
        if_false_actions = []
        
        for action_dict in data.pop('if_true_actions', []):
            action = MacroAction.from_dict(action_dict)
            if action:
                if_true_actions.append(action)
        
        for action_dict in data.pop('if_false_actions', []):
            action = MacroAction.from_dict(action_dict)
            if action:
                if_false_actions.append(action)
        
        # Create conditional branch with reconstructed nested actions
        cond = ConditionalBranchAction(**data)
        cond.if_true_actions = if_true_actions
        cond.if_false_actions = if_false_actions
        return cond

@dataclass
class SkillCheckDigitsAction(MacroAction):
    """Detect digits in a region and press corresponding keys in order (e.g., 1325)."""
    region_x: int = 0
    region_y: int = 0
    region_w: int = 300
    region_h: int = 120
    max_digits: int = 6
    key_delay_ms: int = 60
    key_press_ms: int = 40

    def __post_init__(self):
        self.action_type = "skill_check_digits"

# ============================
# MACRO PROFILE
# ============================

@dataclass
class MacroProfile:
    """Complete macro profile with actions and settings."""
    name: str
    game: str  # "OSRS", "FiveM", "General", etc.
    description: str = ""
    hotkey: str = "None"
    actions: List[MacroAction] = None
    loop_enabled: bool = False
    loop_count: int = 1
    
    def __post_init__(self):
        if self.actions is None:
            self.actions = []
    
    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'game': self.game,
            'description': self.description,
            'hotkey': self.hotkey,
            'actions': [a.to_dict() for a in self.actions],
            'loop_enabled': self.loop_enabled,
            'loop_count': self.loop_count
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'MacroProfile':
        # Basic validation
        if not isinstance(data, dict):
            raise ValueError("Profile data must be a dictionary")
        if 'name' not in data:
            logger.warning("Profile missing 'name' field, using default")
        if 'actions' in data and not isinstance(data.get('actions'), list):
            logger.warning("Profile 'actions' field is not a list, resetting to empty")
            data['actions'] = []
        
        # Deserialize actions with error handling
        actions = []
        for idx, action_data in enumerate(data.get('actions', [])):
            try:
                actions.append(MacroAction.from_dict(action_data))
            except Exception as e:
                logger.warning(f"Skipping malformed action at index {idx}: {e}")
        
        return MacroProfile(
            name=data.get('name', 'Untitled'),
            game=data.get('game', 'General'),
            description=data.get('description', ''),
            hotkey=data.get('hotkey', 'None'),
            actions=actions,
            loop_enabled=data.get('loop_enabled', False),
            loop_count=data.get('loop_count', 1)
        )
    
    def save_to_file(self, directory: str):
        """Save profile to JSON file with a sanitized, collision-safe filename."""
        import re
        Path(directory).mkdir(parents=True, exist_ok=True)
        # Strip all characters that are illegal in Windows filenames
        _illegal = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
        safe_game = _illegal.sub('_', self.game).strip()
        safe_name = _illegal.sub('_', self.name).strip() or 'Untitled'
        base = f"{safe_game}_{safe_name}".replace(" ", "_")

        # Find a filename that either (a) doesn't exist yet, or (b) already belongs to this
        # same profile (same name+game), so we can overwrite it safely.
        candidate = os.path.join(directory, f"{base}.json")
        counter = 2
        while os.path.exists(candidate):
            try:
                with open(candidate, 'r', encoding='utf-8') as _f:
                    existing_name = json.load(_f).get('name', '')
            except Exception:
                existing_name = ''
            if existing_name.strip().lower() == self.name.strip().lower():
                break  # same profile - overwrite
            candidate = os.path.join(directory, f"{base}_{counter}.json")
            counter += 1

        filepath = candidate
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2)
        return filepath
    
    @staticmethod
    def load_from_file(filepath: str) -> 'MacroProfile':
        """Load profile from JSON file with validation."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return MacroProfile.from_dict(data)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in profile file {filepath}: {e}")
            raise ValueError(f"Corrupt profile file: {filepath}") from e
        except Exception as e:
            logger.error(f"Failed to load profile from {filepath}: {e}")
            raise

# ============================
# MACRO EXECUTOR (Worker Thread)
# ============================

class MacroExecutor(QThread):
    """Execute macro actions in background thread."""
    progress = Signal(int, str)  # progress percentage, status message
    finished = Signal(str)  # completion message
    error = Signal(str)  # error message
    
    def __init__(self, profile: MacroProfile, force_randomize_delays: bool = False):
        super().__init__()
        self.profile = profile
        self.is_running = True
        self.is_paused = False
        self.force_randomize_delays = force_randomize_delays
        self._nest_depth = 0  # tracks RunProfile / trigger_macro nesting level
        
        # Import automation libraries
        try:
            from pynput.keyboard import Controller as KeyboardController, Key
            from pynput.mouse import Controller as MouseController, Button
            self.keyboard = KeyboardController()
            self.mouse = MouseController()
            self.Key = Key
            self.Button = Button
            self.has_pynput = True
            # Build key map once - reused by every _execute_key_action call
            self._key_map = {
                'space': Key.space,
                'enter': Key.enter,
                'return': Key.enter,
                'tab': Key.tab,
                'shift': Key.shift,
                'shift_l': Key.shift_l,
                'shift_r': Key.shift_r,
                'ctrl': Key.ctrl,
                'ctrl_l': Key.ctrl_l,
                'ctrl_r': Key.ctrl_r,
                'alt': Key.alt,
                'alt_l': Key.alt_l,
                'alt_r': Key.alt_r,
                'alt_gr': Key.alt_gr,
                'cmd': Key.cmd,
                'cmd_l': Key.cmd_l,
                'cmd_r': Key.cmd_r,
                'win': Key.cmd,
                'super': Key.cmd,
                'menu': Key.menu,
                'esc': Key.esc,
                'escape': Key.esc,
                'up': Key.up,
                'down': Key.down,
                'left': Key.left,
                'right': Key.right,
                'backspace': Key.backspace,
                'delete': Key.delete,
                'home': Key.home,
                'end': Key.end,
                'page_up': Key.page_up,
                'page_down': Key.page_down,
                'insert': Key.insert,
                'caps_lock': Key.caps_lock,
                'num_lock': Key.num_lock,
                'scroll_lock': Key.scroll_lock,
                'print_screen': Key.print_screen,
                'pause': Key.pause,
                'f1': Key.f1, 'f2': Key.f2, 'f3': Key.f3,
                'f4': Key.f4, 'f5': Key.f5, 'f6': Key.f6,
                'f7': Key.f7, 'f8': Key.f8, 'f9': Key.f9,
                'f10': Key.f10, 'f11': Key.f11, 'f12': Key.f12,
            }
            # Add f13-f20 only if available (pynput >= 1.6)
            try:
                self._key_map.update({
                    'f13': Key.f13, 'f14': Key.f14, 'f15': Key.f15,
                    'f16': Key.f16, 'f17': Key.f17, 'f18': Key.f18,
                    'f19': Key.f19, 'f20': Key.f20,
                })
            except AttributeError:
                logger.debug("F13-F20 keys not available in this pynput version")
        except ImportError:
            self.has_pynput = False
            logger.warning("pynput not installed - macro execution disabled")
    
    def stop(self):
        """Stop macro execution."""
        self.is_running = False
    
    def pause(self):
        """Pause macro execution."""
        self.is_paused = True
    
    def resume(self):
        """Resume macro execution."""
        self.is_paused = False
    
    def run(self):
        """Execute macro actions."""
        if not self.has_pynput:
            self.error.emit("Input automation backend unavailable in this runtime")
            return
        
        try:
            loops = self.profile.loop_count if self.profile.loop_enabled else 1
            is_infinite = self.profile.loop_enabled and loops <= 0
            if is_infinite:
                loops = 1
            loop_num = 0
            while self.is_running and (is_infinite or loop_num < loops):
                if not self.is_running:
                    break
                self._execute_actions_with_loops(self.profile.actions, loop_num, loops, is_infinite)
                loop_num += 1
            self.finished.emit(f"Macro '{self.profile.name}' completed successfully")
        except Exception as e:
            logger.error(f"Macro execution error: {e}")
            self.error.emit(f"Error: {str(e)}")
    
    def _execute_actions_with_loops(self, actions: list, outer_loop_num: int = 0,
                                     outer_loops: int = 1, outer_is_infinite: bool = True):
        """Run through an action list, handling loop_start / loop_end markers."""
        n = len(actions)
        i = 0
        loop_stack = []  # each frame: {'start', 'type', 'iteration', 'max', 'end_time'}
        while i < n:
            while self.is_paused and self.is_running:
                time.sleep(0.05)
            if not self.is_running:
                return
            action = actions[i]
            if not action.enabled:
                i += 1
                continue
            if action.action_type == "loop_start":
                loop_type = getattr(action, 'loop_type', 'count')
                count = max(1, int(getattr(action, 'count', 10)))
                duration_seconds = int(getattr(action, 'duration_seconds', 60))
                loop_stack.append({
                    'start': i + 1,
                    'type': loop_type,
                    'iteration': 0,
                    'max': count,
                    'end_time': time.time() + duration_seconds,
                })
                i += 1
                continue
            if action.action_type == "loop_end":
                if not loop_stack:
                    i += 1
                    continue
                frame = loop_stack[-1]
                frame['iteration'] += 1
                if frame['type'] == 'infinite':
                    keep = True
                elif frame['type'] == 'count':
                    keep = frame['iteration'] < frame['max']
                else:  # time-based
                    keep = time.time() < frame['end_time']
                if keep and self.is_running:
                    i = frame['start']
                else:
                    loop_stack.pop()
                    i += 1
                continue
            depth_tag = '[L] ' * len(loop_stack)
            if outer_is_infinite:
                pct = 0
                status = f"Loop {outer_loop_num + 1}/\u221e {depth_tag}Action {i + 1}/{n}: {action.action_type}"
            else:
                pct = int(((outer_loop_num * n + i + 1) / max(1, outer_loops * n)) * 100)
                status = f"Loop {outer_loop_num + 1}/{outer_loops} {depth_tag}Action {i + 1}/{n}: {action.action_type}"
            self.progress.emit(pct, status)
            self._execute_action(action)
            i += 1

    def _execute_action(self, action: MacroAction):
        """Execute a single macro action."""
        import random
        
        if action.action_type == "key":
            self._execute_key_action(action)
        
        elif action.action_type == "mouse_click":
            self._execute_mouse_click(action)
        
        elif action.action_type == "mouse_move":
            self._execute_mouse_move(action)
        
        elif action.action_type == "delay":
            duration = action.duration
            if self.force_randomize_delays:
                # Global humanize: apply random ±30% even if the action has no range
                if action.randomize and action.random_max > action.random_min:
                    duration = random.randint(action.random_min, action.random_max)
                else:
                    min_delay = max(1, int(action.duration * 0.7))
                    max_delay = max(min_delay, int(action.duration * 1.3))
                    duration = random.randint(min_delay, max_delay)
            elif action.randomize and action.random_max > action.random_min:
                # Per-action randomize flag - always honoured regardless of global setting
                duration = random.randint(action.random_min, action.random_max)
            time.sleep(duration / 1000.0)
        
        elif action.action_type == "pixel_check":
            self._execute_pixel_check(action)
        
        elif action.action_type == "image_match":
            self._execute_image_match(action)
        
        elif action.action_type == "region_watcher":
            self._execute_region_watcher(action)
        
        elif action.action_type == "window_focus_check":
            self._execute_window_focus_check(action)
        
        elif action.action_type == "conditional_branch":
            self._execute_conditional_branch(action)

        elif action.action_type == "skill_check_digits":
            self._execute_skill_check_digits(action)

        elif action.action_type == "run_profile":
            self._execute_run_profile(action)

    def _execute_skill_check_digits(self, action: SkillCheckDigitsAction):
        """OCR digits in region and press each matching key."""
        self.progress.emit(0, "Skill Check: checking OCR installation...")
        try:
            import pyautogui
            import pytesseract
        except ImportError as e:
            msg = f"Skill-check failed: missing dependency ({e.name})"
            logger.warning(msg)
            self.progress.emit(0, msg)
            return

        if not TESSERACT_AVAILABLE:
            msg = "Skill-check failed: OCR not found. Install tesseract.exe at ./teseract/tesseract.exe (or ./tesseract/tesseract.exe)"
            logger.warning(msg)
            self.progress.emit(0, msg)
            return

        try:
            screenshot = pyautogui.screenshot(region=(action.region_x, action.region_y, action.region_w, action.region_h))

            import PIL.ImageOps
            import PIL.ImageEnhance
            screenshot = screenshot.convert('L')
            screenshot = PIL.ImageOps.autocontrast(screenshot)
            screenshot = PIL.ImageEnhance.Sharpness(screenshot).enhance(2.0)

            text = pytesseract.image_to_string(
                screenshot,
                config='--psm 7 -c tessedit_char_whitelist=0123456789'
            )
            digits = ''.join(ch for ch in text if ch.isdigit())[:max(1, action.max_digits)]
            if not digits:
                self.progress.emit(0, "Skill-check: no digits detected")
                return

            for idx, digit in enumerate(digits, 1):
                if not self.is_running:
                    return
                self.progress.emit(int((idx / len(digits)) * 100), f"Skill Check key: {digit}")
                self._execute_key_action(KeyAction(key=digit, hold_duration=action.key_press_ms, press_type="press"))
                time.sleep(action.key_delay_ms / 1000.0)

            self.progress.emit(100, f"Skill-check complete: {digits}")
        except Exception as e:
            msg = f"Skill-check action failed: {e}"
            logger.error(msg, exc_info=True)
            self.progress.emit(0, msg)
    
    def _execute_key_action(self, action: KeyAction):
        """Execute keyboard action."""
        key = action.key.lower() if action.key else ''

        key_map = self._key_map

        key_to_press = key_map.get(key, key)
        
        try:
            if action.press_type == "press":
                self.keyboard.press(key_to_press)
                time.sleep(action.hold_duration / 1000.0)
                self.keyboard.release(key_to_press)
            elif action.press_type == "hold":
                self.keyboard.press(key_to_press)
                time.sleep(action.hold_duration / 1000.0)
            elif action.press_type == "release":
                self.keyboard.release(key_to_press)
        except Exception as e:
            logger.warning(f"Key action failed for '{key}': {e}")
            raise ValueError(f"Unknown key '{key}' - check your macro action") from e
    
    def _execute_mouse_click(self, action: MouseClickAction):
        """Execute mouse click action."""
        if not action.relative:
            x, y = action.x, action.y
            if getattr(action, 'pct_screen', False):
                geom = QGuiApplication.primaryScreen().geometry()
                x = int(float(x) * geom.width())
                y = int(float(y) * geom.height())
            self.mouse.position = (int(x), int(y))

        button_map = {
            'left': self.Button.left,
            'right': self.Button.right,
            'middle': self.Button.middle
        }
        button = button_map.get(action.button, self.Button.left)

        # Handle both 'clicks' and legacy 'click_count' attribute names
        click_count = getattr(action, 'clicks', getattr(action, 'click_count', 1))
        for _ in range(click_count):
            self.mouse.click(button)
            time.sleep(0.05)

    def _execute_mouse_move(self, action: MouseMoveAction):
        """Execute mouse movement with smooth interpolation."""
        if action.relative:
            current_x, current_y = self.mouse.position
            target_x = current_x + action.x
            target_y = current_y + action.y
        elif getattr(action, 'pct_screen', False):
            geom = QGuiApplication.primaryScreen().geometry()
            target_x = int(float(action.x) * geom.width())
            target_y = int(float(action.y) * geom.height())
        else:
            target_x = action.x
            target_y = action.y

        # Smooth movement
        steps = max(10, action.duration // 10)
        current_x, current_y = self.mouse.position
        
        for step in range(steps):
            if not self.is_running:
                break
            
            progress = (step + 1) / steps
            x = int(current_x + (target_x - current_x) * progress)
            y = int(current_y + (target_y - current_y) * progress)
            self.mouse.position = (x, y)
            time.sleep(action.duration / 1000.0 / steps)
    
    def _execute_pixel_check(self, action: PixelCheckAction):
        """Check pixel color (requires PIL/Pillow and pyautogui)."""
        try:
            import pyautogui
            # Parse target color
            target_color = action.color.lstrip('#')
            r_target = int(target_color[0:2], 16)
            g_target = int(target_color[2:4], 16)
            b_target = int(target_color[4:6], 16)

            wait_for_match = getattr(action, 'wait_for_match', True)
            timeout_ms = max(100, int(getattr(action, 'timeout_ms', 5000)))
            poll_interval_ms = max(10, int(getattr(action, 'poll_interval_ms', 30)))

            start_time = time.time()
            while self.is_running:
                screenshot = pyautogui.screenshot(region=(action.x, action.y, 1, 1))
                pixel = screenshot.getpixel((0, 0))
                screenshot.close()

                r_diff = abs(pixel[0] - r_target)
                g_diff = abs(pixel[1] - g_target)
                b_diff = abs(pixel[2] - b_target)
                matched = r_diff <= action.tolerance and g_diff <= action.tolerance and b_diff <= action.tolerance

                if wait_for_match:
                    if matched:
                        logger.info(f"Pixel match found at ({action.x}, {action.y})")
                        # Trigger macro if specified
                        if hasattr(action, 'trigger_macro_name') and action.trigger_macro_name:
                            self._trigger_macro(action.trigger_macro_name)
                        break
                    elapsed_ms = (time.time() - start_time) * 1000
                    if elapsed_ms >= timeout_ms:
                        logger.info(f"Pixel check timeout at ({action.x}, {action.y}) after {timeout_ms}ms")
                        break
                    time.sleep(poll_interval_ms / 1000.0)
                else:
                    if matched:
                        logger.info(f"Pixel match found at ({action.x}, {action.y})")
                    else:
                        logger.info(f"Pixel mismatch at ({action.x}, {action.y})")
                    break
        
        except ImportError:
            logger.warning("pyautogui not installed - pixel check skipped")
    
    def _execute_image_match(self, action: ImageMatchAction):
        """Match image template on screen (requires OpenCV and pyautogui)."""
        try:
            import pyautogui
            location = pyautogui.locateOnScreen(
                action.template_path,
                confidence=action.confidence,
                region=(action.region_x, action.region_y, action.region_w, action.region_h)
            )
            
            if location:
                logger.info(f"Image matched at {location}")
            else:
                logger.info(f"Image not found: {action.template_path}")
        
        except ImportError:
            logger.warning("pyautogui/opencv not installed - image matching skipped")
        except Exception as e:
            logger.warning(f"Image matching failed: {e}")
    
    def _execute_region_watcher(self, action: RegionColorWatcherAction):
        """Watch a rectangular region for color presence/changes. Gaming-focused."""
        try:
            import pyautogui
            from PIL import Image
            
            start_time = time.time()
            check_interval = 0.02  # Poll every 20ms (50 FPS) instead of every frame
            last_check = 0

            # Capture baseline brightness for increases/decreases_brightness watch types
            baseline_brightness = None
            if action.check_type in ("increases_brightness", "decreases_brightness"):
                try:
                    _bs = pyautogui.screenshot(region=(action.x, action.y, action.width, action.height))
                    _pixels = list(_bs.getdata())
                    _bs.close()
                    baseline_brightness = sum(
                        0.2126 * p[0] + 0.7152 * p[1] + 0.0722 * p[2] for p in _pixels
                    ) / max(1, len(_pixels))
                except Exception:
                    baseline_brightness = 128.0  # fallback if baseline capture fails

            while time.time() - start_time < action.wait_timeout_ms / 1000.0:
                # cap check rate so we don't slam the CPU
                current_time = time.time() - start_time
                if current_time - last_check < check_interval:
                    time.sleep(0.005)  # Small sleep to avoid spinning
                    continue
                
                last_check = current_time
                
                # grab just the region we need, not the whole screen
                try:
                    screenshot = pyautogui.screenshot(region=(
                        action.x, action.y,
                        action.width, action.height
                    ))
                except Exception:
                    # Fallback to full screenshot if region capture fails
                    _full = pyautogui.screenshot()
                    screenshot = _full.crop((action.x, action.y, action.x + action.width, action.y + action.height))
                    _full.close()

                pixels = list(screenshot.getdata())
                screenshot.close()
                
                # Parse target color
                target_color = action.target_color.lstrip('#')
                r_target = int(target_color[0:2], 16)
                g_target = int(target_color[2:4], 16)
                b_target = int(target_color[4:6], 16)
                
                # Check if target color appears in region
                match_count = 0
                for pixel in pixels:
                    r_diff = abs(pixel[0] - r_target)
                    g_diff = abs(pixel[1] - g_target)
                    b_diff = abs(pixel[2] - b_target)
                    
                    if r_diff <= action.tolerance and g_diff <= action.tolerance and b_diff <= action.tolerance:
                        match_count += 1
                
                # need at least ~2% of region pixels to match before triggering
                match_threshold = max(5, int(len(pixels) * 0.02))
                if action.check_type == "appears" and match_count >= match_threshold:
                    logger.info(f"Region watcher detected color change: {action.description}")
                    if hasattr(action, 'trigger_macro_name') and action.trigger_macro_name:
                        self._trigger_macro(action.trigger_macro_name)
                    break
                elif action.check_type == "disappears" and match_count == 0:
                    logger.info(f"Region watcher detected disappearance: {action.description}")
                    if hasattr(action, 'trigger_macro_name') and action.trigger_macro_name:
                        self._trigger_macro(action.trigger_macro_name)
                    break
                elif action.check_type in ("increases_brightness", "decreases_brightness") and baseline_brightness is not None:
                    avg_brightness = sum(
                        0.2126 * p[0] + 0.7152 * p[1] + 0.0722 * p[2] for p in pixels
                    ) / max(1, len(pixels))
                    triggered = (
                        (action.check_type == "increases_brightness" and avg_brightness > baseline_brightness + 10)
                        or (action.check_type == "decreases_brightness" and avg_brightness < baseline_brightness - 10)
                    )
                    if triggered:
                        logger.info(f"Region watcher brightness change detected: {action.description}")
                        if hasattr(action, 'trigger_macro_name') and action.trigger_macro_name:
                            self._trigger_macro(action.trigger_macro_name)
                        break
        
        except ImportError:
            logger.warning("pyautogui not installed - region watcher skipped")
        except Exception as e:
            logger.warning(f"Region watcher failed: {e}")
    
    def _execute_window_focus_check(self, action: WindowFocusCheckAction):
        """Check if a window matching any of the pipe-separated title patterns is focused."""
        try:
            import pygetwindow

            # Support pipe-separated alternatives: "RuneScape | WoW" means either title.
            title_patterns = [t.strip() for t in action.window_title_contains.split('|') if t.strip()]
            if not title_patterns:
                return  # Nothing to match - skip silently

            start_time = time.time()
            while time.time() - start_time < action.timeout_ms / 1000.0:
                try:
                    focused_window = pygetwindow.getActiveWindow()
                    if focused_window and any(p in focused_window.title for p in title_patterns):
                        logger.info(f"Window check passed: {action.description}")
                        return
                except Exception as e:
                    logger.debug(f"Window focus polling error: {e}")

                time.sleep(0.1)

            logger.warning(f"Window check timeout: {action.description}")

        except ImportError:
            logger.warning("pygetwindow not installed - window focus check skipped")
        except Exception as e:
            logger.warning(f"Window focus check failed: {e}")
    
    def _trigger_macro(self, macro_name: str):
        """Trigger another macro by name (nested execution, max depth 5)."""
        MAX_NEST = 5
        self._nest_depth += 1
        try:
            if self._nest_depth > MAX_NEST:
                logger.warning(f"Macro nesting limit ({MAX_NEST}) reached - '{macro_name}' skipped to prevent recursion")
                return
            if not macro_name:
                return
            # Sanitize: strip path separators to prevent directory traversal
            safe_name = os.path.basename(macro_name.replace('\\', '/'))
            if not safe_name or safe_name in ('.', '..'):
                logger.warning(f"Rejected unsafe nested macro name: {macro_name!r}")
                return

            profiles_dir = os.path.join(get_base_dir(), "profiles")
            # Try name-based filename first
            macro_path = os.path.join(profiles_dir, f"{safe_name}.json")
            if not os.path.exists(macro_path):
                # Fallback: scan all profiles for a matching name field
                found = None
                for fname in os.listdir(profiles_dir):
                    if not fname.endswith('.json'):
                        continue
                    fp = os.path.join(profiles_dir, fname)
                    try:
                        with open(fp, 'r') as _f:
                            d = json.load(_f)
                        if d.get('name', '').strip().lower() == macro_name.strip().lower():
                            found = fp
                            break
                    except Exception:
                        continue
                if found:
                    macro_path = found
                else:
                    logger.warning(f"Macro '{macro_name}' not found in profiles")
                    return

            with open(macro_path, 'r') as f:
                data = json.load(f)
            macro_profile = MacroProfile.from_dict(data)
            logger.info(f"Triggering nested macro: {macro_name} (depth {self._nest_depth})")
            self._execute_profile(macro_profile)
        except Exception as e:
            logger.error(f"Failed to trigger macro '{macro_name}': {e}")
        finally:
            self._nest_depth -= 1

    def _execute_run_profile(self, action: 'RunProfileAction'):
        """Execute a profile by name from within an action list."""
        if not action.profile_name:
            logger.warning("Run profile action skipped: no profile selected")
            return
        self._trigger_macro(action.profile_name)

    def _execute_profile(self, profile: MacroProfile):
        """Execute a macro profile (used for nested/triggered macros)."""
        try:
            loops = profile.loop_count if profile.loop_enabled else 1
            is_infinite = profile.loop_enabled and loops <= 0
            if is_infinite:
                loops = 1
            loop_num = 0
            while self.is_running and (is_infinite or loop_num < loops):
                if not self.is_running:
                    break
                self._execute_actions_with_loops(profile.actions, loop_num, loops, is_infinite)
                loop_num += 1
        except Exception as e:
            logger.error(f"Error executing nested macro: {e}")
    
    def _execute_conditional_branch(self, action: ConditionalBranchAction):
        """Execute conditional branching logic - evaluate condition, then execute appropriate action list."""
        condition_result = False
        
        # Evaluate condition
        if action.condition_type == "pixel_match":
            # Check pixel color at (x, y) matches target color
            try:
                import pyautogui
                actual_color = pyautogui.pixel(action.x, action.y)
                target_rgb = self._hex_to_rgb(action.color)
                tolerance = action.tolerance
                
                # Check if color matches within tolerance
                condition_result = (
                    abs(actual_color[0] - target_rgb[0]) <= tolerance and
                    abs(actual_color[1] - target_rgb[1]) <= tolerance and
                    abs(actual_color[2] - target_rgb[2]) <= tolerance
                )
            except Exception as e:
                logger.warning(f"Pixel match check failed: {e}")
                condition_result = False
        
        elif action.condition_type == "image_match":
            # Check if image is found on screen
            try:
                import pyautogui

                if action.template_path and os.path.exists(action.template_path):
                    region = None
                    if action.region_w > 0 and action.region_h > 0:
                        region = (action.region_x, action.region_y, action.region_w, action.region_h)

                    location = pyautogui.locateOnScreen(
                        action.template_path,
                        confidence=float(action.confidence),
                        region=region
                    )
                    condition_result = location is not None
                else:
                    logger.warning("Conditional image_match skipped: template image not set or not found")
                    condition_result = False
            except Exception as e:
                logger.warning(f"Image match condition check failed: {e}")
                condition_result = False
        
        elif action.condition_type == "region_watch":
            # Check if target color appears in the selected region
            try:
                import pyautogui

                screenshot = pyautogui.screenshot(region=(action.region_x, action.region_y, action.region_w, action.region_h))
                target_rgb = self._hex_to_rgb(action.color)
                match_count = 0
                step = 10

                for y in range(0, screenshot.height, step):
                    for x in range(0, screenshot.width, step):
                        pixel = screenshot.getpixel((x, y))
                        if (
                            abs(pixel[0] - target_rgb[0]) <= action.tolerance and
                            abs(pixel[1] - target_rgb[1]) <= action.tolerance and
                            abs(pixel[2] - target_rgb[2]) <= action.tolerance
                        ):
                            match_count += 1

                condition_result = match_count > 3
            except Exception as e:
                logger.warning(f"Region watch condition check failed: {e}")
                condition_result = False
        
        # Execute appropriate action list
        if condition_result:
            self.progress.emit(0, f"Condition TRUE: executing {len(action.if_true_actions)} actions")
            self._execute_action_list(action.if_true_actions)
        else:
            self.progress.emit(0, f"Condition FALSE: executing {len(action.if_false_actions)} actions")
            self._execute_action_list(action.if_false_actions)
    
    def _execute_action_list(self, actions: list):
        """Run a list of actions, handling loop_start / loop_end markers."""
        if not actions:
            return
        self._execute_actions_with_loops(actions, outer_loop_num=0, outer_loops=1, outer_is_infinite=False)
    
    def _hex_to_rgb(self, hex_color: str) -> tuple:
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

# ============================
# BACKUP MANAGER
# ============================

class BackupManager:
    """Manage profile backups"""
    def __init__(self, profiles_dir="profiles", backup_dir="backups"):
        base = get_base_dir()
        self.profiles_dir = Path(os.path.join(base, profiles_dir))
        self.backup_dir = Path(os.path.join(base, backup_dir))
        self.backup_dir.mkdir(exist_ok=True, parents=True)
        self.max_backups = 10
        self._auto_backup_timer = None

    def start_auto_backup(self, interval_minutes: int = 30):
        """Schedule automatic backups every interval_minutes using a QTimer."""
        if self._auto_backup_timer is not None:
            return  # Already running
        self._auto_backup_timer = QTimer()
        self._auto_backup_timer.setInterval(interval_minutes * 60 * 1000)
        # Run backup on a daemon thread so ZIP I/O never blocks the UI
        self._auto_backup_timer.timeout.connect(self._backup_on_thread)
        self._auto_backup_timer.start()
        logger.info(f"Auto-backup timer started: every {interval_minutes} minutes")

    def _backup_on_thread(self):
        """Spawn a daemon thread for backup so main-thread UI is never blocked."""
        t = threading.Thread(target=self.create_backup, daemon=True)
        t.start()
    
    def create_backup(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{timestamp}.zip"
        backup_path = self.backup_dir / backup_name
        
        try:
            import zipfile
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for profile_file in self.profiles_dir.glob("*.json"):
                    zipf.write(profile_file, profile_file.name)
            
            # Keep only last 10 backups
            backups = sorted(self.backup_dir.glob("backup_*.zip"), reverse=True)
            for old_backup in backups[self.max_backups:]:
                old_backup.unlink()
            
            return backup_path, True
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return None, False
    
    def get_latest_backup_time(self):
        backups = sorted(self.backup_dir.glob("backup_*.zip"), reverse=True)
        if backups:
            return backups[0].stat().st_mtime
        return None

# ============================
# MACRO RECORDER & AFK DETECTION
# ============================

class MacroRecorder(QObject):
    """Record keyboard and mouse actions in real-time"""
    action_recorded = Signal(dict)
    recording_stopped = Signal()
    
    def __init__(self):
        super().__init__()
        self.recording = False
        self.actions = []
        self.start_time = None
        self.last_action_time = None
        self.keyboard_listener = None
        self.mouse_listener = None
        self.record_mouse_moves = False
        self.use_relative_coords = False  # store coords as % of screen size for portability
        self.min_delay_threshold_ms = 50
        self.mouse_move_min_interval_ms = 35
        self.mouse_move_min_distance_px = 5
        self.last_move_time = None
        self.last_move_pos = None
    
    def start_recording(self):
        self.recording = True
        self.actions = []
        self.start_time = time.time()
        self.last_action_time = self.start_time
        self.last_move_time = self.start_time
        self.last_move_pos = None
        
        try:
            from pynput import keyboard, mouse
            self.keyboard_listener = keyboard.Listener(on_press=self._on_key_press)
            self.keyboard_listener.start()
            self.mouse_listener = mouse.Listener(on_click=self._on_mouse_click, on_move=self._on_mouse_move)
            self.mouse_listener.start()
        except ImportError:
            logger.warning("pynput not installed - recording disabled")
    
    def stop_recording(self):
        self.recording = False
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        if self.mouse_listener:
            self.mouse_listener.stop()
        self.recording_stopped.emit()
        return self.actions
    
    def _add_delay_action(self):
        if self.last_action_time is None:
            return
        current_time = time.time()
        delay_ms = int((current_time - self.last_action_time) * 1000)
        if delay_ms >= self.min_delay_threshold_ms:
            action = {
                'action_type': 'delay', 'duration': delay_ms, 'randomize': True,
                'random_min': int(delay_ms * 0.9), 'random_max': int(delay_ms * 1.1), 'enabled': True
            }
            self.actions.append(action)
            self.action_recorded.emit(action)
        self.last_action_time = current_time
    
    def _on_key_press(self, key):
        if not self.recording:
            return
        self._add_delay_action()
        try:
            key_str = key.char
            if key_str is None:
                raise AttributeError  # treat as special key
        except AttributeError:
            key_str = str(key).replace('Key.', '')
        if not key_str:
            return  # skip empty/unrecognised keys
        action = {'action_type': 'key', 'key': key_str, 'hold_duration': 50, 'press_type': 'press', 'enabled': True}
        self.actions.append(action)
        self.action_recorded.emit(action)
    
    def _on_mouse_click(self, x, y, button, pressed):
        if not self.recording or not pressed:
            return
        self._add_delay_action()
        button_str = str(button).replace('Button.', '')
        if self.use_relative_coords:
            screen = QGuiApplication.primaryScreen()
            geom = screen.geometry()
            sw, sh = geom.width(), geom.height()
            rx = round(x / sw, 5)
            ry = round(y / sh, 5)
            action = {'action_type': 'mouse_click', 'x': rx, 'y': ry, 'button': button_str,
                      'clicks': 1, 'pct_screen': True, 'enabled': True}
        else:
            action = {'action_type': 'mouse_click', 'x': x, 'y': y, 'button': button_str,
                      'clicks': 1, 'pct_screen': False, 'enabled': True}
        self.actions.append(action)
        self.action_recorded.emit(action)

    def _on_mouse_move(self, x, y):
        if not self.recording or not self.record_mouse_moves:
            return

        current_time = time.time()
        if self.last_move_time is not None:
            elapsed_ms = (current_time - self.last_move_time) * 1000.0
            if elapsed_ms < self.mouse_move_min_interval_ms:
                return

        if self.last_move_pos is not None:
            dx = abs(x - self.last_move_pos[0])
            dy = abs(y - self.last_move_pos[1])
            if dx < self.mouse_move_min_distance_px and dy < self.mouse_move_min_distance_px:
                return

        self._add_delay_action()
        if self.use_relative_coords:
            screen = QGuiApplication.primaryScreen()
            geom = screen.geometry()
            sw, sh = geom.width(), geom.height()
            action = {
                'action_type': 'mouse_move',
                'x': round(x / sw, 5),
                'y': round(y / sh, 5),
                'relative': False,
                'pct_screen': True,
                'duration': max(10, self.mouse_move_min_interval_ms),
                'enabled': True
            }
        else:
            action = {
                'action_type': 'mouse_move',
                'x': int(x),
                'y': int(y),
                'relative': False,
                'pct_screen': False,
                'duration': max(10, self.mouse_move_min_interval_ms),
                'enabled': True
            }
        self.actions.append(action)
        self.action_recorded.emit(action)
        self.last_move_time = current_time
        self.last_move_pos = (x, y)

class AFKDetector(QObject):
    """Detect user AFK status"""
    afk_detected = Signal()
    activity_detected = Signal()
    
    def __init__(self, timeout_seconds=300):
        super().__init__()
        self.timeout_seconds = timeout_seconds
        self.enabled = False
        self.is_afk = False
        self.last_activity_time = datetime.now()
        self.keyboard_listener = None
        self.mouse_listener = None
        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self._check_afk_status)
        self.check_timer.setInterval(5000)
    
    def start(self):
        if not self.enabled:
            return
        self.last_activity_time = datetime.now()
        self.is_afk = False
        
        try:
            from pynput import keyboard, mouse
            self.keyboard_listener = keyboard.Listener(on_press=self._on_activity)
            self.keyboard_listener.start()
            self.mouse_listener = mouse.Listener(on_move=self._on_activity, on_click=self._on_activity)
            self.mouse_listener.start()
            self.check_timer.start()
        except ImportError:
            logger.warning("pynput not installed - AFK detection disabled")
    
    def stop(self):
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        if self.mouse_listener:
            self.mouse_listener.stop()
        self.check_timer.stop()
    
    def _on_activity(self, *args, **kwargs):
        self.last_activity_time = datetime.now()
        if self.is_afk:
            self.is_afk = False
            self.activity_detected.emit()
    
    def _check_afk_status(self):
        if not self.enabled:
            return
        now = datetime.now()
        elapsed = (now - self.last_activity_time).total_seconds()
        if elapsed >= self.timeout_seconds and not self.is_afk:
            self.is_afk = True
            self.afk_detected.emit()
    
    def set_timeout(self, seconds):
        self.timeout_seconds = seconds
    
    def set_enabled(self, enabled):
        self.enabled = enabled
        if not enabled:
            self.stop()
        else:
            self.start()

# ============================
# CUSTOM WIDGETS
# ============================

class NoWheelScrollArea(QScrollArea):
    """ScrollArea that only consumes wheel events when it can scroll.
    If at limits (or no scroll range), event is ignored so parent scroll area can handle it.
    """
    def wheelEvent(self, event):
        """Propagate wheel to parent when this area cannot scroll further."""
        bar = self.verticalScrollBar()
        delta_y = event.angleDelta().y()

        if bar is None or delta_y == 0:
            event.ignore()
            return

        can_scroll_up = bar.value() > bar.minimum()
        can_scroll_down = bar.value() < bar.maximum()

        if (delta_y > 0 and can_scroll_up) or (delta_y < 0 and can_scroll_down):
            super().wheelEvent(event)
            event.accept()
            return

        event.ignore()

def apply_dark_title_bar(widget):
    """Force dark native title bar on Windows 10/11 for any top-level window/dialog."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = int(widget.winId())
        value = ctypes.c_int(1)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd), ctypes.c_uint(attr),
                ctypes.byref(value), ctypes.sizeof(value)
            ) == 0:
                break
    except Exception:
        pass


class HelpDialog(QDialog):
    """Help and documentation dialog."""
    
    def showEvent(self, event):
        super().showEvent(event)
        apply_dark_title_bar(self)

    def __init__(self, parent=None, theme_name='midnight'):
        super().__init__(parent)
        self.setWindowTitle("🦥 Sloth - Complete Help & Documentation")
        self.setGeometry(100, 100, 1200, 800)
        self.setMinimumSize(900, 600)

        theme = THEMES.get(theme_name, THEMES['midnight'])
        bg_dark = theme['bg_dark']
        bg_medium = theme['bg_medium']
        border = theme['border']
        accent = theme['accent']
        text_primary = theme['text_primary']
        text_secondary = theme['text_secondary']
        hover = theme['hover']
        
        layout = QVBoxLayout(self)

        search_row = QHBoxLayout()
        self.help_search_input = QLineEdit()
        self.help_search_input.setPlaceholderText("Search help... (e.g. OSRS, delay, hotkey, region watcher)")
        self.help_search_input.returnPressed.connect(self._find_next)
        search_row.addWidget(self.help_search_input, 1)

        find_next_btn = QPushButton("Find Next")
        find_next_btn.clicked.connect(self._find_next)
        search_row.addWidget(find_next_btn)

        find_prev_btn = QPushButton("Find Prev")
        find_prev_btn.clicked.connect(self._find_prev)
        search_row.addWidget(find_prev_btn)

        layout.addLayout(search_row)
        
        # Help text
        self.help_text = QTextEdit()
        self.help_text.setReadOnly(True)
        self.help_text.setStyleSheet(
            f"QTextEdit {{ background: {bg_dark}; color: {text_primary}; border: 1px solid {border}; border-radius: 8px; padding: 10px; }}"
        )
        self.help_text.setHtml(f"""
<div style="font-family: 'Segoe UI'; color: {text_primary};">
    <h1 style="margin:0 0 4px 0; color:{accent};">🦥 Sloth Help Center</h1>
    <p style="margin:0 0 12px 0; color:{text_secondary};">Search with keywords like <b>profile</b>, <b>hotkey</b>, <b>conditional</b>, <b>region</b>, <b>image match</b>, <b>ocr</b>, <b>loop</b>, <b>backup</b>, <b>recording</b>.</p>

    <!-- ===== QUICK START + SHORTCUTS ===== -->
    <table width="100%" cellspacing="8" cellpadding="10" style="border-collapse:separate;">
        <tr>
            <td width="50%" style="background:{bg_medium}; border:1px solid {border}; border-radius:8px; vertical-align:top;">
                <h3 style="margin:0 0 8px 0; color:{accent};">Quick Start</h3>
                <ol style="margin:0; padding-left:18px; color:{text_primary};">
                    <li><b>Profile Manager</b> - create a profile, set name, game, hotkey (any key combo), loop mode.</li>
                    <li><b>Macro Editor</b> - insert a template or add actions manually.</li>
                    <li>Pick coordinates with the <b>Pick</b> button (cross-hair overlay).</li>
                    <li>Click <b>▶️ Test Run</b> to verify behavior before going live.</li>
                    <li>Press your configured <b>hotkey</b> (e.g. F6) to start/stop from anywhere.</li>
                    <li>Enable <b>🎲 Humanized Timings</b> to randomize delays automatically.</li>
                </ol>
            </td>
            <td width="50%" style="background:{bg_medium}; border:1px solid {border}; border-radius:8px; vertical-align:top;">
                <h3 style="margin:0 0 8px 0; color:{accent};">Keyboard Shortcuts</h3>
                <table width="100%" cellspacing="0" cellpadding="6" style="border-collapse:collapse;">
                    <tr><td style="color:{accent}; width:140px;"><b>Ctrl+C</b></td><td>Copy selected action(s)</td></tr>
                    <tr><td style="color:{accent};"><b>Ctrl+V</b></td><td>Paste after selection</td></tr>
                    <tr><td style="color:{accent};"><b>Ctrl+D</b></td><td>Duplicate selected action</td></tr>
                    <tr><td style="color:{accent};"><b>Ctrl+Z</b></td><td>Undo last change</td></tr>
                    <tr><td style="color:{accent};"><b>Ctrl+Y</b></td><td>Redo</td></tr>
                    <tr><td style="color:{accent};"><b>Delete</b></td><td>Remove selected action</td></tr>
                    <tr><td style="color:{accent};"><b>Double-click row</b></td><td>Edit that action inline</td></tr>
                    <tr><td style="color:{accent};"><b>Right-click row</b></td><td>Context menu (dup, move, delete)</td></tr>
                </table>
            </td>
        </tr>
    </table>

    <!-- ===== TOOL AREAS ===== -->
    <h2 style="margin:14px 0 6px 0; color:{accent};">Tool Areas</h2>
    <table width="100%" cellspacing="0" cellpadding="8" style="border-collapse:collapse; border:1px solid {border};">
        <tr style="background:{bg_medium}; color:{accent};">
            <th align="left" style="border:1px solid {border}; width:160px;">Area</th>
            <th align="left" style="border:1px solid {border};">What it does</th>
            <th align="left" style="border:1px solid {border};">Tips</th>
        </tr>
        <tr><td style="border:1px solid {border};"><b>Home</b></td><td style="border:1px solid {border};">Navigation and quick links</td><td style="border:1px solid {border};">Jump to Profile Manager or Editor from here</td></tr>
        <tr><td style="border:1px solid {border};"><b>Profile Manager</b></td><td style="border:1px solid {border};">Create / edit / import / export profiles</td><td style="border:1px solid {border};">Set unique hotkeys per profile (any key combo supported); use search/sort to find profiles fast</td></tr>
        <tr><td style="border:1px solid {border};"><b>Macro Editor</b></td><td style="border:1px solid {border};">Build and run action sequences</td><td style="border:1px solid {border};">Test often; keep sequences short and modular</td></tr>
        <tr><td style="border:1px solid {border};"><b>Templates</b></td><td style="border:1px solid {border};">Prebuilt action flows by game</td><td style="border:1px solid {border};">Insert a template then customize coordinates and delays</td></tr>
        <tr><td style="border:1px solid {border};"><b>Settings</b></td><td style="border:1px solid {border};">Theme, opacity, safety, AFK, backup</td><td style="border:1px solid {border};">Set theme first; configure safety timeout and AFK detection</td></tr>
        <tr><td style="border:1px solid {border};"><b>Backup Manager</b></td><td style="border:1px solid {border};">Restore previous profile states</td><td style="border:1px solid {border};">Auto-backup runs every 30 min; manual backup available anytime</td></tr>
    </table>

    <!-- ===== ACTION REFERENCE ===== -->
    <h2 style="margin:14px 0 6px 0; color:{accent};">Action Reference</h2>
    <table width="100%" cellspacing="0" cellpadding="8" style="border-collapse:collapse; border:1px solid {border};">
        <tr style="background:{bg_medium}; color:{accent};">
            <th align="left" style="border:1px solid {border}; width:160px;">Action</th>
            <th align="left" style="border:1px solid {border};">Description</th>
            <th align="left" style="border:1px solid {border};">Key settings</th>
        </tr>
        <tr><td style="border:1px solid {border};"><b>Keyboard Key</b></td><td style="border:1px solid {border};">Simulate a key press, hold, or release. Use for skills, UI navigation, hotbars.</td><td style="border:1px solid {border};">key, press_type (press/hold/release), hold_duration (ms)</td></tr>
        <tr><td style="border:1px solid {border};"><b>Mouse Click</b></td><td style="border:1px solid {border};">Left / right / middle click at an absolute or relative screen position.</td><td style="border:1px solid {border};">x, y, button, clicks, relative mode</td></tr>
        <tr><td style="border:1px solid {border};"><b>Mouse Move</b></td><td style="border:1px solid {border};">Move cursor smoothly to a position. Combine with a Click action for more natural movement.</td><td style="border:1px solid {border};">x, y, duration (ms), relative mode</td></tr>
        <tr><td style="border:1px solid {border};"><b>Delay</b></td><td style="border:1px solid {border};">Pause for a fixed or randomized duration. Essential between actions for natural pacing.</td><td style="border:1px solid {border};">duration (ms), randomize, min/max range</td></tr>
        <tr><td style="border:1px solid {border};"><b>Loop Start / Loop End</b></td><td style="border:1px solid {border};">Repeat a block of actions a fixed number of times. Nest loops for complex repetition.</td><td style="border:1px solid {border};">iterations count on Loop Start; no params on Loop End</td></tr>
        <tr><td style="border:1px solid {border};"><b>Pixel Check</b></td><td style="border:1px solid {border};">Wait until a specific pixel at x,y matches a target color within tolerance. Good for detecting game state changes.</td><td style="border:1px solid {border};">x, y, color (hex), tolerance (0-255), timeout (ms)</td></tr>
        <tr><td style="border:1px solid {border};"><b>Image Match</b></td><td style="border:1px solid {border};">Find a saved template image on screen using OpenCV. Can click the match or just wait for it to appear.</td><td style="border:1px solid {border};">template_path, confidence (0-1), search region, click_match</td></tr>
        <tr><td style="border:1px solid {border};"><b>Region Watcher</b></td><td style="border:1px solid {border};">Continuously sample pixels in a rectangle and trigger when enough match a target color. Useful for health bars, indicators, loot spawns.</td><td style="border:1px solid {border};">x, y, w, h, target_color, tolerance, check_type (appears/disappears)</td></tr>
        <tr><td style="border:1px solid {border};"><b>Conditional Branch</b></td><td style="border:1px solid {border};">IF a condition is true → run THEN actions, otherwise run ELSE actions. Supports pixel, image, window, and region conditions.</td><td style="border:1px solid {border};">condition_type, nested THEN actions list, nested ELSE actions list</td></tr>
        <tr><td style="border:1px solid {border};"><b>Window Focus Check</b></td><td style="border:1px solid {border};">Pause or abort execution when a required window title is not in focus. Separate multiple titles with <b>|</b> (pipe).</td><td style="border:1px solid {border};">window_title (supports pipe-separated list), action_on_mismatch</td></tr>
        <tr><td style="border:1px solid {border};"><b>Skill Check Digits</b></td><td style="border:1px solid {border};">Read digits from screen with OCR (Tesseract) and press the matching number keys. Built for FiveM / GTA skill check mini-games.</td><td style="border:1px solid {border};">region, max_digits, key_delay (ms), tesseract path</td></tr>
        <tr><td style="border:1px solid {border};"><b>Run Profile</b></td><td style="border:1px solid {border};">Run another saved profile from within this one. Good for chaining macros together.</td><td style="border:1px solid {border};">profile_name</td></tr>
    </table>

    <!-- ===== PROFILES ===== -->
    <h2 style="margin:14px 0 6px 0; color:{accent};">Profiles Explained</h2>
    <table width="100%" cellspacing="8" cellpadding="10" style="border-collapse:separate;">
        <tr>
            <td width="50%" style="background:{bg_medium}; border:1px solid {border}; border-radius:8px; vertical-align:top;">
                <h3 style="margin:0 0 8px 0; color:{accent};">Profile Settings</h3>
                <ul style="margin:0; padding-left:18px; color:{text_primary};">
                    <li><b>Name</b> - identifies the profile; shown in lists and hotkey overlays.</li>
                    <li><b>Game</b> - used for grouping; shown as [Game] tag in lists.</li>
                    <li><b>Hotkey</b> - Any key or key combination (e.g., F5, Ctrl+F8, Alt+Q) that starts/stops this profile globally.</li>
                    <li><b>Description</b> - notes for yourself; not used during execution.</li>
                    <li><b>Loop modes:</b><br>
                        &nbsp;&nbsp;• <i>Loop Once</i> - run the sequence a single time then stop.<br>
                        &nbsp;&nbsp;• <i>Loop Forever</i> - repeat until hotkey pressed again or error.<br>
                        &nbsp;&nbsp;• <i>Loop X Times</i> - repeat a specific number of times then stop.
                    </li>
                </ul>
            </td>
            <td width="50%" style="background:{bg_medium}; border:1px solid {border}; border-radius:8px; vertical-align:top;">
                <h3 style="margin:0 0 8px 0; color:{accent};">Import / Export (.sloth)</h3>
                <ul style="margin:0; padding-left:18px; color:{text_primary};">
                    <li>Use <b>Export .sloth</b> to save a profile as a shareable file.</li>
                    <li>Use <b>Import .sloth</b> to load a profile from someone else or from backup.</li>
                    <li>.sloth files are JSON-based and portable across machines.</li>
                    <li><b>Search bar</b> - live filter profiles by name or game tag.</li>
                    <li><b>Sort</b> - order by Name, Game, Hotkey, or Recently Modified.</li>
                </ul>
            </td>
        </tr>
    </table>

    <!-- ===== LOOPS ===== -->
    <h2 style="margin:14px 0 6px 0; color:{accent};">Using Loops Inside a Sequence</h2>
    <p style="margin:0 0 8px 0; color:{text_primary};">Inline loops let you repeat a block of actions without making a separate profile.</p>
    <table width="100%" cellspacing="0" cellpadding="8" style="border-collapse:collapse; border:1px solid {border};">
        <tr style="background:{bg_medium}; color:{accent};">
            <th align="left" style="border:1px solid {border};">Step</th>
            <th align="left" style="border:1px solid {border};">What to do</th>
        </tr>
        <tr><td style="border:1px solid {border};">1</td><td style="border:1px solid {border};">Add a <b>Loop Start</b> action; set <i>iterations</i> (e.g. 5).</td></tr>
        <tr><td style="border:1px solid {border};">2</td><td style="border:1px solid {border};">Add the actions you want to repeat between Loop Start and End.</td></tr>
        <tr><td style="border:1px solid {border};">3</td><td style="border:1px solid {border};">Add a <b>Loop End</b> action directly after the last repeated action.</td></tr>
        <tr><td style="border:1px solid {border};">4</td><td style="border:1px solid {border};">Loops can be nested - place a second Loop Start/End block inside the first.</td></tr>
        <tr><td style="border:1px solid {border};">Note</td><td style="border:1px solid {border};">Always pair every Loop Start with a Loop End or execution will run to end-of-sequence.</td></tr>
    </table>

    <!-- ===== CONDITIONAL BRANCH ===== -->
    <h2 style="margin:14px 0 6px 0; color:{accent};">Conditional Branching Deep-Dive</h2>
    <table width="100%" cellspacing="8" cellpadding="10" style="border-collapse:separate;">
        <tr>
            <td width="50%" style="background:{bg_medium}; border:1px solid {border}; border-radius:8px; vertical-align:top;">
                <h3 style="margin:0 0 8px 0; color:{accent};">Condition Types</h3>
                <ul style="margin:0; padding-left:18px; color:{text_primary};">
                    <li><b>Pixel Color</b> - checks a single pixel x/y for a target color ± tolerance.</li>
                    <li><b>Image Present</b> - checks if a template image is visible on screen.</li>
                    <li><b>Image Absent</b> - true when the template is NOT visible.</li>
                    <li><b>Region Color</b> - true when enough pixels in a rectangle match a color.</li>
                    <li><b>Window Active</b> - true when a window with a given title is focused.</li>
                    <li><b>Always True / Always False</b> - useful for testing THEN/ELSE paths in isolation.</li>
                </ul>
            </td>
            <td width="50%" style="background:{bg_medium}; border:1px solid {border}; border-radius:8px; vertical-align:top;">
                <h3 style="margin:0 0 8px 0; color:{accent};">Build Strategy</h3>
                <ul style="margin:0; padding-left:18px; color:{text_primary};">
                    <li>Keep the IF region/image as small and specific as possible.</li>
                    <li>Start with <b>Always True</b> to build and test THEN actions first.</li>
                    <li>Swap to <b>Always False</b> to test the ELSE path.</li>
                    <li>Add recovery actions in ELSE (re-click, wait, retry loop).</li>
                    <li>Conditional branches can contain other conditional branches (nested branching).</li>
                    <li>Double-click a Conditional Branch row in the editor to open it directly.</li>
                </ul>
            </td>
        </tr>
    </table>

    <!-- ===== REGION WATCHER ===== -->
    <h2 style="margin:14px 0 6px 0; color:{accent};">Region Watcher &amp; Image Match Tips</h2>
    <table width="100%" cellspacing="8" cellpadding="10" style="border-collapse:separate;">
        <tr>
            <td width="50%" style="background:{bg_medium}; border:1px solid {border}; border-radius:8px; vertical-align:top;">
                <h3 style="margin:0 0 8px 0; color:{accent};">Region Watcher</h3>
                <ul style="margin:0; padding-left:18px; color:{text_primary};">
                    <li>Use the <b>Pick Region</b> button to draw the watch area on screen.</li>
                    <li>Set <b>target_color</b> to the hex color you want to detect (use Pick Color).</li>
                    <li>Increase <b>tolerance</b> (5-30) if the color shifts slightly during gameplay.</li>
                    <li><b>appears</b> - triggers when the color shows up in the region.</li>
                    <li><b>disappears</b> - triggers when the color leaves the region.</li>
                    <li>Threshold is 2% of total region pixels - small regions need bright, distinct colors.</li>
                </ul>
            </td>
            <td width="50%" style="background:{bg_medium}; border:1px solid {border}; border-radius:8px; vertical-align:top;">
                <h3 style="margin:0 0 8px 0; color:{accent};">Image Match</h3>
                <ul style="margin:0; padding-left:18px; color:{text_primary};">
                    <li>Capture a clean, small template image of the UI element (no background clutter).</li>
                    <li><b>Confidence 0.8-0.9</b> is usually ideal. Lower = more false positives. Higher = misses.</li>
                    <li>Restrict the <b>search region</b> to the area of the screen where the element appears.</li>
                    <li>If OpenCV (cv2) is not installed, Image Match will log an error and skip.</li>
                    <li>Template images are stored relative to the Sloth folder; use short, descriptive filenames.</li>
                </ul>
            </td>
        </tr>
    </table>

    <!-- ===== RECORDING ===== -->
    <h2 style="margin:14px 0 6px 0; color:{accent};">Recording</h2>
    <p style="margin:0 0 8px 0; color:{text_primary};">The recording panel (bottom of Macro Editor) captures live mouse clicks and key presses.</p>
    <table width="100%" cellspacing="0" cellpadding="8" style="border-collapse:collapse; border:1px solid {border};">
        <tr style="background:{bg_medium}; color:{accent};">
            <th align="left" style="border:1px solid {border};">Step</th>
            <th align="left" style="border:1px solid {border};">Details</th>
        </tr>
        <tr><td style="border:1px solid {border};">1. Start Recording</td><td style="border:1px solid {border};">Click <b>🔴 Start Recording</b>. Sloth captures all mouse clicks and key presses in the background.</td></tr>
        <tr><td style="border:1px solid {border};">2. Perform Actions</td><td style="border:1px solid {border};">Switch to your game/app and perform the sequence you want to automate. Timing is captured.</td></tr>
        <tr><td style="border:1px solid {border};">3. Stop &amp; Import</td><td style="border:1px solid {border};">Click <b>Stop</b>, then <b>Import to Sequence</b> to append recorded actions. Review and clean up.</td></tr>
        <tr><td style="border:1px solid {border};">Tip</td><td style="border:1px solid {border};">Recorded delays include exact timing. Enable <b>Humanized Timings</b> to add natural variation after import.</td></tr>
    </table>

    <!-- ===== SAFETY & AFK ===== -->
    <h2 style="margin:14px 0 6px 0; color:{accent};">Safety Features &amp; AFK Detection</h2>
    <table width="100%" cellspacing="8" cellpadding="10" style="border-collapse:separate;">
        <tr>
            <td width="50%" style="background:{bg_medium}; border:1px solid {border}; border-radius:8px; vertical-align:top;">
                <h3 style="margin:0 0 8px 0; color:{accent};">Safety Timeout</h3>
                <ul style="margin:0; padding-left:18px; color:{text_primary};">
                    <li>Auto-stops any running macro if it runs longer than a configured duration.</li>
                    <li>Configure in <b>Settings ⚙️ Safety</b>.</li>
                    <li>Prevents unattended macros running indefinitely if something goes wrong.</li>
                </ul>
            </td>
            <td width="50%" style="background:{bg_medium}; border:1px solid {border}; border-radius:8px; vertical-align:top;">
                <h3 style="margin:0 0 8px 0; color:{accent};">AFK Detection</h3>
                <ul style="margin:0; padding-left:18px; color:{text_primary};">
                    <li>Monitors screen brightness changes to detect if the game has gone to a login/AFK screen.</li>
                    <li>When triggered, stops or pauses the macro.</li>
                    <li>Enable and tune sensitivity in <b>Settings ⚙️ AFK</b>.</li>
                    <li>Combine with a <b>Window Focus Check</b> action for an extra layer of safety.</li>
                </ul>
            </td>
        </tr>
    </table>

    <!-- ===== BACKUP ===== -->
    <h2 style="margin:14px 0 6px 0; color:{accent};">Backup &amp; Restore</h2>
    <p style="margin:0 0 8px 0; color:{text_primary};">Sloth auto-saves a backup of all profiles every <b>6 hours</b>. You can also trigger a manual backup at any time.</p>
    <table width="100%" cellspacing="0" cellpadding="8" style="border-collapse:collapse; border:1px solid {border};">
        <tr style="background:{bg_medium}; color:{accent};">
            <th align="left" style="border:1px solid {border};">Feature</th>
            <th align="left" style="border:1px solid {border};">Details</th>
        </tr>
        <tr><td style="border:1px solid {border};">Auto-backup</td><td style="border:1px solid {border};">Runs every 6 hours while Sloth is open. Stored in <b>./backups/</b> with timestamps.</td></tr>
        <tr><td style="border:1px solid {border};">Manual backup</td><td style="border:1px solid {border};">Use <b>Settings 💾 Backup Now</b> to create a snapshot at any time.</td></tr>
        <tr><td style="border:1px solid {border};">Restore</td><td style="border:1px solid {border};">Open the Backup Manager page and click any backup entry to restore it.</td></tr>
        <tr><td style="border:1px solid {border};">Max backups kept</td><td style="border:1px solid {border};">The 10 most recent backups are kept. Older ones are automatically pruned.</td></tr>
    </table>

    <!-- ===== OCR + TESSERACT ===== -->
    <h2 style="margin:14px 0 6px 0; color:{accent};">OCR / Tesseract Setup</h2>
    <table width="100%" cellspacing="8" cellpadding="10" style="border-collapse:separate;">
        <tr>
            <td width="50%" style="background:{bg_medium}; border:1px solid {border}; border-radius:8px; vertical-align:top;">
                <h3 style="margin:0 0 8px 0; color:{accent};">Installation</h3>
                <ul style="margin:0; padding-left:18px; color:{text_primary};">
                    <li>Tesseract OCR is <b>not bundled</b> with Sloth - install it separately.</li>
                    <li>Download from: <b>https://github.com/tesseract-ocr/tesseract</b></li>
                    <li>Place <b>tesseract.exe</b> in one of these paths next to Sloth:</li>
                    <li style="list-style:none; margin-left:8px; color:{text_secondary};"> • <code>./tesseract/tesseract.exe</code></li>
                    <li style="list-style:none; margin-left:8px; color:{text_secondary};"> • <code>./teseract/tesseract.exe</code></li>
                    <li>Skill Check Digits will log an error if the path is wrong.</li>
                </ul>
            </td>
            <td width="50%" style="background:{bg_medium}; border:1px solid {border}; border-radius:8px; vertical-align:top;">
                <h3 style="margin:0 0 8px 0; color:{accent};">Using Skill Check Digits</h3>
                <ul style="margin:0; padding-left:18px; color:{text_primary};">
                    <li>Draw the OCR region tightly around the digit area only.</li>
                    <li>Set <b>max_digits</b> - how many digits to read and press.</li>
                    <li>Set <b>key_delay</b> between each key press.</li>
                    <li>Works best with high-contrast UI (white on dark background).</li>
                    <li>Add a short Delay before this action so the skill check fully appears on screen.</li>
                </ul>
            </td>
        </tr>
    </table>

    <!-- ===== TROUBLESHOOTING ===== -->
    <h2 style="margin:14px 0 6px 0; color:{accent};">Troubleshooting</h2>
    <table width="100%" cellspacing="0" cellpadding="8" style="border-collapse:collapse; border:1px solid {border};">
        <tr style="background:{bg_medium}; color:{accent};">
            <th align="left" style="border:1px solid {border}; width:220px;">Issue</th>
            <th align="left" style="border:1px solid {border};">Solutions</th>
        </tr>
        <tr><td style="border:1px solid {border};">Macro does not start</td><td style="border:1px solid {border};">Check the profile has at least one enabled action, the hotkey is set and not conflicting, and no other macro is running.</td></tr>
        <tr><td style="border:1px solid {border};">Clicks / moves miss target</td><td style="border:1px solid {border};">Re-pick coordinates using the Pick button. Disable <i>relative mode</i> unless you specifically need cursor-relative offsets. Add a short Delay before the click.</td></tr>
        <tr><td style="border:1px solid {border};">Image match unreliable</td><td style="border:1px solid {border};">Recapture the template image with no UI clutter. Narrow the search region. Try confidence 0.75-0.85. Make sure OpenCV (cv2) is installed.</td></tr>
        <tr><td style="border:1px solid {border};">Region watcher not triggering</td><td style="border:1px solid {border};">Re-pick region, re-pick target color exactly. Increase tolerance by 5-10 at a time. Ensure the region doesn't include UI chrome (health bar border etc.).</td></tr>
        <tr><td style="border:1px solid {border};">Conditional branch always takes same path</td><td style="border:1px solid {border};">Temporarily set condition to <i>Always True</i> or <i>Always False</i> to confirm both paths are correct. Then set real condition and re-test.</td></tr>
        <tr><td style="border:1px solid {border};">OCR finds no digits</td><td style="border:1px solid {border};">Confirm tesseract.exe path. Tighten the OCR region to digits only. Add contrast in game settings if digits are dim.</td></tr>
        <tr><td style="border:1px solid {border};">Profile changes not persisting</td><td style="border:1px solid {border};">Changes auto-save after a 350 ms delay. If unsure, click Save Profile manually. Reload from list to verify.</td></tr>
        <tr><td style="border:1px solid {border};">Hotkey not triggering</td><td style="border:1px solid {border};">Ensure Sloth is running and the profile is loaded/selected. Check Settings for conflicts. Some games block global hotkeys - run Sloth as Administrator.</td></tr>
        <tr><td style="border:1px solid {border};">Overlay covers other dialogs</td><td style="border:1px solid {border};">Coordinate/region pickers auto-hide sibling dialogs while active and restore them after picking.</td></tr>
    </table>

    <p style="margin-top:14px; color:{text_secondary}; font-size:11px;"><b>Support &amp; Community:</b> <a href="https://orvlyn.me" style="color:{accent};">orvlyn.me</a> • Discord: <b>Orvlyn</b> • X/Twitter: <b>@Orvlyn</b></p>
</div>
""")
        
        layout.addWidget(self.help_text)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

    def _find_next(self):
        text = self.help_search_input.text().strip()
        if text:
            if not self.help_text.find(text):
                cursor = self.help_text.textCursor()
                cursor.movePosition(QTextCursor.Start)
                self.help_text.setTextCursor(cursor)
                self.help_text.find(text)

    def _find_prev(self):
        text = self.help_search_input.text().strip()
        if text:
            if not self.help_text.find(text, QTextDocument.FindBackward):
                cursor = self.help_text.textCursor()
                cursor.movePosition(QTextCursor.End)
                self.help_text.setTextCursor(cursor)
                self.help_text.find(text, QTextDocument.FindBackward)


class NoWheelSlider(QSlider):
    """Slider that ignores mouse wheel events."""
    def wheelEvent(self, event):
        event.ignore()

class NoWheelComboBox(QComboBox):
    """ComboBox that ignores mouse wheel events."""
    def wheelEvent(self, event):
        event.ignore()

class NoWheelSpinBox(QSpinBox):
    """SpinBox that ignores mouse wheel events."""
    def wheelEvent(self, event):
        event.ignore()

class CollapsibleGroupBox(QWidget):
    """Collapsible container for UI elements"""
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.title = title
        self.toggle_button = QPushButton(f"▼ {title}")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(True)
        self.toggle_button.setStyleSheet("text-align: left; padding: 8px; font-weight: bold; background: transparent; border: none;")
        self.toggle_button.clicked.connect(self.toggle_content)
        layout.addWidget(self.toggle_button)
        
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(10, 5, 10, 5)
        layout.addWidget(self.content_widget)
    
    def setChecked(self, checked):
        """Set the expanded/collapsed state"""
        self.toggle_button.setChecked(checked)
        self.content_widget.setVisible(checked)
        arrow = "▼" if checked else "▶"
        self.toggle_button.setText(f"{arrow} {self.title}")
    
    def toggle_content(self):
        is_visible = self.content_widget.isVisible()
        self.content_widget.setVisible(not is_visible)
        arrow = "▼" if not is_visible else "▶"
        self.toggle_button.setText(f"{arrow} {self.title}")
    
    def add_widget(self, widget):
        self.content_layout.addWidget(widget)
    
    def add_layout(self, layout):
        self.content_layout.addLayout(layout)

class MousePositionTracker(QLabel):
    """Real-time mouse position display"""
    def __init__(self, parent=None):
        super().__init__("Mouse: (0, 0)", parent)
        self.setStyleSheet("font-family: 'Consolas', monospace; padding: 5px;")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_position)
    
    def update_position(self):
        pos = QCursor.pos()
        self.setText(f"Mouse: ({pos.x()}, {pos.y()})")
    
    def start(self):
        self.timer.start(50)
    
    def stop(self):
        self.timer.stop()


# -----------------------------------------------------------------------------
class CustomThemeDialog(QDialog):
    """Color-picker dialog for the Custom theme."""

    theme_saved = Signal(dict)

    # (settings key, display label, tooltip)
    _FIELDS = [
        ('accent',          'Accent',           'Primary highlight - buttons, focused borders, sliders'),
        ('accent_text',     'Accent Text',       'Text drawn on top of the accent color'),
        ('bg_dark',         'Background Dark',   'Darkest surface (window / sidebar fill)'),
        ('bg_medium',       'Background Medium', 'Card / panel surface, slightly lighter'),
        ('border',          'Border',            'Widget outline and divider lines'),
        ('hover',           '🎨 Hover',              'Button / row background when hovered'),
        ('scrollbar',       'Scrollbar',         'Scrollbar track background color'),
        ('scrollbar_hover', 'Scrollbar Hover',   'Scrollbar thumb color on mouse-over'),
        ('text_primary',    'Text Primary',      'Main readable body text'),
        ('text_secondary',  'Text Secondary',    'Labels, hints, and secondary text'),
        ('text_disabled',   'Text Disabled',     'Grayed-out inactive controls'),
    ]

    def __init__(self, current_colors: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Theme Editor")
        self.setMinimumWidth(820)
        self.setMinimumHeight(520)
        self._colors = dict(current_colors)
        self._row_widgets: dict = {}   # key → (QLineEdit, QPushButton swatch)
        self._build_ui()
        QTimer.singleShot(0, lambda: apply_dark_title_bar(self))

    # -- Layout ----------------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        header = QLabel("🎨 Custom Theme Editor")
        header.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 2px;")
        outer.addWidget(header)

        sub = QLabel("Click a color swatch to pick, or type a hex value. Preview updates live.")
        sub.setStyleSheet("font-size: 11px; color: #A0A0A0; margin-bottom: 8px;")
        sub.setWordWrap(True)
        outer.addWidget(sub)

        # -- Body: color editor (left) + live preview (right) -----------------
        body_row = QHBoxLayout()
        body_row.setSpacing(16)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setColumnStretch(1, 1)
        grid.addWidget(QLabel("<b>Role</b>"), 0, 0)
        grid.addWidget(QLabel("<b>Hex</b>"), 0, 1)
        grid.addWidget(QLabel("<b>Swatch</b>"), 0, 2)

        for row, (key, label, tip) in enumerate(self._FIELDS, start=1):
            lbl = QLabel(label)
            lbl.setToolTip(tip)

            color_val = self._colors.get(key, '#888888')

            hex_edit = QLineEdit(color_val)
            hex_edit.setMaxLength(9)
            hex_edit.setPlaceholderText('#RRGGBB')
            hex_edit.setToolTip(tip)
            hex_edit.setMinimumWidth(90)

            swatch_btn = QPushButton()
            swatch_btn.setFixedSize(44, 30)
            swatch_btn.setToolTip(f"Pick {label} color")
            swatch_btn.setCursor(Qt.PointingHandCursor)
            self._paint_swatch(swatch_btn, color_val)

            def _on_hex(text, k=key, btn=swatch_btn):
                if text.startswith('#') and len(text) in (7, 9) and QColor(text).isValid():
                    self._colors[k] = text.upper()
                    self._paint_swatch(btn, text)
                    self._update_preview()

            def _on_pick(_, k=key, edit=hex_edit, btn=swatch_btn):
                init_color = QColor(self._colors.get(k, '#000000'))
                picked = QColorDialog.getColor(init_color, self, f"Pick - {k}")
                if picked.isValid():
                    hex_val = picked.name().upper()
                    self._colors[k] = hex_val
                    edit.setText(hex_val)
                    self._paint_swatch(btn, hex_val)
                    self._update_preview()

            hex_edit.textChanged.connect(_on_hex)
            swatch_btn.clicked.connect(_on_pick)
            self._row_widgets[key] = (hex_edit, swatch_btn)

            grid.addWidget(lbl, row, 0)
            grid.addWidget(hex_edit, row, 1)
            grid.addWidget(swatch_btn, row, 2)

        left_layout.addLayout(grid)

        # preset buttons
        preset_group = QGroupBox("Quick presets")
        preset_row = QHBoxLayout(preset_group)
        preset_row.setSpacing(6)
        for preset_name in ('midnight', 'cyberpunk', 'foxfire', 'void', 'nord'):
            btn = QPushButton(THEMES[preset_name]['name'])
            btn.setToolTip(f"Copy {THEMES[preset_name]['name']} colors as starting point")
            btn.clicked.connect(lambda _, n=preset_name: self._load_preset(n))
            preset_row.addWidget(btn)
        left_layout.addWidget(preset_group)
        left_layout.addStretch()

        body_row.addWidget(left_widget, 3)

        # -- Live preview panel ------------------------------------------------
        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._preview_label.setWordWrap(True)
        self._preview_label.setMinimumWidth(230)
        self._preview_label.setTextFormat(Qt.RichText)
        body_row.addWidget(self._preview_label, 2)

        outer.addLayout(body_row, 1)
        self._update_preview()  # initial render

        # -- OK / Cancel -------------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("💾 Save Theme")
        save_btn.setDefault(True)
        save_btn.setStyleSheet("font-weight: bold;")
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        outer.addLayout(btn_row)

    # -- Helpers ---------------------------------------------------------------

    def _update_preview(self):
        """Render a realistic HTML mockup of the Sloth UI using current colors."""
        c = self._colors
        bg  = c.get('bg_dark',        '#0B1020')
        med = c.get('bg_medium',      '#141B2D')
        brd = c.get('border',         '#24314A')
        hvr = c.get('hover',          '#1B2740')
        acc = c.get('accent',         '#4CC9F0')
        act = c.get('accent_text',    '#04111A')
        tp  = c.get('text_primary',   '#EAF2FF')
        ts  = c.get('text_secondary', '#A9BDD8')
        td  = c.get('text_disabled',  '#62718A')
        scr = c.get('scrollbar',       '#1B2740')
        scr_h = c.get('scrollbar_hover', '#2A3C5E')

        def btn(label, active=False, accent=False, disabled=False):
            if accent:
                bg_b, brd_b, fg = acc, acc, act
                fw = 'bold'
            elif active:
                bg_b, brd_b, fg = hvr, acc, tp
                fw = '600'
            elif disabled:
                bg_b, brd_b, fg = bg, brd, td
                fw = 'normal'
            else:
                bg_b, brd_b, fg = med, brd, tp
                fw = 'normal'
            return (
                f"<div style='background:{bg_b}; border:2px solid {brd_b}; border-radius:5px;"
                f" padding:4px 10px; margin-bottom:4px; font-size:11px;"
                f" color:{fg}; font-weight:{fw};'>{label}</div>"
            )

        def nav_item(icon, label, active=False):
            bg_n = hvr if active else 'transparent'
            brd_l = f"border-left:3px solid {acc};" if active else "border-left:3px solid transparent;"
            fg_n = tp if active else ts
            fw_n = '600' if active else 'normal'
            return (
                f"<div style='background:{bg_n}; {brd_l} padding:6px 10px; border-radius:0 4px 4px 0;"
                f" margin-bottom:2px; font-size:11px; color:{fg_n}; font-weight:{fw_n};'>"
                f"{icon} {label}</div>"
            )

        def chip(label, color=None):
            bg_c = color if color else hvr
            return (
                f"<span style='background:{bg_c}; color:{tp}; border:1px solid {brd};"
                f" border-radius:4px; padding:1px 7px; font-size:10px;"
                f" font-weight:600; margin-right:4px;'>{label}</span>"
            )

        def action_row(num, icon, detail, enabled=True):
            alpha = tp if enabled else td
            return (
                f"<tr>"
                f"<td style='border-bottom:1px solid {brd}; padding:3px 6px;"
                f" color:{td}; font-size:10px; text-align:center;'>{num}</td>"
                f"<td style='border-bottom:1px solid {brd}; padding:3px 6px;"
                f" color:{acc}; font-size:10px;'>{icon}</td>"
                f"<td style='border-bottom:1px solid {brd}; padding:3px 6px;"
                f" color:{alpha}; font-size:10px;'>{detail}</td>"
                f"<td style='border-bottom:1px solid {brd}; padding:3px 6px;"
                f" font-size:10px; text-align:center;"
                f" color:{'#55DD77' if enabled else td};'>{'✓' if enabled else '✗'}</td>"
                f"</tr>"
            )

        # progress bar
        pct = 62
        progress_bar = (
            f"<div style='background:{brd}; border-radius:3px; height:6px; margin:4px 0;'>"
            f"<div style='background:{acc}; width:{pct}%; height:6px; border-radius:3px;'></div>"
            f"</div>"
        )

        # scrollbar strip
        scrollbar = (
            f"<div style='background:{scr}; width:6px; border-radius:3px; min-height:120px;'>"
            f"<div style='background:{acc}; width:6px; height:32px; border-radius:3px;'></div>"
            f"</div>"
        )

        html = f"""
<table cellspacing="0" cellpadding="0" width="100%" style="background:{bg};
  border:1px solid {brd}; border-radius:8px;
  font-family:Segoe UI,Arial,sans-serif;">
<tr>

  <!-- SIDEBAR -->
  <td valign="top" width="115" style="background:{bg}; border-right:1px solid {brd};
    padding:0;">
    <div style="padding:8px 10px 2px 10px; font-size:14px; font-weight:bold;
      color:{tp};">&#129445; Sloth</div>
    <div style="padding:0 10px 8px 10px; font-size:9px; color:{td};">v{APP_VERSION}</div>
    {nav_item('&#127968;', 'Home')}
    {nav_item('&#128193;', 'Profiles')}
    {nav_item('&#9998;', 'Editor', active=True)}
    {nav_item('&#9881;', 'Settings')}
    <div style="padding:6px 7px 0 7px;">
      <div style="background:{med}; border:1px solid {brd}; border-radius:4px;
        padding:4px 8px; font-size:10px; color:{tp}; margin-bottom:3px;">
        &#128295; Toolbar
      </div>
    </div>
  </td>

  <!-- MAIN CONTENT -->
  <td valign="top" style="padding:8px;">

    <!-- Profile title bar -->
    <table cellspacing="0" cellpadding="0" width="100%"
      style="margin-bottom:7px; border-bottom:1px solid {brd}; padding-bottom:6px;">
    <tr>
      <td style="font-size:12px; font-weight:bold; color:{tp};">
        &#9998; Fishing Macro
      </td>
      <td align="right" style="font-size:10px; color:{td};">
        <span style="background:{hvr}; color:{acc}; border:1px solid {brd};
          border-radius:3px; padding:1px 7px; font-size:10px; font-weight:600;">
          F5
        </span>
      </td>
    </tr>
    <tr>
      <td colspan="2" style="font-size:10px; color:{ts}; padding-top:2px;">
        Auto-fishes using left click + F1 hotkeys
      </td>
    </tr>
    </table>

    <!-- Inner split: sequence table + right panel -->
    <table cellspacing="0" cellpadding="0" width="100%">
    <tr valign="top">

      <!-- Action sequence table -->
      <td style="padding-right:6px;">
        <div style="background:{med}; border:1px solid {brd}; border-radius:6px;
          padding:6px;">
          <div style="font-size:10px; font-weight:600; color:{ts};
            border-bottom:1px solid {brd}; padding-bottom:3px; margin-bottom:4px;">
            Action Sequence
          </div>
          <table cellspacing="0" cellpadding="0" width="100%"
            style="border-collapse:collapse;">
            <tr style="background:{bg};">
              <th width="20" style="padding:2px 5px; font-size:9px; color:{td};
                font-weight:600; text-align:center;">#</th>
              <th width="30" style="padding:2px 5px; font-size:9px; color:{td};
                font-weight:600; text-align:left;">Type</th>
              <th style="padding:2px 5px; font-size:9px; color:{td};
                font-weight:600; text-align:left;">Details</th>
              <th width="22" style="padding:2px 5px; font-size:9px; color:{td};
                font-weight:600; text-align:center;">On</th>
            </tr>
            {action_row(1, '&#9000;', 'Press key: F1')}
            {action_row(2, '&#9200;', 'Delay: 450-820ms')}
            {action_row(3, '&#128432;', 'Click left (543,712)')}
            {action_row(4, '&#9200;', 'Delay: 200ms', enabled=False)}
            {action_row(5, '&#127919;', 'Pixel check #48A0FF')}
          </table>
          <!-- Move/delete row -->
          <table cellspacing="0" cellpadding="0" style="margin-top:5px;">
          <tr>
            <td style="padding-right:3px;">
              <div style="background:{bg}; border:1px solid {brd}; border-radius:4px;
                padding:2px 7px; font-size:10px; color:{tp};">&#11014;</div>
            </td>
            <td style="padding-right:3px;">
              <div style="background:{bg}; border:1px solid {brd}; border-radius:4px;
                padding:2px 7px; font-size:10px; color:{tp};">&#11015;</div>
            </td>
            <td>
              <div style="background:{bg}; border:1px solid {brd}; border-radius:4px;
                padding:2px 7px; font-size:10px; color:{tp};">&#128465; Delete</div>
            </td>
          </tr>
          </table>
          <!-- Execution status -->
          <div style="margin-top:5px; background:{bg}; border:1px solid {brd};
            border-radius:4px; padding:4px 6px;">
            <div style="font-size:9px; color:{ts}; margin-bottom:3px;">
              &#9889; Running... ({pct}%)
            </div>
            {progress_bar}
            <div style="font-size:9px; color:{td};">Step 3 of 5 - Mouse click</div>
          </div>
        </div>
      </td>

      <!-- Right panel -->
      <td width="140" valign="top">
        <!-- Quick actions -->
        <div style="background:{med}; border:1px solid {brd}; border-radius:6px;
          padding:6px; margin-bottom:5px;">
          <div style="font-size:9px; font-weight:600; color:{ts};
            border-bottom:1px solid {brd}; padding-bottom:3px; margin-bottom:4px;">
            &#9889; Quick Actions
          </div>
          {btn('&#9654; Test Run', accent=True)}
          {btn('&#9632; Stop', disabled=True)}
          <div style="height:3px; background:{acc}; border-radius:2px; margin-top:4px;"></div>
        </div>
        <!-- Add action form -->
        <div style="background:{med}; border:1px solid {brd}; border-radius:6px;
          padding:6px; margin-bottom:5px;">
          <div style="font-size:9px; font-weight:600; color:{ts}; margin-bottom:4px;">
            &#10133; Add Action
          </div>
          <div style="background:{bg}; border:1px solid {brd}; border-radius:4px;
            padding:3px 6px; font-size:10px; color:{tp}; margin-bottom:3px;">
            &#9000; Keyboard Key &#9660;
          </div>
          <div style="background:{bg}; border:1px solid {brd}; border-radius:4px;
            padding:3px 6px; font-size:10px; color:{ts}; margin-bottom:3px;">
            Key: F1
          </div>
          <div style="font-size:9px; color:{acc}; border:1px solid {brd};
            border-radius:3px; padding:2px 5px;">
            Preview: Press key F1
          </div>
        </div>
        <!-- Pinned add button -->
        <div style="background:{hvr}; border:2px solid {brd}; border-radius:5px;
          padding:5px; text-align:center; font-size:11px;
          font-weight:bold; color:{tp};">
          &#10133; Add Action to Sequence
        </div>
      </td>

      <!-- Scrollbar strip -->
      <td width="8" valign="top" style="padding-left:3px;">
        <div style="background:{scr}; width:6px; border-radius:3px; height:160px;">
          <div style="background:{scr_h}; width:6px; height:36px; border-radius:3px;
            margin-top:10px;"></div>
        </div>
      </td>

    </tr>
    </table>
  </td>

</tr>
</table>
"""
        self._preview_label.setText(html)

    @staticmethod
    def _paint_swatch(btn: QPushButton, hex_color: str):
        """Fill button with hex_color, choosing black/white label for contrast."""
        try:
            l = QColor(hex_color).lightness()
            fg = '#000000' if l > 128 else '#FFFFFF'
        except Exception:
            fg = '#FFFFFF'
        btn.setStyleSheet(
            f"background:{hex_color}; color:{fg}; border:1px solid #555; border-radius:3px;"
        )
        btn.setText('')

    def _load_preset(self, preset_name: str):
        """Copy a built-in theme's colors into all fields."""
        src = THEMES.get(preset_name, {})
        for key, (edit, btn) in self._row_widgets.items():
            val = src.get(key, self._colors.get(key, '#888888'))
            self._colors[key] = val
            edit.setText(val)
            self._paint_swatch(btn, val)
        self._update_preview()

    def _save(self):
        self.theme_saved.emit(dict(self._colors))
        self.accept()

    def get_colors(self) -> dict:
        return dict(self._colors)


class FloatingMacroToolbar(QDialog):
    """Floating toolbar for macro control while gaming."""
    execution_started = Signal()
    execution_stopped = Signal()
    pause_toggled = Signal(bool)
    stop_requested = Signal()

    def __init__(self, main_window_ref=None):
        # Pass None as Qt parent so this window stays visible when the main window is minimized.
        # A direct reference to the main window is kept for navigation.
        super().__init__(None)
        self._main_window = main_window_ref

        self.setWindowTitle("Sloth")
        self.setWindowFlags(
            Qt.Window | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
        )
        # Don't let this window prevent app exit or steal focus on show
        self.setAttribute(Qt.WA_QuitOnClose, False)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(480, 175)

        self.is_paused = False
        self.elapsed_time = 0
        self._drag_start_pos: Optional[QPoint] = None
        self.current_profile_name = ""
        self.current_profile_hotkey = ""

        # Default theme colors (midnight) -- updated by apply_toolbar_theme()
        self._accent       = "#4CC9F0"
        self._accent_text  = "#04111A"
        self._bg_dark      = "#0B1020"
        self._bg_medium    = "#141B2D"
        self._border       = "#24314A"
        self._text_primary = "#EAF2FF"
        self._text_secondary = "#A9BDD8"

        self._build_ui()
        self._apply_styles()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    # -- Layout ----------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header / drag bar
        header = QWidget()
        header.setObjectName("TBHeader")
        header.setFixedHeight(38)
        hrow = QHBoxLayout(header)
        hrow.setContentsMargins(12, 0, 8, 0)
        hrow.setSpacing(8)

        self.status_dot = QLabel("🟢")
        self.status_dot.setObjectName("TBDot")
        hrow.addWidget(self.status_dot)

        app_lbl = QLabel("🦥 Sloth")
        app_lbl.setObjectName("TBAppLabel")
        hrow.addWidget(app_lbl)

        self.status_label = QLabel("Idle")
        self.status_label.setObjectName("TBStatus")
        hrow.addWidget(self.status_label)

        hrow.addStretch()

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("TBClose")
        self.close_btn.setFixedSize(26, 26)
        self.close_btn.setToolTip("Close toolbar")
        self.close_btn.clicked.connect(self.close)
        hrow.addWidget(self.close_btn)

        root.addWidget(header)

        # Thin accent divider
        self.accent_line = QWidget()
        self.accent_line.setObjectName("TBAccentLine")
        self.accent_line.setFixedHeight(2)
        root.addWidget(self.accent_line)

        # Body
        body = QWidget()
        body.setObjectName("TBBody")
        blayout = QVBoxLayout(body)
        blayout.setContentsMargins(12, 7, 12, 8)
        blayout.setSpacing(5)

        # Row 1: profile chip + hotkey chip + elapsed timer
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        self.profile_chip = QLabel("No profile loaded")
        self.profile_chip.setObjectName("TBProfileChip")
        row1.addWidget(self.profile_chip)

        self.hotkey_chip = QLabel("")
        self.hotkey_chip.setObjectName("TBHotkeyChip")
        self.hotkey_chip.setVisible(False)
        row1.addWidget(self.hotkey_chip)

        row1.addStretch()

        self.time_label = QLabel("0s")
        self.time_label.setObjectName("TBTime")
        row1.addWidget(self.time_label)

        blayout.addLayout(row1)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("TBProgress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(5)
        blayout.addWidget(self.progress_bar)

        # Current action detail
        self.detail_label = QLabel("Ready")
        self.detail_label.setObjectName("TBDetail")
        self.detail_label.setWordWrap(True)
        blayout.addWidget(self.detail_label)

        # Row 4: controls + opacity slider
        row4 = QHBoxLayout()
        row4.setSpacing(5)

        self.pause_btn = QPushButton("⏸️ Pause")
        self.pause_btn.setFixedHeight(26)
        self.pause_btn.setToolTip("Pause macro")
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.pause_btn.setEnabled(False)
        row4.addWidget(self.pause_btn)

        self.stop_btn = QPushButton("⏹️ Stop")
        self.stop_btn.setFixedHeight(26)
        self.stop_btn.setToolTip("Stop macro")
        self.stop_btn.clicked.connect(self.stop_macro)
        self.stop_btn.setEnabled(False)
        row4.addWidget(self.stop_btn)

        self.purge_btn = QPushButton("🗑️")
        self.purge_btn.setFixedSize(32, 26)
        self.purge_btn.setToolTip("Purge: kill all Sloth processes immediately")
        self.purge_btn.clicked.connect(self._purge_from_toolbar)
        row4.addWidget(self.purge_btn)

        self.edit_btn = QPushButton("✏️ Edit")
        self.edit_btn.setFixedHeight(26)
        self.edit_btn.setToolTip("Open macro in editor")
        self.edit_btn.clicked.connect(self._open_editor)
        row4.addWidget(self.edit_btn)

        row4.addStretch()

        opacity_lbl = QLabel("🔆")
        opacity_lbl.setToolTip("Toolbar opacity")
        row4.addWidget(opacity_lbl)

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setFixedWidth(68)
        self.opacity_slider.setToolTip("Toolbar opacity")
        self.opacity_slider.valueChanged.connect(lambda v: self.setWindowOpacity(v / 100.0))
        row4.addWidget(self.opacity_slider)

        blayout.addLayout(row4)
        root.addWidget(body)

    # -- Styling ---------------------------------------------------------------

    def _apply_styles(self):
        a   = self._accent
        at  = self._accent_text
        bg  = self._bg_dark
        med = self._bg_medium
        brd = self._border
        txt = self._text_primary
        sec = self._text_secondary
        self.setStyleSheet(f"""
            QDialog {{
                background: {bg};
                border: 1px solid {brd};
                border-radius: 8px;
            }}
            QWidget#TBHeader {{
                background: {bg};
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }}
            QWidget#TBAccentLine {{ background: {a}; }}
            QWidget#TBBody {{
                background: {med};
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }}
            QLabel {{ background: transparent; color: {txt}; }}
            QLabel#TBAppLabel {{ font-weight: 700; font-size: 13px; color: {txt}; }}
            QLabel#TBDot     {{ font-size: 10px; color: #FF5555; }}
            QLabel#TBStatus  {{ font-size: 11px; color: {sec}; padding: 0 4px; }}
            QLabel#TBProfileChip {{
                font-size: 11px; font-weight: 600; color: {txt};
                background: {bg}; border: 1px solid {brd}; border-radius: 4px;
                padding: 2px 8px;
            }}
            QLabel#TBHotkeyChip {{
                font-size: 10px; font-weight: 700; color: {at};
                background: {a}; border-radius: 9px; padding: 2px 8px;
            }}
            QLabel#TBTime   {{ font-size: 11px; font-weight: 600; color: {sec}; }}
            QLabel#TBDetail {{ font-size: 10px; color: {sec}; }}
            QPushButton#TBClose {{
                background: transparent; border: none;
                color: {a}; font-size: 13px; font-weight: bold; border-radius: 4px;
            }}
            QPushButton#TBClose:hover {{
                color: #FF5555; background: rgba(255,85,85,0.15);
            }}
            QPushButton {{
                background: {bg}; border: 1px solid {brd}; border-radius: 4px;
                color: {txt}; font-size: 11px; padding: 2px 10px;
            }}
            QPushButton:hover {{ border-color: {a}; background: {med}; }}
            QPushButton:disabled {{ color: #555; border-color: {brd}; }}
            QProgressBar#TBProgress {{
                background: {bg}; border: none; border-radius: 2px;
            }}
            QProgressBar#TBProgress::chunk {{ background: {a}; border-radius: 2px; }}
            QSlider::groove:horizontal {{ background: {brd}; height: 4px; border-radius: 2px; }}
            QSlider::handle:horizontal {{
                background: {a}; width: 12px; margin: -4px 0; border-radius: 6px;
            }}
            QSlider::sub-page:horizontal {{ background: {a}; border-radius: 2px; }}
        """)

    def apply_toolbar_theme(self, theme: dict):
        """Update toolbar colors from a theme dict."""
        self._accent        = theme.get('accent',        '#4CC9F0')
        self._accent_text   = theme.get('accent_text',   '#04111A')
        self._bg_dark       = theme.get('bg_dark',       '#0B1020')
        self._bg_medium     = theme.get('bg_medium',     '#141B2D')
        self._border        = theme.get('border',        '#24314A')
        self._text_primary  = theme.get('text_primary',  '#EAF2FF')
        self._text_secondary = theme.get('text_secondary', '#A9BDD8')
        self._apply_styles()

    def showEvent(self, event):
        """Re-apply styles on every show so Qt's internal polish can't reset them."""
        super().showEvent(event)
        self._apply_styles()

    # -- Profile info ----------------------------------------------------------

    def set_profile_info(self, profile_name="", hotkey=""):
        """Update displayed profile and hotkey information."""
        self.current_profile_name = profile_name
        self.current_profile_hotkey = hotkey
        if profile_name:
            self.profile_chip.setText(f"  {profile_name}")
            if hotkey:
                self.hotkey_chip.setText(hotkey)
                self.hotkey_chip.setVisible(True)
            else:
                self.hotkey_chip.setVisible(False)
        else:
            self.profile_chip.setText("No profile loaded")
            self.hotkey_chip.setVisible(False)

    # -- Execution state -------------------------------------------------------

    def start_execution(self, macro_name=""):
        """Called when macro execution starts."""
        self.status_dot.setStyleSheet("font-size: 10px; color: #55DD77;")
        self.status_label.setText("Running")
        self.detail_label.setText("Executing...")
        self.progress_bar.setValue(0)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.elapsed_time = 0
        self.timer.start(100)
        self.show()
        self.raise_()
        self.execution_started.emit()

    def stop_execution(self):
        """Called when macro execution stops."""
        self.status_dot.setStyleSheet("font-size: 10px; color: #FF5555;")
        self.status_label.setText("Idle")
        self.detail_label.setText("Ready")
        self.progress_bar.setValue(0)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.is_paused = False
        self.pause_btn.setText("⏸️ Pause")
        self.timer.stop()
        self.execution_stopped.emit()

    def toggle_pause(self):
        """Toggle pause state."""
        self.is_paused = not self.is_paused
        self.pause_btn.setText("▶️ Resume" if self.is_paused else "⏸️ Pause")
        if self.is_paused:
            self.status_dot.setStyleSheet("font-size: 10px; color: #FFAA00;")
            self.status_label.setText("Paused")
        else:
            self.status_dot.setStyleSheet("font-size: 10px; color: #55DD77;")
            self.status_label.setText("Running")
        self.detail_label.setText("Paused" if self.is_paused else "Resumed")
        self.pause_toggled.emit(self.is_paused)

    def stop_macro(self):
        """Stop macro execution."""
        self.stop_requested.emit()
        self.stop_execution()
        self.execution_stopped.emit()

    def _tick(self):
        self.elapsed_time += 1
        s = self.elapsed_time // 10
        self.time_label.setText(f"{s // 60}m {s % 60}s" if s >= 60 else f"{s}s")

    def update_time(self):  # backward-compat alias
        self._tick()

    def set_progress(self, progress: int, status: str):
        """Update toolbar progress details."""
        self.progress_bar.setValue(max(0, min(100, int(progress))))
        self.detail_label.setText(status)

    # -- Navigation ------------------------------------------------------------

    def _purge_from_toolbar(self):
        """Delegate purge to main window."""
        if self._main_window and hasattr(self._main_window, 'purge_sloth_processes_and_exit'):
            self._main_window.purge_sloth_processes_and_exit()

    def _open_editor(self):
        """Navigate main window to editor and bring it to front."""
        if self._main_window:
            self._main_window.navigate_to_page('editor')
            if self._main_window.isMinimized():
                self._main_window.showNormal()
            self._main_window.raise_()
            self._main_window.activateWindow()

    # -- Window flags ----------------------------------------------------------

    def set_always_on_top(self, on_top):
        """Toggle always-on-top flag."""
        flags = self.windowFlags()
        if on_top:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    # -- Drag to move ----------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_pos is not None and (event.buttons() & Qt.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_start_pos)
            event.accept()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

# ============================
# BASE CARD PAGE
# ============================

class CardPage(QWidget):
    """Base page with card-style layout."""
    def __init__(self, title=""):
        super().__init__()
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)

        self.card = QWidget()
        self.card.setObjectName("Card")
        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setSpacing(15)
        self.card_layout.setContentsMargins(20, 20, 20, 20)

        self.scroll_area.setWidget(self.card)
        main_layout.addWidget(self.scroll_area)

# ============================
# HOME PAGE
# ============================

class HomePage(CardPage):
    """Welcome page with quick start guide - Theme-aware."""
    def __init__(self, current_theme='midnight'):
        super().__init__("Home")
        self.current_theme = current_theme
        self._pending_update = None  # (version, url) tuple when update available

        # Update notification banner - sits above the scroll area, hidden by default
        self._update_banner = QLabel()
        self._update_banner.setAlignment(Qt.AlignCenter)
        self._update_banner.setCursor(Qt.PointingHandCursor)
        self._update_banner.hide()
        self.layout().insertWidget(0, self._update_banner)

        self._build_ui()
    
    def _get_theme_colors(self):
        """Get colors from current theme"""
        theme = THEMES.get(self.current_theme, THEMES['midnight'])
        return theme
    
    def _build_ui(self):
        """Build the UI with current theme colors"""
        theme = self._get_theme_colors()
        
        # Header section
        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)
        
        title = QLabel("🦥 Sloth")
        title.setObjectName("HomePageTitle")
        title.setStyleSheet(f"font-size: 48px; font-weight: bold; color: {theme['accent']};")
        title.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(title)
        
        tagline = QLabel(f"v{APP_VERSION}")
        tagline.setStyleSheet(f"font-size: 15px; color: {theme['text_secondary']}; font-weight: 500; letter-spacing: 1px;")
        tagline.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(tagline)
        
        subtagline = QLabel("Stop clicking the same thing 500 times. Set a hotkey, let Sloth handle it.")
        subtagline.setStyleSheet(f"font-size: 13px; color: {theme['text_secondary']}; margin-bottom: 10px;")
        subtagline.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(subtagline)
        
        self.card_layout.addWidget(header)
        
        # Quick Action Buttons
        quick_actions = QGroupBox("⚡ Quick Actions")
        quick_layout = QHBoxLayout(quick_actions)
        quick_layout.setSpacing(15)
        
        new_macro_btn = QPushButton("Create New Macro")
        new_macro_btn.setMinimumHeight(55)
        new_macro_btn.setStyleSheet(f"font-size: 13px; font-weight: bold; background: {theme['hover']}; border: 2px solid {theme['accent']};")
        new_macro_btn.clicked.connect(self._navigate_to_profiles)
        quick_layout.addWidget(new_macro_btn)
        
        examples_btn = QPushButton("View Examples")
        examples_btn.setMinimumHeight(55)
        examples_btn.setStyleSheet(f"font-size: 13px; font-weight: bold; background: {theme['hover']}; border: 2px solid {theme['accent']};")
        examples_btn.clicked.connect(self._navigate_to_editor)
        quick_layout.addWidget(examples_btn)
        
        settings_btn = QPushButton("Settings")
        settings_btn.setMinimumHeight(55)
        settings_btn.setStyleSheet(f"font-size: 13px; font-weight: bold; background: {theme['hover']}; border: 2px solid {theme['accent']};")
        settings_btn.clicked.connect(self._navigate_to_settings)
        quick_layout.addWidget(settings_btn)
        
        self.card_layout.addWidget(quick_actions)
        
        # Getting Started
        guide = QGroupBox("Getting Started (60 seconds)")
        guide_layout = QVBoxLayout(guide)
        
        steps = [
            ("1", "Create Profile", "Profile Manager → Click New"),
            ("2", "Build Actions", "Add keyboard, mouse and delay actions from the editor"),
            ("3", "Set Hotkey", "Assign F1-F12 to trigger your macro"),
            ("4", "Test & Tweak", "Use Test Run to verify it works"),
            ("5", "Go Live", "Press your hotkey in-game!"),
        ]
        
        for emoji, title_text, desc in steps:
            step_widget = QWidget()
            step_layout = QHBoxLayout(step_widget)
            step_layout.setContentsMargins(10, 8, 10, 8)
            step_layout.setSpacing(12)
            
            emoji_label = QLabel(emoji)
            emoji_label.setStyleSheet("font-size: 18px;")
            emoji_label.setAlignment(Qt.AlignTop)
            step_layout.addWidget(emoji_label)
            
            text_widget = QWidget()
            text_layout = QVBoxLayout(text_widget)
            text_layout.setContentsMargins(0, 0, 0, 0)
            text_layout.setSpacing(2)
            
            step_title = QLabel(title_text)
            step_title.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {theme['text_primary']};")
            text_layout.addWidget(step_title)
            
            step_desc = QLabel(desc)
            step_desc.setStyleSheet(f"font-size: 11px; color: {theme['text_secondary']};")
            step_desc.setWordWrap(True)
            text_layout.addWidget(step_desc)
            
            step_layout.addWidget(text_widget, 1)
            step_widget.setStyleSheet(f"background: {theme['bg_medium']}; border-radius: 6px; border: 1px solid {theme['border']};")
            guide_layout.addWidget(step_widget)
        
        self.card_layout.addWidget(guide)
        
        # Key Features (3 columns)
        features = QGroupBox("Key Features")
        features_layout = QGridLayout(features)
        features_layout.setSpacing(15)
        
        feature_list = [
            ("⌨️", "Keyboard Control", "Press, hold, and release keys with custom timing"),
            ("🖱️", "Mouse Precision", "Click, move, and drag with pixel-perfect accuracy"),
            ("⏱️", "Smart Delays", "Randomized waits so timing never looks the same"),
            ("🔄", "Smart Loops", "Count-based, infinite, or time-based repetition"),
            ("👁️", "Region Watch", "Monitor screen areas for color changes"),
            ("✅", "Safety Checks", "Focus detection, AFK protection, and more"),
        ]
        
        for i, (icon, feature_title, feature_desc) in enumerate(feature_list):
            row = i // 3
            col = i % 3
            
            feature_widget = QWidget()
            feature_layout = QVBoxLayout(feature_widget)
            feature_layout.setContentsMargins(12, 12, 12, 12)
            feature_layout.setSpacing(8)
            
            icon_title = QLabel(f"{icon} {feature_title}")
            icon_title.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {theme['accent']};")
            feature_layout.addWidget(icon_title)
            
            desc_label = QLabel(feature_desc)
            desc_label.setStyleSheet(f"font-size: 11px; color: {theme['text_secondary']};")
            desc_label.setWordWrap(True)
            feature_layout.addWidget(desc_label)
            
            feature_widget.setStyleSheet(f"background: {theme['bg_medium']}; border: 1px solid {theme['border']}; border-radius: 6px;")
            features_layout.addWidget(feature_widget, row, col)
        
        self.card_layout.addWidget(features)
        
        self.card_layout.addStretch()

        # Re-style update banner if visible (surviving theme changes)
        if self._pending_update is not None:
            self.show_update_banner(*self._pending_update)

    def show_update_banner(self, version, url):
        """Display update notification banner at the top of the page."""
        self._pending_update = (version, url)
        theme = self._get_theme_colors()
        self._update_banner.setText(
            f"🎉 Sloth {version} is available - click here to download!"
        )
        self._update_banner.setStyleSheet(
            f"background: {theme['accent']}; color: #ffffff; font-size: 13px; "
            f"font-weight: bold; padding: 8px;"
        )
        self._update_banner.mousePressEvent = (
            lambda _e, u=url: QDesktopServices.openUrl(QUrl(u))
        )
        self._update_banner.show()

    def update_theme(self, theme_name):
        """Update homepage when theme changes."""
        self.current_theme = theme_name
        # Clear and rebuild UI with new theme
        while self.card_layout.count() > 0:
            item = self.card_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._build_ui()
    
    def _navigate_to_profiles(self):
        try:
            main_window = self.window()
            if hasattr(main_window, "switch_page"):
                main_window.switch_page("profiles")
                if hasattr(main_window, "nav_buttons") and "profiles" in main_window.nav_buttons:
                    main_window.nav_buttons["profiles"].setChecked(True)
                if hasattr(main_window, "profile_page") and main_window.profile_page:
                    main_window.profile_page.create_new_profile()
        except Exception:
            pass
    
    def _navigate_to_editor(self):
        try:
            main_window = self.window()
            if hasattr(main_window, "switch_page"):
                main_window.switch_page("editor")
                if hasattr(main_window, "nav_buttons") and "editor" in main_window.nav_buttons:
                    main_window.nav_buttons["editor"].setChecked(True)
        except Exception:
            pass
    
    def _navigate_to_settings(self):
        try:
            main_window = self.window()
            if hasattr(main_window, "switch_page"):
                main_window.switch_page("settings")
                if hasattr(main_window, "nav_buttons") and "settings" in main_window.nav_buttons:
                    main_window.nav_buttons["settings"].setChecked(True)
        except Exception:
            pass

# ============================
# PROFILE MANAGER PAGE
# ============================

class ProfileManagerPage(CardPage):
    """Manage macro profiles."""
    profile_selected = Signal(MacroProfile)
    
    def __init__(self):
        super().__init__("Profile Manager")
        
        self.profiles_dir = os.path.join(get_base_dir(), "profiles")
        Path(self.profiles_dir).mkdir(exist_ok=True)
        self._create_default_profiles_if_empty()
        
        self.current_profile: Optional[MacroProfile] = None
        
        # Split layout
        split = QHBoxLayout()
        
        # Left: Profile list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        
        left_layout.addWidget(QLabel("Macro Profiles"))

        # Search + sort controls
        search_row = QHBoxLayout()
        self.profile_search_input = QLineEdit()
        self.profile_search_input.setPlaceholderText("🔍 Search profiles...")
        self.profile_search_input.setClearButtonEnabled(True)
        self.profile_search_input.textChanged.connect(self.refresh_profile_list)
        search_row.addWidget(self.profile_search_input)
        left_layout.addLayout(search_row)

        sort_row = QHBoxLayout()
        sort_row.addWidget(QLabel("Sort:"))
        self.profile_sort_combo = NoWheelComboBox()
        self.profile_sort_combo.addItems(["Name A-Z", "Game", "Hotkey", "Recently Modified"])
        self.profile_sort_combo.currentIndexChanged.connect(self.refresh_profile_list)
        sort_row.addWidget(self.profile_sort_combo)
        sort_row.addStretch()
        left_layout.addLayout(sort_row)

        self.profile_list = QListWidget()
        self.profile_list.itemClicked.connect(self.load_selected_profile)
        left_layout.addWidget(self.profile_list)
        
        btn_row = QHBoxLayout()
        self.new_btn = QPushButton("➕ New")
        self.clone_btn = QPushButton("Clone")
        self.clone_btn.setToolTip("Duplicate selected profile under a new name")
        self.delete_btn = QPushButton("🗑️ Delete")
        self.deselect_btn = QPushButton("⭕ Deselect")
        self.refresh_btn = QPushButton("🔄 Refresh")
        btn_row.addWidget(self.new_btn)
        btn_row.addWidget(self.clone_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addWidget(self.deselect_btn)
        btn_row.addWidget(self.refresh_btn)
        left_layout.addLayout(btn_row)

        share_row = QHBoxLayout()
        self.import_sloth_btn = QPushButton("📎 Import .sloth")
        self.export_sloth_btn = QPushButton("💾 Export .sloth")
        share_row.addWidget(self.import_sloth_btn)
        share_row.addWidget(self.export_sloth_btn)
        left_layout.addLayout(share_row)
        
        # Right: Profile details
        right = QWidget()
        right_layout = QVBoxLayout(right)
        
        right_layout.addWidget(QLabel("Profile Details"))
        
        form = QGridLayout()
        
        form.addWidget(QLabel("Name:"), 0, 0)
        self.name_input = QLineEdit()
        form.addWidget(self.name_input, 0, 1)
        
        form.addWidget(QLabel("Game:"), 1, 0)
        self.game_combo = NoWheelComboBox()
        self.game_combo.addItems(["General", "OSRS", "Minecraft", "WoW", "Valorant", "League of Legends", "Fortnite", "ARK", "FiveM", "FF14", "Custom"])
        self.game_combo.setEditable(True)
        form.addWidget(self.game_combo, 1, 1)
        
        form.addWidget(QLabel("Hotkey:"), 2, 0)
        self.hotkey_edit = KeyCaptureEdit()
        self.hotkey_edit.setPlaceholderText("Click here and press any key combo (e.g., Ctrl+F5, F8, Mouse4)")
        self.hotkey_edit.setMinimumWidth(200)
        form.addWidget(self.hotkey_edit, 2, 1)
        
        form.addWidget(QLabel("Description:"), 3, 0)
        self.desc_input = QTextEdit()
        self.desc_input.setMaximumHeight(100)
        form.addWidget(self.desc_input, 3, 1)
        
        form.addWidget(QLabel("Loop Settings:"), 4, 0)
        loop_widget = QWidget()
        loop_layout = QHBoxLayout(loop_widget)
        loop_layout.setContentsMargins(0, 0, 0, 0)
        self.loop_enabled_combo = NoWheelComboBox()
        self.loop_enabled_combo.addItems(["Loop Once (No Loop)", "Loop Forever", "Loop X Times"])
        self.loop_enabled_combo.currentIndexChanged.connect(self.update_loop_display)
        loop_layout.addWidget(self.loop_enabled_combo)
        self.loop_count_spinner = NoWheelSpinBox()
        self.loop_count_spinner.setRange(1, 9999)
        self.loop_count_spinner.setValue(1)
        self.loop_count_spinner.setVisible(False)
        loop_layout.addWidget(self.loop_count_spinner)
        form.addWidget(loop_widget, 4, 1)
        
        right_layout.addLayout(form)
        
        # Save button
        self.save_btn = QPushButton("💾 Save Profile")
        self.save_btn.clicked.connect(self.save_current_profile)
        right_layout.addWidget(self.save_btn)
        
        right_layout.addStretch()
        
        split.addWidget(left, 40)
        split.addWidget(right, 60)
        self.card_layout.addLayout(split)

        # Bottom-right purge button (small, unobtrusive)
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        self.purge_btn = QPushButton("🗑️ Purge")
        self.purge_btn.setMaximumWidth(100)
        self.purge_btn.setMaximumHeight(24)
        self.purge_btn.setStyleSheet("font-size: 9px; padding: 2px 6px;")
        self.purge_btn.setToolTip("Force-close all Sloth processes and exit")
        self.purge_btn.clicked.connect(self._purge_from_profiles)
        bottom_row.addWidget(self.purge_btn)
        self.card_layout.addLayout(bottom_row)
        
        # Connect signals
        self.new_btn.clicked.connect(self.create_new_profile)
        self.clone_btn.clicked.connect(self.clone_selected_profile)
        self.delete_btn.clicked.connect(self.delete_selected_profile)
        self.deselect_btn.clicked.connect(self.deselect_profile)
        self.refresh_btn.clicked.connect(self.refresh_profile_list)
        self.import_sloth_btn.clicked.connect(self.import_profile_from_sloth)
        self.export_sloth_btn.clicked.connect(self.export_selected_profile_as_sloth)
        
        # Load existing profiles
        self.refresh_profile_list()

    def _create_default_profiles_if_empty(self):
        """Create starter profiles on first run if the profiles folder is empty."""
        try:
            existing_names = set()
            for filename in os.listdir(self.profiles_dir):
                if not filename.endswith('.json'):
                    continue
                try:
                    profile = MacroProfile.load_from_file(os.path.join(self.profiles_dir, filename))
                    existing_names.add(profile.name.strip().lower())
                except Exception:
                    continue

            starters = [
                ("Starter Mining", "OSRS", "F2", "Simple OSRS mining starter", "OSRS: Copper Mining"),
                ("Starter FiveM Interact", "FiveM", "F3", "Basic FiveM interaction loop", "FiveM: Click Interaction"),
                ("Starter Minecraft Fish", "Minecraft", "F4", "AFK fishing starter template", "Minecraft: AFK Fishing"),
                ("Starter WoW DPS", "WoW", "F5", "Simple MMO rotation starter", "WoW: Melee DPS Rotation"),
            ]

            for name, game, hotkey, description, template_name in starters:
                if name.strip().lower() in existing_names:
                    continue
                actions = [MacroAction.from_dict(a) for a in ACTION_TEMPLATES.get(template_name, [])]
                profile = MacroProfile(
                    name=name,
                    game=game,
                    description=description,
                    hotkey=hotkey,
                    actions=actions,
                    loop_enabled=True,
                    loop_count=0
                )
                profile.save_to_file(self.profiles_dir)
            logger.info("Ensured starter profiles are available")
        except Exception as e:
            logger.warning(f"Could not create default starter profiles: {e}")
    
    def _purge_from_profiles(self):
        """Call purge from profiles page."""
        main_window = self.window()
        if hasattr(main_window, 'purge_sloth_processes_and_exit'):
            main_window.purge_sloth_processes_and_exit()
    
    def refresh_profile_list(self):
        """Reload profiles from disk with search filtering and sorting."""
        self.profile_list.clear()

        if not os.path.exists(self.profiles_dir):
            return

        entries = []
        for filename in os.listdir(self.profiles_dir):
            if not filename.endswith('.json'):
                continue
            filepath = os.path.join(self.profiles_dir, filename)
            try:
                mtime = os.path.getmtime(filepath)
                profile = MacroProfile.load_from_file(filepath)
                entries.append((profile, filepath, mtime))
            except Exception as e:
                logger.error(f"Failed to load profile {filename}: {e}")

        # Sort
        sort_mode = self.profile_sort_combo.currentText() if hasattr(self, 'profile_sort_combo') else "Name A-Z"
        if sort_mode == "Name A-Z":
            entries.sort(key=lambda x: x[0].name.lower())
        elif sort_mode == "Game":
            entries.sort(key=lambda x: (x[0].game.lower(), x[0].name.lower()))
        elif sort_mode == "Hotkey":
            entries.sort(key=lambda x: x[0].hotkey)
        elif sort_mode == "Recently Modified":
            entries.sort(key=lambda x: x[2], reverse=True)

        # Filter
        query = self.profile_search_input.text().strip().lower() if hasattr(self, 'profile_search_input') else ""
        for profile, filepath, _ in entries:
            if query and query not in profile.name.lower() and query not in profile.game.lower():
                continue
            item = QListWidgetItem(f"[{profile.game}] {profile.name} ({profile.hotkey})")
            item.setData(Qt.UserRole, filepath)
            self.profile_list.addItem(item)
    
    def create_new_profile(self):
        """Create new empty profile."""
        profile = MacroProfile(
            name="New Macro",
            game="General",
            description="",
            hotkey="F1",
            actions=[],
            loop_enabled=True,
            loop_count=0
        )
        self.current_profile = profile
        self.populate_form(profile)

    def clone_selected_profile(self):
        """Duplicate the currently loaded profile under a new name and save it."""
        if not self.current_profile:
            QMessageBox.warning(self, "No Profile", "Load a profile first to clone it.")
            return
        from copy import deepcopy
        cloned = deepcopy(self.current_profile)
        cloned.name = f"{self.current_profile.name} (Copy)"
        self.current_profile = cloned
        self.populate_form(cloned)
        self.save_current_profile()

    def update_loop_display(self, *_):
        """Show/hide loop count spinner based on selection."""
        mode = self.loop_enabled_combo.currentText()
        self.loop_count_spinner.setVisible(mode == "Loop X Times")
    
    def load_selected_profile(self, item: QListWidgetItem):
        """Load selected profile from list."""
        filepath = item.data(Qt.UserRole)
        try:
            profile = MacroProfile.load_from_file(filepath)
            self.current_profile = profile
            self.populate_form(profile)
            self.profile_selected.emit(profile)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load profile: {e}")
    
    def populate_form(self, profile: MacroProfile):
        """Fill form with profile data."""
        self.name_input.setText(profile.name)
        self.game_combo.setCurrentText(profile.game)
        self.hotkey_edit.setText(profile.hotkey if profile.hotkey and profile.hotkey != "None" else "")
        self.desc_input.setPlainText(profile.description)
        
        # Update loop settings
        if profile.loop_enabled:
            if profile.loop_count <= 0:
                self.loop_enabled_combo.setCurrentText("Loop Forever")
            else:
                self.loop_enabled_combo.setCurrentText("Loop X Times")
                self.loop_count_spinner.setValue(profile.loop_count)
        else:
            self.loop_enabled_combo.setCurrentText("Loop Once (No Loop)")
    
    def save_current_profile(self):
        """Save current profile to disk."""
        if not self.current_profile:
            QMessageBox.warning(self, "Warning", "No profile loaded")
            return
        
        # Update profile from form
        self.current_profile.name = self.name_input.text() or "Untitled"
        self.current_profile.game = self.game_combo.currentText()
        self.current_profile.hotkey = self.hotkey_edit.text().strip() if self.hotkey_edit.text().strip() else "None"
        self.current_profile.description = self.desc_input.toPlainText()
        
        # Handle loop settings
        loop_mode = self.loop_enabled_combo.currentText()
        if loop_mode == "Loop Once (No Loop)":
            self.current_profile.loop_enabled = False
            self.current_profile.loop_count = 1
        elif loop_mode == "Loop Forever":
            self.current_profile.loop_enabled = True
            self.current_profile.loop_count = 0
        elif loop_mode == "Loop X Times":
            self.current_profile.loop_enabled = True
            self.current_profile.loop_count = self.loop_count_spinner.value()
        
        try:
            filepath = self.current_profile.save_to_file(self.profiles_dir)
            QMessageBox.information(self, "Success", f"Profile saved to {filepath}")
            self.refresh_profile_list()
            self.profile_selected.emit(self.current_profile)
            main_window = self.window()
            if hasattr(main_window, 'start_hotkey_listener'):
                main_window.start_hotkey_listener()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save profile: {e}")
    
    def delete_selected_profile(self):
        """Delete selected profile."""
        current_item = self.profile_list.currentItem()
        if not current_item:
            return
        
        filepath = current_item.data(Qt.UserRole)
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete profile: {current_item.text()}?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                os.remove(filepath)
                self.refresh_profile_list()
                main_window = self.window()
                if hasattr(main_window, 'start_hotkey_listener'):
                    main_window.start_hotkey_listener()
                QMessageBox.information(self, "Success", "Profile deleted")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete: {e}")

    def export_selected_profile_as_sloth(self):
        """Export current profile as portable .sloth file."""
        if not self.current_profile:
            QMessageBox.warning(self, "No Profile", "Load or create a profile to export.")
            return
        export_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Profile",
            f"{self.current_profile.name}.sloth",
            "Sloth Profile (*.sloth)"
        )
        if not export_path:
            return
        if not export_path.lower().endswith(".sloth"):
            export_path += ".sloth"
        try:
            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(self.current_profile.to_dict(), f, indent=2)
            QMessageBox.information(self, "Export Complete", f"Exported to:\n{export_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))

    def import_profile_from_sloth(self):
        """Import portable .sloth profile and save into local profiles."""
        import_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Profile",
            "",
            "Sloth Profile (*.sloth);;JSON (*.json)"
        )
        if not import_path:
            return
        try:
            with open(import_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            profile = MacroProfile.from_dict(data)
            profile.save_to_file(self.profiles_dir)
            self.refresh_profile_list()
            QMessageBox.information(self, "Import Complete", f"Imported profile: {profile.name}")
        except Exception as e:
            QMessageBox.critical(self, "Import Failed", str(e))
    
    def deselect_profile(self):
        """Deselect current profile and clear form."""
        self.current_profile = None
        self.profile_list.clearSelection()
        
        # Clear form fields
        self.name_input.clear()
        self.game_combo.setCurrentIndex(0)
        self.hotkey_edit.clear()
        self.desc_input.clear()
        self.loop_enabled_combo.setCurrentText("Loop Once (No Loop)")
        self.loop_count_spinner.setValue(1)
        self.update_loop_display()
        
        QMessageBox.information(self, "Deselected", "Profile deselected. Create new or select another profile.")

# ============================
# MACRO EDITOR PAGE
# ============================

class MacroEditorPage(CardPage):
    """Visual macro sequence editor."""
    
    def __init__(self):
        super().__init__("Macro Editor")

        self.current_profile: Optional[MacroProfile] = None
        self.executor: Optional[MacroExecutor] = None
        self._recorded_actions_buffer: List[Dict[str, Any]] = []
        self._active_overlay = None

        info_bar = QHBoxLayout()
        self.profile_label = QLabel("No profile loaded")
        self.profile_label.setObjectName("ProfileLabel")
        self.profile_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        info_bar.addWidget(self.profile_label)
        info_bar.addStretch()
        self.card_layout.addLayout(info_bar)

        desc_bar = QHBoxLayout()
        self.profile_desc_label = QLabel("")
        self.profile_desc_label.setStyleSheet("font-size: 11px; color: #A0A0A0; font-style: italic; margin-bottom: 4px;")
        self.profile_desc_label.setWordWrap(True)
        desc_bar.addWidget(self.profile_desc_label)
        self.card_layout.addLayout(desc_bar)

        split = QHBoxLayout()

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Action Sequence"))

        self.action_table = QTableWidget()
        self.action_table.setColumnCount(4)
        self.action_table.setHorizontalHeaderLabels(["#", "Type", "Details", "Enabled"])
        self.action_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)  # prevent accidental typing into cells
        self.action_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.action_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.action_table.horizontalHeader().setStretchLastSection(False)
        self.action_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.action_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.action_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.action_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.action_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.action_table.customContextMenuRequested.connect(self._show_action_context_menu)
        left_layout.addWidget(self.action_table, 1)

        self._copied_actions_buffer: List[Dict[str, Any]] = []
        self._last_action_defaults: Dict[str, Dict[str, Any]] = {}
        self._undo_stack: List[List[Dict[str, Any]]] = []
        self._redo_stack: List[List[Dict[str, Any]]] = []
        self._history_limit = 100
        self._suspend_history = False
        self._drag_start_pos = QPoint()

        action_btn_row = QHBoxLayout()
        self.move_up_btn = QPushButton("↑")
        self.move_down_btn = QPushButton("↓")
        self.delete_action_btn = QPushButton("🗑️ Delete")
        self.clear_all_btn = QPushButton("Clear All")
        action_btn_row.addWidget(self.move_up_btn)
        action_btn_row.addWidget(self.move_down_btn)
        action_btn_row.addWidget(self.delete_action_btn)
        action_btn_row.addWidget(self.clear_all_btn)
        left_layout.addLayout(action_btn_row)

        exec_status_group = QGroupBox("📊 Execution Status")
        exec_status_layout = QVBoxLayout(exec_status_group)
        exec_status_layout.setContentsMargins(8, 8, 8, 8)
        exec_status_layout.setSpacing(4)
        self.exec_progress = QProgressBar()
        self.exec_progress.setRange(0, 100)
        self.exec_progress.setValue(0)
        self.exec_progress.setTextVisible(True)
        self.exec_progress.setFixedHeight(20)
        exec_status_layout.addWidget(self.exec_progress)
        self.exec_status = QLabel("Ready to execute")
        self.exec_status.setStyleSheet("font-size: 11px; color: #A0A0A0;")
        self.exec_status.setWordWrap(True)
        exec_status_layout.addWidget(self.exec_status)

        # Execution log toggle
        log_toggle_row = QHBoxLayout()
        self._exec_log_toggle_btn = QPushButton("📜 Show Log")
        self._exec_log_toggle_btn.setCheckable(True)
        self._exec_log_toggle_btn.setFixedHeight(20)
        self._exec_log_toggle_btn.setStyleSheet("font-size: 10px; padding: 0 4px;")
        self._exec_log_toggle_btn.toggled.connect(self._toggle_exec_log)
        log_toggle_row.addStretch()
        log_toggle_row.addWidget(self._exec_log_toggle_btn)
        exec_status_layout.addLayout(log_toggle_row)

        self.exec_log_list = QListWidget()
        self.exec_log_list.setMaximumHeight(80)
        self.exec_log_list.setStyleSheet("font-size: 10px; background: #1a1a2e;")
        self.exec_log_list.hide()
        exec_status_layout.addWidget(self.exec_log_list)

        hist_toggle_row = QHBoxLayout()
        self._run_history_toggle_btn = QPushButton("Run History (0)")
        self._run_history_toggle_btn.setCheckable(True)
        self._run_history_toggle_btn.setChecked(False)
        self._run_history_toggle_btn.setMaximumWidth(180)
        self._run_history_toggle_btn.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self._run_history_toggle_btn.toggled.connect(self._toggle_run_history)
        hist_toggle_row.addWidget(self._run_history_toggle_btn)
        hist_toggle_row.addStretch()
        exec_status_layout.addLayout(hist_toggle_row)

        self.run_history_list = QListWidget()
        self.run_history_list.setMaximumHeight(90)
        self.run_history_list.setStyleSheet("font-size: 10px; background: #1a1a2e;")
        self.run_history_list.hide()
        exec_status_layout.addWidget(self.run_history_list)
        self._run_history_entries: list = []

        left_layout.addWidget(exec_status_group)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # ===== TOP SECTION: Quick Execution Controls (PINNED) =====
        top_control_box = QGroupBox("⚡ Quick Actions")
        top_control_layout = QVBoxLayout(top_control_box)
        top_control_layout.setContentsMargins(10, 10, 10, 10)
        top_control_layout.setSpacing(8)
        
        exec_btn_row = QHBoxLayout()
        self.test_btn = QPushButton("▶ Test Run")
        self.test_btn.setMinimumHeight(36)
        self.test_btn.setStyleSheet("font-weight: bold; font-size: 11px;")
        self.debug_btn = QPushButton("🔍 Debug")
        self.debug_btn.setMinimumHeight(36)
        self.debug_btn.setStyleSheet("font-size: 11px;")
        self.stop_btn = QPushButton("⏹ Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setMinimumHeight(36)
        self.stop_btn.setStyleSheet("font-size: 11px;")
        exec_btn_row.addWidget(self.test_btn)
        exec_btn_row.addWidget(self.debug_btn)
        exec_btn_row.addWidget(self.stop_btn)
        top_control_layout.addLayout(exec_btn_row)
        
        self.force_humanized_check = QCheckBox("🎲 Global Humanized Timings")
        self.force_humanized_check.setChecked(True)
        self.force_humanized_check.setToolTip("ON = delays get randomized so timing isn't robotic\nOFF = use exact millisecond timings")
        self.force_humanized_check.setStyleSheet("font-size: 10px; padding: 4px;")
        top_control_layout.addWidget(self.force_humanized_check)
        
        right_layout.addWidget(top_control_box)

        # ===== MIDDLE SECTION: Scrollable Content (Add Action + Templates) =====
        center_scroll = NoWheelScrollArea()
        center_scroll.setWidgetResizable(True)
        center_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        center_scroll_container = QWidget()
        center_scroll_layout = QVBoxLayout(center_scroll_container)
        center_scroll_layout.setContentsMargins(8, 8, 8, 8)
        center_scroll_layout.setSpacing(12)

        # ===== Add Action Section =====
        add_action_collapsible = CollapsibleGroupBox("➕ Add Action")
        add_action_content_layout = QVBoxLayout()
        add_action_content_layout.setContentsMargins(10, 10, 10, 10)
        add_action_content_layout.setSpacing(10)

        action_type_label = QLabel("Action Type:")
        action_type_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        add_action_content_layout.addWidget(action_type_label)
        
        self.action_type_combo = NoWheelComboBox()
        self.action_type_combo.setMinimumHeight(38)
        self.action_type_combo.setStyleSheet("font-size: 11px;")
        self.action_type_combo.addItems([
            "Keyboard Key", "Mouse Click", "Mouse Move", "Delay",
            "Loop Start", "Loop End", "Pixel Check", "Image Match",
            "Region Watcher", "Skill Check Digits", "Window Focus Check", "Conditional Branch"
        ])
        self.action_type_combo.currentTextChanged.connect(self.update_action_form)
        add_action_content_layout.addWidget(self.action_type_combo)

        params_label = QLabel("Parameters:")
        params_label.setStyleSheet("font-weight: bold; font-size: 12px; margin-top: 8px;")
        add_action_content_layout.addWidget(params_label)
        
        self.action_form_stack = QStackedWidget()
        add_action_content_layout.addWidget(self.action_form_stack)

        self._create_key_form()
        self._create_mouse_click_form()
        self._create_mouse_move_form()
        self._create_delay_form()
        self._create_loop_start_form()
        self._create_loop_end_form()
        self._create_pixel_check_form()
        self._create_image_match_form()
        self._create_region_watcher_form()
        self._create_skill_check_digits_form()
        self._create_window_focus_check_form()
        self._create_conditional_branch_form()

        add_action_collapsible.content_layout.addLayout(add_action_content_layout)
        add_action_collapsible.setChecked(True)
        center_scroll_layout.addWidget(add_action_collapsible)

        # ===== Templates Section =====
        templates_collapsible = CollapsibleGroupBox("Templates by Game")
        templates_layout = QVBoxLayout()
        templates_layout.setContentsMargins(0, 0, 0, 0)
        templates_scroll = NoWheelScrollArea()
        templates_scroll.setWidgetResizable(True)
        templates_scroll.setMinimumHeight(560)
        templates_scroll.setMaximumHeight(560)
        templates_container = QWidget()
        templates_container_layout = QVBoxLayout(templates_container)
        templates_container_layout.setContentsMargins(0, 0, 0, 0)
        templates_container_layout.setSpacing(4)
        templates_container_layout.setAlignment(Qt.AlignTop)

        games = {}
        for template_name in ACTION_TEMPLATES.keys():
            if ":" in template_name:
                category = template_name.split(":", 1)[0].strip()
                parts = category.split(" ", 1)
                category = parts[1].strip() if len(parts) > 1 else category
            else:
                category = "General"
            if category not in games:
                games[category] = []
            games[category].append(template_name)

        for game_category in sorted(games.keys()):
            game_templates = games[game_category]
            header_btn = QPushButton(f"🎮 {game_category} ({len(game_templates)})")
            header_btn.setObjectName("TemplateCategoryBtn")
            header_btn.setCheckable(True)
            header_btn.setChecked(False)
            header_btn.setFixedHeight(28)
            header_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            templates_container_layout.addWidget(header_btn)

            game_grid_container = QWidget()
            game_grid_container.setVisible(False)
            game_grid = QGridLayout(game_grid_container)
            game_grid.setSpacing(10)
            game_grid.setContentsMargins(8, 8, 8, 12)
            game_grid.setColumnStretch(0, 1)
            game_grid.setColumnStretch(1, 1)

            for i, template_name in enumerate(game_templates):
                clean_name = template_name.split(":", 1)[1].strip() if ":" in template_name else template_name
                if len(clean_name) > 24:
                    clean_name = clean_name[:24].rstrip() + "..."

                summary = self._template_summary(template_name)

                card = QWidget()
                card.setObjectName("TemplateCard")
                card.setFixedHeight(136)
                card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(10, 8, 10, 8)
                card_layout.setSpacing(4)

                title_lbl = QLabel(clean_name)
                title_lbl.setObjectName("TemplateTitle")
                title_lbl.setAlignment(Qt.AlignCenter)
                title_lbl.setWordWrap(False)
                card_layout.addWidget(title_lbl)

                summary_lbl = QLabel(summary)
                summary_lbl.setObjectName("TemplateSummary")
                summary_lbl.setAlignment(Qt.AlignCenter)
                summary_lbl.setWordWrap(False)
                card_layout.addWidget(summary_lbl)

                card_layout.addStretch()

                insert_btn = QPushButton("Use Template")
                insert_btn.setObjectName("TemplateInsertBtn")
                insert_btn.setToolTip(f"Insert {len(ACTION_TEMPLATES[template_name])} actions")
                insert_btn.setCursor(Qt.PointingHandCursor)
                insert_btn.clicked.connect(lambda checked, name=template_name: self.insert_template(name))
                insert_btn.setProperty("template_name", template_name)
                insert_btn.installEventFilter(self)
                insert_btn.setFixedHeight(34)
                card_layout.addWidget(insert_btn)

                game_grid.addWidget(card, i // 2, i % 2)

            def toggle_game_section(checked, container=game_grid_container, btn=header_btn):
                container.setVisible(checked)
                label = btn.text()
                if label.startswith("✓") or label.startswith("✗"):
                    base = label[2:]
                else:
                    base = label
                btn.setText(("✓ " if checked else "✗ ") + base)
            header_btn.toggled.connect(toggle_game_section)
            templates_container_layout.addWidget(game_grid_container)

        templates_scroll.setWidget(templates_container)
        templates_layout.addWidget(templates_scroll)
        templates_collapsible.content_layout.addLayout(templates_layout)
        templates_collapsible.setChecked(False)

        center_scroll_layout.insertWidget(0, templates_collapsible)
        center_scroll_layout.addStretch()
        center_scroll.setWidget(center_scroll_container)

        right_layout.addWidget(center_scroll, 1)

        # ===== PINNED: action preview + Add Action button =====
        self.action_preview_label = QLabel("Preview: Ready")
        self.action_preview_label.setWordWrap(True)
        self.action_preview_label.setStyleSheet(
            "font-size: 11px; color: #A0A0A0; padding: 6px;"
            " border: 1px solid #2A2A2A; border-radius: 4px; margin: 0 0 2px 0;"
        )
        right_layout.addWidget(self.action_preview_label)

        # ===== PINNED: Add Action button - always visible, no scrolling needed =====
        self.add_action_btn = QPushButton("➕ Add Action to Sequence")
        self.add_action_btn.setMinimumHeight(46)
        self.add_action_btn.setObjectName("AddActionBtn")
        self.add_action_btn.setToolTip("Add the configured action below to the sequence  (Ctrl+Enter)")
        self.add_action_btn.clicked.connect(self.add_current_action)
        right_layout.addWidget(self.add_action_btn)

        # Recording controls (pinned at bottom)
        record_collapsible = CollapsibleGroupBox("Recording Controls")
        record_content_layout = QVBoxLayout()
        record_content_layout.setContentsMargins(10, 10, 10, 10)
        record_content_layout.setSpacing(8)
        
        record_btn_row = QHBoxLayout()
        record_btn_row.setSpacing(6)
        self.record_btn = QPushButton("⏺ Start Recording")
        self.record_btn.setMinimumHeight(36)
        self.record_btn.setStyleSheet("font-weight: bold; font-size: 11px;")
        self.stop_record_btn = QPushButton("⏹ Stop")
        self.stop_record_btn.setEnabled(False)
        self.stop_record_btn.setMinimumHeight(36)
        self.stop_record_btn.setStyleSheet("font-size: 11px;")
        self.import_record_btn = QPushButton("📥 Import Recording")
        self.import_record_btn.setEnabled(False)
        self.import_record_btn.setMinimumHeight(36)
        self.import_record_btn.setStyleSheet("font-size: 11px;")
        record_btn_row.addWidget(self.record_btn)
        record_btn_row.addWidget(self.stop_record_btn)
        record_btn_row.addWidget(self.import_record_btn)
        record_content_layout.addLayout(record_btn_row)
        
        self.record_moves_check = QCheckBox("Include Mouse Movement")
        self.record_moves_check.setChecked(False)
        self.record_moves_check.setStyleSheet("font-size: 10px; padding: 4px;")
        record_content_layout.addWidget(self.record_moves_check)

        self.record_pct_check = QCheckBox("Record coords as % of screen (portable across resolutions)")
        self.record_pct_check.setChecked(False)
        self.record_pct_check.setToolTip(
            "Store mouse positions as a fraction of screen size so the macro works\n"
            "correctly on different screen resolutions.")
        self.record_pct_check.setStyleSheet("font-size: 10px; padding: 4px;")
        record_content_layout.addWidget(self.record_pct_check)

        record_collapsible.content_layout.addLayout(record_content_layout)
        record_collapsible.setChecked(True)
        right_layout.addWidget(record_collapsible)

        split.addWidget(left, 50)
        split.addWidget(right, 50)
        self.card_layout.addLayout(split)

        # Bottom-right purge button (small, unobtrusive)
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        self.purge_btn = QPushButton("🗑️ Purge")
        self.purge_btn.setMaximumWidth(100)
        self.purge_btn.setMaximumHeight(24)
        self.purge_btn.setStyleSheet("font-size: 9px; padding: 2px 6px;")
        self.purge_btn.setToolTip("Force-close all Sloth processes and exit")
        self.purge_btn.clicked.connect(self._purge_from_editor)
        bottom_row.addWidget(self.purge_btn)
        self.card_layout.addLayout(bottom_row)

        self.move_up_btn.clicked.connect(self.move_action_up)
        self.move_down_btn.clicked.connect(self.move_action_down)
        self.delete_action_btn.clicked.connect(self.delete_selected_action)
        self.clear_all_btn.clicked.connect(self.clear_all_actions)
        self.test_btn.clicked.connect(self.test_macro)
        self.debug_btn.clicked.connect(self.debug_macro_preview)
        self.stop_btn.clicked.connect(self.stop_macro)
        self.record_btn.clicked.connect(self.start_recording_macro)
        self.stop_record_btn.clicked.connect(self.stop_recording_macro)
        self.import_record_btn.clicked.connect(self.import_recorded_macro)

        # Keyboard shortcuts for fast editing
        self.shortcut_add_action = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.shortcut_add_action.activated.connect(self.add_current_action)
        self.shortcut_add_action2 = QShortcut(QKeySequence("Ctrl+Enter"), self)
        self.shortcut_add_action2.activated.connect(self.add_current_action)
        self.shortcut_delete_action = QShortcut(QKeySequence("Delete"), self)
        self.shortcut_delete_action.activated.connect(self.delete_selected_action)
        self.shortcut_duplicate_action = QShortcut(QKeySequence("Ctrl+D"), self)
        self.shortcut_duplicate_action.activated.connect(self.duplicate_selected_action)
        self.shortcut_copy_action = QShortcut(QKeySequence("Ctrl+C"), self)
        self.shortcut_copy_action.activated.connect(self.copy_selected_actions)
        self.shortcut_paste_action = QShortcut(QKeySequence("Ctrl+V"), self)
        self.shortcut_paste_action.activated.connect(self.paste_actions)
        self.shortcut_undo = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.shortcut_undo.activated.connect(self.undo_last_change)
        self.shortcut_redo = QShortcut(QKeySequence("Ctrl+Y"), self)
        self.shortcut_redo.activated.connect(self.redo_last_change)

        # Live preview updates when form values change
        for idx in range(self.action_form_stack.count()):
            self._connect_preview_signals(self.action_form_stack.widget(idx))
        self.action_type_combo.currentTextChanged.connect(self.update_action_preview)
        self.update_action_preview()

        # Drag/drop + hover tracking
        self.action_table.setAcceptDrops(True)
        self.action_table.viewport().setAcceptDrops(True)
        self.action_table.viewport().setMouseTracking(True)
        self.action_table.viewport().installEventFilter(self)
        self._hovered_action_row = -1

        # Double-click to edit action inline
        self.action_table.cellDoubleClicked.connect(self._on_action_double_clicked)

        # Debounced auto-save timer (fires 350 ms after the last change)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(350)
        self._save_timer.timeout.connect(self._flush_save)

    def _purge_from_editor(self):
        """Call purge from editor page."""
        main_window = self.window()
        if hasattr(main_window, 'purge_sloth_processes_and_exit'):
            main_window.purge_sloth_processes_and_exit()

    def _template_summary(self, template_name: str) -> str:
        """Readable one-line template description for button labels."""
        summaries = {
            "OSRS: Copper Mining": "re-click ore when depleted",
            "OSRS: AFK Fishing": "loop fishing spot clicks",
            "OSRS: Alching": "alch key + item click cycle",
            "OSRS: Inventory Drop": "fast item drop pattern",
            "OSRS: Woodcutting": "wait for tree depletion then click",
            "OSRS: Smithing": "repeat smithing interaction",
            "OSRS: Burning Logs": "right-click + burn flow",
            "FiveM: Auto Cruise": "hold drive + occasional adjust",
            "FiveM: Click Interaction": "E interact + click loop",
            "FiveM: Slot Machine": "rapid interaction loop",
            "FiveM: Store Robbery": "open + interact sequence",
            "Minecraft: Auto Mine": "continuous mining clicks",
            "Minecraft: Block Builder": "place + move pattern",
            "Minecraft: AFK Fishing": "cast, wait, reel loop",
            "Minecraft: Farm Crop": "harvest + move rhythm",
            "WoW: Melee DPS Rotation": "1-2-3 rotation loop",
            "WoW: Gathering (Herb/Ore)": "interact + move + repeat",
            "WoW: Healing Rotation": "healing key cadence",
            "Valorant: Aim Practice": "click + reposition drill",
            "Valorant: Ability Spam": "q/e timing loop",
            "Click Loop": "simple repeated clicking",
            "Key Spam": "repeat key press pattern",
            "Wait & Click": "delay then click"
        }
        summary = summaries.get(template_name, "quick starter macro")
        if len(summary) > 26:
            summary = summary[:26].rstrip() + "..."
        return summary

    def _template_button_label(self, template_name: str) -> str:
        """Stable two-line label for template cards (prevents shrinking/clipping)."""
        clean_name = template_name.split(":", 1)[1].strip() if ":" in template_name else template_name
        if len(clean_name) > 20:
            clean_name = clean_name[:20].rstrip() + "..."
        summary = self._template_summary(template_name)
        if len(summary) > 24:
            summary = summary[:24].rstrip() + "..."
        return f"{clean_name}\n{summary}"

    def _normalize_action_type_label(self, label: str) -> str:
        """Remove decorative emoji/icons from action type labels."""
        if not label:
            return ""
        normalized = label
        if " " in normalized:
            first, rest = normalized.split(" ", 1)
            if any(ch for ch in first if ord(ch) > 127):
                normalized = rest
        return normalized.strip()

    def _make_help_label(self, text: str, tooltip: str) -> QWidget:
        """Create a compact label + '?' hint button row."""
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        lbl = QLabel(text)
        hint = QPushButton("❓")
        hint.setFixedSize(18, 18)
        hint.setToolTip(tooltip)
        hint.setStyleSheet("font-size: 10px; font-weight: bold; padding: 0;")
        row.addWidget(lbl)
        row.addWidget(hint)
        row.addStretch()
        return container

    def _action_row_color(self, action: MacroAction) -> QColor:
        """Generate subtle per-action-type background tint for sequence table rows."""
        base = QColor(self.get_theme_color('accent'))
        if not base.isValid():
            base = QColor("#4CC9F0")

        offsets = {
            "key": 0,
            "mouse_click": 20,
            "mouse_move": 40,
            "delay": 60,
            "loop_start": 80,
            "loop_end": 90,
            "pixel_check": 120,
            "image_match": 140,
            "region_watcher": 160,
            "skill_check_digits": 180,
            "window_focus_check": 200,
            "conditional_branch": 220,
            "run_profile": 240,
        }

        hue = base.hue() if base.hue() >= 0 else 200
        shifted = (hue + offsets.get(action.action_type, 0)) % 360
        tint = QColor.fromHsv(shifted, max(30, base.saturation() // 3), max(35, base.value() // 3))
        tint.setAlpha(55)
        return tint
    
    def _create_key_form(self):
        """Create keyboard action form."""
        form = QWidget()
        layout = QVBoxLayout(form)
        
        grid = QGridLayout()
        
        grid.addWidget(QLabel("Key:"), 0, 0)
        key_row = QHBoxLayout()
        self.key_input = QLineEdit("a")
        self.capture_key_btn = QPushButton("⌨️ Press Key")
        self.capture_key_btn.clicked.connect(self.start_key_capture)
        self.is_capturing_key = False
        key_row.addWidget(self.key_input)
        key_row.addWidget(self.capture_key_btn)
        grid.addLayout(key_row, 0, 1)
        
        grid.addWidget(QLabel("Type:"), 1, 0)
        self.key_type_combo = NoWheelComboBox()
        self.key_type_combo.addItems(["press", "hold", "release"])
        grid.addWidget(self.key_type_combo, 1, 1)
        
        grid.addWidget(QLabel("Hold Duration (ms):"), 2, 0)
        self.key_duration_spin = NoWheelSpinBox()
        self.key_duration_spin.setRange(1, 10000)
        self.key_duration_spin.setValue(50)
        grid.addWidget(self.key_duration_spin, 2, 1)
        
        layout.addLayout(grid)
        
        hint = QLabel("Supported keys: a-z, 0-9, space, enter, tab, shift, ctrl, alt, esc, arrow keys")
        hint.setStyleSheet("font-size: 11px; color: #666; font-style: italic;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        
        layout.addStretch()
        self.action_form_stack.addWidget(form)
    
    def _create_mouse_click_form(self):
        """Create mouse click form."""
        form = QWidget()
        layout = QVBoxLayout(form)
        
        grid = QGridLayout()
        
        grid.addWidget(QLabel("Button:"), 0, 0)
        self.click_button_combo = NoWheelComboBox()
        self.click_button_combo.addItems(["left", "right", "middle"])
        grid.addWidget(self.click_button_combo, 0, 1)
        
        grid.addWidget(QLabel("X Position:"), 1, 0)
        self.click_x_spin = NoWheelSpinBox()
        self.click_x_spin.setRange(0, 9999)
        grid.addWidget(self.click_x_spin, 1, 1)
        
        grid.addWidget(QLabel("Y Position:"), 2, 0)
        self.click_y_spin = NoWheelSpinBox()
        self.click_y_spin.setRange(0, 9999)
        grid.addWidget(self.click_y_spin, 2, 1)
        
        # Pick coordinates button
        pick_click_btn = QPushButton("🎯 Pick from Screen")
        pick_click_btn.clicked.connect(self.pick_click_coordinates)
        grid.addWidget(pick_click_btn, 3, 0, 1, 2)
        
        self.click_relative = QCheckBox("Relative to current position")
        grid.addWidget(self.click_relative, 4, 0, 1, 2)
        
        grid.addWidget(QLabel("Click Count:"), 5, 0)
        self.clicks_spin = NoWheelSpinBox()
        self.clicks_spin.setRange(1, 10)
        self.clicks_spin.setValue(1)
        grid.addWidget(self.clicks_spin, 5, 1)
        
        layout.addLayout(grid)
        layout.addStretch()
        self.action_form_stack.addWidget(form)
    
    def _create_mouse_move_form(self):
        """Create mouse move form."""
        form = QWidget()
        layout = QVBoxLayout(form)
        
        grid = QGridLayout()
        
        grid.addWidget(QLabel("X Position:"), 0, 0)
        self.move_x_spin = NoWheelSpinBox()
        self.move_x_spin.setRange(0, 9999)
        grid.addWidget(self.move_x_spin, 0, 1)
        
        grid.addWidget(QLabel("Y Position:"), 1, 0)
        self.move_y_spin = NoWheelSpinBox()
        self.move_y_spin.setRange(0, 9999)
        grid.addWidget(self.move_y_spin, 1, 1)
        
        # Pick coordinates button
        pick_move_btn = QPushButton("🎯 Pick Mouse Position from Screen")
        pick_move_btn.clicked.connect(self.pick_move_coordinates)
        grid.addWidget(pick_move_btn, 2, 0, 1, 2)
        
        self.move_relative = QCheckBox("Relative movement")
        grid.addWidget(self.move_relative, 3, 0, 1, 2)
        
        grid.addWidget(QLabel("Duration (ms):"), 4, 0)
        self.move_duration_spin = NoWheelSpinBox()
        self.move_duration_spin.setRange(10, 5000)
        self.move_duration_spin.setValue(100)
        grid.addWidget(self.move_duration_spin, 4, 1)
        
        layout.addLayout(grid)

        hint = QLabel("Set mouse position by typing X/Y or clicking the pick button")
        hint.setStyleSheet("font-size: 11px; color: #666; font-style: italic;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addStretch()
        self.action_form_stack.addWidget(form)
    
    def _create_delay_form(self):
        """Create delay form."""
        form = QWidget()
        layout = QVBoxLayout(form)
        
        grid = QGridLayout()
        
        grid.addWidget(QLabel("Duration (ms):"), 0, 0)
        self.delay_duration_spin = NoWheelSpinBox()
        self.delay_duration_spin.setRange(1, 60000)
        self.delay_duration_spin.setValue(1000)
        grid.addWidget(self.delay_duration_spin, 0, 1)
        
        self.delay_randomize = QCheckBox("Randomize timing")
        self.delay_randomize.setChecked(False)
        self.delay_randomize.toggled.connect(lambda: self.delay_random_group.setVisible(self.delay_randomize.isChecked()))
        grid.addWidget(self.delay_randomize, 1, 0, 1, 2)
        
        layout.addLayout(grid)
        
        self.delay_random_group = QWidget()
        random_layout = QGridLayout(self.delay_random_group)
        
        random_layout.addWidget(QLabel("Random Min (ms):"), 0, 0)
        self.delay_min_spin = NoWheelSpinBox()
        self.delay_min_spin.setRange(1, 60000)
        self.delay_min_spin.setValue(800)
        random_layout.addWidget(self.delay_min_spin, 0, 1)
        
        random_layout.addWidget(QLabel("Random Max (ms):"), 1, 0)
        self.delay_max_spin = NoWheelSpinBox()
        self.delay_max_spin.setRange(1, 60000)
        self.delay_max_spin.setValue(1200)
        random_layout.addWidget(self.delay_max_spin, 1, 1)
        
        self.delay_random_group.setVisible(False)
        layout.addWidget(self.delay_random_group)
        
        layout.addStretch()
        self.action_form_stack.addWidget(form)
    
    def _create_loop_start_form(self):
        """Create loop start form."""
        form = QWidget()
        layout = QVBoxLayout(form)
        
        grid = QGridLayout()
        
        grid.addWidget(QLabel("Loop Type:"), 0, 0)
        self.loop_type_combo = NoWheelComboBox()
        self.loop_type_combo.addItems(["count", "infinite", "time"])
        self.loop_type_combo.currentTextChanged.connect(self.update_loop_form)
        grid.addWidget(self.loop_type_combo, 0, 1)
        
        grid.addWidget(QLabel("Loop Count:"), 1, 0)
        self.loop_count_spin_edit = NoWheelSpinBox()
        self.loop_count_spin_edit.setRange(1, 99999)
        self.loop_count_spin_edit.setValue(10)
        grid.addWidget(self.loop_count_spin_edit, 1, 1)
        
        grid.addWidget(QLabel("Duration (seconds):"), 2, 0)
        self.loop_duration_spin = NoWheelSpinBox()
        self.loop_duration_spin.setRange(1, 86400)
        self.loop_duration_spin.setValue(60)
        self.loop_duration_spin.setVisible(False)
        grid.addWidget(self.loop_duration_spin, 2, 1)
        
        layout.addLayout(grid)
        
        hint = QLabel("Loop End action must be added to close the loop")
        hint.setStyleSheet("font-size: 11px; color: #FF6B6B; font-style: italic;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        
        layout.addStretch()
        self.action_form_stack.addWidget(form)
    
    def _create_loop_end_form(self):
        """Create loop end form."""
        form = QWidget()
        layout = QVBoxLayout(form)
        
        info = QLabel("Marks the end of a loop block. All actions between Loop Start and Loop End will be repeated.")
        info.setStyleSheet("font-size: 12px; color: #A0A0A0;")
        info.setWordWrap(True)
        layout.addWidget(info)
        
        layout.addStretch()
        self.action_form_stack.addWidget(form)
    
    def _create_pixel_check_form(self):
        """Create pixel check form."""
        form = QWidget()
        layout = QVBoxLayout(form)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Position section
        pos_group = CollapsibleGroupBox("Pixel Position")
        pos_layout = QGridLayout()
        pos_layout.setSpacing(10)
        pos_layout.setColumnStretch(1, 1)
        
        pos_layout.addWidget(QLabel("X:"), 0, 0)
        self.pixel_x_spin = NoWheelSpinBox()
        self.pixel_x_spin.setRange(0, 9999)
        self.pixel_x_spin.setMinimumHeight(32)
        pos_layout.addWidget(self.pixel_x_spin, 0, 1)
        
        pos_layout.addWidget(QLabel("Y:"), 1, 0)
        self.pixel_y_spin = NoWheelSpinBox()
        self.pixel_y_spin.setRange(0, 9999)
        self.pixel_y_spin.setMinimumHeight(32)
        pos_layout.addWidget(self.pixel_y_spin, 1, 1)
        
        pick_coords_btn = QPushButton("🎯 Pick Pixel from Screen")
        pick_coords_btn.setMinimumHeight(38)
        pick_coords_btn.setStyleSheet("font-weight: bold;")
        pick_coords_btn.clicked.connect(self.pick_pixel_coordinates)
        pos_layout.addWidget(pick_coords_btn, 2, 0, 1, 2)
        pos_group.content_layout.addLayout(pos_layout)
        pos_group.setChecked(True)
        layout.addWidget(pos_group)
        
        # Color section
        color_group = CollapsibleGroupBox("Target Color")
        color_layout = QGridLayout()
        color_layout.setSpacing(10)
        
        color_layout.addWidget(QLabel("Color Hex:"), 0, 0)
        color_row = QHBoxLayout()
        color_row.setSpacing(6)
        self.pixel_color_input = QLineEdit("#FFFFFF")
        self.pixel_color_input.setMinimumHeight(32)
        self.pixel_color_btn = QPushButton("🎨 Pick")
        self.pixel_color_btn.setMaximumWidth(80)
        self.pixel_color_btn.setMinimumHeight(32)
        self.pixel_color_btn.clicked.connect(self.pick_pixel_color)
        color_row.addWidget(self.pixel_color_input, 2)
        color_row.addWidget(self.pixel_color_btn, 1)
        color_layout.addLayout(color_row, 0, 1)
        
        color_layout.addWidget(self._make_help_label("Tolerance:", "How much RGB variation is allowed. 0 = exact, 255 = very loose."), 1, 0)
        self.pixel_tolerance_spin = NoWheelSpinBox()
        self.pixel_tolerance_spin.setRange(0, 255)
        self.pixel_tolerance_spin.setValue(10)
        self.pixel_tolerance_spin.setMinimumHeight(32)
        self.pixel_tolerance_spin.setToolTip("0 = exact match, 255 = very loose")
        color_layout.addWidget(self.pixel_tolerance_spin, 1, 1)
        color_group.content_layout.addLayout(color_layout)
        color_group.setChecked(True)
        layout.addWidget(color_group)

        # Wait settings
        wait_group = CollapsibleGroupBox("Wait Settings")
        wait_layout = QGridLayout()
        wait_layout.setSpacing(10)
        
        self.pixel_wait_check = QCheckBox("Wait until color matches")
        self.pixel_wait_check.setChecked(True)
        self.pixel_wait_check.setMinimumHeight(26)
        wait_layout.addWidget(self.pixel_wait_check, 0, 0, 1, 2)

        wait_layout.addWidget(self._make_help_label("Timeout (ms):", "Max time to wait before giving up."), 1, 0)
        self.pixel_timeout_spin = NoWheelSpinBox()
        self.pixel_timeout_spin.setRange(100, 120000)
        self.pixel_timeout_spin.setValue(5000)
        self.pixel_timeout_spin.setMinimumHeight(32)
        wait_layout.addWidget(self.pixel_timeout_spin, 1, 1)

        wait_layout.addWidget(self._make_help_label("Check Every:", "Polling interval. Lower values react faster but use more CPU."), 2, 0)
        self.pixel_poll_spin = NoWheelSpinBox()
        self.pixel_poll_spin.setRange(10, 1000)
        self.pixel_poll_spin.setValue(30)
        self.pixel_poll_spin.setSuffix(" ms")
        self.pixel_poll_spin.setMinimumHeight(32)
        wait_layout.addWidget(self.pixel_poll_spin, 2, 1)
        wait_group.content_layout.addLayout(wait_layout)
        wait_group.setChecked(False)
        layout.addWidget(wait_group)
        
        # Trigger section
        trigger_layout = QHBoxLayout()
        trigger_layout.addWidget(QLabel("Trigger Macro:"))
        self.pixel_trigger_macro_combo = QComboBox()
        self.pixel_trigger_macro_combo.setMinimumHeight(32)
        self.pixel_trigger_macro_combo.addItem("(None)")
        self._load_macro_names_to_combo(self.pixel_trigger_macro_combo)
        trigger_layout.addWidget(self.pixel_trigger_macro_combo, 1)
        layout.addLayout(trigger_layout)
        
        layout.addStretch()
        self.action_form_stack.addWidget(form)
    
    def _create_image_match_form(self):
        """Create image match form."""
        form = QWidget()
        layout = QVBoxLayout(form)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        image_group = CollapsibleGroupBox("Template Image")
        image_layout = QGridLayout()
        image_layout.setSpacing(10)

        image_layout.addWidget(QLabel("Template Image:"), 0, 0)
        template_row = QHBoxLayout()
        self.image_template_input = QLineEdit()
        self.image_template_input.setPlaceholderText("Select image used for screen matching")
        self.image_template_input.textChanged.connect(self._update_image_match_preview)
        self.image_template_btn = QPushButton("Browse")
        self.image_template_btn.setMinimumHeight(32)
        self.image_template_btn.clicked.connect(self.browse_template_image)
        template_row.addWidget(self.image_template_input, 1)
        template_row.addWidget(self.image_template_btn)
        image_layout.addLayout(template_row, 0, 1, 1, 3)

        self.image_preview = QLabel("No template selected")
        self.image_preview.setAlignment(Qt.AlignCenter)
        self.image_preview.setMinimumHeight(84)
        self.image_preview.setStyleSheet("border: 1px solid #444; border-radius: 4px; padding: 4px;")
        image_layout.addWidget(self.image_preview, 1, 0, 1, 4)

        image_layout.addWidget(self._make_help_label("Confidence (0-1):", "Higher values are stricter matches. Start around 0.80."), 2, 0)
        self.image_confidence_spin = QDoubleSpinBox()
        self.image_confidence_spin.setRange(0.1, 1.0)
        self.image_confidence_spin.setSingleStep(0.05)
        self.image_confidence_spin.setValue(0.8)
        self.image_confidence_spin.setMinimumHeight(32)
        image_layout.addWidget(self.image_confidence_spin, 2, 1)

        image_group.content_layout.addLayout(image_layout)
        image_group.setChecked(True)
        layout.addWidget(image_group)
        
        region_group = CollapsibleGroupBox("Search Region (optional)")
        region_layout = QGridLayout()
        region_layout.setSpacing(10)
        
        region_layout.addWidget(QLabel("X:"), 0, 0)
        self.image_region_x = NoWheelSpinBox()
        self.image_region_x.setRange(0, 9999)
        self.image_region_x.setMinimumHeight(32)
        region_layout.addWidget(self.image_region_x, 0, 1)
        
        region_layout.addWidget(QLabel("Y:"), 0, 2)
        self.image_region_y = NoWheelSpinBox()
        self.image_region_y.setRange(0, 9999)
        self.image_region_y.setMinimumHeight(32)
        region_layout.addWidget(self.image_region_y, 0, 3)
        
        region_layout.addWidget(QLabel("Width:"), 1, 0)
        self.image_region_w = NoWheelSpinBox()
        self.image_region_w.setRange(1, 9999)
        self.image_region_w.setValue(1920)
        self.image_region_w.setMinimumHeight(32)
        region_layout.addWidget(self.image_region_w, 1, 1)
        
        region_layout.addWidget(QLabel("Height:"), 1, 2)
        self.image_region_h = NoWheelSpinBox()
        self.image_region_h.setRange(1, 9999)
        self.image_region_h.setValue(1080)
        self.image_region_h.setMinimumHeight(32)
        region_layout.addWidget(self.image_region_h, 1, 3)

        pick_region_btn = QPushButton("🔲 Drag to Select Region on Screen")
        pick_region_btn.setMinimumHeight(38)
        pick_region_btn.setStyleSheet("font-weight: bold;")
        pick_region_btn.clicked.connect(self.pick_image_match_region_from_screen)
        region_layout.addWidget(pick_region_btn, 2, 0, 1, 4)
        region_group.content_layout.addLayout(region_layout)
        region_group.setChecked(False)
        layout.addWidget(region_group)
        
        hint = QLabel("Requires image matching support (bundled in exe builds)")
        hint.setStyleSheet("font-size: 11px; color: #666; font-style: italic;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        
        layout.addStretch()
        self.action_form_stack.addWidget(form)
    
    def _create_region_watcher_form(self):
        """Create region color watcher form for gaming."""
        form = QWidget()
        layout = QVBoxLayout(form)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Region position section
        region_group = CollapsibleGroupBox("Screen Region")
        region_layout = QGridLayout()
        region_layout.setSpacing(10)
        region_layout.setColumnStretch(1, 1)
        region_layout.setColumnStretch(3, 1)
        
        region_layout.addWidget(QLabel("X:"), 0, 0)
        self.region_x_spin = NoWheelSpinBox()
        self.region_x_spin.setRange(0, 9999)
        self.region_x_spin.setValue(100)
        self.region_x_spin.setMinimumHeight(32)
        region_layout.addWidget(self.region_x_spin, 0, 1)
        
        region_layout.addWidget(QLabel("Y:"), 0, 2)
        self.region_y_spin = NoWheelSpinBox()
        self.region_y_spin.setRange(0, 9999)
        self.region_y_spin.setValue(100)
        self.region_y_spin.setMinimumHeight(32)
        region_layout.addWidget(self.region_y_spin, 0, 3)
        
        region_layout.addWidget(QLabel("Width:"), 1, 0)
        self.region_w_spin = NoWheelSpinBox()
        self.region_w_spin.setRange(1, 9999)
        self.region_w_spin.setValue(200)
        self.region_w_spin.setMinimumHeight(32)
        region_layout.addWidget(self.region_w_spin, 1, 1)
        
        region_layout.addWidget(QLabel("Height:"), 1, 2)
        self.region_h_spin = NoWheelSpinBox()
        self.region_h_spin.setRange(1, 9999)
        self.region_h_spin.setValue(50)
        self.region_h_spin.setMinimumHeight(32)
        region_layout.addWidget(self.region_h_spin, 1, 3)
        
        pick_region_btn = QPushButton("🔲 Drag to Select Region on Screen")
        pick_region_btn.setMinimumHeight(38)
        pick_region_btn.setStyleSheet("font-weight: bold;")
        pick_region_btn.clicked.connect(self.pick_region_from_screen)
        region_layout.addWidget(pick_region_btn, 2, 0, 1, 4)
        region_group.content_layout.addLayout(region_layout)
        region_group.setChecked(True)
        layout.addWidget(region_group)
        
        # Watch settings
        watch_group = CollapsibleGroupBox("Watch Settings")
        watch_layout = QGridLayout()
        watch_layout.setSpacing(10)
        
        watch_layout.addWidget(QLabel("Target Color:"), 0, 0)
        color_row = QHBoxLayout()
        color_row.setSpacing(6)
        self.region_color_input = QLineEdit("#FF0000")
        self.region_color_input.setMinimumHeight(32)
        self.region_color_btn = QPushButton("🎨 Pick")
        self.region_color_btn.setMaximumWidth(80)
        self.region_color_btn.setMinimumHeight(32)
        def _pick_rw_color():
            c = QColorDialog.getColor()
            if c.isValid():
                self.region_color_input.setText(c.name())
        self.region_color_btn.clicked.connect(_pick_rw_color)
        color_row.addWidget(self.region_color_input, 2)
        color_row.addWidget(self.region_color_btn, 1)
        watch_layout.addLayout(color_row, 0, 1)
        
        watch_layout.addWidget(QLabel("Tolerance:"), 1, 0)
        self.region_tolerance_spin = NoWheelSpinBox()
        self.region_tolerance_spin.setRange(0, 255)
        self.region_tolerance_spin.setValue(15)
        self.region_tolerance_spin.setMinimumHeight(32)
        self.region_tolerance_spin.setToolTip("Higher = more color variation accepted")
        watch_layout.addWidget(self.region_tolerance_spin, 1, 1)
        
        watch_layout.addWidget(self._make_help_label("Watch Type:", "appears = color enters region, disappears = color is gone."), 2, 0)
        self.region_watch_type_combo = NoWheelComboBox()
        self.region_watch_type_combo.setMinimumHeight(32)
        self.region_watch_type_combo.addItems(["appears", "disappears", "increases_brightness", "decreases_brightness"])
        watch_layout.addWidget(self.region_watch_type_combo, 2, 1)
        
        watch_layout.addWidget(QLabel("Timeout (ms):"), 3, 0)
        self.region_timeout_spin = NoWheelSpinBox()
        self.region_timeout_spin.setRange(100, 60000)
        self.region_timeout_spin.setValue(5000)
        self.region_timeout_spin.setSuffix(" ms")
        self.region_timeout_spin.setMinimumHeight(32)
        watch_layout.addWidget(self.region_timeout_spin, 3, 1)
        watch_group.content_layout.addLayout(watch_layout)
        watch_group.setChecked(True)
        layout.addWidget(watch_group)
        
        # Optional settings
        desc_layout = QHBoxLayout()
        desc_layout.addWidget(QLabel("Description:"))
        self.region_desc_input = QLineEdit()
        self.region_desc_input.setMinimumHeight(32)
        self.region_desc_input.setPlaceholderText("e.g., Watch health bar")
        desc_layout.addWidget(self.region_desc_input, 1)
        layout.addLayout(desc_layout)
        
        trigger_layout = QHBoxLayout()
        trigger_layout.addWidget(QLabel("Trigger Macro:"))
        self.region_trigger_macro_combo = QComboBox()
        self.region_trigger_macro_combo.setMinimumHeight(32)
        self.region_trigger_macro_combo.addItem("(None)")
        self._load_macro_names_to_combo(self.region_trigger_macro_combo)
        trigger_layout.addWidget(self.region_trigger_macro_combo, 1)
        layout.addLayout(trigger_layout)
        
        layout.addStretch()
        self.action_form_stack.addWidget(form)
    
    def pick_region_from_screen(self):
        """Open fullscreen region picker like Windows Shift+S."""
        logger.info("Region picker button clicked")
        def on_region_selected(x, y, width, height):
            logger.info(f"Region selected: x={x}, y={y}, w={width}, h={height}")
            self.region_x_spin.setValue(x)
            self.region_y_spin.setValue(y)
            self.region_w_spin.setValue(width)
            self.region_h_spin.setValue(height)
        
        try:
            self._active_overlay = RegionPickerOverlay(
                callback=on_region_selected,
                accent_color=self.get_theme_color('accent')
            )
            logger.info("RegionPickerOverlay created, showing fullscreen")
            self._active_overlay.showFullScreen()
            self._active_overlay.raise_()
            self._active_overlay.activateWindow()
            self._active_overlay.setFocus()
            QApplication.processEvents()
        except Exception as e:
            logger.error(f"Error showing region picker: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to open region picker: {e}")
    
    def _get_open_window_titles(self):
        """Return sorted list of all non-empty visible window titles."""
        try:
            import pygetwindow
            titles = sorted({t.strip() for t in pygetwindow.getAllTitles() if t and t.strip()}, key=str.lower)
            return titles
        except Exception:
            return []

    def _create_window_focus_check_form(self):
        """Create window focus check form."""
        form = QWidget()
        layout = QVBoxLayout(form)

        grid = QGridLayout()

        # --- Picker row ---
        grid.addWidget(QLabel("Pick Window:"), 0, 0)
        picker_row = QHBoxLayout()
        picker_row.setSpacing(4)
        self._wf_picker_combo = NoWheelComboBox()
        self._wf_picker_combo.addItem("- choose a running window -")
        self._wf_picker_combo.addItems(self._get_open_window_titles())
        self._wf_picker_combo.setToolTip("Select from currently open windows")
        self._wf_picker_combo.currentIndexChanged.connect(
            lambda i: self.window_title_input.setText(self._wf_picker_combo.currentText())
            if i > 0 else None
        )
        picker_row.addWidget(self._wf_picker_combo, 1)
        refresh_btn = QPushButton("🔄")
        refresh_btn.setFixedWidth(32)
        refresh_btn.setToolTip("Refresh window list")
        def _refresh_wf_picker():
            current = self.window_title_input.text()
            self._wf_picker_combo.blockSignals(True)
            self._wf_picker_combo.clear()
            self._wf_picker_combo.addItem("- choose a running window -")
            self._wf_picker_combo.addItems(self._get_open_window_titles())
            self._wf_picker_combo.blockSignals(False)
            self.window_title_input.setText(current)  # keep whatever the user typed
        refresh_btn.clicked.connect(_refresh_wf_picker)
        picker_row.addWidget(refresh_btn)
        grid.addLayout(picker_row, 0, 1)

        # --- Manual title row ---
        grid.addWidget(QLabel("Title Contains:"), 1, 0)
        self.window_title_input = QLineEdit()
        self.window_title_input.setPlaceholderText("e.g., RuneScape | WoW | Valorant")
        grid.addWidget(self.window_title_input, 1, 1)

        grid.addWidget(QLabel("Timeout (ms):"), 2, 0)
        self.window_timeout_spin = NoWheelSpinBox()
        self.window_timeout_spin.setRange(100, 60000)
        self.window_timeout_spin.setValue(1000)
        grid.addWidget(self.window_timeout_spin, 2, 1)

        grid.addWidget(QLabel("Description:"), 3, 0)
        self.window_desc_input = QLineEdit()
        self.window_desc_input.setPlaceholderText("e.g., Verify game is focused")
        grid.addWidget(self.window_desc_input, 3, 1)

        layout.addLayout(grid)

        hint = QLabel("Pick a window above or type a partial title. Separate multiple alternatives with |")
        hint.setStyleSheet("font-size: 11px; color: #666; font-style: italic;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addStretch()
        self.action_form_stack.addWidget(form)

    def _create_skill_check_digits_form(self):
        """Create OCR skill-check form (bundled OCR expected)."""
        form = QWidget()
        layout = QVBoxLayout(form)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Region section
        region_group = QGroupBox("OCR Region")
        region_layout = QGridLayout(region_group)
        region_layout.setSpacing(10)
        region_layout.setColumnStretch(1, 1)
        region_layout.setColumnStretch(3, 1)
        
        region_layout.addWidget(QLabel("X:"), 0, 0)
        self.skill_region_x = NoWheelSpinBox()
        self.skill_region_x.setRange(0, 9999)
        self.skill_region_x.setMinimumHeight(32)
        region_layout.addWidget(self.skill_region_x, 0, 1)

        region_layout.addWidget(QLabel("Y:"), 0, 2)
        self.skill_region_y = NoWheelSpinBox()
        self.skill_region_y.setRange(0, 9999)
        self.skill_region_y.setMinimumHeight(32)
        region_layout.addWidget(self.skill_region_y, 0, 3)

        region_layout.addWidget(QLabel("Width:"), 1, 0)
        self.skill_region_w = NoWheelSpinBox()
        self.skill_region_w.setRange(20, 5000)
        self.skill_region_w.setValue(260)
        self.skill_region_w.setMinimumHeight(32)
        region_layout.addWidget(self.skill_region_w, 1, 1)

        region_layout.addWidget(QLabel("Height:"), 1, 2)
        self.skill_region_h = NoWheelSpinBox()
        self.skill_region_h.setRange(20, 5000)
        self.skill_region_h.setValue(120)
        self.skill_region_h.setMinimumHeight(32)
        region_layout.addWidget(self.skill_region_h, 1, 3)

        pick_region_btn = QPushButton("🔲 Select OCR Region on Screen")
        pick_region_btn.setMinimumHeight(38)
        pick_region_btn.setStyleSheet("font-weight: bold;")
        pick_region_btn.clicked.connect(self.pick_skill_check_region)
        region_layout.addWidget(pick_region_btn, 2, 0, 1, 4)
        layout.addWidget(region_group)

        # OCR settings
        ocr_group = QGroupBox("OCR Settings")
        ocr_layout = QGridLayout(ocr_group)
        ocr_layout.setSpacing(10)
        
        ocr_layout.addWidget(QLabel("Max Digits:"), 0, 0)
        self.skill_max_digits = NoWheelSpinBox()
        self.skill_max_digits.setRange(1, 10)
        self.skill_max_digits.setValue(6)
        self.skill_max_digits.setMinimumHeight(32)
        self.skill_max_digits.setToolTip("Maximum number of digits to extract")
        ocr_layout.addWidget(self.skill_max_digits, 0, 1)

        ocr_layout.addWidget(QLabel("Key Delay (ms):"), 1, 0)
        self.skill_key_delay = NoWheelSpinBox()
        self.skill_key_delay.setRange(1, 1000)
        self.skill_key_delay.setValue(60)
        self.skill_key_delay.setMinimumHeight(32)
        self.skill_key_delay.setToolTip("Delay between each keypress")
        ocr_layout.addWidget(self.skill_key_delay, 1, 1)
        layout.addWidget(ocr_group)

        test_ocr_btn = QPushButton("📝 Test OCR on Current Region")
        test_ocr_btn.setMinimumHeight(38)
        test_ocr_btn.setStyleSheet("font-weight: bold;")
        test_ocr_btn.clicked.connect(self.test_skill_check_ocr)
        layout.addWidget(test_ocr_btn)

        req = QLabel("OCR required: install tesseract.exe in ./teseract/tesseract.exe (or ./tesseract/tesseract.exe)")
        req.setStyleSheet("font-size: 10px; color: #A0A0A0; font-style: italic;")
        req.setWordWrap(True)
        layout.addWidget(req)

        layout.addStretch()
        self.action_form_stack.addWidget(form)

    def pick_skill_check_region(self):
        """Pick screen region for OCR-based skill checks."""
        def on_region_selected(x, y, width, height):
            self.skill_region_x.setValue(x)
            self.skill_region_y.setValue(y)
            self.skill_region_w.setValue(width)
            self.skill_region_h.setValue(height)

        self._active_overlay = RegionPickerOverlay(
            callback=on_region_selected,
            accent_color=self.get_theme_color('accent')
        )
        self._active_overlay.showFullScreen()
        self._active_overlay.raise_()
        self._active_overlay.activateWindow()
        self._active_overlay.setFocus()
        QApplication.processEvents()

    def test_skill_check_ocr(self):
        """Test OCR on current region using local tesseract install."""
        try:
            import pyautogui
            import pytesseract
        except ImportError as e:
            QMessageBox.warning(self, "Missing Dependency", f"Cannot test OCR: {e.name} not installed")
            return

        if not TESSERACT_AVAILABLE:
            QMessageBox.warning(
                self,
                "OCR Not Found",
                "Install tesseract.exe at one of these paths:\n"
                "./teseract/tesseract.exe\n"
                "./tesseract/tesseract.exe"
            )
            return

        try:
            x = self.skill_region_x.value()
            y = self.skill_region_y.value()
            w = self.skill_region_w.value()
            h = self.skill_region_h.value()
            screenshot = pyautogui.screenshot(region=(x, y, w, h))

            import PIL.ImageOps
            import PIL.ImageEnhance
            screenshot = screenshot.convert('L')
            screenshot = PIL.ImageOps.autocontrast(screenshot)
            screenshot = PIL.ImageEnhance.Sharpness(screenshot).enhance(2.0)

            text = pytesseract.image_to_string(
                screenshot,
                config='--psm 7 -c tessedit_char_whitelist=0123456789'
            )
            digits = ''.join(ch for ch in text if ch.isdigit())
            QMessageBox.information(
                self,
                "OCR Test Result",
                f"Region: ({x}, {y}) {w}x{h}\n\nRaw OCR: '{text.strip()}'\n\nExtracted Digits: '{digits}'"
            )
        except Exception as e:
            QMessageBox.critical(self, "OCR Test Failed", f"Error: {e}")
    
    def _create_conditional_branch_form(self):
        """Create conditional branching form."""
        form = QWidget()
        layout = QVBoxLayout(form)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        
        # Title
        title = QLabel("🔧 Advanced: IF/THEN/ELSE Conditional Logic")
        title.setStyleSheet("font-weight: bold; font-size: 12px; color: #00D4FF;")
        layout.addWidget(title)
        
        # Condition setup section
        cond_group = QGroupBox("Step 1: Define Condition")
        cond_layout = QVBoxLayout(cond_group)
        cond_layout.setContentsMargins(10, 10, 10, 10)
        cond_layout.setSpacing(8)
        
        grid = QGridLayout()
        
        grid.addWidget(QLabel("Condition Type:"), 0, 0)
        self.cond_type_combo = NoWheelComboBox()
        self.cond_type_combo.addItems(["pixel_match: Check pixel color at position", 
                                        "image_match: Find image on screen",
                                        "region_watch: Detect region changes"])
        grid.addWidget(self.cond_type_combo, 0, 1)
        
        cond_layout.addLayout(grid)

        # Pixel condition controls (same flow as Pixel Check)
        self.cond_pixel_group = QGroupBox("Pixel Match Condition")
        pixel_layout = QGridLayout(self.cond_pixel_group)
        pixel_layout.setSpacing(8)
        pixel_layout.addWidget(QLabel("Position X:"), 0, 0)
        self.cond_x_spin = NoWheelSpinBox()
        self.cond_x_spin.setRange(0, 9999)
        self.cond_x_spin.setToolTip("X coordinate to check")
        pixel_layout.addWidget(self.cond_x_spin, 0, 1)

        pixel_layout.addWidget(QLabel("Position Y:"), 0, 2)
        self.cond_y_spin = NoWheelSpinBox()
        self.cond_y_spin.setRange(0, 9999)
        self.cond_y_spin.setToolTip("Y coordinate to check")
        pixel_layout.addWidget(self.cond_y_spin, 0, 3)

        pick_cond_pixel_btn = QPushButton("🎯 Pick Pixel from Screen")
        pick_cond_pixel_btn.setMinimumHeight(34)
        pick_cond_pixel_btn.clicked.connect(self.pick_conditional_pixel_coordinates)
        pixel_layout.addWidget(pick_cond_pixel_btn, 1, 0, 1, 4)

        pixel_layout.addWidget(QLabel("Target Color:"), 2, 0)
        pixel_color_row = QHBoxLayout()
        self.cond_color_input = QLineEdit("#FFFFFF")
        self.cond_color_input.setToolTip("Hex color format: #RRGGBB")
        cond_color_btn = QPushButton("🎨 Pick")
        cond_color_btn.setMaximumWidth(90)
        cond_color_btn.clicked.connect(self.pick_conditional_color)
        pixel_color_row.addWidget(self.cond_color_input, 1)
        pixel_color_row.addWidget(cond_color_btn)
        pixel_layout.addLayout(pixel_color_row, 2, 1, 1, 3)

        pixel_layout.addWidget(QLabel("Color Tolerance:"), 3, 0)
        self.cond_tolerance_spin = NoWheelSpinBox()
        self.cond_tolerance_spin.setRange(0, 255)
        self.cond_tolerance_spin.setValue(15)
        self.cond_tolerance_spin.setToolTip("Color match tolerance (0-255)")
        pixel_layout.addWidget(self.cond_tolerance_spin, 3, 1)
        cond_layout.addWidget(self.cond_pixel_group)

        # Image condition controls (same flow as Image Match)
        self.cond_image_group = QGroupBox("Image Match Condition")
        image_layout = QGridLayout(self.cond_image_group)
        image_layout.setSpacing(8)

        image_layout.addWidget(QLabel("Template Image:"), 0, 0)
        image_row = QHBoxLayout()
        self.cond_image_template_input = QLineEdit()
        self.cond_image_template_btn = QPushButton("Browse")
        self.cond_image_template_btn.clicked.connect(self.browse_conditional_template_image)
        image_row.addWidget(self.cond_image_template_input, 1)
        image_row.addWidget(self.cond_image_template_btn)
        image_layout.addLayout(image_row, 0, 1, 1, 3)

        self.cond_image_preview = QLabel("No template selected")
        self.cond_image_preview.setAlignment(Qt.AlignCenter)
        self.cond_image_preview.setMinimumHeight(80)
        self.cond_image_preview.setStyleSheet("border: 1px solid #444; border-radius: 4px; padding: 4px;")
        image_layout.addWidget(self.cond_image_preview, 1, 0, 1, 4)

        image_layout.addWidget(QLabel("Confidence:"), 2, 0)
        self.cond_image_confidence_spin = QDoubleSpinBox()
        self.cond_image_confidence_spin.setRange(0.1, 1.0)
        self.cond_image_confidence_spin.setSingleStep(0.05)
        self.cond_image_confidence_spin.setValue(0.8)
        image_layout.addWidget(self.cond_image_confidence_spin, 2, 1)

        image_layout.addWidget(QLabel("Region X:"), 3, 0)
        self.cond_image_region_x = NoWheelSpinBox()
        self.cond_image_region_x.setRange(0, 9999)
        image_layout.addWidget(self.cond_image_region_x, 3, 1)
        image_layout.addWidget(QLabel("Region Y:"), 3, 2)
        self.cond_image_region_y = NoWheelSpinBox()
        self.cond_image_region_y.setRange(0, 9999)
        image_layout.addWidget(self.cond_image_region_y, 3, 3)

        image_layout.addWidget(QLabel("Width:"), 4, 0)
        self.cond_image_region_w = NoWheelSpinBox()
        self.cond_image_region_w.setRange(1, 9999)
        self.cond_image_region_w.setValue(1920)
        image_layout.addWidget(self.cond_image_region_w, 4, 1)
        image_layout.addWidget(QLabel("Height:"), 4, 2)
        self.cond_image_region_h = NoWheelSpinBox()
        self.cond_image_region_h.setRange(1, 9999)
        self.cond_image_region_h.setValue(1080)
        image_layout.addWidget(self.cond_image_region_h, 4, 3)

        pick_cond_region_btn = QPushButton("🔲 Drag to Select Region on Screen")
        pick_cond_region_btn.setMinimumHeight(34)
        pick_cond_region_btn.clicked.connect(self.pick_conditional_region_from_screen)
        image_layout.addWidget(pick_cond_region_btn, 5, 0, 1, 4)
        cond_layout.addWidget(self.cond_image_group)

        # Region watch controls
        self.cond_region_group = QGroupBox("Region Watch Condition")
        region_layout = QGridLayout(self.cond_region_group)
        region_layout.setSpacing(8)
        region_layout.addWidget(QLabel("Region X:"), 0, 0)
        self.cond_region_x = NoWheelSpinBox()
        self.cond_region_x.setRange(0, 9999)
        region_layout.addWidget(self.cond_region_x, 0, 1)
        region_layout.addWidget(QLabel("Region Y:"), 0, 2)
        self.cond_region_y = NoWheelSpinBox()
        self.cond_region_y.setRange(0, 9999)
        region_layout.addWidget(self.cond_region_y, 0, 3)

        region_layout.addWidget(QLabel("Width:"), 1, 0)
        self.cond_region_w = NoWheelSpinBox()
        self.cond_region_w.setRange(1, 9999)
        self.cond_region_w.setValue(200)
        region_layout.addWidget(self.cond_region_w, 1, 1)
        region_layout.addWidget(QLabel("Height:"), 1, 2)
        self.cond_region_h = NoWheelSpinBox()
        self.cond_region_h.setRange(1, 9999)
        self.cond_region_h.setValue(100)
        region_layout.addWidget(self.cond_region_h, 1, 3)

        pick_cond_watch_region_btn = QPushButton("🔲 Drag to Select Region on Screen")
        pick_cond_watch_region_btn.setMinimumHeight(34)
        pick_cond_watch_region_btn.clicked.connect(self.pick_conditional_region_from_screen)
        region_layout.addWidget(pick_cond_watch_region_btn, 2, 0, 1, 4)

        region_layout.addWidget(QLabel("Target Color:"), 3, 0)
        region_color_row = QHBoxLayout()
        self.cond_region_color_input = QLineEdit("#FF0000")
        cond_region_color_btn = QPushButton("🎨 Pick")
        cond_region_color_btn.setMaximumWidth(90)
        cond_region_color_btn.clicked.connect(self.pick_conditional_color)
        region_color_row.addWidget(self.cond_region_color_input, 1)
        region_color_row.addWidget(cond_region_color_btn)
        region_layout.addLayout(region_color_row, 3, 1, 1, 3)

        region_layout.addWidget(QLabel("Color Tolerance:"), 4, 0)
        self.cond_region_tolerance_spin = NoWheelSpinBox()
        self.cond_region_tolerance_spin.setRange(0, 255)
        self.cond_region_tolerance_spin.setValue(15)
        region_layout.addWidget(self.cond_region_tolerance_spin, 4, 1)
        cond_layout.addWidget(self.cond_region_group)
        layout.addWidget(cond_group)
        
        # Nested actions section
        actions_group = QGroupBox("Step 2: Configure Nested Actions")
        actions_layout = QVBoxLayout(actions_group)
        actions_layout.setContentsMargins(10, 10, 10, 10)
        actions_layout.setSpacing(8)
        
        info_text = QLabel(
            "💡 After adding this conditional, you can:\n"
            "1. Right-click the conditional action in the sequence\n"
            "2. Select 'Configure Nested Actions'\n"
            "3. Add macros to execute if condition is TRUE\n"
            "4. Add macros to execute if condition is FALSE\n\n"
            "Example: IF health < 50% THEN drink potion ELSE continue farming"
        )
        info_text.setStyleSheet("font-size: 10px; color: #B0B5B8; line-height: 1.4;")
        info_text.setWordWrap(True)
        actions_layout.addWidget(info_text)
        layout.addWidget(actions_group)
        
        # Description
        grid2 = QGridLayout()
        grid2.addWidget(QLabel("Description:"), 0, 0)
        self.cond_desc_input = QLineEdit()
        self.cond_desc_input.setPlaceholderText("e.g., 'If health low, cast heal'")
        grid2.addWidget(self.cond_desc_input, 0, 1)
        layout.addLayout(grid2)

        self.cond_type_combo.currentTextChanged.connect(self._update_conditional_condition_ui)
        self._update_conditional_condition_ui(self.cond_type_combo.currentText())
        
        layout.addStretch()
        self.action_form_stack.addWidget(form)
    
    def update_action_form(self, action_type: str):
        """Switch to appropriate form based on action type."""
        action_type = self._normalize_action_type_label(action_type)
        index_map = {
            "Keyboard Key": 0,
            "Mouse Click": 1,
            "Mouse Move": 2,
            "Mouse Position": 2,
            "Delay": 3,
            "Loop Start": 4,
            "Loop End": 5,
            "Pixel Check": 6,
            "Image Match": 7,
            "Region Watcher": 8,
            "Skill Check Digits": 9,
            "Window Focus Check": 10,
            "Conditional Branch": 11
        }
        self.action_form_stack.setCurrentIndex(index_map.get(action_type, 0))
        self._apply_last_used_defaults(action_type)
        self.update_action_preview()
    
    def update_loop_form(self, loop_type: str):
        """Update loop form based on type."""
        show_count = loop_type == "count"
        show_duration = loop_type == "time"
        
        self.loop_count_spin_edit.setVisible(show_count)
        self.loop_duration_spin.setVisible(show_duration)
    
    def pick_pixel_coordinates(self):
        """Show fullscreen overlay to pick coordinates."""
        def on_coordinates_selected(x, y):
            self.pixel_x_spin.setValue(x)
            self.pixel_y_spin.setValue(y)
        
        self._active_overlay = CoordinatePickerOverlay(
            callback=on_coordinates_selected,
            accent_color=self.get_theme_color('accent')
        )
        self._active_overlay.showFullScreen()
        self._active_overlay.raise_()
        self._active_overlay.activateWindow()
        self._active_overlay.setFocus()
        QApplication.processEvents()
    
    def get_theme_color(self, color_key='accent'):
        """Get current theme color by key (fallback for MacroEditorPage)."""
        theme_name = 'midnight'
        main_window = self.window()
        if hasattr(main_window, 'current_theme'):
            theme_name = main_window.current_theme
        else:
            settings = QSettings("SlothMacro", "Sloth")
            theme_name = settings.value("theme", "midnight")
        theme = THEMES.get(theme_name, THEMES['midnight'])
        return theme.get(color_key, '#FF006E')
    
    def _load_macro_names_to_combo(self, combo_box: QComboBox):
        """Load available macro names from profiles directory into a combobox."""
        try:
            profiles_dir = os.path.join(get_base_dir(), "profiles")
            
            if not os.path.exists(profiles_dir):
                return
            
            macro_files = sorted(f for f in os.listdir(profiles_dir) if f.endswith('.json'))
            for filename in macro_files:
                # Use the profile's actual name field so the value matches what
                # MacroExecutor._trigger_macro() looks up (which searches by name, not filename).
                try:
                    filepath = os.path.join(profiles_dir, filename)
                    with open(filepath, 'r', encoding='utf-8') as fh:
                        data = json.load(fh)
                    name = data.get('name') or filename[:-5]
                except Exception:
                    name = filename[:-5]  # Fallback to filename stem if JSON is unreadable
                if combo_box.findText(name) == -1:  # Only add if not already present
                    combo_box.addItem(name)
        except Exception as e:
            logger.warning(f"Failed to load macro names: {e}")
    
    def start_key_capture(self):
        """Start listening for the next keyboard key press."""
        self.is_capturing_key = True
        self.capture_key_btn.setText("⏳ Waiting for key...")
        self.capture_key_btn.setEnabled(False)
        self.key_input.setEnabled(False)
        
        # Use keyboard listener to capture next key
        def on_key_press(key):
            if not self.is_capturing_key:
                return
            
            try:
                # Convert pynput key to string
                if hasattr(key, 'char'):
                    key_str = key.char if key.char else str(key)
                else:
                    key_str = str(key).replace("Key.", "")
                
                # Map special keys
                key_map = {
                    'space': 'space',
                    'enter': 'enter',
                    'tab': 'tab',
                    'shift': 'shift',
                    'shift_l': 'shift',
                    'shift_r': 'shift',
                    'ctrl': 'ctrl',
                    'ctrl_l': 'ctrl',
                    'ctrl_r': 'ctrl',
                    'alt': 'alt',
                    'alt_l': 'alt',
                    'alt_r': 'alt',
                    'esc': 'esc',
                    'escape': 'esc',
                    'up': 'up',
                    'down': 'down',
                    'left': 'left',
                    'right': 'right',
                }
                
                captured_key = key_map.get(key_str.lower(), key_str.lower())
                self.is_capturing_key = False
                # Marshal UI updates to the Qt main thread (pynput callback runs on its own thread)
                def _update_ui(k=captured_key):
                    self.key_input.setText(k)
                    self.capture_key_btn.setText("⌨️ Press Key")
                    self.capture_key_btn.setEnabled(True)
                    self.key_input.setEnabled(True)
                QTimer.singleShot(0, _update_ui)
                
                return False  # Stop listening
            except Exception as e:
                logger.warning(f"Error capturing key: {e}")
                return False
        
        # Start listening for one key press
        try:
            from pynput.keyboard import Listener
            listener = Listener(on_press=on_key_press)
            listener.start()
            # Auto-cancel after 10 s if no key pressed (prevents listener thread leak)
            def _capture_timeout():
                if self.is_capturing_key:
                    self.is_capturing_key = False
                    listener.stop()
                    self.capture_key_btn.setText("⌨️ Press Key")
                    self.capture_key_btn.setEnabled(True)
                    self.key_input.setEnabled(True)
            QTimer.singleShot(10000, _capture_timeout)
        except ImportError:
            logger.warning("pynput not installed - key capture disabled")
            self.is_capturing_key = False
            self.capture_key_btn.setText("⌨️ Press Key")
            self.capture_key_btn.setEnabled(True)
            self.key_input.setEnabled(True)
    
    def pick_click_coordinates(self):
        """Pick mouse click coordinates with fullscreen overlay."""
        def on_coordinates_selected(x, y):
            self.click_x_spin.setValue(x)
            self.click_y_spin.setValue(y)
        
        self._active_overlay = CoordinatePickerOverlay(
            callback=on_coordinates_selected,
            accent_color=self.get_theme_color('accent')
        )
        self._active_overlay.showFullScreen()
        self._active_overlay.raise_()
        self._active_overlay.activateWindow()
        self._active_overlay.setFocus()
        QApplication.processEvents()
    
    def pick_move_coordinates(self):
        """Pick mouse move coordinates with fullscreen overlay."""
        def on_coordinates_selected(x, y):
            self.move_x_spin.setValue(x)
            self.move_y_spin.setValue(y)
        
        self._active_overlay = CoordinatePickerOverlay(
            callback=on_coordinates_selected,
            accent_color=self.get_theme_color('accent')
        )
        self._active_overlay.showFullScreen()
        self._active_overlay.raise_()
        self._active_overlay.activateWindow()
        self._active_overlay.setFocus()
        QApplication.processEvents()
    
    def pick_pixel_color(self):
        """Color picker for pixel check."""
        color = QColorDialog.getColor()
        if color.isValid():
            self.pixel_color_input.setText(color.name())
    
    def browse_template_image(self):
        """Browse for template image."""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Select Template Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp);;All Files (*.*)"
        )
        if filepath:
            self.image_template_input.setText(filepath)
            self._update_image_match_preview(filepath)

    def _update_image_match_preview(self, image_path: str):
        """Render thumbnail preview for Image Match template."""
        if not hasattr(self, 'image_preview'):
            return

        if not image_path or not os.path.exists(image_path):
            self.image_preview.setPixmap(QPixmap())
            self.image_preview.setText("No template selected")
            return

        pix = QPixmap(image_path)
        if pix.isNull():
            self.image_preview.setPixmap(QPixmap())
            self.image_preview.setText("Unable to preview image")
            return

        preview = pix.scaled(220, 74, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_preview.setText("")
        self.image_preview.setPixmap(preview)

    def pick_image_match_region_from_screen(self):
        """Pick search region for normal Image Match action."""
        def on_region_selected(x, y, width, height):
            self.image_region_x.setValue(x)
            self.image_region_y.setValue(y)
            self.image_region_w.setValue(width)
            self.image_region_h.setValue(height)

        self._active_overlay = RegionPickerOverlay(
            callback=on_region_selected,
            accent_color=self.get_theme_color('accent')
        )
        self._active_overlay.showFullScreen()
        self._active_overlay.raise_()
        self._active_overlay.activateWindow()
        self._active_overlay.setFocus()
        QApplication.processEvents()

    def browse_conditional_template_image(self):
        """Browse for conditional image match template and update preview."""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Select Conditional Template Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp);;All Files (*.*)"
        )
        if filepath:
            self.cond_image_template_input.setText(filepath)
            self._update_conditional_image_preview(filepath)

    def _update_conditional_image_preview(self, image_path: str):
        """Render thumbnail preview for conditional image template."""
        if not image_path or not os.path.exists(image_path):
            self.cond_image_preview.setPixmap(QPixmap())
            self.cond_image_preview.setText("No template selected")
            return

        pix = QPixmap(image_path)
        if pix.isNull():
            self.cond_image_preview.setPixmap(QPixmap())
            self.cond_image_preview.setText("Unable to preview image")
            return

        preview = pix.scaled(220, 74, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.cond_image_preview.setText("")
        self.cond_image_preview.setPixmap(preview)

    def pick_conditional_pixel_coordinates(self):
        """Pick pixel coordinates for conditional pixel match."""
        def on_coordinates_selected(x, y):
            self.cond_x_spin.setValue(x)
            self.cond_y_spin.setValue(y)

        self._active_overlay = CoordinatePickerOverlay(
            callback=on_coordinates_selected,
            accent_color=self.get_theme_color('accent')
        )
        self._active_overlay.showFullScreen()
        self._active_overlay.raise_()
        self._active_overlay.activateWindow()
        self._active_overlay.setFocus()
        QApplication.processEvents()

    def pick_conditional_region_from_screen(self):
        """Pick region for conditional image/region-watch conditions."""
        def on_region_selected(x, y, width, height):
            cond_type_text = self.cond_type_combo.currentText()
            cond_type = cond_type_text.split(":")[0] if ":" in cond_type_text else cond_type_text
            if cond_type == "image_match":
                self.cond_image_region_x.setValue(x)
                self.cond_image_region_y.setValue(y)
                self.cond_image_region_w.setValue(width)
                self.cond_image_region_h.setValue(height)
            else:
                self.cond_region_x.setValue(x)
                self.cond_region_y.setValue(y)
                self.cond_region_w.setValue(width)
                self.cond_region_h.setValue(height)

        self._active_overlay = RegionPickerOverlay(
            callback=on_region_selected,
            accent_color=self.get_theme_color('accent')
        )
        self._active_overlay.showFullScreen()
        self._active_overlay.raise_()
        self._active_overlay.activateWindow()
        self._active_overlay.setFocus()
        QApplication.processEvents()

    def pick_conditional_color(self):
        """Color picker for conditional color-based modes."""
        color = QColorDialog.getColor()
        if not color.isValid():
            return

        cond_type_text = self.cond_type_combo.currentText()
        cond_type = cond_type_text.split(":")[0] if ":" in cond_type_text else cond_type_text
        if cond_type == "region_watch":
            self.cond_region_color_input.setText(color.name())
        else:
            self.cond_color_input.setText(color.name())

    def _update_conditional_condition_ui(self, cond_type_text: str):
        """Show relevant controls based on selected condition type."""
        cond_type = cond_type_text.split(":")[0] if ":" in cond_type_text else cond_type_text
        self.cond_pixel_group.setVisible(cond_type == "pixel_match")
        self.cond_image_group.setVisible(cond_type == "image_match")
        self.cond_region_group.setVisible(cond_type == "region_watch")

    def _connect_preview_signals(self, root_widget: QWidget):
        """Connect standard input signals to action preview updater."""
        for widget in root_widget.findChildren(QLineEdit):
            widget.textChanged.connect(self.update_action_preview)
        for widget in root_widget.findChildren(QComboBox):
            widget.currentTextChanged.connect(self.update_action_preview)
        for widget in root_widget.findChildren(QSpinBox):
            widget.valueChanged.connect(self.update_action_preview)
        for widget in root_widget.findChildren(QDoubleSpinBox):
            widget.valueChanged.connect(self.update_action_preview)
        for widget in root_widget.findChildren(QCheckBox):
            widget.toggled.connect(self.update_action_preview)

    def _set_invalid(self, widget: QWidget, invalid: bool):
        """Mark/unmark field as invalid with visual feedback."""
        widget.setProperty("invalid", invalid)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def _clear_validation_marks(self):
        """Clear invalid state from all add-action controls."""
        roots = [self.action_form_stack.currentWidget(), self.action_type_combo]
        for root in roots:
            if not root:
                continue
            if isinstance(root, QWidget):
                for w in root.findChildren(QWidget):
                    if hasattr(w, 'property') and w.property('invalid'):
                        self._set_invalid(w, False)

    def _validate_current_action_form(self) -> bool:
        """Validate required fields for current action type with visual feedback."""
        self._clear_validation_marks()
        action_type = self._normalize_action_type_label(self.action_type_combo.currentText())
        valid = True
        message = ""

        if action_type == "Keyboard Key":
            if not self.key_input.text().strip():
                self._set_invalid(self.key_input, True)
                valid = False
                message = "Key is required"
        elif action_type == "Image Match":
            if not self.image_template_input.text().strip():
                self._set_invalid(self.image_template_input, True)
                valid = False
                message = "Template image path is required"
        elif action_type == "Conditional Branch":
            cond_type_text = self.cond_type_combo.currentText()
            cond_type = cond_type_text.split(":")[0] if ":" in cond_type_text else cond_type_text
            if cond_type == "image_match" and not self.cond_image_template_input.text().strip():
                self._set_invalid(self.cond_image_template_input, True)
                valid = False
                message = "Conditional image template is required"
            elif cond_type in ("pixel_match", "region_watch"):
                color_input = self.cond_color_input if cond_type == "pixel_match" else self.cond_region_color_input
                if not color_input.text().strip().startswith("#"):
                    self._set_invalid(color_input, True)
                    valid = False
                    message = "Color must be in hex format (e.g. #FF0000)"

        if not valid:
            self.exec_status.setText(f"Validation: {message}")
        return valid

    def update_action_preview(self, *_args):
        """Show human-readable preview of current action settings."""
        action_type = self._normalize_action_type_label(self.action_type_combo.currentText())
        preview = "Preview: Ready"
        try:
            if action_type == "Keyboard Key":
                preview = f"Preview: Press key '{self.key_input.text() or '(no key)'}' ({self.key_type_combo.currentText()}) for {self.key_duration_spin.value()}ms"
            elif action_type == "Mouse Click":
                preview = f"Preview: {self.click_button_combo.currentText()} click x{self.clicks_spin.value()} at ({self.click_x_spin.value()}, {self.click_y_spin.value()})"
            elif action_type in ("Mouse Move", "Mouse Position"):
                mode = "relative" if self.move_relative.isChecked() else "absolute"
                preview = f"Preview: Move mouse to ({self.move_x_spin.value()}, {self.move_y_spin.value()}) [{mode}] over {self.move_duration_spin.value()}ms"
            elif action_type == "Delay":
                if self.delay_randomize.isChecked():
                    preview = f"Preview: Wait random {self.delay_min_spin.value()}-{self.delay_max_spin.value()}ms"
                else:
                    preview = f"Preview: Wait {self.delay_duration_spin.value()}ms"
            elif action_type == "Pixel Check":
                preview = f"Preview: Check pixel ({self.pixel_x_spin.value()}, {self.pixel_y_spin.value()}) equals {self.pixel_color_input.text()} ±{self.pixel_tolerance_spin.value()}"
            elif action_type == "Image Match":
                image_name = os.path.basename(self.image_template_input.text()) or "(no image selected)"
                preview = f"Preview: Find image '{image_name}' with confidence {self.image_confidence_spin.value():.2f}"
            elif action_type == "Region Watcher":
                preview = f"Preview: Watch region ({self.region_x_spin.value()}, {self.region_y_spin.value()}, {self.region_w_spin.value()}x{self.region_h_spin.value()}) for {self.region_color_input.text()}"
            elif action_type == "Window Focus Check":
                preview = f"Preview: Wait until active window contains '{self.window_title_input.text() or '(empty)'}'"
            elif action_type == "Skill Check Digits":
                preview = f"Preview: OCR digits in ({self.skill_region_x.value()}, {self.skill_region_y.value()}, {self.skill_region_w.value()}x{self.skill_region_h.value()})"
            elif action_type == "Conditional Branch":
                cond_type_text = self.cond_type_combo.currentText()
                cond_type = cond_type_text.split(":")[0] if ":" in cond_type_text else cond_type_text
                if cond_type == "image_match":
                    preview = f"Preview: IF image '{os.path.basename(self.cond_image_template_input.text()) or '(none)'}' THEN run THEN-list ELSE run ELSE-list"
                elif cond_type == "region_watch":
                    preview = f"Preview: IF region ({self.cond_region_x.value()}, {self.cond_region_y.value()}, {self.cond_region_w.value()}x{self.cond_region_h.value()}) has {self.cond_region_color_input.text()} THEN/ELSE"
                else:
                    preview = f"Preview: IF pixel ({self.cond_x_spin.value()}, {self.cond_y_spin.value()}) is {self.cond_color_input.text()} ±{self.cond_tolerance_spin.value()} THEN/ELSE"
        except Exception:
            preview = "Preview: Ready"

        if hasattr(self, 'action_preview_label'):
            self.action_preview_label.setText(preview)

    def _save_last_used_defaults(self, action: MacroAction):
        """Store last used values per action type for smart defaults."""
        if not action:
            return
        self._last_action_defaults[action.action_type] = action.to_dict()

    def _apply_last_used_defaults(self, action_type: str):
        """Apply last used values when switching action type."""
        map_ui_to_type = {
            "Keyboard Key": "key",
            "Mouse Click": "mouse_click",
            "Mouse Move": "mouse_move",
            "Mouse Position": "mouse_move",
            "Delay": "delay",
            "Loop Start": "loop_start",
            "Loop End": "loop_end",
            "Pixel Check": "pixel_check",
            "Image Match": "image_match",
            "Region Watcher": "region_watcher",
            "Skill Check Digits": "skill_check_digits",
            "Window Focus Check": "window_focus_check",
            "Conditional Branch": "conditional_branch"
        }
        action_key = map_ui_to_type.get(action_type)
        defaults = self._last_action_defaults.get(action_key)
        if not defaults:
            return

        try:
            if action_key == "key":
                self.key_input.setText(defaults.get('key', self.key_input.text()))
                self.key_duration_spin.setValue(int(defaults.get('hold_duration', self.key_duration_spin.value())))
                self.key_type_combo.setCurrentText(defaults.get('press_type', self.key_type_combo.currentText()))
            elif action_key == "mouse_click":
                self.click_button_combo.setCurrentText(defaults.get('button', self.click_button_combo.currentText()))
                self.click_x_spin.setValue(int(defaults.get('x', self.click_x_spin.value())))
                self.click_y_spin.setValue(int(defaults.get('y', self.click_y_spin.value())))
                self.clicks_spin.setValue(int(defaults.get('clicks', self.clicks_spin.value())))
            elif action_key == "delay":
                self.delay_duration_spin.setValue(int(defaults.get('duration', self.delay_duration_spin.value())))
                self.delay_randomize.setChecked(bool(defaults.get('randomize', self.delay_randomize.isChecked())))
                self.delay_min_spin.setValue(int(defaults.get('random_min', self.delay_min_spin.value())))
                self.delay_max_spin.setValue(int(defaults.get('random_max', self.delay_max_spin.value())))
            elif action_key == "image_match":
                self.image_template_input.setText(defaults.get('template_path', self.image_template_input.text()))
                self.image_confidence_spin.setValue(float(defaults.get('confidence', self.image_confidence_spin.value())))
                self._update_image_match_preview(self.image_template_input.text())
            elif action_key == "pixel_check":
                self.pixel_x_spin.setValue(int(defaults.get('x', self.pixel_x_spin.value())))
                self.pixel_y_spin.setValue(int(defaults.get('y', self.pixel_y_spin.value())))
                self.pixel_color_input.setText(defaults.get('color', self.pixel_color_input.text()))
                self.pixel_tolerance_spin.setValue(int(defaults.get('tolerance', self.pixel_tolerance_spin.value())))
        except Exception:
            pass

    def _snapshot_actions(self) -> List[Dict[str, Any]]:
        """Snapshot current action list for undo/redo history."""
        if not self.current_profile:
            return []
        return [action.to_dict() for action in self.current_profile.actions]

    def _restore_actions_snapshot(self, snapshot: List[Dict[str, Any]]):
        """Restore action list from serialized snapshot."""
        if not self.current_profile:
            return
        self._suspend_history = True
        try:
            self.current_profile.actions = [MacroAction.from_dict(dict(data)) for data in snapshot]
            self.refresh_action_table()
            self.save_current_profile()
        finally:
            self._suspend_history = False

    def _push_undo_state(self):
        """Push current state to undo stack and clear redo stack."""
        if self._suspend_history or not self.current_profile:
            return
        self._undo_stack.append(self._snapshot_actions())
        if len(self._undo_stack) > self._history_limit:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo_last_change(self):
        """Undo the most recent action sequence mutation."""
        if not self.current_profile or not self._undo_stack:
            self.exec_status.setText("Undo: nothing to undo")
            return
        self._redo_stack.append(self._snapshot_actions())
        snapshot = self._undo_stack.pop()
        self._restore_actions_snapshot(snapshot)
        self.exec_status.setText("Undo applied")

    def redo_last_change(self):
        """Redo a previously undone action sequence mutation."""
        if not self.current_profile or not self._redo_stack:
            self.exec_status.setText("Redo: nothing to redo")
            return
        self._undo_stack.append(self._snapshot_actions())
        snapshot = self._redo_stack.pop()
        self._restore_actions_snapshot(snapshot)
        self.exec_status.setText("Redo applied")

    def eventFilter(self, obj, event):
        """Handle template drag start and sequence table drop target events."""
        if isinstance(obj, QPushButton) and obj.property("template_name"):
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_start_pos = event.pos()
            elif event.type() == QEvent.MouseMove and (event.buttons() & Qt.LeftButton):
                if (event.pos() - self._drag_start_pos).manhattanLength() >= 8:
                    drag = QDrag(obj)
                    mime = QMimeData()
                    mime.setData("application/x-sloth-template", obj.property("template_name").encode("utf-8"))
                    drag.setMimeData(mime)
                    drag.exec(Qt.CopyAction)
                    return True

        if obj is self.action_table.viewport():
            if event.type() == QEvent.DragEnter:
                if event.mimeData().hasFormat("application/x-sloth-template"):
                    event.acceptProposedAction()
                    return True
            elif event.type() == QEvent.DragMove:
                if event.mimeData().hasFormat("application/x-sloth-template"):
                    event.acceptProposedAction()
                    return True
            elif event.type() == QEvent.Drop:
                if event.mimeData().hasFormat("application/x-sloth-template"):
                    data = bytes(event.mimeData().data("application/x-sloth-template")).decode("utf-8")
                    drop_row = self.action_table.rowAt(int(event.position().y()))
                    insert_at = len(self.current_profile.actions) if drop_row < 0 else drop_row
                    self.insert_template(data, insert_at=insert_at)
                    event.acceptProposedAction()
                    return True
            elif event.type() == QEvent.MouseMove:
                row = self.action_table.rowAt(int(event.position().y()))
                if row != self._hovered_action_row:
                    old, self._hovered_action_row = self._hovered_action_row, row
                    self._update_row_brush(old)
                    self._update_row_brush(row)
            elif event.type() == QEvent.Leave:
                old, self._hovered_action_row = self._hovered_action_row, -1
                self._update_row_brush(old)

        return super().eventFilter(obj, event)

    def copy_selected_actions(self):
        """Copy selected sequence actions to internal clipboard."""
        if not self.current_profile:
            return
        selected_rows = sorted({idx.row() for idx in self.action_table.selectionModel().selectedRows()}) if self.action_table.selectionModel() else []
        if not selected_rows and self.action_table.currentRow() >= 0:
            selected_rows = [self.action_table.currentRow()]
        if not selected_rows:
            self.exec_status.setText("Copy: no action selected")
            return

        self._copied_actions_buffer = [self.current_profile.actions[row].to_dict() for row in selected_rows]
        self.exec_status.setText(f"Copied {len(self._copied_actions_buffer)} action(s)")

    def paste_actions(self):
        """Paste copied actions after current selection."""
        if not self.current_profile:
            return
        if not self._copied_actions_buffer:
            self.exec_status.setText("Paste: clipboard is empty")
            return

        self._push_undo_state()
        insert_at = self.action_table.currentRow() + 1 if self.action_table.currentRow() >= 0 else len(self.current_profile.actions)
        new_actions = [MacroAction.from_dict(dict(data)) for data in self._copied_actions_buffer]
        for offset, action in enumerate(new_actions):
            self.current_profile.actions.insert(insert_at + offset, action)

        self.refresh_action_table()
        self.save_current_profile()
        self.exec_status.setText(f"Pasted {len(new_actions)} action(s)")

    def duplicate_selected_action(self):
        """Duplicate current selected action."""
        if not self.current_profile:
            return
        row = self.action_table.currentRow()
        if row < 0 or row >= len(self.current_profile.actions):
            self.exec_status.setText("Duplicate: no action selected")
            return

        self._push_undo_state()
        action_copy = MacroAction.from_dict(self.current_profile.actions[row].to_dict())
        self.current_profile.actions.insert(row + 1, action_copy)
        self.refresh_action_table()
        self.action_table.setCurrentCell(row + 1, 0)
        self.save_current_profile()
        self.exec_status.setText("Duplicated selected action")
    
    def add_current_action(self):
        """Add action from form to sequence."""
        if not self.current_profile:
            QMessageBox.warning(self, "Warning", "No profile loaded. Go to Profile Manager first.")
            return

        if not self._validate_current_action_form():
            return
        
        action_type = self._normalize_action_type_label(self.action_type_combo.currentText())
        
        action = None
        
        if action_type == "Keyboard Key":
            action = KeyAction(
                key=self.key_input.text() or "a",
                hold_duration=self.key_duration_spin.value(),
                press_type=self.key_type_combo.currentText()
            )
        
        elif action_type == "Mouse Click":
            action = MouseClickAction(
                button=self.click_button_combo.currentText(),
                x=self.click_x_spin.value(),
                y=self.click_y_spin.value(),
                relative=self.click_relative.isChecked(),
                clicks=self.clicks_spin.value()
            )
        
        elif action_type in ("Mouse Move", "Mouse Position"):
            action = MouseMoveAction(
                x=self.move_x_spin.value(),
                y=self.move_y_spin.value(),
                relative=self.move_relative.isChecked(),
                duration=self.move_duration_spin.value()
            )
        
        elif action_type == "Delay":
            action = DelayAction(
                duration=self.delay_duration_spin.value(),
                randomize=self.delay_randomize.isChecked(),
                random_min=self.delay_min_spin.value() if self.delay_randomize.isChecked() else 0,
                random_max=self.delay_max_spin.value() if self.delay_randomize.isChecked() else 0
            )
        
        elif action_type == "Loop Start":
            action = LoopStartAction(
                loop_type=self.loop_type_combo.currentText(),
                count=self.loop_count_spin_edit.value(),
                duration_seconds=self.loop_duration_spin.value()
            )
        
        elif action_type == "Loop End":
            action = LoopEndAction()
        
        elif action_type == "Pixel Check":
            trigger_macro = self.pixel_trigger_macro_combo.currentText()
            if trigger_macro == "(None)":
                trigger_macro = ""
            action = PixelCheckAction(
                x=self.pixel_x_spin.value(),
                y=self.pixel_y_spin.value(),
                color=self.pixel_color_input.text(),
                tolerance=self.pixel_tolerance_spin.value(),
                wait_for_match=self.pixel_wait_check.isChecked(),
                timeout_ms=self.pixel_timeout_spin.value(),
                poll_interval_ms=self.pixel_poll_spin.value(),
                trigger_macro_name=trigger_macro
            )
        
        elif action_type == "Image Match":
            action = ImageMatchAction(
                template_path=self.image_template_input.text(),
                confidence=self.image_confidence_spin.value(),
                region_x=self.image_region_x.value(),
                region_y=self.image_region_y.value(),
                region_w=self.image_region_w.value(),
                region_h=self.image_region_h.value()
            )
        
        elif action_type == "Region Watcher":
            trigger_macro = self.region_trigger_macro_combo.currentText()
            if trigger_macro == "(None)":
                trigger_macro = ""
            action = RegionColorWatcherAction(
                x=self.region_x_spin.value(),
                y=self.region_y_spin.value(),
                width=self.region_w_spin.value(),
                height=self.region_h_spin.value(),
                target_color=self.region_color_input.text(),
                tolerance=self.region_tolerance_spin.value(),
                check_type=self.region_watch_type_combo.currentText(),
                wait_timeout_ms=self.region_timeout_spin.value(),
                description=self.region_desc_input.text(),
                trigger_macro_name=trigger_macro
            )

        elif action_type == "Skill Check Digits":
            action = SkillCheckDigitsAction(
                region_x=self.skill_region_x.value(),
                region_y=self.skill_region_y.value(),
                region_w=self.skill_region_w.value(),
                region_h=self.skill_region_h.value(),
                max_digits=self.skill_max_digits.value(),
                key_delay_ms=self.skill_key_delay.value()
            )

        elif action_type == "Window Focus Check":
            action = WindowFocusCheckAction(
                window_title_contains=self.window_title_input.text(),
                timeout_ms=self.window_timeout_spin.value(),
                description=self.window_desc_input.text()
            )
        
        elif action_type == "Conditional Branch":
            cond_type_text = self.cond_type_combo.currentText()
            # Extract just the condition type (before the colon)
            cond_type = cond_type_text.split(":")[0] if ":" in cond_type_text else cond_type_text

            cond_kwargs = {
                'condition_type': cond_type,
                'description': self.cond_desc_input.text()
            }

            if cond_type == "pixel_match":
                cond_kwargs.update({
                    'x': self.cond_x_spin.value(),
                    'y': self.cond_y_spin.value(),
                    'color': self.cond_color_input.text(),
                    'tolerance': self.cond_tolerance_spin.value()
                })
            elif cond_type == "image_match":
                cond_kwargs.update({
                    'template_path': self.cond_image_template_input.text(),
                    'confidence': self.cond_image_confidence_spin.value(),
                    'region_x': self.cond_image_region_x.value(),
                    'region_y': self.cond_image_region_y.value(),
                    'region_w': self.cond_image_region_w.value(),
                    'region_h': self.cond_image_region_h.value()
                })
            elif cond_type == "region_watch":
                cond_kwargs.update({
                    'x': self.cond_region_x.value(),
                    'y': self.cond_region_y.value(),
                    'color': self.cond_region_color_input.text(),
                    'tolerance': self.cond_region_tolerance_spin.value(),
                    'region_x': self.cond_region_x.value(),
                    'region_y': self.cond_region_y.value(),
                    'region_w': self.cond_region_w.value(),
                    'region_h': self.cond_region_h.value()
                })

            action = ConditionalBranchAction(
                **cond_kwargs
            )
        
        if action:
            self._push_undo_state()
            self.current_profile.actions.append(action)
            self._save_last_used_defaults(action)
            self.refresh_action_table()
            self.save_current_profile()
            self.exec_status.setText(f"Added action: {action_type}")
            self.update_action_preview()
    
    def save_current_profile(self):
        """Schedule a debounced save (fires after 350 ms of inactivity)."""
        if hasattr(self, '_save_timer'):
            self._save_timer.start()  # restart every call; fires 350ms after last call
        else:
            self._flush_save()

    def _flush_save(self):
        """Actually write the current profile to disk."""
        if self.current_profile:
            try:
                self.current_profile.save_to_file(
                    os.path.join(get_base_dir(), "profiles")
                )
                logger.info(f"Profile saved: {self.current_profile.name}")
            except Exception as e:
                logger.error(f"Error saving profile: {e}")

    def _toggle_exec_log(self, checked: bool):
        """Show/hide the execution log list."""
        self.exec_log_list.setVisible(checked)
        self._exec_log_toggle_btn.setText("👁️ Hide Log" if checked else "👁️ Show Log")

    def _toggle_run_history(self, checked: bool):
        """Show/hide the run history list."""
        self.run_history_list.setVisible(checked)
        count = len(self._run_history_entries)
        self._run_history_toggle_btn.setText(
            f"{('▼' if checked else '▶')} Run History ({count})")

    def _add_run_history_entry(self, label: str, success: bool):
        """Prepend a timestamped run outcome to the history list (max 10 entries)."""
        from datetime import datetime as _dt
        prof_name = self.current_profile.name if self.current_profile else "(no profile)"
        icon = "OK" if success else "ERR"
        entry = f"[{icon}] {_dt.now().strftime('%H:%M:%S')} | {prof_name} | {label}"
        self._run_history_entries.insert(0, entry)
        if len(self._run_history_entries) > 10:
            self._run_history_entries.pop()
        self.run_history_list.clear()
        for e in self._run_history_entries:
            self.run_history_list.addItem(e)
        checked = self._run_history_toggle_btn.isChecked()
        count = len(self._run_history_entries)
        self._run_history_toggle_btn.setText(
            f"{'▼' if checked else '▶'} Run History ({count})")

    def log_exec_event(self, text: str):
        """Append a timestamped message to the exec log panel."""
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self.exec_log_list.addItem(f"[{ts}] {text}")
        if self.exec_log_list.count() > 200:
            self.exec_log_list.takeItem(0)  # keep bounded
        self.exec_log_list.scrollToBottom()

    def _update_row_brush(self, row: int):
        """Repaint a single row's background, accounting for hover state."""
        if not self.current_profile or row < 0 or row >= len(self.current_profile.actions):
            return
        action = self.current_profile.actions[row]
        color = self._action_row_color(action)
        if row == self._hovered_action_row:
            color = color.lighter(170)
        brush = QBrush(color)
        for col in range(self.action_table.columnCount()):
            item = self.action_table.item(row, col)
            if item:
                item.setBackground(brush)

    def _on_action_double_clicked(self, row: int, _col: int):
        """Open the action editor when a row is double-clicked."""
        if not self.current_profile or row < 0 or row >= len(self.current_profile.actions):
            return
        action = self.current_profile.actions[row]
        if action.action_type in ("Conditional Branch", "conditional_branch"):
            self._open_conditional_branch_editor(row, action)
        else:
            self._edit_nested_action_dialog(action)
            self.refresh_action_table()
            self.save_current_profile()
    
    def refresh_action_table(self):
        """Refresh action table display."""
        if not self.current_profile:
            self.action_table.setRowCount(0)
            return

        self.action_table.setUpdatesEnabled(False)
        self.action_table.setRowCount(len(self.current_profile.actions))

        for i, action in enumerate(self.current_profile.actions):
            # Index
            index_item = QTableWidgetItem(str(i + 1))
            self.action_table.setItem(i, 0, index_item)

            # Type
            type_item = QTableWidgetItem(action.action_type)
            self.action_table.setItem(i, 1, type_item)

            # Details
            details = self._format_action_details(action)
            details_item = QTableWidgetItem(details)
            self.action_table.setItem(i, 2, details_item)

            hovered = getattr(self, '_hovered_action_row', -1)
            row_color = self._action_row_color(action)
            if i == hovered:
                row_color = row_color.lighter(170)
            row_brush = QBrush(row_color)
            for col_item in (index_item, type_item, details_item):
                col_item.setBackground(row_brush)

            # Enabled checkbox
            enabled_check = QCheckBox()
            enabled_check.setChecked(action.enabled)
            enabled_check.toggled.connect(lambda checked, idx=i: self._toggle_action_enabled(idx, checked))

            checkbox_widget = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox_layout.addWidget(enabled_check)
            checkbox_layout.setAlignment(Qt.AlignCenter)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)

            self.action_table.setCellWidget(i, 3, checkbox_widget)

        self.action_table.setUpdatesEnabled(True)
    
    def _format_action_details(self, action: MacroAction) -> str:
        """Format action details for display."""
        if isinstance(action, KeyAction):
            return f"Key: {action.key}, {action.press_type}, {action.hold_duration}ms"
        elif isinstance(action, MouseClickAction):
            clicks = getattr(action, 'clicks', getattr(action, 'click_count', 1))
            return f"{action.button} click at ({action.x}, {action.y}), count: {clicks}"
        elif isinstance(action, MouseMoveAction):
            return f"Move to ({action.x}, {action.y}), {action.duration}ms"
        elif isinstance(action, DelayAction):
            if action.randomize:
                return f"Wait {action.random_min}-{action.random_max}ms (random)"
            return f"Wait {action.duration}ms"
        elif isinstance(action, LoopStartAction):
            if action.loop_type == "count":
                return f"Loop {action.count} times"
            elif action.loop_type == "infinite":
                return "Loop infinitely"
            else:
                return f"Loop for {action.duration_seconds}s"
        elif isinstance(action, LoopEndAction):
            return "End loop"
        elif isinstance(action, PixelCheckAction):
            mode = "wait" if getattr(action, 'wait_for_match', True) else "check-once"
            return f"Pixel ({action.x}, {action.y})={action.color}, tol {action.tolerance}, {mode}"
        elif isinstance(action, ImageMatchAction):
            return f"Find image: {os.path.basename(action.template_path)}"
        elif isinstance(action, RegionColorWatcherAction):
            return f"Watch region ({action.x}, {action.y}, {action.width}x{action.height}) for {action.target_color}"
        elif isinstance(action, SkillCheckDigitsAction):
            return f"Skill-check digits in ({action.region_x}, {action.region_y}, {action.region_w}x{action.region_h})"
        elif isinstance(action, WindowFocusCheckAction):
            return f"Verify window contains: {action.window_title_contains}"
        elif isinstance(action, RunProfileAction):
            return f"Run profile: {action.profile_name or '(none)'}"
        elif isinstance(action, ConditionalBranchAction):
            true_count = len(action.if_true_actions) if action.if_true_actions else 0
            false_count = len(action.if_false_actions) if action.if_false_actions else 0
            desc = action.description or "Check condition"
            if action.condition_type == "image_match":
                target = os.path.basename(action.template_path) if action.template_path else "(no image)"
                return f"IF image '{target}' THEN {true_count} actions ELSE {false_count} actions: {desc}"
            if action.condition_type == "region_watch":
                return f"IF region ({action.region_x},{action.region_y},{action.region_w}x{action.region_h}) has {action.color} THEN {true_count} ELSE {false_count}: {desc}"
            return f"IF pixel ({action.x},{action.y})={action.color} THEN {true_count} actions ELSE {false_count} actions: {desc}"
        return str(action)
    
    def _toggle_action_enabled(self, index: int, enabled: bool):
        """Toggle action enabled state."""
        if self.current_profile and 0 <= index < len(self.current_profile.actions):
            self.current_profile.actions[index].enabled = enabled
            self.save_current_profile()

    def _show_action_context_menu(self, pos):
        """Show context menu for action table rows."""
        row = self.action_table.rowAt(pos.y())
        if row < 0 or not self.current_profile or row >= len(self.current_profile.actions):
            return

        self.action_table.selectRow(row)
        action_obj = self.current_profile.actions[row]
        n = len(self.current_profile.actions)

        menu = QMenu(self)
        edit_branch_action = None
        if isinstance(action_obj, ConditionalBranchAction):
            edit_branch_action = menu.addAction("⚙️ Configure IF / THEN / ELSE")
            menu.addSeparator()

        dup_action = menu.addAction("📋 Duplicate")
        move_up_action = menu.addAction("↑ Move Up")
        move_down_action = menu.addAction("↓ Move Down")
        menu.addSeparator()
        del_action = menu.addAction("🗑️ Delete")

        move_up_action.setEnabled(row > 0)
        move_down_action.setEnabled(row < n - 1)

        selected = menu.exec(self.action_table.viewport().mapToGlobal(pos))
        if not selected:
            return

        if selected == edit_branch_action:
            self._open_conditional_branch_editor(row)
        elif selected == dup_action:
            import copy
            cloned = copy.deepcopy(action_obj)
            self.current_profile.actions.insert(row + 1, cloned)
            self.refresh_action_table()
            self.save_current_profile()
        elif selected == move_up_action and row > 0:
            actions = self.current_profile.actions
            actions[row], actions[row - 1] = actions[row - 1], actions[row]
            self.refresh_action_table()
            self.save_current_profile()
            self.action_table.selectRow(row - 1)
        elif selected == move_down_action and row < n - 1:
            actions = self.current_profile.actions
            actions[row], actions[row + 1] = actions[row + 1], actions[row]
            self.refresh_action_table()
            self.save_current_profile()
            self.action_table.selectRow(row + 1)
        elif selected == del_action:
            reply = QMessageBox.question(
                self, "Delete Action",
                f"Delete action '{action_obj.action_type}'?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.current_profile.actions.pop(row)
                self.refresh_action_table()
                self.save_current_profile()

    def _create_default_action_for_type(self, action_type_label: str) -> MacroAction:
        """Create a default action object for branch editors."""
        if action_type_label == "Keyboard Key":
            return KeyAction(key="space", hold_duration=50, press_type="press")
        if action_type_label == "Mouse Click":
            return MouseClickAction(button="left", x=960, y=540, relative=False, clicks=1)
        if action_type_label in ("Mouse Move", "Mouse Position"):
            return MouseMoveAction(x=960, y=540, relative=False, duration=200)
        if action_type_label == "Delay":
            return DelayAction(duration=500, randomize=False)
        if action_type_label == "Pixel Check":
            return PixelCheckAction(x=0, y=0, color="#FFFFFF", tolerance=10)
        if action_type_label == "Image Match":
            return ImageMatchAction(template_path="", confidence=0.8)
        if action_type_label == "Region Watcher":
            return RegionColorWatcherAction(x=0, y=0, width=200, height=100, target_color="#FF0000", tolerance=15)
        if action_type_label == "Window Focus Check":
            return WindowFocusCheckAction(window_title_contains="", timeout_ms=1000)
        if action_type_label == "Skill Check Digits":
            return SkillCheckDigitsAction(region_x=0, region_y=0, region_w=260, region_h=120, max_digits=6, key_delay_ms=60)
        if action_type_label == "Run Profile":
            return RunProfileAction(profile_name="")
        if action_type_label == "Conditional Branch":
            return ConditionalBranchAction(condition_type="pixel_match", x=0, y=0, color="#FFFFFF", tolerance=15, description="Nested condition")
        return DelayAction(duration=500, randomize=False)

    def _edit_nested_action_dialog(self, nested_action: MacroAction) -> bool:
        """Edit a nested branch action with type-specific controls."""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Edit Nested Action: {nested_action.action_type}")
        dialog.setMinimumSize(620, 420)
        QTimer.singleShot(0, lambda: apply_dark_title_bar(dialog))

        root = QVBoxLayout(dialog)
        grid = QGridLayout()
        grid.setSpacing(8)

        row = 0

        def _restore_nested_editor_dialog():
            dialog.setWindowOpacity(1.0)
            dialog.setEnabled(True)
            if not dialog.isVisible():
                dialog.showNormal()
            dialog.raise_()
            dialog.activateWindow()
            dialog.setFocus()
            QApplication.processEvents()

        def _start_coord_picker(on_selected):
            restored = {'done': False}
            # Collect sibling QDialogs (e.g. the branch editor) so they get
            # hidden too - otherwise the overlay ends up behind them.
            _siblings = [
                w for w in QApplication.topLevelWidgets()
                if isinstance(w, QDialog) and w is not dialog and w.isVisible()
            ]
            for _w in _siblings:
                _w.hide()

            def restore_once():
                if restored['done']:
                    return
                restored['done'] = True
                for _w in _siblings:
                    _w.show()
                    _w.raise_()
                _restore_nested_editor_dialog()

            def wrapped(x, y):
                on_selected(x, y)
                restore_once()

            dialog.setEnabled(False)
            dialog.setWindowOpacity(0.12)
            dialog.lower()
            dialog.hide()
            QApplication.processEvents()
            self._active_overlay = CoordinatePickerOverlay(
                callback=wrapped,
                accent_color=self.get_theme_color('accent'),
                parent=None
            )
            self._active_overlay.destroyed.connect(lambda *_: restore_once())
            self._active_overlay.showFullScreen()
            self._active_overlay.raise_()
            self._active_overlay.activateWindow()
            self._active_overlay.setFocus()
            QApplication.processEvents()

        def _start_region_picker(on_selected):
            restored = {'done': False}
            # Collect sibling QDialogs (e.g. the branch editor) so they get
            # hidden too - otherwise the overlay ends up behind them.
            _siblings = [
                w for w in QApplication.topLevelWidgets()
                if isinstance(w, QDialog) and w is not dialog and w.isVisible()
            ]
            for _w in _siblings:
                _w.hide()

            def restore_once():
                if restored['done']:
                    return
                restored['done'] = True
                for _w in _siblings:
                    _w.show()
                    _w.raise_()
                _restore_nested_editor_dialog()

            def wrapped(x, y, width, height):
                on_selected(x, y, width, height)
                restore_once()

            dialog.setEnabled(False)
            dialog.setWindowOpacity(0.12)
            dialog.lower()
            dialog.hide()
            QApplication.processEvents()
            self._active_overlay = RegionPickerOverlay(
                callback=wrapped,
                accent_color=self.get_theme_color('accent'),
                parent=None
            )
            self._active_overlay.destroyed.connect(lambda *_: restore_once())
            self._active_overlay.showFullScreen()
            self._active_overlay.raise_()
            self._active_overlay.activateWindow()
            self._active_overlay.setFocus()
            QApplication.processEvents()

        if isinstance(nested_action, KeyAction):
            key_input = QLineEdit(nested_action.key)
            hold_spin = NoWheelSpinBox()
            hold_spin.setRange(1, 10000)
            hold_spin.setValue(int(nested_action.hold_duration))
            press_combo = QComboBox()
            press_combo.addItems(["press", "hold", "release"])
            press_combo.setCurrentText(nested_action.press_type)

            grid.addWidget(QLabel("Key:"), row, 0); grid.addWidget(key_input, row, 1); row += 1
            grid.addWidget(QLabel("Hold Duration (ms):"), row, 0); grid.addWidget(hold_spin, row, 1); row += 1
            grid.addWidget(QLabel("Press Type:"), row, 0); grid.addWidget(press_combo, row, 1); row += 1

            def apply_changes():
                nested_action.key = key_input.text().strip() or "space"
                nested_action.hold_duration = hold_spin.value()
                nested_action.press_type = press_combo.currentText()

        elif isinstance(nested_action, DelayAction):
            dur_spin = NoWheelSpinBox()
            dur_spin.setRange(1, 600000)
            dur_spin.setValue(int(nested_action.duration))
            random_check = QCheckBox("Randomize")
            random_check.setChecked(bool(getattr(nested_action, 'randomize', False)))
            min_spin = NoWheelSpinBox(); min_spin.setRange(1, 600000); min_spin.setValue(int(getattr(nested_action, 'random_min', 100)))
            max_spin = NoWheelSpinBox(); max_spin.setRange(1, 600000); max_spin.setValue(int(getattr(nested_action, 'random_max', 300)))

            grid.addWidget(QLabel("Duration (ms):"), row, 0); grid.addWidget(dur_spin, row, 1); row += 1
            grid.addWidget(random_check, row, 1); row += 1
            grid.addWidget(QLabel("Random Min (ms):"), row, 0); grid.addWidget(min_spin, row, 1); row += 1
            grid.addWidget(QLabel("Random Max (ms):"), row, 0); grid.addWidget(max_spin, row, 1); row += 1

            def apply_changes():
                nested_action.duration = dur_spin.value()
                nested_action.randomize = random_check.isChecked()
                nested_action.random_min = min_spin.value()
                nested_action.random_max = max(max_spin.value(), nested_action.random_min)

        elif isinstance(nested_action, MouseClickAction):
            btn_combo = QComboBox(); btn_combo.addItems(["left", "right", "middle"]); btn_combo.setCurrentText(nested_action.button)
            x_spin = NoWheelSpinBox(); x_spin.setRange(-9999, 9999); x_spin.setValue(int(nested_action.x))
            y_spin = NoWheelSpinBox(); y_spin.setRange(-9999, 9999); y_spin.setValue(int(nested_action.y))
            c_spin = NoWheelSpinBox(); c_spin.setRange(1, 100); c_spin.setValue(int(getattr(nested_action, 'clicks', 1)))
            rel_check = QCheckBox("Relative")
            rel_check.setChecked(bool(nested_action.relative))

            pick_btn = QPushButton("🎯 Pick Position")
            pick_btn.setMinimumHeight(32)

            def on_pick_click_coords(x, y):
                x_spin.setValue(x)
                y_spin.setValue(y)

            def pick_click_coords():
                _start_coord_picker(on_pick_click_coords)

            grid.addWidget(QLabel("Button:"), row, 0); grid.addWidget(btn_combo, row, 1); row += 1
            grid.addWidget(QLabel("X:"), row, 0); grid.addWidget(x_spin, row, 1); row += 1
            grid.addWidget(QLabel("Y:"), row, 0); grid.addWidget(y_spin, row, 1); row += 1
            grid.addWidget(pick_btn, row, 1); row += 1
            grid.addWidget(QLabel("Clicks:"), row, 0); grid.addWidget(c_spin, row, 1); row += 1
            grid.addWidget(rel_check, row, 1); row += 1
            pick_btn.clicked.connect(pick_click_coords)

            def apply_changes():
                nested_action.button = btn_combo.currentText()
                nested_action.x = x_spin.value()
                nested_action.y = y_spin.value()
                nested_action.clicks = c_spin.value()
                nested_action.relative = rel_check.isChecked()

        elif isinstance(nested_action, MouseMoveAction):
            x_spin = NoWheelSpinBox(); x_spin.setRange(-9999, 9999); x_spin.setValue(int(nested_action.x))
            y_spin = NoWheelSpinBox(); y_spin.setRange(-9999, 9999); y_spin.setValue(int(nested_action.y))
            d_spin = NoWheelSpinBox(); d_spin.setRange(1, 60000); d_spin.setValue(int(nested_action.duration))
            rel_check = QCheckBox("Relative")
            rel_check.setChecked(bool(nested_action.relative))

            pick_btn = QPushButton("🎯 Pick Move Target")
            pick_btn.setMinimumHeight(32)

            def on_pick_move_coords(x, y):
                x_spin.setValue(x)
                y_spin.setValue(y)

            def pick_move_coords():
                _start_coord_picker(on_pick_move_coords)

            grid.addWidget(QLabel("X:"), row, 0); grid.addWidget(x_spin, row, 1); row += 1
            grid.addWidget(QLabel("Y:"), row, 0); grid.addWidget(y_spin, row, 1); row += 1
            grid.addWidget(pick_btn, row, 1); row += 1
            grid.addWidget(QLabel("Duration (ms):"), row, 0); grid.addWidget(d_spin, row, 1); row += 1
            grid.addWidget(rel_check, row, 1); row += 1
            pick_btn.clicked.connect(pick_move_coords)

            def apply_changes():
                nested_action.x = x_spin.value()
                nested_action.y = y_spin.value()
                nested_action.duration = d_spin.value()
                nested_action.relative = rel_check.isChecked()

        elif isinstance(nested_action, RunProfileAction):
            profile_combo = QComboBox()
            profile_combo.addItem("(Select profile)")
            self._load_macro_names_to_combo(profile_combo)
            profile_combo.setMaxVisibleItems(14)
            profile_combo.setInsertPolicy(QComboBox.NoInsert)
            refresh_btn = QPushButton("Refresh")
            refresh_btn.setMinimumHeight(30)
            refresh_btn.setMaximumWidth(100)

            missing_label = QLabel("")
            missing_label.setWordWrap(True)
            missing_label.setStyleSheet("font-size: 11px; color: #A0A0A0;")

            def refresh_profiles():
                current = profile_combo.currentText()
                profile_combo.clear()
                profile_combo.addItem("(Select profile)")
                self._load_macro_names_to_combo(profile_combo)
                if current and current != "(Select profile)" and profile_combo.findText(current) == -1:
                    profile_combo.addItem(current)
                    missing_label.setText("Saved profile is not currently found on disk, but kept for editing.")
                else:
                    missing_label.setText("")
                if current:
                    profile_combo.setCurrentText(current)

            refresh_btn.clicked.connect(refresh_profiles)
            if nested_action.profile_name:
                if profile_combo.findText(nested_action.profile_name) == -1:
                    profile_combo.addItem(nested_action.profile_name)
                    missing_label.setText("Saved profile is not currently found on disk, but kept for editing.")
                profile_combo.setCurrentText(nested_action.profile_name)

            profile_row = QWidget()
            profile_row_layout = QHBoxLayout(profile_row)
            profile_row_layout.setContentsMargins(0, 0, 0, 0)
            profile_row_layout.addWidget(profile_combo, 1)
            profile_row_layout.addWidget(refresh_btn)

            grid.addWidget(QLabel("Profile to Run:"), row, 0)
            grid.addWidget(profile_row, row, 1)
            row += 1
            grid.addWidget(missing_label, row, 1)
            row += 1

            def apply_changes():
                text = profile_combo.currentText().strip()
                nested_action.profile_name = "" if text == "(Select profile)" else text

        elif isinstance(nested_action, PixelCheckAction):
            x_spin = NoWheelSpinBox(); x_spin.setRange(0, 9999); x_spin.setValue(int(nested_action.x))
            y_spin = NoWheelSpinBox(); y_spin.setRange(0, 9999); y_spin.setValue(int(nested_action.y))
            color_input = QLineEdit(nested_action.color)
            tol_spin = NoWheelSpinBox(); tol_spin.setRange(0, 255); tol_spin.setValue(int(nested_action.tolerance))

            pick_btn = QPushButton("🎯 Pick Pixel")
            color_btn = QPushButton("🎨 Pick Color")

            def on_pick_pixel(x, y):
                x_spin.setValue(x)
                y_spin.setValue(y)

            def pick_pixel():
                _start_coord_picker(on_pick_pixel)

            def pick_color():
                color = QColorDialog.getColor()
                if color.isValid():
                    color_input.setText(color.name())

            grid.addWidget(QLabel("X:"), row, 0); grid.addWidget(x_spin, row, 1); row += 1
            grid.addWidget(QLabel("Y:"), row, 0); grid.addWidget(y_spin, row, 1); row += 1
            grid.addWidget(pick_btn, row, 1); row += 1
            color_row = QWidget()
            color_row_layout = QHBoxLayout(color_row)
            color_row_layout.setContentsMargins(0, 0, 0, 0)
            color_row_layout.addWidget(color_input, 1)
            color_row_layout.addWidget(color_btn)
            grid.addWidget(QLabel("Color:"), row, 0); grid.addWidget(color_row, row, 1); row += 1
            grid.addWidget(QLabel("Tolerance:"), row, 0); grid.addWidget(tol_spin, row, 1); row += 1
            pick_btn.clicked.connect(pick_pixel)
            color_btn.clicked.connect(pick_color)

            def apply_changes():
                nested_action.x = x_spin.value()
                nested_action.y = y_spin.value()
                nested_action.color = color_input.text().strip() or "#FFFFFF"
                nested_action.tolerance = tol_spin.value()

        elif isinstance(nested_action, ImageMatchAction):
            path_input = QLineEdit(nested_action.template_path)
            browse_btn = QPushButton("Browse")
            conf_spin = QDoubleSpinBox(); conf_spin.setRange(0.1, 1.0); conf_spin.setSingleStep(0.05); conf_spin.setValue(float(nested_action.confidence))
            region_x = NoWheelSpinBox(); region_x.setRange(0, 9999); region_x.setValue(int(getattr(nested_action, 'region_x', 0)))
            region_y = NoWheelSpinBox(); region_y.setRange(0, 9999); region_y.setValue(int(getattr(nested_action, 'region_y', 0)))
            region_w = NoWheelSpinBox(); region_w.setRange(1, 9999); region_w.setValue(int(getattr(nested_action, 'region_w', 1920)))
            region_h = NoWheelSpinBox(); region_h.setRange(1, 9999); region_h.setValue(int(getattr(nested_action, 'region_h', 1080)))
            preview_label = QLabel("No template selected")
            preview_label.setAlignment(Qt.AlignCenter)
            preview_label.setMinimumHeight(80)
            preview_label.setStyleSheet("border: 1px solid #444; border-radius: 4px; padding: 4px;")
            pick_region_btn = QPushButton("🔲 Pick Region")

            def update_preview(path: str):
                if not path or not os.path.exists(path):
                    preview_label.setPixmap(QPixmap())
                    preview_label.setText("No template selected")
                    return
                pix = QPixmap(path)
                if pix.isNull():
                    preview_label.setPixmap(QPixmap())
                    preview_label.setText("Unable to preview image")
                    return
                preview_label.setText("")
                preview_label.setPixmap(pix.scaled(220, 74, Qt.KeepAspectRatio, Qt.SmoothTransformation))

            path_input.textChanged.connect(update_preview)

            def browse_image():
                path, _ = QFileDialog.getOpenFileName(self, "Select Template Image", "", "Images (*.png *.jpg *.jpeg *.bmp);;All Files (*.*)")
                if path:
                    path_input.setText(path)

            def on_region_pick(x, y, width, height):
                region_x.setValue(x)
                region_y.setValue(y)
                region_w.setValue(width)
                region_h.setValue(height)

            def pick_region():
                _start_region_picker(on_region_pick)

            browse_btn.clicked.connect(browse_image)
            path_row = QHBoxLayout(); path_row.addWidget(path_input, 1); path_row.addWidget(browse_btn)
            path_widget = QWidget(); path_widget.setLayout(path_row)

            grid.addWidget(QLabel("Template Path:"), row, 0); grid.addWidget(path_widget, row, 1); row += 1
            grid.addWidget(preview_label, row, 0, 1, 2); row += 1
            grid.addWidget(QLabel("Confidence:"), row, 0); grid.addWidget(conf_spin, row, 1); row += 1
            grid.addWidget(QLabel("Region X:"), row, 0); grid.addWidget(region_x, row, 1); row += 1
            grid.addWidget(QLabel("Region Y:"), row, 0); grid.addWidget(region_y, row, 1); row += 1
            grid.addWidget(QLabel("Width:"), row, 0); grid.addWidget(region_w, row, 1); row += 1
            grid.addWidget(QLabel("Height:"), row, 0); grid.addWidget(region_h, row, 1); row += 1
            grid.addWidget(pick_region_btn, row, 1); row += 1
            pick_region_btn.clicked.connect(pick_region)
            update_preview(path_input.text())

            def apply_changes():
                nested_action.template_path = path_input.text().strip()
                nested_action.confidence = conf_spin.value()
                nested_action.region_x = region_x.value()
                nested_action.region_y = region_y.value()
                nested_action.region_w = region_w.value()
                nested_action.region_h = region_h.value()

        elif isinstance(nested_action, RegionColorWatcherAction):
            x_spin = NoWheelSpinBox(); x_spin.setRange(0, 9999); x_spin.setValue(int(nested_action.x))
            y_spin = NoWheelSpinBox(); y_spin.setRange(0, 9999); y_spin.setValue(int(nested_action.y))
            w_spin = NoWheelSpinBox(); w_spin.setRange(1, 9999); w_spin.setValue(int(nested_action.width))
            h_spin = NoWheelSpinBox(); h_spin.setRange(1, 9999); h_spin.setValue(int(nested_action.height))
            color_input = QLineEdit(nested_action.target_color)
            tol_spin = NoWheelSpinBox(); tol_spin.setRange(0, 255); tol_spin.setValue(int(nested_action.tolerance))
            check_combo = QComboBox(); check_combo.addItems(["appears", "disappears", "increases_brightness", "decreases_brightness"])
            check_combo.setCurrentText(getattr(nested_action, 'check_type', 'appears'))
            timeout_spin = NoWheelSpinBox(); timeout_spin.setRange(100, 120000); timeout_spin.setValue(int(getattr(nested_action, 'wait_timeout_ms', 5000)))
            desc_input = QLineEdit(getattr(nested_action, 'description', ''))
            trigger_combo = QComboBox(); trigger_combo.addItem("(None)"); self._load_macro_names_to_combo(trigger_combo)
            if getattr(nested_action, 'trigger_macro_name', ''):
                if trigger_combo.findText(nested_action.trigger_macro_name) == -1:
                    trigger_combo.addItem(nested_action.trigger_macro_name)
                trigger_combo.setCurrentText(nested_action.trigger_macro_name)

            pick_region_btn = QPushButton("🔲 Pick Region")
            pick_color_btn = QPushButton("🎨 Pick Color")

            def on_pick_region(x, y, width, height):
                x_spin.setValue(x)
                y_spin.setValue(y)
                w_spin.setValue(width)
                h_spin.setValue(height)

            def pick_region():
                _start_region_picker(on_pick_region)

            def pick_color():
                color = QColorDialog.getColor()
                if color.isValid():
                    color_input.setText(color.name())

            grid.addWidget(QLabel("X:"), row, 0); grid.addWidget(x_spin, row, 1); row += 1
            grid.addWidget(QLabel("Y:"), row, 0); grid.addWidget(y_spin, row, 1); row += 1
            grid.addWidget(QLabel("Width:"), row, 0); grid.addWidget(w_spin, row, 1); row += 1
            grid.addWidget(QLabel("Height:"), row, 0); grid.addWidget(h_spin, row, 1); row += 1
            grid.addWidget(pick_region_btn, row, 1); row += 1
            color_row = QWidget()
            color_row_layout = QHBoxLayout(color_row)
            color_row_layout.setContentsMargins(0, 0, 0, 0)
            color_row_layout.addWidget(color_input, 1)
            color_row_layout.addWidget(pick_color_btn)
            grid.addWidget(QLabel("Target Color:"), row, 0); grid.addWidget(color_row, row, 1); row += 1
            grid.addWidget(QLabel("Tolerance:"), row, 0); grid.addWidget(tol_spin, row, 1); row += 1
            grid.addWidget(QLabel("Check Type:"), row, 0); grid.addWidget(check_combo, row, 1); row += 1
            grid.addWidget(QLabel("Timeout (ms):"), row, 0); grid.addWidget(timeout_spin, row, 1); row += 1
            grid.addWidget(QLabel("Description:"), row, 0); grid.addWidget(desc_input, row, 1); row += 1
            grid.addWidget(QLabel("Trigger Macro:"), row, 0); grid.addWidget(trigger_combo, row, 1); row += 1
            pick_region_btn.clicked.connect(pick_region)
            pick_color_btn.clicked.connect(pick_color)

            def apply_changes():
                nested_action.x = x_spin.value()
                nested_action.y = y_spin.value()
                nested_action.width = w_spin.value()
                nested_action.height = h_spin.value()
                nested_action.target_color = color_input.text().strip() or "#FF0000"
                nested_action.tolerance = tol_spin.value()
                nested_action.check_type = check_combo.currentText()
                nested_action.wait_timeout_ms = timeout_spin.value()
                nested_action.description = desc_input.text().strip()
                trig = trigger_combo.currentText().strip()
                nested_action.trigger_macro_name = "" if trig == "(None)" else trig

        elif isinstance(nested_action, WindowFocusCheckAction):
            # --- window picker ---
            pick_combo = NoWheelComboBox()
            pick_combo.addItem("- choose a running window -")
            try:
                import pygetwindow as _pgw
                _titles = sorted({t.strip() for t in _pgw.getAllTitles() if t and t.strip()}, key=str.lower)
            except Exception:
                _titles = []
            pick_combo.addItems(_titles)
            pick_combo.setToolTip("Select from currently open windows")

            title_input = QLineEdit(nested_action.window_title_contains)
            title_input.setPlaceholderText("e.g., RuneScape | WoW (| separates alternatives)")

            def _on_pick_window(i, _combo=pick_combo, _inp=title_input):
                if i > 0:
                    _inp.setText(_combo.currentText())
            pick_combo.currentIndexChanged.connect(_on_pick_window)

            refresh_pick_btn = QPushButton("🔄")
            refresh_pick_btn.setFixedWidth(32)
            refresh_pick_btn.setToolTip("Refresh window list")
            def _refresh_pick(_combo=pick_combo, _inp=title_input):
                saved = _inp.text()
                _combo.blockSignals(True)
                _combo.clear()
                _combo.addItem("- choose a running window -")
                try:
                    import pygetwindow as _pgw2
                    _combo.addItems(sorted({t.strip() for t in _pgw2.getAllTitles() if t and t.strip()}, key=str.lower))
                except Exception:
                    pass
                _combo.blockSignals(False)
                _inp.setText(saved)
            refresh_pick_btn.clicked.connect(_refresh_pick)

            pick_row = QHBoxLayout()
            pick_row.setSpacing(4)
            pick_row.addWidget(pick_combo, 1)
            pick_row.addWidget(refresh_pick_btn)

            timeout_spin = NoWheelSpinBox(); timeout_spin.setRange(100, 120000); timeout_spin.setValue(int(nested_action.timeout_ms))
            desc_input = QLineEdit(getattr(nested_action, 'description', ''))

            grid.addWidget(QLabel("Pick Window:"), row, 0)
            picker_container = QWidget()
            picker_container.setLayout(pick_row)
            grid.addWidget(picker_container, row, 1); row += 1
            grid.addWidget(QLabel("Title Contains:"), row, 0); grid.addWidget(title_input, row, 1); row += 1
            grid.addWidget(QLabel("Timeout (ms):"), row, 0); grid.addWidget(timeout_spin, row, 1); row += 1
            grid.addWidget(QLabel("Description:"), row, 0); grid.addWidget(desc_input, row, 1); row += 1

            def apply_changes():
                nested_action.window_title_contains = title_input.text().strip()
                nested_action.timeout_ms = timeout_spin.value()
                nested_action.description = desc_input.text().strip()

        elif isinstance(nested_action, SkillCheckDigitsAction):
            rx = NoWheelSpinBox(); rx.setRange(0, 9999); rx.setValue(int(nested_action.region_x))
            ry = NoWheelSpinBox(); ry.setRange(0, 9999); ry.setValue(int(nested_action.region_y))
            rw = NoWheelSpinBox(); rw.setRange(1, 9999); rw.setValue(int(nested_action.region_w))
            rh = NoWheelSpinBox(); rh.setRange(1, 9999); rh.setValue(int(nested_action.region_h))
            max_digits = NoWheelSpinBox(); max_digits.setRange(1, 16); max_digits.setValue(int(nested_action.max_digits))
            key_delay = NoWheelSpinBox(); key_delay.setRange(10, 1000); key_delay.setValue(int(nested_action.key_delay_ms))
            press_ms = NoWheelSpinBox(); press_ms.setRange(10, 1000); press_ms.setValue(int(getattr(nested_action, 'key_press_ms', 40)))
            pick_btn = QPushButton("🔲 Pick Skill Region")

            def on_region_pick(x, y, width, height):
                rx.setValue(x)
                ry.setValue(y)
                rw.setValue(width)
                rh.setValue(height)

            def pick_region():
                _start_region_picker(on_region_pick)

            grid.addWidget(QLabel("Region X:"), row, 0); grid.addWidget(rx, row, 1); row += 1
            grid.addWidget(QLabel("Region Y:"), row, 0); grid.addWidget(ry, row, 1); row += 1
            grid.addWidget(QLabel("Width:"), row, 0); grid.addWidget(rw, row, 1); row += 1
            grid.addWidget(QLabel("Height:"), row, 0); grid.addWidget(rh, row, 1); row += 1
            grid.addWidget(pick_btn, row, 1); row += 1
            grid.addWidget(QLabel("Max Digits:"), row, 0); grid.addWidget(max_digits, row, 1); row += 1
            grid.addWidget(QLabel("Key Delay (ms):"), row, 0); grid.addWidget(key_delay, row, 1); row += 1
            grid.addWidget(QLabel("Key Press (ms):"), row, 0); grid.addWidget(press_ms, row, 1); row += 1
            pick_btn.clicked.connect(pick_region)

            def apply_changes():
                nested_action.region_x = rx.value()
                nested_action.region_y = ry.value()
                nested_action.region_w = rw.value()
                nested_action.region_h = rh.value()
                nested_action.max_digits = max_digits.value()
                nested_action.key_delay_ms = key_delay.value()
                nested_action.key_press_ms = press_ms.value()

        elif isinstance(nested_action, ConditionalBranchAction):
            cond_combo = QComboBox()
            cond_combo.addItems(["pixel_match", "image_match", "region_watch"])
            cond_combo.setCurrentText(getattr(nested_action, 'condition_type', 'pixel_match'))
            desc_input = QLineEdit(getattr(nested_action, 'description', ''))

            pixel_widget = QWidget()
            pixel_layout = QGridLayout(pixel_widget)
            px = NoWheelSpinBox(); px.setRange(0, 9999); px.setValue(int(getattr(nested_action, 'x', 0)))
            py = NoWheelSpinBox(); py.setRange(0, 9999); py.setValue(int(getattr(nested_action, 'y', 0)))
            pcolor = QLineEdit(getattr(nested_action, 'color', '#FFFFFF'))
            ptol = NoWheelSpinBox(); ptol.setRange(0, 255); ptol.setValue(int(getattr(nested_action, 'tolerance', 15)))
            pick_pixel_btn = QPushButton("🎯 Pick Pixel")
            pick_pixel_color_btn = QPushButton("🎨 Pick Color")

            def on_pick_nested_pixel(x, y):
                px.setValue(x)
                py.setValue(y)

            def pick_nested_pixel():
                _start_coord_picker(on_pick_nested_pixel)

            def pick_nested_color(line_edit: QLineEdit):
                color = QColorDialog.getColor()
                if color.isValid():
                    line_edit.setText(color.name())

            pixel_layout.addWidget(QLabel("X:"), 0, 0); pixel_layout.addWidget(px, 0, 1)
            pixel_layout.addWidget(QLabel("Y:"), 0, 2); pixel_layout.addWidget(py, 0, 3)
            pixel_layout.addWidget(pick_pixel_btn, 1, 0, 1, 4)
            pcolor_row = QWidget()
            pcolor_row_layout = QHBoxLayout(pcolor_row)
            pcolor_row_layout.setContentsMargins(0, 0, 0, 0)
            pcolor_row_layout.addWidget(pcolor, 1)
            pcolor_row_layout.addWidget(pick_pixel_color_btn)
            pixel_layout.addWidget(QLabel("Color:"), 2, 0); pixel_layout.addWidget(pcolor_row, 2, 1, 1, 3)
            pixel_layout.addWidget(QLabel("Tolerance:"), 3, 0); pixel_layout.addWidget(ptol, 3, 1)
            pick_pixel_btn.clicked.connect(pick_nested_pixel)
            pick_pixel_color_btn.clicked.connect(lambda: pick_nested_color(pcolor))

            image_widget = QWidget()
            image_layout = QGridLayout(image_widget)
            ipath = QLineEdit(getattr(nested_action, 'template_path', ''))
            ibrowse = QPushButton("Browse")
            iconf = QDoubleSpinBox(); iconf.setRange(0.1, 1.0); iconf.setSingleStep(0.05); iconf.setValue(float(getattr(nested_action, 'confidence', 0.8)))
            irx = NoWheelSpinBox(); irx.setRange(0, 9999); irx.setValue(int(getattr(nested_action, 'region_x', 0)))
            iry = NoWheelSpinBox(); iry.setRange(0, 9999); iry.setValue(int(getattr(nested_action, 'region_y', 0)))
            irw = NoWheelSpinBox(); irw.setRange(1, 9999); irw.setValue(int(getattr(nested_action, 'region_w', 1920)))
            irh = NoWheelSpinBox(); irh.setRange(1, 9999); irh.setValue(int(getattr(nested_action, 'region_h', 1080)))
            i_preview = QLabel("No template selected")
            i_preview.setAlignment(Qt.AlignCenter)
            i_preview.setMinimumHeight(72)
            i_preview.setStyleSheet("border: 1px solid #444; border-radius: 4px; padding: 4px;")
            ipick = QPushButton("🔲 Pick Region")

            def update_nested_image_preview(path: str):
                if not path or not os.path.exists(path):
                    i_preview.setPixmap(QPixmap())
                    i_preview.setText("No template selected")
                    return
                pix = QPixmap(path)
                if pix.isNull():
                    i_preview.setPixmap(QPixmap())
                    i_preview.setText("Unable to preview image")
                    return
                i_preview.setText("")
                i_preview.setPixmap(pix.scaled(220, 66, Qt.KeepAspectRatio, Qt.SmoothTransformation))

            def browse_nested_cond_image():
                path, _ = QFileDialog.getOpenFileName(self, "Select Template Image", "", "Images (*.png *.jpg *.jpeg *.bmp);;All Files (*.*)")
                if path:
                    ipath.setText(path)

            def on_pick_nested_image_region(x, y, width, height):
                irx.setValue(x)
                iry.setValue(y)
                irw.setValue(width)
                irh.setValue(height)

            def pick_nested_image_region():
                _start_region_picker(on_pick_nested_image_region)

            ipath.textChanged.connect(update_nested_image_preview)
            ibrowse.clicked.connect(browse_nested_cond_image)
            image_row = QWidget()
            image_row_layout = QHBoxLayout(image_row)
            image_row_layout.setContentsMargins(0, 0, 0, 0)
            image_row_layout.addWidget(ipath, 1)
            image_row_layout.addWidget(ibrowse)
            image_layout.addWidget(QLabel("Template:"), 0, 0); image_layout.addWidget(image_row, 0, 1, 1, 3)
            image_layout.addWidget(i_preview, 1, 0, 1, 4)
            image_layout.addWidget(QLabel("Confidence:"), 2, 0); image_layout.addWidget(iconf, 2, 1)
            image_layout.addWidget(QLabel("Region X:"), 3, 0); image_layout.addWidget(irx, 3, 1)
            image_layout.addWidget(QLabel("Region Y:"), 3, 2); image_layout.addWidget(iry, 3, 3)
            image_layout.addWidget(QLabel("Width:"), 4, 0); image_layout.addWidget(irw, 4, 1)
            image_layout.addWidget(QLabel("Height:"), 4, 2); image_layout.addWidget(irh, 4, 3)
            image_layout.addWidget(ipick, 5, 0, 1, 4)
            ipick.clicked.connect(pick_nested_image_region)
            update_nested_image_preview(ipath.text())

            region_widget = QWidget()
            region_layout = QGridLayout(region_widget)
            rgx = NoWheelSpinBox(); rgx.setRange(0, 9999); rgx.setValue(int(getattr(nested_action, 'region_x', 0)))
            rgy = NoWheelSpinBox(); rgy.setRange(0, 9999); rgy.setValue(int(getattr(nested_action, 'region_y', 0)))
            rgw = NoWheelSpinBox(); rgw.setRange(1, 9999); rgw.setValue(int(getattr(nested_action, 'region_w', 200)))
            rgh = NoWheelSpinBox(); rgh.setRange(1, 9999); rgh.setValue(int(getattr(nested_action, 'region_h', 100)))
            rg_color = QLineEdit(getattr(nested_action, 'color', '#FF0000'))
            rg_tol = NoWheelSpinBox(); rg_tol.setRange(0, 255); rg_tol.setValue(int(getattr(nested_action, 'tolerance', 15)))
            pick_region_btn = QPushButton("🔲 Pick Region")
            pick_region_color_btn = QPushButton("🎨 Pick Color")

            def on_pick_nested_region(x, y, width, height):
                rgx.setValue(x)
                rgy.setValue(y)
                rgw.setValue(width)
                rgh.setValue(height)

            def pick_nested_region():
                _start_region_picker(on_pick_nested_region)

            region_layout.addWidget(QLabel("Region X:"), 0, 0); region_layout.addWidget(rgx, 0, 1)
            region_layout.addWidget(QLabel("Region Y:"), 0, 2); region_layout.addWidget(rgy, 0, 3)
            region_layout.addWidget(QLabel("Width:"), 1, 0); region_layout.addWidget(rgw, 1, 1)
            region_layout.addWidget(QLabel("Height:"), 1, 2); region_layout.addWidget(rgh, 1, 3)
            region_layout.addWidget(pick_region_btn, 2, 0, 1, 4)
            rg_color_row = QWidget()
            rg_color_row_layout = QHBoxLayout(rg_color_row)
            rg_color_row_layout.setContentsMargins(0, 0, 0, 0)
            rg_color_row_layout.addWidget(rg_color, 1)
            rg_color_row_layout.addWidget(pick_region_color_btn)
            region_layout.addWidget(QLabel("Color:"), 3, 0); region_layout.addWidget(rg_color_row, 3, 1, 1, 3)
            region_layout.addWidget(QLabel("Tolerance:"), 4, 0); region_layout.addWidget(rg_tol, 4, 1)
            pick_region_btn.clicked.connect(pick_nested_region)
            pick_region_color_btn.clicked.connect(lambda: pick_nested_color(rg_color))

            stack = QStackedWidget()
            stack.addWidget(pixel_widget)
            stack.addWidget(image_widget)
            stack.addWidget(region_widget)

            def update_stack(cond: str):
                stack.setCurrentIndex({"pixel_match": 0, "image_match": 1, "region_watch": 2}.get(cond, 0))

            cond_combo.currentTextChanged.connect(update_stack)
            update_stack(cond_combo.currentText())

            grid.addWidget(QLabel("Condition Type:"), row, 0); grid.addWidget(cond_combo, row, 1); row += 1
            grid.addWidget(QLabel("Description:"), row, 0); grid.addWidget(desc_input, row, 1); row += 1
            grid.addWidget(stack, row, 0, 1, 2); row += 1

            def apply_changes():
                nested_action.condition_type = cond_combo.currentText()
                nested_action.description = desc_input.text().strip()
                if nested_action.condition_type == "image_match":
                    nested_action.template_path = ipath.text().strip()
                    nested_action.confidence = iconf.value()
                    nested_action.region_x = irx.value()
                    nested_action.region_y = iry.value()
                    nested_action.region_w = irw.value()
                    nested_action.region_h = irh.value()
                elif nested_action.condition_type == "region_watch":
                    nested_action.region_x = rgx.value()
                    nested_action.region_y = rgy.value()
                    nested_action.region_w = rgw.value()
                    nested_action.region_h = rgh.value()
                    nested_action.color = rg_color.text().strip() or "#FF0000"
                    nested_action.tolerance = rg_tol.value()
                else:
                    nested_action.x = px.value()
                    nested_action.y = py.value()
                    nested_action.color = pcolor.text().strip() or "#FFFFFF"
                    nested_action.tolerance = ptol.value()

        else:
            message = QLabel("This nested action type currently has no detailed editor.\nYou can still reorder/remove it.")
            message.setWordWrap(True)
            grid.addWidget(message, row, 0, 1, 2)

            def apply_changes():
                return

        root.addLayout(grid)

        footer = QHBoxLayout()
        footer.addStretch()
        cancel_btn = QPushButton("Cancel")
        save_btn = QPushButton("Save")
        save_btn.setObjectName("AddActionBtn")
        footer.addWidget(cancel_btn)
        footer.addWidget(save_btn)
        root.addLayout(footer)

        cancel_btn.clicked.connect(dialog.reject)

        def on_save():
            apply_changes()
            dialog.accept()

        save_btn.clicked.connect(on_save)
        return dialog.exec() == QDialog.Accepted

    def _open_conditional_branch_editor(self, row: int):
        """Open dialog to edit THEN/ELSE nested action lists for a conditional branch."""
        if not self.current_profile or row < 0 or row >= len(self.current_profile.actions):
            return

        branch = self.current_profile.actions[row]
        if not isinstance(branch, ConditionalBranchAction):
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Configure IF / THEN / ELSE")
        dialog.setMinimumSize(760, 520)
        QTimer.singleShot(0, lambda: apply_dark_title_bar(dialog))

        root_layout = QVBoxLayout(dialog)
        root_layout.setSpacing(10)

        cond_desc = branch.description or "(no description)"
        if branch.condition_type == "image_match":
            cond_text = f"IF image '{os.path.basename(branch.template_path) if branch.template_path else '(not set)'}'"
        elif branch.condition_type == "region_watch":
            cond_text = f"IF region ({branch.region_x},{branch.region_y},{branch.region_w}x{branch.region_h}) has {branch.color}"
        else:
            cond_text = f"IF pixel ({branch.x},{branch.y}) == {branch.color} ±{branch.tolerance}"

        header = QLabel(f"{cond_text}\nDescription: {cond_desc}")
        header.setWordWrap(True)
        header.setStyleSheet("font-weight: bold; padding: 6px;")
        root_layout.addWidget(header)

        tabs = QTabWidget()
        root_layout.addWidget(tabs, 1)

        def build_branch_tab(title: str, action_list: List[MacroAction]):
            page = QWidget()
            page_layout = QVBoxLayout(page)

            list_widget = QListWidget()
            page_layout.addWidget(list_widget, 1)

            add_row = QHBoxLayout()
            add_row.addWidget(QLabel("Add Action:"))
            type_combo = QComboBox()
            type_combo.addItems([
                "Keyboard Key", "Mouse Click", "Mouse Move", "Delay",
                "Pixel Check", "Image Match", "Region Watcher",
                "Window Focus Check", "Skill Check Digits", "Run Profile", "Conditional Branch"
            ])
            add_btn = QPushButton("➕ Add")
            add_row.addWidget(type_combo, 1)
            add_row.addWidget(add_btn)
            page_layout.addLayout(add_row)

            btn_row = QHBoxLayout()
            up_btn = QPushButton("↑ Up")
            down_btn = QPushButton("↓ Down")
            remove_btn = QPushButton("🗑️ Remove")
            edit_btn = QPushButton("✏️ Edit")
            btn_row.addWidget(up_btn)
            btn_row.addWidget(down_btn)
            btn_row.addWidget(edit_btn)
            btn_row.addWidget(remove_btn)
            btn_row.addStretch()
            page_layout.addLayout(btn_row)

            def refresh_list():
                list_widget.clear()
                for idx, nested_action in enumerate(action_list, start=1):
                    details = self._format_action_details(nested_action)
                    list_widget.addItem(f"{idx}. {nested_action.action_type} - {details}")

            def add_action_to_branch():
                new_action = self._create_default_action_for_type(type_combo.currentText())
                action_list.append(new_action)
                refresh_list()
                list_widget.setCurrentRow(len(action_list) - 1)

            def remove_selected():
                idx = list_widget.currentRow()
                if 0 <= idx < len(action_list):
                    del action_list[idx]
                    refresh_list()
                    if action_list:
                        list_widget.setCurrentRow(min(idx, len(action_list) - 1))

            def move_selected_up():
                idx = list_widget.currentRow()
                if 0 < idx < len(action_list):
                    action_list[idx - 1], action_list[idx] = action_list[idx], action_list[idx - 1]
                    refresh_list()
                    list_widget.setCurrentRow(idx - 1)

            def move_selected_down():
                idx = list_widget.currentRow()
                if 0 <= idx < len(action_list) - 1:
                    action_list[idx + 1], action_list[idx] = action_list[idx], action_list[idx + 1]
                    refresh_list()
                    list_widget.setCurrentRow(idx + 1)

            def edit_selected():
                idx = list_widget.currentRow()
                if 0 <= idx < len(action_list):
                    if self._edit_nested_action_dialog(action_list[idx]):
                        refresh_list()
                        list_widget.setCurrentRow(idx)

            add_btn.clicked.connect(add_action_to_branch)
            remove_btn.clicked.connect(remove_selected)
            up_btn.clicked.connect(move_selected_up)
            down_btn.clicked.connect(move_selected_down)
            edit_btn.clicked.connect(edit_selected)
            list_widget.itemDoubleClicked.connect(lambda _item: edit_selected())

            refresh_list()
            return page

        true_actions_working = list(branch.if_true_actions or [])
        false_actions_working = list(branch.if_false_actions or [])

        tabs.addTab(build_branch_tab("THEN", true_actions_working), "✓ THEN (TRUE)")
        tabs.addTab(build_branch_tab("ELSE", false_actions_working), "✗ ELSE (FALSE)")

        footer = QHBoxLayout()
        footer.addStretch()
        cancel_btn = QPushButton("Cancel")
        save_btn = QPushButton("💾 Save Branch")
        save_btn.setObjectName("AddActionBtn")
        footer.addWidget(cancel_btn)
        footer.addWidget(save_btn)
        root_layout.addLayout(footer)

        cancel_btn.clicked.connect(dialog.reject)

        def save_and_close():
            self._push_undo_state()
            branch.if_true_actions = true_actions_working
            branch.if_false_actions = false_actions_working
            self.refresh_action_table()
            self.save_current_profile()
            self.exec_status.setText(
                f"Updated conditional branch: THEN {len(branch.if_true_actions)} / ELSE {len(branch.if_false_actions)}"
            )
            dialog.accept()

        save_btn.clicked.connect(save_and_close)
        dialog.exec()
    
    def move_action_up(self):
        """Move selected action up."""
        current_row = self.action_table.currentRow()
        if current_row > 0 and self.current_profile:
            self._push_undo_state()
            actions = self.current_profile.actions
            actions[current_row], actions[current_row - 1] = actions[current_row - 1], actions[current_row]
            self.refresh_action_table()
            self.action_table.setCurrentCell(current_row - 1, 0)
            self.save_current_profile()
    
    def move_action_down(self):
        """Move selected action down."""
        current_row = self.action_table.currentRow()
        if self.current_profile and 0 <= current_row < len(self.current_profile.actions) - 1:
            self._push_undo_state()
            actions = self.current_profile.actions
            actions[current_row], actions[current_row + 1] = actions[current_row + 1], actions[current_row]
            self.refresh_action_table()
            self.action_table.setCurrentCell(current_row + 1, 0)
            self.save_current_profile()
    
    def delete_selected_action(self):
        """Delete selected action."""
        current_row = self.action_table.currentRow()
        if current_row >= 0 and self.current_profile:
            self._push_undo_state()
            del self.current_profile.actions[current_row]
            self.refresh_action_table()
            self.save_current_profile()
    
    def clear_all_actions(self):
        """Clear all actions."""
        if self.current_profile:
            reply = QMessageBox.question(
                self,
                "Confirm Clear",
                "Delete all actions?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._push_undo_state()
                self.current_profile.actions.clear()
                self.refresh_action_table()
                self.save_current_profile()

    def insert_template(self, template_name, insert_at: Optional[int] = None):
        """Insert predefined action template."""
        if not self.current_profile:
            QMessageBox.warning(self, "No Profile", "Please load a profile first")
            return
        
        if template_name in ACTION_TEMPLATES:
            self._push_undo_state()
            template_actions = ACTION_TEMPLATES[template_name]
            if insert_at is None:
                insert_at = len(self.current_profile.actions)
            insert_at = max(0, min(insert_at, len(self.current_profile.actions)))

            for offset, action_dict in enumerate(template_actions):
                action = MacroAction.from_dict(action_dict)
                self.current_profile.actions.insert(insert_at + offset, action)
            
            self.refresh_action_table()
            self.save_current_profile()
            if self.action_table.currentRow() >= 0 or insert_at != len(self.current_profile.actions):
                self.exec_status.setText(f"Template inserted at row {insert_at + 1}: {len(template_actions)} actions")
            else:
                QMessageBox.information(self, "Template Inserted", 
                    f"Added {len(template_actions)} actions from '{template_name}' template")
    
    def load_profile(self, profile: MacroProfile):
        """Load profile into editor."""
        self.current_profile = profile
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.profile_label.setText(f"Editing: [{profile.game}] {profile.name}")
        if hasattr(self, 'profile_desc_label'):
            _desc = (profile.description or "").strip()
            self.profile_desc_label.setText(_desc if _desc else "No description")
        self.refresh_action_table()
        
        # Update floating toolbar with profile info
        try:
            main_window = self.window()
            if hasattr(main_window, 'macro_toolbar') and main_window.macro_toolbar:
                main_window.macro_toolbar.set_profile_info(profile.name, profile.hotkey)
        except Exception:
            pass
    
    def test_macro(self):
        """Test run the macro."""
        if not self.current_profile or not self.current_profile.actions:
            QMessageBox.warning(self, "Warning", "No actions to execute")
            return
        self.execute_profile(self.current_profile, countdown_seconds=3, show_toolbar=False)

    def debug_macro_preview(self):
        """Show a readable action-by-action preview before execution."""
        if not self.current_profile or not self.current_profile.actions:
            QMessageBox.warning(self, "Warning", "No actions to preview")
            return
        lines = [f"Profile: {self.current_profile.name}", f"Actions: {len(self.current_profile.actions)}", ""]
        for idx, action in enumerate(self.current_profile.actions, start=1):
            lines.append(f"{idx:02d}. {action.action_type}: {self._format_action_details(action)}")
        QMessageBox.information(self, "Debug Preview", "\n".join(lines))

    def execute_profile(self, profile: MacroProfile, countdown_seconds: int = 0, show_toolbar: bool = False):
        """Execute a profile in editor context."""
        if not profile or not profile.actions:
            self.exec_status.setText("No actions to execute")
            return

        if self.executor and self.executor.isRunning():
            self.exec_status.setText("Macro already running")
            return

        self.current_profile = profile
        self.profile_label.setText(f"Editing: [{profile.game}] {profile.name}")
        if hasattr(self, 'profile_desc_label'):
            _desc = (profile.description or "").strip()
            self.profile_desc_label.setText(_desc if _desc else "No description")
        self.refresh_action_table()

        if countdown_seconds > 0:
            for i in range(countdown_seconds, 0, -1):
                self.exec_status.setText(f"Starting in {i}...")
                QApplication.processEvents()
                time.sleep(1)

        self.exec_status.setText("Running...")
        self.exec_progress.setValue(0)
        self.test_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        self.executor = MacroExecutor(
            profile,
            force_randomize_delays=self.force_humanized_check.isChecked() if hasattr(self, 'force_humanized_check') else False
        )
        self.executor.progress.connect(self.update_exec_progress)
        self.executor.finished.connect(self.on_exec_finished)
        self.executor.error.connect(self.on_exec_error)

        try:
            main_window = self.window()
            # Ensure toolbar is created when explicitly requested
            if show_toolbar and hasattr(main_window, 'ensure_macro_toolbar'):
                main_window.ensure_macro_toolbar()
            # Always wire up the toolbar if it already exists (handles the case where
            # the user opened it manually and then triggered a run via hotkey/test button)
            toolbar = getattr(main_window, 'macro_toolbar', None)
            if toolbar is not None:
                self.executor.progress.connect(lambda p, s: toolbar.set_progress(p, s))
                self.executor.finished.connect(lambda m: toolbar.stop_execution())
                toolbar.start_execution(profile.name)
        except Exception:
            pass

        self.executor.start()
    
    def start_recording_macro(self):
        """Start recording keyboard/mouse actions."""
        try:
            from pynput import keyboard  # noqa: F401
            from pynput import mouse  # noqa: F401
        except ImportError:
            QMessageBox.warning(self, "Missing Dependency", "Recording support is unavailable in this runtime.")
            return

        main_window = self.window()
        if not hasattr(main_window, 'macro_recorder'):
            QMessageBox.warning(self, "Unavailable", "Macro recorder is not available.")
            return

        self._recorded_actions_buffer = []
        recorder = main_window.macro_recorder
        recorder.record_mouse_moves = self.record_moves_check.isChecked()
        recorder.use_relative_coords = self.record_pct_check.isChecked() if hasattr(self, 'record_pct_check') else False
        recorder.action_recorded.connect(self._on_recorder_action)
        recorder.start_recording()

        self.record_btn.setEnabled(False)
        self.stop_record_btn.setEnabled(True)
        self.import_record_btn.setEnabled(False)
        self.exec_status.setText("Recording... perform actions, then click Stop Recording")

    def stop_recording_macro(self):
        """Stop recording keyboard/mouse actions."""
        main_window = self.window()
        if not hasattr(main_window, 'macro_recorder'):
            return

        recorder = main_window.macro_recorder
        recorded = recorder.stop_recording()
        try:
            recorder.action_recorded.disconnect(self._on_recorder_action)
        except Exception:
            pass

        if not self._recorded_actions_buffer and recorded:
            self._recorded_actions_buffer = recorded

        self.record_btn.setEnabled(True)
        self.stop_record_btn.setEnabled(False)
        self.import_record_btn.setEnabled(len(self._recorded_actions_buffer) > 0)
        self.exec_status.setText(f"Recorded {len(self._recorded_actions_buffer)} actions")

    def _on_recorder_action(self, action_data: Dict[str, Any]):
        """Receive live recorder actions."""
        self._recorded_actions_buffer.append(dict(action_data))

    def import_recorded_macro(self):
        """Import buffered recorded actions into current profile."""
        if not self.current_profile:
            QMessageBox.warning(self, "No Profile", "Please load a profile before importing recording.")
            return
        if not self._recorded_actions_buffer:
            QMessageBox.information(self, "No Recording", "No recorded actions to import.")
            return

        imported = 0
        for action_data in self._recorded_actions_buffer:
            try:
                action = MacroAction.from_dict(action_data)
                self.current_profile.actions.append(action)
                imported += 1
            except Exception as e:
                logger.error(f"Skipping recorded action due to error: {e}")

        self.refresh_action_table()
        self.save_current_profile()
        self.exec_status.setText(f"Imported {imported} recorded actions")
        QMessageBox.information(self, "Recording Imported", f"Imported {imported} actions into current profile.")
    
    def stop_macro(self):
        """Stop running macro."""
        if self.executor:
            self.executor.stop()
            self.exec_status.setText("Stopped")
            self.test_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            
            # Stop floating toolbar
            try:
                main_window = self.window()
                toolbar = getattr(main_window, 'macro_toolbar', None)
                if toolbar:
                    toolbar.stop_execution()
            except Exception:
                pass

    def set_execution_paused(self, paused: bool):
        """Pause/resume active executor from toolbar."""
        if not self.executor:
            return
        if paused:
            self.executor.pause()
            self.exec_status.setText("Paused")
        else:
            self.executor.resume()
            self.exec_status.setText("Running...")
    
    def update_exec_progress(self, progress: int, status: str):
        """Update execution progress."""
        self.exec_progress.setValue(progress)
        self.exec_status.setText(status)
    
    def on_exec_finished(self, message: str):
        """Handle execution completion."""
        self.exec_status.setText(message)
        self.exec_progress.setValue(100)
        self.test_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.executor = None
        self._add_run_history_entry("Completed", success=True)
        try:
            main_window = self.window()
            toolbar = getattr(main_window, 'macro_toolbar', None)
            if toolbar:
                toolbar.stop_execution()
        except Exception:
            pass

    def on_exec_error(self, error: str):
        """Handle execution error."""
        self.exec_status.setText(f"Error: {error}")
        self.test_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.executor = None
        self._add_run_history_entry(f"Error: {error[:40]}", success=False)
        try:
            main_window = self.window()
            toolbar = getattr(main_window, 'macro_toolbar', None)
            if toolbar:
                toolbar.stop_execution()
        except Exception:
            pass
        logger.error(f"Macro execution error: {error}")

# ============================
# COORDINATE PICKER OVERLAY
# ============================

def get_virtual_desktop_geometry() -> tuple[int, int, int, int]:
    """Return bounding rectangle that covers all connected screens."""
    screens = QApplication.screens()
    if not screens:
        return (0, 0, 1920, 1080)

    min_x = min(screen.geometry().x() for screen in screens)
    min_y = min(screen.geometry().y() for screen in screens)
    max_x = max(screen.geometry().x() + screen.geometry().width() for screen in screens)
    max_y = max(screen.geometry().y() + screen.geometry().height() for screen in screens)
    return (min_x, min_y, max_x - min_x, max_y - min_y)


def monitor_display_label(index: int, screen) -> str:
    geo = screen.geometry()
    return f"Display {index + 1}: {screen.name()} ({geo.width()}x{geo.height()} @ {geo.x()},{geo.y()})"

class CoordinatePickerOverlay(QWidget):
    """Fullscreen overlay for picking screen coordinates (multi-monitor aware)."""
    
    def __init__(self, callback=None, accent_color="#FF006E", parent=None):
        super().__init__(parent)
        self.callback = callback
        self.accent_color = accent_color
        self.current_pos = [0, 0]
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Window)
        self.setWindowModality(Qt.ApplicationModal)
        self.setCursor(Qt.CrossCursor)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        desktop_x, desktop_y, desktop_w, desktop_h = get_virtual_desktop_geometry()
        self.setGeometry(desktop_x, desktop_y, desktop_w, desktop_h)
        self.setMouseTracking(True)
        self.setWindowState(Qt.WindowFullScreen)
    
    def showEvent(self, event):
        """Resize to cover all screens on show."""
        super().showEvent(event)
        desktop_x, desktop_y, desktop_w, desktop_h = get_virtual_desktop_geometry()
        self.setGeometry(desktop_x, desktop_y, desktop_w, desktop_h)
        self.raise_()
        self.activateWindow()
        self.setFocus()
        QTimer.singleShot(0, self._force_front)
        QTimer.singleShot(60, self._force_front)

    def _force_front(self):
        if not self.isVisible():
            return
        self.raise_()
        self.activateWindow()
        self.setFocus()
    
    def mouseMoveEvent(self, event):
        """Track mouse position."""
        pos = event.position()
        self.current_pos[0] = int(pos.x())
        self.current_pos[1] = int(pos.y())
        self.update()
    
    def mousePressEvent(self, event):
        """Capture click and call callback."""
        if event.button() == Qt.LeftButton:
            if self.callback:
                global_pos = self.mapToGlobal(QPoint(self.current_pos[0], self.current_pos[1]))
                self.callback(global_pos.x(), global_pos.y())
            self.close()
    
    def keyPressEvent(self, event):
        """Handle ESC to cancel."""
        if event.key() == Qt.Key_Escape:
            self.close()
    
    def paintEvent(self, event):
        """Draw crosshair and coordinates."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 26))
        
        # Draw crosshair lines
        pen = QPen(QColor(self.accent_color), 2)
        painter.setPen(pen)
        
        # Vertical line
        painter.drawLine(self.current_pos[0], 0, self.current_pos[0], self.height())
        # Horizontal line
        painter.drawLine(0, self.current_pos[1], self.width(), self.current_pos[1])
        
        # Circle around cursor
        painter.drawEllipse(self.current_pos[0] - 20, self.current_pos[1] - 20, 40, 40)
        
        # Draw coordinates
        painter.setPen(QPen(QColor("#FFFFFF"), 1))
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)
        
        global_pos = self.mapToGlobal(QPoint(self.current_pos[0], self.current_pos[1]))
        coord_text = f"X: {global_pos.x()}, Y: {global_pos.y()}"
        painter.drawText(10, 30, coord_text)
        painter.drawText(10, 50, "Click to select | ESC to cancel")

class RegionPickerOverlay(QWidget):
    """Fullscreen region picker (like Windows Shift+S). Drag to select region (multi-monitor aware)."""
    
    def __init__(self, callback=None, accent_color="#FF006E", parent=None):
        super().__init__(parent)
        self.callback = callback
        self.accent_color = accent_color 
        self.start_pos = None
        self.current_pos = [0, 0]
        self.selected_region = None
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Window)
        self.setWindowModality(Qt.ApplicationModal)
        self.setCursor(Qt.CrossCursor)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        desktop_x, desktop_y, desktop_w, desktop_h = get_virtual_desktop_geometry()
        self.setGeometry(desktop_x, desktop_y, desktop_w, desktop_h)
        self.setMouseTracking(True)
        self.setWindowState(Qt.WindowFullScreen)
    
    def showEvent(self, event):
        """Resize to cover all screens on show."""
        super().showEvent(event)
        desktop_x, desktop_y, desktop_w, desktop_h = get_virtual_desktop_geometry()
        self.setGeometry(desktop_x, desktop_y, desktop_w, desktop_h)
        self.raise_()
        self.activateWindow()
        self.setFocus()
        QTimer.singleShot(0, self._force_front)
        QTimer.singleShot(60, self._force_front)

    def _force_front(self):
        if not self.isVisible():
            return
        self.raise_()
        self.activateWindow()
        self.setFocus()
    
    def mousePressEvent(self, event):
        """Start region selection."""
        if event.button() == Qt.LeftButton:
            pos = event.position()
            self.start_pos = [int(pos.x()), int(pos.y())]
            self.current_pos = self.start_pos.copy()
    
    def mouseMoveEvent(self, event):
        """Track mouse for drag region."""
        pos = event.position()
        self.current_pos[0] = int(pos.x())
        self.current_pos[1] = int(pos.y())
        self.update()
    
    def mouseReleaseEvent(self, event):
        """Finish region selection and return coordinates."""
        if event.button() == Qt.LeftButton and self.start_pos:
            x1, y1 = self.start_pos
            x2, y2 = self.current_pos
            
            # Normalize coordinates
            x = min(x1, x2)
            y = min(y1, y2)
            width = abs(x2 - x1)
            height = abs(y2 - y1)
            
            if width > 10 and height > 10:  # Ignore tiny selections
                if self.callback:
                    global_pos = self.mapToGlobal(QPoint(x, y))
                    self.callback(global_pos.x(), global_pos.y(), width, height)
            
            self.close()
    
    def keyPressEvent(self, event):
        """Handle ESC to cancel."""
        if event.key() == Qt.Key_Escape:
            self.close()
    
    def paintEvent(self, event):
        """Draw selection rectangle."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 26))
        
        if self.start_pos:
            # Draw selection rectangle
            x1, y1 = self.start_pos
            x2, y2 = self.current_pos
            
            x = min(x1, x2)
            y = min(y1, y2)
            width = abs(x2 - x1)
            height = abs(y2 - y1)
            
            # Draw border
            pen = QPen(QColor(self.accent_color), 3)
            painter.setPen(pen)
            painter.drawRect(x, y, width, height)

            # Draw corner handles for better visibility on bright backgrounds
            handle_len = 14
            painter.drawLine(x, y, x + handle_len, y)
            painter.drawLine(x, y, x, y + handle_len)
            painter.drawLine(x + width, y, x + width - handle_len, y)
            painter.drawLine(x + width, y, x + width, y + handle_len)
            painter.drawLine(x, y + height, x + handle_len, y + height)
            painter.drawLine(x, y + height, x, y + height - handle_len)
            painter.drawLine(x + width, y + height, x + width - handle_len, y + height)
            painter.drawLine(x + width, y + height, x + width, y + height - handle_len)
            
            # Draw dimensions
            painter.setPen(QPen(QColor("#FFFFFF"), 1))
            font = painter.font()
            font.setPointSize(12)
            font.setBold(True)
            painter.setFont(font)
            
            dim_text = f"{width} x {height}"
            painter.drawText(x + 10, y - 10, dim_text)
        
        # Draw instructions
        painter.setPen(QPen(QColor("#FFFFFF"), 1))
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(10, 30, "Drag to select region | ESC to cancel")


# -----------------------------------------------------------------------------
class KeyCaptureEdit(QLineEdit):
    """Click-to-arm QLineEdit that records the next key/mouse combo (e.g. Ctrl+F12, Mouse4, Ctrl+Left)."""
    combo_captured = Signal(str)   # emitted with e.g. "Ctrl+F12", "Mouse4", "Alt+Left"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("Click here, then press key or mouse button…")
        self.setCursor(Qt.PointingHandCursor)
        self._armed = False
        self._kb_listener = None
        self._mouse_listener = None
        self._held_modifiers = set()
        # Auto-disarm after 10 s if user does nothing
        self._arm_timer = QTimer(self)
        self._arm_timer.setSingleShot(True)
        self._arm_timer.timeout.connect(self._disarm_capture)

    # Combos that should never be set as hotkeys (system shortcuts / normal clicks)
    _BLACKLISTED = frozenset({
        'Ctrl+C', 'Ctrl+V', 'Ctrl+D', 'Ctrl+Z', 'Ctrl+Y',
        'Del', 'Left', 'Right',
    })

    def mousePressEvent(self, event):
        btn = event.button()
        if not self._armed:
            # Only left-click arms the widget
            if btn == Qt.LeftButton:
                super().mousePressEvent(event)
                self._arm_capture()
            event.accept()
            return

        # Widget is armed — left click cancels; other buttons capture
        if btn == Qt.LeftButton:
            self._disarm_capture()
            event.accept()
            return

        # Map Qt button to name for direct capture
        _btn_map = {
            Qt.RightButton:   'Right',
            Qt.MiddleButton:  'Middle',
            Qt.BackButton:    'Mouse4',
            Qt.ForwardButton: 'Mouse5',
        }
        mouse_name = _btn_map.get(btn)
        if mouse_name is None:
            # Extra buttons Qt.ExtraButton3+ — use numeric label
            mouse_name = f'Mouse{int(btn):x}'

        # Derive modifiers from Qt event (more reliable than the pynput-tracked set)
        mods = event.modifiers()
        parts = []
        if mods & Qt.ControlModifier:
            parts.append('Ctrl')
        if mods & Qt.AltModifier:
            parts.append('Alt')
        if mods & Qt.ShiftModifier:
            parts.append('Shift')
        parts.append(mouse_name)
        self._emit_combo(parts[-1], parts[:-1])
        event.accept()

    def focusOutEvent(self, event):
        # Do NOT disarm on focus-out: the click that stole focus may be the
        # mouse button the user wants to capture.  We rely on Escape or a
        # successful capture to disarm.
        super().focusOutEvent(event)

    def _arm_capture(self):
        """Start capturing keyboard/mouse input using pynput."""
        self._armed = True
        self._held_modifiers = set()
        self.setPlaceholderText("Press key or click mouse button (Esc to cancel)…")
        self._highlight(True)
        self._arm_timer.start(10000)  # auto-cancel after 10 s

        try:
            from pynput import keyboard, mouse

            # --- keyboard callback (runs in pynput thread) ---
            def on_key_press(key):
                if not self._armed:
                    return False  # stop listener
                try:
                    from pynput.keyboard import Key as _PKey
                    if key in (_PKey.ctrl_l, _PKey.ctrl_r, _PKey.ctrl):
                        self._held_modifiers.add('Ctrl')
                        return  # keep listening
                    if key in (_PKey.alt_l, _PKey.alt_r, _PKey.alt):
                        self._held_modifiers.add('Alt')
                        return  # keep listening
                    if key in (_PKey.shift_l, _PKey.shift_r, _PKey.shift):
                        self._held_modifiers.add('Shift')
                        return  # keep listening
                    if key in (_PKey.esc, _PKey.escape):
                        QTimer.singleShot(0, self._disarm_capture)
                        return False  # stop listener
                    key_name = self._extract_key_name_from_pynput(key)
                    if key_name:
                        # Snapshot modifiers NOW, then marshal to Qt main thread
                        held = list(sorted(self._held_modifiers))
                        QTimer.singleShot(0, lambda kn=key_name, hm=held: self._emit_combo(kn, hm))
                        return False  # stop listener
                except Exception:
                    pass
                return None  # keep listening for unrecognised keys

            def on_key_release(key):
                if not self._armed:
                    return False
                try:
                    from pynput.keyboard import Key as _PKey
                    if key in (_PKey.ctrl_l, _PKey.ctrl_r, _PKey.ctrl):
                        self._held_modifiers.discard('Ctrl')
                    elif key in (_PKey.alt_l, _PKey.alt_r, _PKey.alt):
                        self._held_modifiers.discard('Alt')
                    elif key in (_PKey.shift_l, _PKey.shift_r, _PKey.shift):
                        self._held_modifiers.discard('Shift')
                except Exception:
                    pass

            # --- mouse callback (runs in pynput thread) ---
            def on_mouse_click(x, y, button, pressed):
                if not self._armed or not pressed:
                    return  # keep listening
                try:
                    from pynput.mouse import Button
                    btn_str = str(button).lower()
                    # Skip left/right — they are either for arming/cancelling or blacklisted
                    if button == Button.left or button == Button.right:
                        return  # keep listening
                    if 'x1' in btn_str:
                        mouse_name = 'Mouse4'
                    elif 'x2' in btn_str:
                        mouse_name = 'Mouse5'
                    elif button == Button.middle:
                        mouse_name = 'Middle'
                    else:
                        mouse_name = str(button)
                    if mouse_name:
                        held = list(sorted(self._held_modifiers))
                        QTimer.singleShot(0, lambda mn=mouse_name, hm=held: self._emit_combo(mn, hm))
                        return False  # stop listener
                except Exception:
                    pass
                return None  # keep listening

            self._kb_listener = keyboard.Listener(
                on_press=on_key_press,
                on_release=on_key_release,
            )
            self._kb_listener.daemon = True
            self._kb_listener.start()

            self._mouse_listener = mouse.Listener(on_click=on_mouse_click)
            self._mouse_listener.daemon = True
            self._mouse_listener.start()

        except ImportError:
            pass  # fall back to Qt keyPressEvent

    def _disarm_capture(self):
        """Stop capturing and clean up listeners."""
        self._armed = False
        self._held_modifiers = set()
        self._arm_timer.stop()
        self.setPlaceholderText("Click here, then press key or mouse button…")
        self._highlight(False)

        if self._kb_listener:
            try:
                self._kb_listener.stop()
            except Exception:
                pass
            self._kb_listener = None

        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
            self._mouse_listener = None

    def _extract_key_name_from_pynput(self, key) -> Optional[str]:
        """Extract a display-style key name from a pynput key object."""
        try:
            from pynput.keyboard import Key as _PKey, KeyCode as _PKCode
            if isinstance(key, _PKey):
                key_str = str(key).lower()
                if key_str.startswith('key.f'):
                    suffix = key_str.replace('key.f', '')
                    if suffix.isdigit():
                        return f"F{suffix}"
                _special = {
                    'key.delete': 'Del', 'key.insert': 'Ins',
                    'key.home': 'Home', 'key.end': 'End',
                    'key.page_up': 'PgUp', 'key.page_down': 'PgDown',
                    'key.backspace': 'Backspace', 'key.tab': 'Tab',
                    'key.space': 'Space', 'key.enter': 'Return',
                    'key.num_lock': 'Num Lock',
                }
                return _special.get(key_str)
            elif isinstance(key, _PKCode):
                if key.char:
                    c = key.char
                    # When Ctrl is held, pynput reports control chars 0x01-0x1A
                    # (Ctrl+A=\x01 ... Ctrl+Z=\x1A).  Decode back to the letter.
                    if len(c) == 1 and 1 <= ord(c) <= 26:
                        return chr(ord(c) + 64)  # \x01->A, \x02->B, etc.
                    return c.upper()
                elif hasattr(key, 'vk') and key.vk is not None:
                    # Fallback: virtual-key code
                    if 65 <= key.vk <= 90:   # A-Z
                        return chr(key.vk)
                    if 48 <= key.vk <= 57:   # 0-9
                        return chr(key.vk)
        except Exception:
            pass
        return None

    def _emit_combo(self, key_name: str, held_mods: list = None):
        """Build and emit the final combo string.  Must run on the Qt main thread."""
        if not self._armed:
            return  # already captured/disarmed; guard against pynput+Qt double-fire
        if held_mods is None:
            held_mods = sorted(self._held_modifiers)
        parts = held_mods + [key_name]
        combo = "+".join(parts)
        # Silently reject system shortcuts and plain left/right clicks
        if combo in self._BLACKLISTED:
            self._disarm_capture()
            return
        self.setText(combo)
        self.combo_captured.emit(combo)
        self._disarm_capture()

    def keyPressEvent(self, event):
        # Fallback for when pynput is not available
        if not self._armed:
            super().keyPressEvent(event)
            return
        key = event.key()
        if key in (Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta):
            return  # Wait for a non-modifier key
        if key == Qt.Key_Escape:
            self._disarm_capture()
            return
        mods = event.modifiers()
        parts = []
        if mods & Qt.ControlModifier:
            parts.append("Ctrl")
        if mods & Qt.AltModifier:
            parts.append("Alt")
        if mods & Qt.ShiftModifier:
            parts.append("Shift")
        key_name = QKeySequence(key).toString()
        if key_name:
            self._emit_combo(key_name, parts)  # routes through blacklist check

    def _highlight(self, active: bool):
        if active:
            self.setStyleSheet("border: 2px solid #4CC9F0; color: #4CC9F0;")
        else:
            self.setStyleSheet("")


# ============================
# MAIN WINDOW
# ============================

class MainWindow(QMainWindow):
    hotkey_triggered = Signal(str)
    emergency_stop_signal = Signal()  # emitted from pynput thread; connected to stop_macro on main thread
    purge_signal = Signal()           # emitted from pynput thread; triggers immediate process kill

    def __init__(self):
        logger.info("MainWindow.__init__ started")
        super().__init__()
        logger.info("QMainWindow super().__init__() complete")
        
        # Prevent ANY visual flash during initialization
        self.setAttribute(Qt.WA_DontShowOnScreen, True)
        self.setWindowOpacity(0.0)  # Completely invisible during init
        self._apply_windows_dark_title_bar()  # pre-apply while hidden so first show is already dark
        
        self.setWindowTitle(f"🦥 Sloth v{APP_VERSION}")
        self.setGeometry(100, 100, 1400, 900)
        
        # Set window icon from GitHub download or cache
        icon = get_cached_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
            QApplication.instance().setWindowIcon(icon)
            logger.info("Window icon set from embedded data")
        else:
            logger.warning("Failed to set window icon")
        
        logger.info("Window title and geometry set")
        
        # Initialize QSettings for persistence
        self.settings = QSettings("SlothMacro", "Sloth")
        self.hotkey_listener = None
        self.mouse_hotkey_listener = None
        self.hotkey_bindings: Dict[str, bool] = {}
        self._hotkey_last_trigger: Dict[str, float] = {}
        self._hotkey_lock = threading.Lock()
        self._held_modifiers: set = set()   # modifier keys currently held (written only by pynput thread)
        
        # Initialize helpers
        self.current_theme = self.settings.value("theme", "midnight")  # Load saved theme or default to 'midnight'
        logger.info(f"Loaded theme from settings: {self.current_theme}")
        
        logger.info("Initializing BackupManager...")
        self.backup_manager = BackupManager()
        self.backup_manager.start_auto_backup(360)  # auto-backup every 6 hours
        logger.info("Initializing AFKDetector...")
        self.afk_detector = AFKDetector(timeout_seconds=300)
        logger.info("Initializing MacroRecorder...")
        self.macro_recorder = MacroRecorder()
        logger.info("All helpers initialized")
        
        # Central widget with sidebar
        logger.info("Creating central widget and layout...")
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Sidebar
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 20, 10, 20)
        sidebar_layout.setSpacing(8)
        
        # Logo
        self.logo = QLabel("🦥 Sloth")
        self.logo.setObjectName("AppLogo")
        self.logo.setStyleSheet("font-size: 24px; font-weight: bold; padding: 10px;")
        sidebar_layout.addWidget(self.logo)
        
        # Version
        version = QLabel("Sloth")
        version.setStyleSheet("font-size: 11px; color: #666; padding-left: 10px; margin-bottom: 20px;")
        sidebar_layout.addWidget(version)
        
        # Navigation buttons
        self.nav_buttons = {}
        nav_items = [
            ("🏠 Home", "home"),
            ("📋 Profile Manager", "profiles"),
            ("⚙️ Macro Editor", "editor"),
            ("🔧 Settings", "settings"),
        ]
        
        self.nav_group = QButtonGroup(self)
        
        for text, page_id in nav_items:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setProperty("page", page_id)
            btn.clicked.connect(lambda checked, p=page_id: self.switch_page(p))
            sidebar_layout.addWidget(btn)
            self.nav_buttons[page_id] = btn
            self.nav_group.addButton(btn)
        
        sidebar_layout.addSpacing(20)
        
        # Floating toolbar button
        toolbar_btn = QPushButton("📦 Show Toolbar")
        toolbar_btn.setToolTip("Show the floating macro toolbar")
        toolbar_btn.clicked.connect(self.show_macro_toolbar)
        toolbar_btn.setIcon(QIcon())  # No icon
        sidebar_layout.addWidget(toolbar_btn)

        sidebar_layout.addStretch()

        support_btn = QPushButton("☕ Support Me")
        support_btn.setToolTip("Buy Me a Coffee")
        support_btn.setStyleSheet("font-size: 11px; color: #777; padding: 4px 8px;")
        support_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://buymeacoffee.com/orvlyn")))
        sidebar_layout.addWidget(support_btn)

        site_btn = QPushButton("🌐 orvlyn.me")
        site_btn.setToolTip("Open website")
        site_btn.setStyleSheet("font-size: 11px; color: #777; padding: 4px 8px;")
        site_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://orvlyn.me")))
        sidebar_layout.addWidget(site_btn)
        
        # Content area
        self.content_stack = QStackedWidget()
        
        # Create pages
        logger.info("Creating pages...")
        self.pages = {}
        try:
            logger.info("Creating home page...")
            # Load current theme from settings
            current_theme = self.settings.value("theme", "midnight")
            self.home_page = HomePage(current_theme)
            logger.info("Creating profile manager page...")
            self.profile_page = ProfileManagerPage()
            logger.info("Creating editor page...")
            self.editor_page = MacroEditorPage()
            logger.info("Creating settings page...")
            self.settings_page = self._create_settings_page()
            logger.info("All pages created successfully")
        except Exception as e:
            logger.error(f"Error creating pages: {e}", exc_info=True)
            raise
        
        self.pages["home"] = self.home_page
        self.pages["profiles"] = self.profile_page
        self.pages["editor"] = self.editor_page
        self.pages["settings"] = self.settings_page
        
        logger.info("Adding pages to stack...")
        for page in self.pages.values():
            self.content_stack.addWidget(page)
        
        # Connect profile manager to editor
        self.profile_page.profile_selected.connect(self.editor_page.load_profile)
        self.hotkey_triggered.connect(self._run_profile_for_hotkey)
        self.emergency_stop_signal.connect(self.editor_page.stop_macro)
        self.purge_signal.connect(self.purge_sloth_processes_and_exit)
        
        logger.info("Adding widgets to main layout...")
        main_layout.addWidget(sidebar)
        main_layout.addWidget(self.content_stack, 1)
        
        # Status bar with mouse position tracker
        self.status_bar = self.statusBar()
        self.mouse_tracker = MousePositionTracker()
        self.mouse_tracker.start()
        self.status_bar.addPermanentWidget(self.mouse_tracker)
        
        # Set home as default
        self.switch_page("home")
        self.nav_buttons["home"].setChecked(True)

        # Initialize theme description
        if hasattr(self, 'theme_desc'):
            self.update_theme_description()

        # Floating toolbar is created lazily on first use (reduces startup flash)
        self.macro_toolbar = None
        
        # Store desired opacity for later
        saved_opacity = self.settings.value("window_opacity", 100)
        try:
            saved_opacity = int(saved_opacity)
        except Exception:
            saved_opacity = 100
        self._target_opacity = max(0.3, min(1.0, saved_opacity / 100.0))
        
        # Apply theme (while invisible)
        self.apply_theme(self.current_theme)
        
        # Apply always-on-top setting if saved
        always_on_top = self.settings.value("always_on_top", False)
        if isinstance(always_on_top, str):
            always_on_top = always_on_top.lower() == 'true'
        self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(always_on_top))

        self.start_hotkey_listener()
        QTimer.singleShot(200, self._delayed_show)  # Show after full initialization (reduce flash)
        
        logger.info("MainWindow.__init__ completed successfully")
    
    def _delayed_show(self):
        """Show window after initialization completes to avoid startup flash."""
        self.setAttribute(Qt.WA_DontShowOnScreen, False)
        # Re-read theme from settings and re-apply - ensures correct theme even if something
        # during init accidentally reset current_theme back to 'midnight'.
        saved_theme = self.settings.value("theme", "midnight")
        self.apply_theme(saved_theme)
        self._apply_windows_dark_title_bar()  # apply before show to prevent white title bar flash
        self.setWindowOpacity(self._target_opacity)
        self.show()
        logger.info("Window displayed after full initialization")
        # Check for updates in background - non-blocking, never delays startup
        def _on_update_found(version, url):
            QTimer.singleShot(0, lambda: self.home_page.show_update_banner(version, url))
        threading.Thread(
            target=_check_for_updates, args=(_on_update_found,), daemon=True
        ).start()
    
    def get_theme_color(self, color_key='accent'):
        """Get current theme color by key."""
        theme = THEMES.get(self.current_theme, THEMES['midnight'])
        return theme.get(color_key, '#FF006E')

    def ensure_macro_toolbar(self):
        """Create floating toolbar on first use, applying the saved theme immediately."""
        if self.macro_toolbar is None:
            self.macro_toolbar = FloatingMacroToolbar(main_window_ref=self)
            self.macro_toolbar.hide()
            self.macro_toolbar.stop_requested.connect(self.editor_page.stop_macro)
            self.macro_toolbar.pause_toggled.connect(self.editor_page.set_execution_paused)
            # Read theme directly from settings so we get the correct theme even if
            # self.current_theme was somehow reset during startup.
            tn = self.settings.value("theme", "midnight")
            self.macro_toolbar.apply_toolbar_theme(_resolve_theme(tn, self.settings))
        return self.macro_toolbar

    def show_macro_toolbar(self):
        """Open floating toolbar and bring it to front."""
        toolbar = self.ensure_macro_toolbar()
        # Always re-sync theme from settings - most authoritative source
        tn = self.settings.value("theme", "midnight")
        toolbar.apply_toolbar_theme(_resolve_theme(tn, self.settings))
        toolbar.show()
        toolbar.raise_()
        toolbar.activateWindow()
    
    def update_purge_hotkey(self):
        """No-op: purge hotkey is read directly from QSettings in _on_global_key_press."""
        pass

    def _populate_monitor_combo(self):
        """Refresh monitor dropdown labels."""
        if not hasattr(self, 'monitor_combo'):
            return
        self.monitor_combo.blockSignals(True)
        self.monitor_combo.clear()
        for index, screen in enumerate(QApplication.screens()):
            self.monitor_combo.addItem(monitor_display_label(index, screen), index)
        self.monitor_combo.blockSignals(False)

    def set_preferred_monitor(self, index: int):
        """Persist preferred monitor index."""
        self.settings.setValue("preferred_monitor", int(index))

    def restore_to_preferred_monitor(self):
        """Move the window to the preferred monitor center if available."""
        screens = QApplication.screens()
        if not screens:
            return

        saved_monitor = self.settings.value("preferred_monitor", 0)
        try:
            saved_monitor = int(saved_monitor)
        except Exception:
            saved_monitor = 0
        monitor_index = max(0, min(saved_monitor, len(screens) - 1))
        target_geo = screens[monitor_index].availableGeometry()

        frame_geo = self.frameGeometry()
        frame_geo.moveCenter(target_geo.center())
        self.move(frame_geo.topLeft())

    def _apply_windows_dark_title_bar(self):
        """Attempt to force dark native title bar on Windows 10/11."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            hwnd = int(self.winId())
            value = ctypes.c_int(1)
            for attr in (20, 19):
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    ctypes.c_void_p(hwnd),
                    ctypes.c_uint(attr),
                    ctypes.byref(value),
                    ctypes.sizeof(value)
                )
                if result == 0:
                    break
        except Exception:
            pass
    
    def _create_settings_page(self) -> CardPage:
        """Create settings page."""
        page = CardPage("Settings")
        
        # Header
        title = QLabel("Settings")
        title.setStyleSheet("font-size: 28px; font-weight: bold; margin-bottom: 25px;")
        page.card_layout.addWidget(title)
        
        # Documentation Section
        doc_section = QGroupBox("Documentation & Help")
        doc_layout = QVBoxLayout(doc_section)
        
        help_btn = QPushButton("📖 Open Complete Help Guide")
        help_btn.setMinimumHeight(50)
        help_btn.setStyleSheet("font-size: 13px; font-weight: bold;")
        help_btn.clicked.connect(self.open_help_dialog)
        doc_layout.addWidget(help_btn)
        
        help_desc = QLabel("Guides, action reference, game examples and troubleshooting")
        help_desc.setStyleSheet("font-size: 11px; color: #A0A0A0; margin-top: -5px;")
        doc_layout.addWidget(help_desc)
        
        page.card_layout.addWidget(doc_section)
        
        # Theme Section
        theme_group = QGroupBox("Appearance & Theme")
        theme_layout = QVBoxLayout(theme_group)
        
        theme_label = QLabel("Choose your theme:")
        theme_label.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        self.theme_combo = NoWheelComboBox()
        theme_names = [THEMES[key]['name'] for key in THEMES.keys()]
        self.theme_combo.addItems(theme_names)
        
        # Set current theme to saved setting - block signals so no spurious change_theme(0) fires
        saved_theme = self.settings.value("theme", "midnight")
        theme_keys = list(THEMES.keys())
        self.theme_combo.blockSignals(True)
        if saved_theme in theme_keys:
            self.theme_combo.setCurrentIndex(theme_keys.index(saved_theme))
        self.theme_combo.blockSignals(False)

        self.theme_combo.currentIndexChanged.connect(self.change_theme)
        theme_layout.addWidget(theme_label)
        theme_layout.addWidget(self.theme_combo)

        # "Configure" button - only visible when custom is selected
        self.configure_custom_btn = QPushButton("🎨 Configure Custom Theme...")
        self.configure_custom_btn.setToolTip("Open the custom color editor")
        self.configure_custom_btn.setMinimumHeight(34)
        self.configure_custom_btn.setStyleSheet("font-weight: bold;")
        self.configure_custom_btn.clicked.connect(self.open_custom_theme_dialog)
        self.configure_custom_btn.setVisible(saved_theme == 'custom')
        theme_layout.addWidget(self.configure_custom_btn)

        # Show theme description
        self.theme_desc = QLabel()
        self.theme_desc.setStyleSheet("font-size: 11px; color: #A0A0A0; margin-top: 8px; font-style: italic; padding: 8px; background: #0B0F15; border-radius: 4px;")
        self.theme_desc.setWordWrap(True)
        self.theme_combo.currentIndexChanged.connect(self.update_theme_description)
        theme_layout.addWidget(self.theme_desc)

        page.card_layout.addWidget(theme_group)
        
        # Window Section
        window_group = QGroupBox("Window Behavior")
        window_layout = QVBoxLayout(window_group)
        
        # Transparency
        trans_label = QLabel("Window Opacity:")
        trans_label.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        window_layout.addWidget(trans_label)
        
        trans_slider_row = QHBoxLayout()
        self.transparency_slider = NoWheelSlider(Qt.Horizontal)
        self.transparency_slider.setRange(30, 100)
        saved_opacity = self.settings.value("window_opacity", 100)
        try:
            saved_opacity = int(saved_opacity)
        except Exception:
            saved_opacity = 100
        self.transparency_slider.setValue(max(30, min(100, saved_opacity)))
        self.transparency_slider.setTickPosition(QSlider.TicksBelow)
        self.transparency_slider.setTickInterval(10)
        self.transparency_slider.valueChanged.connect(self.update_transparency)
        trans_slider_row.addWidget(QLabel("Transparent"))
        trans_slider_row.addWidget(self.transparency_slider)
        self.transparency_value = QLabel(f"{self.transparency_slider.value()}%")
        self.transparency_value.setStyleSheet("min-width: 40px; font-weight: bold;")
        trans_slider_row.addWidget(self.transparency_value)
        window_layout.addLayout(trans_slider_row)
        
        trans_tip = QLabel("Lower opacity = see game behind window (useful while playing)")
        trans_tip.setStyleSheet("font-size: 11px; color: #A0A0A0; margin-top: 8px; font-style: italic;")
        window_layout.addWidget(trans_tip)
        
        # Always on top
        self.always_on_top_check = QCheckBox("Keep window always on top")
        self.always_on_top_check.setToolTip("Keep Sloth visible above other windows")
        always_on_top_saved = self.settings.value("always_on_top", False)
        if isinstance(always_on_top_saved, str):
            always_on_top_saved = always_on_top_saved.lower() == 'true'
        self.always_on_top_check.setChecked(always_on_top_saved)
        self.always_on_top_check.toggled.connect(self.set_always_on_top)
        window_layout.addWidget(self.always_on_top_check)

        monitor_label = QLabel("Preferred monitor:")
        monitor_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        window_layout.addWidget(monitor_label)

        self.monitor_combo = NoWheelComboBox()
        self._populate_monitor_combo()
        saved_monitor = self.settings.value("preferred_monitor", 0)
        try:
            saved_monitor = int(saved_monitor)
        except Exception:
            saved_monitor = 0
        if self.monitor_combo.count() > 0:
            saved_monitor = max(0, min(saved_monitor, self.monitor_combo.count() - 1))
            self.monitor_combo.setCurrentIndex(saved_monitor)
        self.monitor_combo.currentIndexChanged.connect(self.set_preferred_monitor)
        window_layout.addWidget(self.monitor_combo)

        move_window_btn = QPushButton("Move Sloth to selected monitor")
        move_window_btn.clicked.connect(self.restore_to_preferred_monitor)
        window_layout.addWidget(move_window_btn)

        monitor_tip = QLabel("Coordinate and region pickers now span all connected displays.")
        monitor_tip.setStyleSheet("font-size: 11px; color: #A0A0A0; margin-top: 6px; font-style: italic;")
        monitor_tip.setWordWrap(True)
        window_layout.addWidget(monitor_tip)
        
        page.card_layout.addWidget(window_group)
        
        # Safety Features Section
        safety_group = QGroupBox("Safety & Protection")
        safety_layout = QVBoxLayout(safety_group)
        
        afk_desc = QLabel("Automatic AFK Detection stops your macro if inactivity is detected.")
        afk_desc.setStyleSheet("font-size: 11px; color: #A0A0A0; margin-bottom: 10px;")
        safety_layout.addWidget(afk_desc)
        
        self.afk_enabled_check = QCheckBox("Enable AFK Detection")
        self.afk_enabled_check.setToolTip("Stop macro if no input detected (safer for online games)")
        self.afk_enabled_check.setChecked(self.settings.value("afk_enabled", False, type=bool))
        def _on_afk_toggled(enabled):
            self.afk_detector.set_enabled(enabled)
            self.settings.setValue("afk_enabled", enabled)
        self.afk_enabled_check.toggled.connect(_on_afk_toggled)
        safety_layout.addWidget(self.afk_enabled_check)
        
        afk_timeout_layout = QHBoxLayout()
        afk_timeout_layout.addWidget(QLabel("Timeout:"  ))
        self.afk_timeout_spin = NoWheelSpinBox()
        self.afk_timeout_spin.setRange(1, 60)
        _saved_afk_mins = self.settings.value("afk_timeout_minutes", 5, type=int)
        self.afk_timeout_spin.setValue(max(1, min(60, _saved_afk_mins)))
        self.afk_timeout_spin.setSuffix(" minutes")
        def _on_afk_timeout_changed(mins):
            self.afk_detector.set_timeout(mins * 60)
            self.settings.setValue("afk_timeout_minutes", mins)
        self.afk_timeout_spin.valueChanged.connect(_on_afk_timeout_changed)
        self.afk_detector.set_timeout(max(1, min(60, _saved_afk_mins)) * 60)
        afk_timeout_layout.addWidget(self.afk_timeout_spin)
        afk_timeout_layout.addStretch()
        safety_layout.addLayout(afk_timeout_layout)

        estop_lbl = QLabel("Emergency stop key:")
        estop_lbl.setStyleSheet("font-weight: bold; margin-top: 8px;")
        safety_layout.addWidget(estop_lbl)
        estop_row = QHBoxLayout()
        self.emergency_stop_combo = NoWheelComboBox()
        self.emergency_stop_combo.addItems(["None", "F8", "F9", "F10", "F11", "F12"])
        _saved_estop = self.settings.value("emergency_stop_key", "F12")
        _estop_idx = self.emergency_stop_combo.findText(_saved_estop)
        self.emergency_stop_combo.setCurrentIndex(_estop_idx if _estop_idx >= 0 else self.emergency_stop_combo.findText("F12"))
        def _on_estop_changed():
            self.settings.setValue("emergency_stop_key", self.emergency_stop_combo.currentText())
        self.emergency_stop_combo.currentIndexChanged.connect(_on_estop_changed)
        estop_row.addWidget(self.emergency_stop_combo)
        estop_row.addStretch()
        safety_layout.addLayout(estop_row)
        estop_tip = QLabel("Instantly stops any running macro from anywhere (no need to alt-tab).")
        estop_tip.setStyleSheet("font-size: 11px; color: #A0A0A0; font-style: italic;")
        estop_tip.setWordWrap(True)
        safety_layout.addWidget(estop_tip)

        purge_lbl = QLabel("Purge hotkey:")
        purge_lbl.setStyleSheet("font-weight: bold; margin-top: 8px;")
        safety_layout.addWidget(purge_lbl)
        purge_row = QHBoxLayout()
        self.purge_hotkey_edit = KeyCaptureEdit()
        self.purge_hotkey_edit.setMinimumWidth(180)
        _saved_purge = self.settings.value("purge_hotkey", "None")
        if _saved_purge and _saved_purge != "None":
            self.purge_hotkey_edit.setText(_saved_purge)
        def _on_purge_captured(combo):
            self.settings.setValue("purge_hotkey", combo)
        self.purge_hotkey_edit.combo_captured.connect(_on_purge_captured)
        purge_row.addWidget(self.purge_hotkey_edit)
        purge_clear_btn = QPushButton("\u2715 Clear")
        purge_clear_btn.setMinimumWidth(90)
        def _clear_purge():
            self.purge_hotkey_edit.clear()
            self.settings.setValue("purge_hotkey", "None")
        purge_clear_btn.clicked.connect(_clear_purge)
        purge_row.addWidget(purge_clear_btn)
        purge_row.addStretch()
        safety_layout.addLayout(purge_row)
        purge_tip = QLabel("Immediately kills all Sloth processes. Useful when inputs/macros get stuck. Works from any app.")
        purge_tip.setStyleSheet("font-size: 11px; color: #A0A0A0; font-style: italic;")
        purge_tip.setWordWrap(True)
        safety_layout.addWidget(purge_tip)

        page.card_layout.addWidget(safety_group)
        
        # Data Management Section
        data_group = QGroupBox("Data & Backups")
        data_layout = QVBoxLayout(data_group)
        
        backup_desc = QLabel("Automatic backups are created every 6 hours. Create a manual backup anytime.")
        backup_desc.setStyleSheet("font-size: 11px; color: #A0A0A0; margin-bottom: 10px;")
        data_layout.addWidget(backup_desc)
        
        backup_btn_layout = QHBoxLayout()
        create_backup_btn = QPushButton("💾 Create Backup Now")
        create_backup_btn.setMinimumHeight(40)
        create_backup_btn.clicked.connect(self.create_backup_now)
        backup_btn_layout.addWidget(create_backup_btn)
        backup_btn_layout.addStretch()
        data_layout.addLayout(backup_btn_layout)
        
        self.backup_status_label = QLabel()
        self._refresh_backup_status_label()
        self.backup_status_label.setStyleSheet("font-size: 11px; color: #A0A0A0; padding: 8px; background: #0B0F15; border-radius: 4px;")
        data_layout.addWidget(self.backup_status_label)

        restore_btn = QPushButton("Restore from Backup")
        restore_btn.setMinimumHeight(36)
        restore_btn.clicked.connect(self.restore_from_backup)
        data_layout.addWidget(restore_btn)

        page.card_layout.addWidget(data_group)
        
        # Hotkey settings
        hotkey_group = QGroupBox("Hotkeys")
        hotkey_layout = QVBoxLayout(hotkey_group)

        hotkey_info = QLabel("Global hotkeys are configured per profile in Profile Manager")
        hotkey_info.setStyleSheet("font-size: 12px; color: #A0A0A0;")
        hotkey_info.setWordWrap(True)
        hotkey_layout.addWidget(hotkey_info)

        page.card_layout.addWidget(hotkey_group)
        
        # Runtime Environment
        deps_group = QGroupBox("Runtime Environment")
        deps_layout = QVBoxLayout(deps_group)

        ocr_bundle_status = QLabel(
            "OCR (Skill Check): " +
            ("✅ Found ./teseract/tesseract.exe or ./tesseract/tesseract.exe" if TESSERACT_AVAILABLE else "❌ Missing OCR executable in expected local folders")
        )
        ocr_bundle_status.setStyleSheet("font-size: 11px; color: #A0A0A0; padding: 8px; background: #0B0F15; border-radius: 4px;")
        ocr_bundle_status.setWordWrap(True)
        deps_layout.addWidget(ocr_bundle_status)

        runtime_info = QLabel(
            "Tesseract OCR is not bundled and must be user-installed.\n"
            "Install tesseract.exe in ./teseract/ or ./tesseract/ next to Sloth.\n"
            "If running from source, also ensure required Python packages are installed."
        )
        runtime_info.setStyleSheet("font-size: 12px; color: #A0A0A0; margin-top: 10px;")
        runtime_info.setWordWrap(True)
        deps_layout.addWidget(runtime_info)
        page.card_layout.addWidget(deps_group)
        
        # About
        about_group = QGroupBox("About")
        about_layout = QVBoxLayout(about_group)
        
        about_text = QLabel(
            "<html><body style='font-size:12px; color:#A0A0A0; line-height:1.6;'>"
            f"<b>Sloth</b><br>"
            f"v{APP_VERSION}<br><br>"
            "<b>Features:</b><br>"
            "&bull; Profile-based macro management<br>"
            "&bull; Keyboard and mouse automation<br>"
            "&bull; Visual action sequence builder<br>"
            "&bull; Loop and conditional support<br>"
            "&bull; Pixel and image detection<br>"
            "&bull; Randomized timing so delays are never identical<br><br>"
            "<b>Support &amp; Links:</b><br>"
            "&bull; X / Twitter: <a href='https://x.com/Orvlyn' style='color:#6CB4F0;'>@Orvlyn</a><br>"
            "&bull; Discord: Orvlyn<br>"
            "&bull; Website: <a href='https://orvlyn.me' style='color:#6CB4F0;'>orvlyn.me</a><br>"
            "&bull; BuyMeACoffee: <a href='https://buymeacoffee.com/orvlyn' style='color:#6CB4F0;'>buymeacoffee.com/orvlyn</a>"
            "</body></html>"
        )
        about_text.setStyleSheet("font-size: 12px; color: #A0A0A0;")
        about_text.setWordWrap(True)
        about_text.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        about_text.setOpenExternalLinks(True)
        about_layout.addWidget(about_text)

        check_update_btn = QPushButton("Check for Updates")
        check_update_btn.setMaximumWidth(180)
        check_update_btn.clicked.connect(self._manual_check_for_updates)
        about_layout.addWidget(check_update_btn)

        page.card_layout.addWidget(about_group)
        page.card_layout.addStretch()

        return page

    def _manual_check_for_updates(self):
        """Manually check for updates and show a dialog with the result."""
        btn = self.sender()
        if btn:
            btn.setEnabled(False)
            btn.setText("Checking\u2026")

        # result[0]: 'update' | 'uptodate' | 'error'
        # result[1]: version string or error message
        # result[2]: url (only for 'update')
        result = [None, None, None]

        def _run():
            try:
                import urllib.request
                import json as _json
                with urllib.request.urlopen(UPDATE_CHECK_URL, timeout=6) as resp:
                    data = _json.loads(resp.read().decode())
                latest = data.get("version", "")
                url = data.get("url", "")
                if latest and latest != APP_VERSION:
                    result[:] = ['update', latest, url]
                else:
                    result[:] = ['uptodate', None, None]
            except Exception as e:
                logger.debug(f"Manual update check failed: {e}")
                result[:] = ['error', str(e), None]

            # 3-arg form: posts _finish to self's thread (main thread) safely
            QTimer.singleShot(0, self, _finish)

        def _finish():
            if btn:
                btn.setEnabled(True)
                btn.setText("Check for Updates")

            state = result[0]
            if state == 'update':
                version, url = result[1], result[2]
                self.home_page.show_update_banner(version, url)
                msg = QMessageBox(self)
                msg.setWindowTitle("Update Available")
                msg.setText(f"Sloth v{version} is available.\nClick OK to open the download page.")
                msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
                if msg.exec() == QMessageBox.Ok:
                    QDesktopServices.openUrl(QUrl(url))
            elif state == 'uptodate':
                QMessageBox.information(
                    self, "Up to Date",
                    f"You're already on the latest version (v{APP_VERSION})."
                )
            else:
                QMessageBox.warning(
                    self, "Couldn't Check for Updates",
                    "Couldn't reach the update server.\nCheck your internet connection and try again."
                )

        threading.Thread(target=_run, daemon=True).start()

    def purge_sloth_processes_and_exit(self):
        logger.info("PURGE INITIATED: Closing all Sloth processes")
        try:
            ps_script = (
                "Start-Sleep -Milliseconds 700; "
                "$procs = Get-CimInstance Win32_Process | Where-Object { "
                "($_.Name -ieq 'Sloth.exe') -or ((($_.Name -ieq 'python.exe') -or ($_.Name -ieq 'pythonw.exe')) -and ($_.CommandLine -match 'Sloth\\.py')) }; "
                "$procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                creationflags=0x08000000
            )
        except Exception as e:
            logger.warning(f"Failed to spawn purge helper: {e}")
        finally:
            # Close the window first, then quit the application
            self.close()
            QApplication.quit()

    def _load_all_profiles(self) -> List[MacroProfile]:
        """Load all profiles from disk, using a mod-time cache to avoid repeated reads."""
        if not hasattr(self, '_profile_cache'):
            self._profile_cache: Dict[str, tuple] = {}  # filepath -> (mtime, profile)
        profiles_dir = os.path.join(get_base_dir(), "profiles")
        if not os.path.exists(profiles_dir):
            return []
        profiles = []
        current_files = set()
        for filename in os.listdir(profiles_dir):
            if not filename.endswith('.json'):
                continue
            filepath = os.path.join(profiles_dir, filename)
            current_files.add(filepath)
            try:
                mtime = os.path.getmtime(filepath)
                cached = self._profile_cache.get(filepath)
                if cached and cached[0] == mtime:
                    profiles.append(cached[1])
                else:
                    p = MacroProfile.load_from_file(filepath)
                    self._profile_cache[filepath] = (mtime, p)
                    profiles.append(p)
            except Exception as e:
                logger.error(f"Failed to load profile {filename}: {e}")
        # Evict deleted files from cache
        for stale in list(self._profile_cache.keys()):
            if stale not in current_files:
                del self._profile_cache[stale]
        return profiles

    def start_hotkey_listener(self):
        """Start global hotkey listener from saved profiles."""
        try:
            from pynput import keyboard, mouse
        except ImportError:
            logger.warning("pynput not installed - global hotkeys disabled")
            return

        hotkeys = set()
        # Collect all hotkey strings (e.g., "F5", "Ctrl+F8", "Mouse4", etc.)
        for profile in self._load_all_profiles():
            if profile.hotkey and profile.hotkey != "None" and profile.actions:
                key = profile.hotkey.strip()
                if key:
                    hotkeys.add(key)

        if self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
            except Exception:
                pass
            self.hotkey_listener = None

        if self.mouse_hotkey_listener:
            try:
                self.mouse_hotkey_listener.stop()
            except Exception:
                pass
            self.mouse_hotkey_listener = None

        self.hotkey_bindings = {h: True for h in sorted(hotkeys)}
        
        # Start keyboard listener
        self.hotkey_listener = keyboard.Listener(
            on_press=self._on_global_key_press,
            on_release=self._on_global_key_release
        )
        self.hotkey_listener.daemon = True
        self.hotkey_listener.start()
        
        # Start mouse listener for mouse button hotkeys
        self.mouse_hotkey_listener = mouse.Listener(
            on_click=self._on_global_mouse_click
        )
        self.mouse_hotkey_listener.daemon = True
        self.mouse_hotkey_listener.start()
        
        if self.hotkey_bindings:
            logger.info(f"Global hotkeys started: {', '.join(self.hotkey_bindings.keys())}")
        else:
            logger.info("Global hotkey listener started (no profile hotkeys configured)")

    def _extract_key_name(self, key) -> Optional[str]:
        """Extract a display-style key name from a pynput key for hotkey matching.
        Covers F-keys, common special keys, and character keys (A-Z, 0-9).
        Returns a string like 'F9', 'Del', 'A', '5', etc. or None."""
        try:
            from pynput.keyboard import Key as _PKey, KeyCode as _PKCode
            if isinstance(key, _PKey):
                key_str = str(key).lower()
                if key_str.startswith('key.f'):
                    suffix = key_str.replace('key.f', '')
                    if suffix.isdigit() and 1 <= int(suffix) <= 24:
                        return f"F{int(suffix)}"
                _special = {
                    'key.delete': 'Del', 'key.insert': 'Ins',
                    'key.home': 'Home', 'key.end': 'End',
                    'key.page_up': 'PgUp', 'key.page_down': 'PgDown',
                    'key.backspace': 'Backspace', 'key.tab': 'Tab',
                    'key.space': 'Space', 'key.esc': 'Esc', 'key.escape': 'Esc',
                    'key.enter': 'Return', 'key.num_lock': 'Num Lock',
                }
                return _special.get(key_str)
            elif isinstance(key, _PKCode):
                if key.char:
                    c = key.char
                    # When Ctrl is held, pynput reports control chars 0x01-0x1A
                    # (Ctrl+A=\x01 ... Ctrl+Z=\x1A).  Decode back to the letter.
                    if len(c) == 1 and 1 <= ord(c) <= 26:
                        return chr(ord(c) + 64)  # \x01->A, \x02->B, etc.
                    return c.upper()
                elif hasattr(key, 'vk') and key.vk is not None:
                    # Fallback: use virtual-key code for keys where .char is None
                    if 65 <= key.vk <= 90:   # A-Z
                        return chr(key.vk)
                    if 48 <= key.vk <= 57:   # 0-9
                        return chr(key.vk)
        except Exception:
            pass
        return None

    def _on_global_key_press(self, key):
        """Handle global keypress events for configured profile hotkeys."""
        # Track modifier state (written only from this pynput thread)
        try:
            from pynput.keyboard import Key as _PKey
            if key in (_PKey.ctrl_l, _PKey.ctrl_r, _PKey.ctrl):
                with self._hotkey_lock:
                    self._held_modifiers.add('ctrl')
                return
            if key in (_PKey.alt_l, _PKey.alt_r, _PKey.alt):
                with self._hotkey_lock:
                    self._held_modifiers.add('alt')
                return
            if key in (_PKey.shift_l, _PKey.shift_r, _PKey.shift):
                with self._hotkey_lock:
                    self._held_modifiers.add('shift')
                return
        except Exception:
            pass

        # Extract key name for any key (F-keys, letters, numbers, special keys, etc.)
        key_name = self._extract_key_name(key)
        if not key_name:
            return
        
        # Build combo string with modifiers (thread-safe read)
        with self._hotkey_lock:
            mods = sorted(self._held_modifiers)  # deterministic: ['alt', 'ctrl', 'shift']
        combo = "+".join(m.capitalize() for m in mods) + ("+" if mods else "") + key_name
        
        # Check purge hotkey first
        purge_key = self.settings.value("purge_hotkey", "None")
        if purge_key != "None" and combo.upper() == purge_key.upper():
            logger.info(f"Purge hotkey triggered by {combo}")
            self.purge_signal.emit()
            return

        # Check emergency stop
        estop_key = self.settings.value("emergency_stop_key", "F12")
        if estop_key != "None" and combo.upper() == estop_key.upper():
            if self.editor_page.executor and self.editor_page.executor.isRunning():
                logger.info(f"Emergency stop triggered by {combo}")
                self.emergency_stop_signal.emit()  # thread-safe cross-thread stop
                return  # stop consumed the key; don't also trigger a profile
            # Macro not running - fall through so the key can trigger a profile
        
        # Check profile hotkeys - snapshot reference atomically
        bindings = self.hotkey_bindings
        if combo not in bindings:
            # Debug logging for troubleshooting
            if mods:  # Only log combos with modifiers to avoid spam
                logger.debug(f"Hotkey combo '{combo}' not in bindings. Registered: {list(bindings.keys())}")
            return
        
        # Debounce: prevent rapid repeated triggers
        with self._hotkey_lock:
            now = time.time()
            last = self._hotkey_last_trigger.get(combo, 0)
            if now - last < 0.35:
                return
            self._hotkey_last_trigger[combo] = now
        
        logger.debug(f"Hotkey triggered: {combo}")
        self.hotkey_triggered.emit(combo)

    def _on_global_key_release(self, key):
        """Clear tracked modifier key state on release."""
        try:
            from pynput.keyboard import Key as _PKey
            with self._hotkey_lock:
                if key in (_PKey.ctrl_l, _PKey.ctrl_r, _PKey.ctrl):
                    self._held_modifiers.discard('ctrl')
                elif key in (_PKey.alt_l, _PKey.alt_r, _PKey.alt):
                    self._held_modifiers.discard('alt')
                elif key in (_PKey.shift_l, _PKey.shift_r, _PKey.shift):
                    self._held_modifiers.discard('shift')
        except Exception:
            pass

    def _on_global_mouse_click(self, x, y, button, pressed):
        """Handle global mouse button events for configured profile hotkeys."""
        if not pressed:
            return  # Only trigger on button press, not release
        
        try:
            from pynput.mouse import Button
            
            # Map mouse buttons to readable names
            mouse_names = {
                Button.left: 'Left',
                Button.right: 'Right',
                Button.middle: 'Middle',
            }
            
            # Handle side buttons (Mouse4/Mouse5)
            btn_str = str(button).lower()
            if 'x1' in btn_str or 'button.x1' in btn_str:
                mouse_name = 'Mouse4'
            elif 'x2' in btn_str or 'button.x2' in btn_str:
                mouse_name = 'Mouse5'
            else:
                mouse_name = mouse_names.get(button)
            
            if not mouse_name:
                return
            
            # Build combo string with modifiers (thread-safe read)
            with self._hotkey_lock:
                mods = sorted(self._held_modifiers)
            combo = "+".join(m.capitalize() for m in mods) + ("+" if mods else "") + mouse_name
            
            # Check if this combo is a registered hotkey
            bindings = self.hotkey_bindings
            if combo not in bindings:
                return
            
            # Debounce: prevent rapid repeated triggers
            with self._hotkey_lock:
                now = time.time()
                last = self._hotkey_last_trigger.get(combo, 0)
                if now - last < 0.35:
                    return
                self._hotkey_last_trigger[combo] = now
            
            self.hotkey_triggered.emit(combo)
        except Exception as e:
            logger.debug(f"Error in mouse hotkey handler: {e}")

    def _run_profile_for_hotkey(self, hotkey: str):
        """Execute or stop profile mapped to pressed hotkey (toggle behavior)."""
        if self.editor_page.executor and self.editor_page.executor.isRunning():
            running_profile = self.editor_page.current_profile
            if running_profile and running_profile.hotkey.upper() == hotkey.upper():
                logger.info(f"Hotkey {hotkey} pressed again - stopping macro '{running_profile.name}'")
                self.editor_page.stop_macro()
                self.editor_page.exec_status.setText(f"Stopped by hotkey {hotkey}")
                return
            logger.info(f"Hotkey {hotkey} ignored - another macro is already running")
            return

        # If the editor page is the active/visible page, run the profile that is currently
        # loaded in the editor - never switch to a different profile from disk. This prevents
        # F-key presses from loading/starting a different profile that shares the same hotkey.
        editor_is_active = (self.content_stack.currentWidget() is self.pages.get("editor"))
        if editor_is_active:
            loaded = self.editor_page.current_profile
            if not loaded or loaded.hotkey.upper() != hotkey.upper():
                logger.debug(f"Hotkey {hotkey} suppressed - editor is active and hotkey belongs to a different profile")
                return
            # Hotkey matches the open profile - run it directly without touching disk
            if not loaded.actions:
                logger.info(f"Hotkey {hotkey}: editor profile '{loaded.name}' has no actions, skipping")
                return
            logger.info(f"Hotkey {hotkey} triggered editor-loaded profile '{loaded.name}'")
            self.editor_page.execute_profile(loaded, countdown_seconds=0, show_toolbar=False)
            return

        profiles = self._load_all_profiles()
        profile = next((p for p in profiles if p.hotkey.upper() == hotkey.upper() and p.actions), None)
        if not profile:
            logger.info(f"No runnable profile mapped to {hotkey}")
            return

        logger.info(f"Hotkey {hotkey} triggered profile '{profile.name}'")
        self.editor_page.execute_profile(profile, countdown_seconds=0, show_toolbar=False)

    def closeEvent(self, event):
        """Cleanup listeners on app close."""
        # Stop backup timer
        if hasattr(self, '_auto_backup_timer') and self._auto_backup_timer:
            self._auto_backup_timer.stop()
        
        try:
            if hasattr(self, 'editor_page') and self.editor_page:
                self.editor_page.save_current_profile()
                overlay = getattr(self.editor_page, '_active_overlay', None)
                if overlay:
                    try:
                        overlay.close()
                    except Exception as e:
                        logger.debug(f"Failed to close overlay: {e}")
                # Stop any running macro executor cleanly
                executor = getattr(self.editor_page, 'executor', None)
                if executor and executor.isRunning():
                    executor.stop()
                    executor.quit()
                    executor.wait(3000)
            if self.hotkey_listener:
                self.hotkey_listener.stop()
            if self.mouse_hotkey_listener:
                self.mouse_hotkey_listener.stop()
            # Close standalone toolbar (it has no Qt parent so won't close automatically)
            if hasattr(self, 'macro_toolbar') and self.macro_toolbar:
                try:
                    self.macro_toolbar.close()
                except Exception as e:
                    logger.debug(f"Failed to close toolbar: {e}")
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")
        # Ensure all settings (theme, etc.) are flushed to disk before exit
        try:
            self.settings.sync()
        except Exception as e:
            logger.warning(f"Failed to sync settings: {e}")
        super().closeEvent(event)
    
    def switch_page(self, page_id: str):
        """Switch to specified page."""
        if page_id in self.pages:
            self.content_stack.setCurrentWidget(self.pages[page_id])

    def navigate_to_page(self, page_id: str):
        """Backward-compatible navigation method used by other UI components."""
        self.switch_page(page_id)
        if hasattr(self, 'nav_buttons') and page_id in self.nav_buttons:
            self.nav_buttons[page_id].setChecked(True)
    
    def change_theme(self, index):
        """Change application theme"""
        theme_keys = list(THEMES.keys())
        if 0 <= index < len(theme_keys):
            self.current_theme = theme_keys[index]
            self.settings.setValue("theme", self.current_theme)  # Save theme preference
            logger.info(f"Theme changed to: {self.current_theme}, saved to settings")
            self.apply_theme(self.current_theme)
    
    def apply_theme(self, theme_name='midnight'):
        """Apply theme stylesheet"""
        logger.info(f"Applying theme: {theme_name}")
        self.current_theme = theme_name
        self.settings.setValue("theme", theme_name)  # Ensure it's saved
        # Resolve custom theme colors from QSettings before generating stylesheet
        theme_data = _resolve_theme(theme_name, self.settings)
        stylesheet = generate_stylesheet(theme_name, theme_override=theme_data)
        logger.info(f"Generated stylesheet length: {len(stylesheet)} characters")
        self.setStyleSheet(stylesheet)
        # Keep theme_combo in sync (block signals so change_theme doesn't re-fire)
        if hasattr(self, 'theme_combo'):
            theme_keys = list(THEMES.keys())
            if theme_name in theme_keys:
                self.theme_combo.blockSignals(True)
                self.theme_combo.setCurrentIndex(theme_keys.index(theme_name))
                self.theme_combo.blockSignals(False)
        # Show/hide the "Configure" button in Settings
        if hasattr(self, 'configure_custom_btn'):
            self.configure_custom_btn.setVisible(theme_name == 'custom')
        # Update HomePage colors to match new theme
        if hasattr(self, 'home_page') and self.home_page:
            self.home_page.update_theme(theme_name)
        # Propagate theme colors to floating toolbar if it has been created
        if hasattr(self, 'macro_toolbar') and self.macro_toolbar:
            self.macro_toolbar.apply_toolbar_theme(theme_data)
        logger.info("Theme applied successfully")
    
    def open_custom_theme_dialog(self):
        """Open the custom-theme color picker and save the result."""
        current_colors = _resolve_theme('custom', self.settings)
        dlg = CustomThemeDialog(current_colors, parent=self)
        if dlg.exec():
            colors = dlg.get_colors()
            # Persist every key under custom_theme/ in QSettings
            for k, v in colors.items():
                self.settings.setValue(f"custom_theme/{k}", v)
            self.settings.sync()
            # Re-apply so the change is visible immediately
            self.apply_theme('custom')

    def update_theme_description(self):
        """Update theme description label"""
        theme_keys = list(THEMES.keys())
        index = self.theme_combo.currentIndex()
        if 0 <= index < len(theme_keys):
            theme = THEMES[theme_keys[index]]
            self.theme_desc.setText(theme.get('description', ''))
    
    def open_help_dialog(self):
        """Open the complete help documentation in a popup dialog."""
        dialog = HelpDialog(self, theme_name=self.current_theme)
        dialog.exec()
    
    def update_transparency(self, value):
        """Update window transparency/opacity."""
        opacity = value / 100.0
        self.setWindowOpacity(opacity)
        self.transparency_value.setText(f"{value}%")
        self.settings.setValue("window_opacity", value)
    
    def set_always_on_top(self, checked):
        """Toggle always on top flag."""
        self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(checked))
        self.show()
        self._apply_windows_dark_title_bar()
        self.settings.setValue("always_on_top", checked)
        logger.info(f"Always on top: {checked}")
    
    def create_backup_now(self):
        """Create backup immediately and refresh status label."""
        backup_path, success = self.backup_manager.create_backup()
        if success:
            self._refresh_backup_status_label()
            QMessageBox.information(self, "Backup Created", f"Backup saved to: {backup_path}")
        else:
            QMessageBox.warning(self, "Backup Failed", "Failed to create backup")

    def _refresh_backup_status_label(self):
        """Update the backup status label with the most recent backup time."""
        if not hasattr(self, 'backup_status_label'):
            return
        latest = self.backup_manager.get_latest_backup_time()
        if latest:
            t = datetime.fromtimestamp(latest).strftime("%Y-%m-%d %H:%M")
            self.backup_status_label.setText(f"Last backup: {t}")
        else:
            self.backup_status_label.setText("Last backup: Never")

    def restore_from_backup(self):
        """Show a picker of available ZIP backups and restore the chosen one."""
        import zipfile
        from PySide6.QtWidgets import QInputDialog
        backup_dir = self.backup_manager.backup_dir
        zips = sorted(backup_dir.glob("backup_*.zip"), reverse=True)
        if not zips:
            QMessageBox.information(self, "No Backups", "No backups found in the backups folder.")
            return
        items = [z.name for z in zips]
        choice, ok = QInputDialog.getItem(
            self, "Restore Backup", "Select a backup to restore:", items, 0, False)
        if not ok or not choice:
            return
        zip_path = backup_dir / choice
        confirm = QMessageBox.question(
            self, "Confirm Restore",
            f"This will overwrite all current profiles with those in:\n{choice}\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            profiles_dir = self.backup_manager.profiles_dir
            safe_root = Path(profiles_dir).resolve()
            with zipfile.ZipFile(zip_path, 'r') as z:
                # Guard against ZipSlip: reject any entry that would escape profiles_dir
                for member in z.infolist():
                    dest = (safe_root / member.filename).resolve()
                    if not str(dest).startswith(str(safe_root)):
                        raise ValueError(f"Unsafe path in backup ZIP: {member.filename}")
                z.extractall(profiles_dir)
            self.profile_page.refresh_profile_list()
            self.start_hotkey_listener()
            QMessageBox.information(self, "Restore Complete", f"Profiles restored from {choice}")
        except Exception as e:
            QMessageBox.critical(self, "Restore Failed", str(e))


    def apply_dark_theme(self):
        """Apply dark theme stylesheet (deprecated - use apply_theme)"""
        self.apply_theme('midnight')

    def _dead_theme_qss_placeholder(self):
        qss = """
        QMainWindow { background: #070A0E; }
        QWidget { 
            background: #070A0E; 
            color: #E6EAF0; 
            font: 13px 'Segoe UI'; 
        }
        
        #Sidebar {
            background: #0B0F15;
            border-right: 1px solid #141A22;
        }
        
        #Sidebar QPushButton {
            background: transparent;
            border: none;
            padding: 12px;
            border-radius: 6px;
            text-align: left;
            color: #E6EAF0;
        }
        
        #Sidebar QPushButton:checked {
            background: #00FFC6;
            color: #070A0E;
            font-weight: bold;
        }
        
        #Sidebar QPushButton:hover {
            background: #141A22;
        }
        
        QWidget#Card {
            background: #0B0F15;
            border-radius: 12px;
            padding: 20px;
        }
        
        QPushButton {
            background: #0B0F15;
            border: 1px solid #141A22;
            border-radius: 8px;
            padding: 8px 12px;
            color: #E6EAF0;
        }
        
        QPushButton:hover {
            border: 1px solid #00FFC6;
            background: #141A22;
        }
        
        QPushButton:pressed {
            background: #00FFC6;
            color: #070A0E;
        }
        
        QPushButton:disabled {
            background: #0B0F15;
            border: 1px solid #0B0F15;
            color: #555;
        }
        
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {
            background: #0B0F15;
            border: 1px solid #141A22;
            border-radius: 6px;
            padding: 6px;
            color: #E6EAF0;
        }
        
        QLineEdit:focus, QTextEdit:focus {
            border: 1px solid #00FFC6;
        }
        
        QProgressBar {
            background: #0B0F15;
            border-radius: 6px;
            text-align: center;
            color: #E6EAF0;
        }
        
        QProgressBar::chunk {
            background: #00FFC6;
            border-radius: 6px;
        }
        
        QLabel {
            font: 13px 'Segoe UI';
            background: transparent;
        }
        
        QScrollArea {
            border: none;
            background: #0B0F15;
        }
        
        QTableWidget {
            background: #0B0F15;
            gridline-color: #141A22;
            border: 1px solid #141A22;
            border-radius: 6px;
        }
        
        QTableWidget::item {
            padding: 8px;
        }
        
        QTableWidget::item:selected {
            background: #00FFC6;
            color: #070A0E;
        }
        
        QHeaderView::section {
            background: #141A22;
            color: #E6EAF0;
            padding: 8px;
            border: none;
            font-weight: bold;
        }
        
        QListWidget {
            background: #0B0F15;
            border: 1px solid #141A22;
            border-radius: 6px;
            padding: 4px;
        }
        
        QListWidget::item {
            padding: 8px;
            border-radius: 4px;
        }
        
        QListWidget::item:selected {
            background: #00FFC6;
            color: #070A0E;
        }
        
        QListWidget::item:hover {
            background: #141A22;
        }
        
        QGroupBox {
            border: 1px solid #141A22;
            border-radius: 8px;
            margin-top: 12px;
            padding-top: 12px;
            font-weight: bold;
        }
        
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 4px 8px;
            color: #00FFC6;
        }
        
        QCheckBox {
            spacing: 8px;
        }
        
        QCheckBox::indicator {
            width: 18px;
            height: 18px;
            border: 1px solid #141A22;
            border-radius: 4px;
            background: #0B0F15;
        }
        
        QCheckBox::indicator:checked {
            background: #00FFC6;
            border: 1px solid #00FFC6;
        }
        
        QSlider::groove:horizontal {
            background: #141A22;
            height: 6px;
            border-radius: 3px;
        }
        
        QSlider::handle:horizontal {
            background: #00FFC6;
            width: 14px;
            margin: -4px 0;
            border-radius: 7px;
        }
        
        QTabWidget::pane {
            border: 1px solid #141A22;
            border-radius: 6px;
            background: #0B0F15;
        }
        
        QTabBar::tab {
            background: #0B0F15;
            border: 1px solid #141A22;
            padding: 8px 16px;
            margin-right: 2px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
        }
        
        QTabBar::tab:selected {
            background: #00FFC6;
            color: #070A0E;
        }
        
        QTabBar::tab:hover {
            background: #141A22;
        }
        """
        self.setStyleSheet(qss)

# ============================
# RUN APPLICATION
# ============================

if __name__ == "__main__":
    logger.info(f"Sloth version: {APP_VERSION}")
    
    try:
        logger.info("Starting Sloth application...")
        app = QApplication(sys.argv)
        app.setApplicationName("Sloth")
        app.setOrganizationName("Sloth")
        
        logger.info("Creating main window...")
        window = MainWindow()
        # Window will show via _delayed_show() - don't call show() here to prevent flash
        
        logger.info("Application started successfully!")
        sys.exit(app.exec())
    
    except Exception as e:
        logger.error(f"Fatal error during startup: {e}", exc_info=True)
        
        # Try to show error dialog
        try:
            error_app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(
                None,
                "Sloth - Startup Error",
                f"Failed to start Sloth:\n\n{str(e)}\n\nCheck sloth.log for details."
            )
        except Exception:
            # If GUI fails, print to console
            print(f"FATAL ERROR: {e}")
            import traceback
            traceback.print_exc()
        
        sys.exit(1)

