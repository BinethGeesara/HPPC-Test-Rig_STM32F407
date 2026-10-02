"""Dark-theme colour palette and global Qt stylesheet."""

# ---- Base surfaces ----
BG           = "#0B0D10"
PANEL        = "#15181D"
PANEL_GLASS  = ("qlineargradient(x1:0, y1:0, x2:0, y2:1,"
                " stop:0 #1B1F26, stop:1 #14171C)")
PANEL_SOLID  = "#1B1F26"
BORDER       = "rgba(255,255,255,0.06)"
BORDER_HOVER = "rgba(255,255,255,0.16)"
INNER_DARK   = "#0E1116"
HAIRLINE     = "rgba(255,255,255,0.04)"

# ---- Text ----
TEXT       = "#F2F4F8"
TEXT_MUTED = "#9AA3B0"
TEXT_DIM   = "#5C6470"

# ---- Accents ----
ACCENT     = "#22D3EE"
ACCENT_ALT = "#A78BFA"
SUCCESS    = "#34D399"
WARNING    = "#FBBF24"
ERROR      = "#F87171"
GOLD       = "#FBBF24"

# ---- Fonts ----
FONT_FAMILY = "'Inter', 'SF Pro Display', 'Segoe UI', sans-serif"
FONT_MONO   = "'JetBrains Mono', 'SF Mono', 'Consolas', monospace"

# ---- Radii ----
RADIUS_CARD  = 14
RADIUS_PILL  = 999
RADIUS_INPUT = 8


def app_stylesheet() -> str:
    return f"""
        /* ---- Root defaults ---- */
        QWidget {{
            background: {BG};
            color: {TEXT};
            font-family: {FONT_FAMILY};
        }}
        QMainWindow {{ background: {BG}; }}

        /* ---- Baseline font size ---- */
        QLabel, QPushButton, QLineEdit, QPlainTextEdit,
        QSpinBox, QDoubleSpinBox, QTabBar, QCheckBox, QGroupBox,
        QComboBox {{
            font-size: 13px;
        }}

        /* ---- Glass cards ---- */
        QFrame#GlassCard, QGroupBox#GlassCard {{
            background: {PANEL_GLASS};
            border: 1px solid {BORDER};
            border-radius: {RADIUS_CARD}px;
        }}

        /* ---- Text hierarchy ---- */
        QLabel#Heading {{
            color: {TEXT_MUTED};
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 2px;
        }}
        QLabel#Title {{
            color: {TEXT};
            font-size: 16px;
            font-weight: 700;
            letter-spacing: 0.5px;
        }}
        QLabel#Body  {{ color: {TEXT};       font-size: 13px; }}
        QLabel#Muted {{ color: {TEXT_MUTED}; font-size: 12px; }}
        QLabel#Value {{ color: {TEXT};       font-size: 22px; font-weight: 700; }}
        QLabel#Badge {{
            background: {PANEL};
            color: {TEXT};
            border-radius: {RADIUS_PILL}px;
            padding: 6px 12px;
            font-size: 13px;
        }}

        /* ---- Pill buttons ---- */
        QPushButton#Pill {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #20242B, stop:1 #171A20);
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: {RADIUS_PILL}px;
            padding: 9px 20px;
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton#Pill:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #2A2F38, stop:1 #1D2128);
            border-color: {BORDER_HOVER};
        }}
        QPushButton#Pill:pressed  {{ background: {ACCENT};  color: #05080B; }}
        QPushButton#Pill:disabled {{ color: {TEXT_DIM};     border-color: {BORDER}; }}
        QPushButton#Pill:checked  {{ background: {ACCENT};  color: #05080B;
                                     border-color: {ACCENT}; }}

        /* ---- Danger / action pill variants ---- */
        QPushButton#PillDanger {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #3B1B1B, stop:1 #2A1010);
            color: {ERROR};
            border: 1px solid rgba(248,113,113,0.25);
            border-radius: {RADIUS_PILL}px;
            padding: 9px 20px;
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton#PillDanger:hover  {{ border-color: {ERROR}; }}
        QPushButton#PillDanger:pressed {{ background: {ERROR}; color: #05080B; }}
        QPushButton#PillDanger:disabled {{ color: {TEXT_DIM}; }}

        QPushButton#PillSuccess {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #1B3B2A, stop:1 #102A1B);
            color: {SUCCESS};
            border: 1px solid rgba(52,211,153,0.25);
            border-radius: {RADIUS_PILL}px;
            padding: 9px 20px;
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton#PillSuccess:hover  {{ border-color: {SUCCESS}; }}
        QPushButton#PillSuccess:pressed {{ background: {SUCCESS}; color: #05080B; }}
        QPushButton#PillSuccess:disabled {{ color: {TEXT_DIM}; }}

        /* ---- Tabs ---- */
        QTabBar::tab {{
            background: transparent;
            color: {TEXT_DIM};
            padding: 9px 18px;
            margin-right: 4px;
            border: none;
            border-radius: {RADIUS_PILL}px;
            font-size: 12px;
            font-weight: 600;
        }}
        QTabBar::tab:selected {{
            background: {PANEL_SOLID};
            color: {TEXT};
            border: 1px solid {BORDER};
        }}
        QTabBar::tab:hover:!selected {{ color: {TEXT_MUTED}; }}

        /* ---- Inputs ---- */
        QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{
            background: {INNER_DARK};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: {RADIUS_INPUT}px;
            padding: 8px 10px;
            selection-background-color: {ACCENT};
        }}
        QLineEdit:focus, QSpinBox:focus,
        QDoubleSpinBox:focus, QPlainTextEdit:focus {{
            border-color: {ACCENT};
        }}

        QComboBox {{
            background: {INNER_DARK};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: {RADIUS_INPUT}px;
            padding: 6px 10px;
        }}
        QComboBox QAbstractItemView {{
            background: {PANEL_SOLID};
            color: {TEXT};
            selection-background-color: {ACCENT};
        }}

        /* ---- Scrollbars ---- */
        QScrollBar:vertical   {{ background: transparent; width:  8px; margin: 0; }}
        QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0; }}
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
            background: {BORDER_HOVER}; border-radius: 4px;
            min-height: 30px; min-width: 30px;
        }}
        QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    """


# ----------------------------------------------------------------- helpers

def pill_btn(text: str, *, danger: bool = False, success: bool = False) -> str:
    """Return the object-name string for a themed pill button."""
    if danger:
        return "PillDanger"
    if success:
        return "PillSuccess"
    return "Pill"

