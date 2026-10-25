"""Accessible status colours shared by the Streamlit pages."""

from html import escape

import streamlit as st


APPROVE_BLUE = "#5F97BE"
REJECT_ORANGE = "#C18678"

CHART_STATUS_COLORS = {
    "no_alert": "#5F97BE",
    "watch": "#AA8D4F",
    "review_signals": "#C18678",
    "insufficient_data": "#9387AA",
}

HISTOGRAM_STATUS_COLORS = {
    "no_alert": "#3F7FA8",
    "watch": "#967532",
    "review_signals": "#AC6964",
    "insufficient_data": "#817198",
}

STATUS_PALETTE = {
    "no_alert": {"background": "#E3F0F8", "text": "#294B63", "border": "#5F97BE"},
    "watch": {"background": "#F5EBD0", "text": "#514B3D", "border": "#AA8D4F"},
    "review_signals": {"background": "#FBE6DE", "text": "#4B4350", "border": "#C18678"},
    "insufficient_data": {"background": "#ECE7F3", "text": "#4B465D", "border": "#9387AA"},
}

STATUS_LEGEND = (
    ("no_alert", "✓", "No heuristic alert", "No heuristic threshold triggered"),
    ("watch", "◇", "Watch", "Check the indicators"),
    ("review_signals", "!", "Review signals", "Signals need attention"),
    ("insufficient_data", "i", "Insufficient data", "More reviews needed"),
)


def apply_accessible_styles(*, review_queue: bool = False) -> None:
    """Use a distinguishable blue/orange pair with readable text contrast."""
    st.markdown(
        """
        <style>
        .ll-status {
            align-items: flex-start;
            border: 1px solid;
            border-radius: 0.5rem;
            display: flex;
            gap: 0.65rem;
            line-height: 1.5;
            margin: 0 0 0.75rem 0;
            padding: 0.7rem 0.9rem;
        }
        .ll-status--blue {
            background: #FBF1CF;
            border-color: #BDA567;
            color: #554B2E;
        }
        .ll-status--orange {
            background: #F7E1E8;
            border-color: #B98B9C;
            color: #5B3F4A;
        }
        .ll-status__icon { font-weight: 700; }
        [data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) {
            background-color: #EEE8F6;
            color: #4B465D;
        }
        [data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]) {
            background-color: #FBF1CF;
            color: #554B2E;
        }
        [data-testid="stAlertContentInfo"] { color: #4B465D; }
        [data-testid="stAlertContentSuccess"] { color: #554B2E; }
        [data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]) {
            background-color: #F5EBD0;
            color: #514B3D;
        }
        [data-testid="stAlertContentWarning"] { color: #514B3D; }
        [data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) {
            background-color: #F7E1E8;
            color: #5B3F4A;
        }
        [data-testid="stAlertContentError"] { color: #5B3F4A; }
        [data-testid="stSliderThumbValue"],
        [data-testid="stSliderThumbValue"] p { color: #294B63 !important; }
        [data-testid="stButton"] button,
        [data-testid="stFormSubmitButton"] button,
        [data-testid="stDownloadButton"] button {
            background-color: #DAEEF9 !important;
            border-color: #5F97BE !important;
            color: #294B63 !important;
        }
        [data-testid="stButton"] button:not(:disabled):hover,
        [data-testid="stFormSubmitButton"] button:not(:disabled):hover,
        [data-testid="stDownloadButton"] button:not(:disabled):hover {
            background-color: #C3E0F1 !important;
            border-color: #4B83AA !important;
            color: #294B63 !important;
        }
        [data-testid="stButton"] button:disabled,
        [data-testid="stFormSubmitButton"] button:disabled,
        [data-testid="stDownloadButton"] button:disabled {
            background-color: #ECEFF4 !important;
            border-color: #CCD5DF !important;
            color: #687487 !important;
        }
        [class*="st-key-rq_approve_"] button {
            background-color: #C9E3F3 !important;
            border-color: #5F97BE !important;
            color: #294B63 !important;
        }
        [class*="st-key-rq_reject_"] button {
            background-color: #F1C6B8 !important;
            border-color: #C18678 !important;
            color: #4B4350 !important;
        }
        [class*="st-key-rq_approve_"] button:not(:disabled):hover {
            background-color: #B9D9ED !important;
            border-color: #4B83AA !important;
            color: #294B63 !important;
        }
        [class*="st-key-rq_reject_"] button:not(:disabled):hover {
            background-color: #EAB7A7 !important;
            border-color: #B67C71 !important;
            color: #4B4350 !important;
        }
        [class*="st-key-rq_approve_"] button:focus-visible {
            box-shadow: 0 0 0 2px #FFFFFF, 0 0 0 5px #5F97BE !important;
        }
        [class*="st-key-rq_reject_"] button:focus-visible {
            box-shadow: 0 0 0 2px #FFFFFF, 0 0 0 5px #C18678 !important;
        }
        [class*="st-key-rq_approve_"] button:disabled,
        [class*="st-key-rq_reject_"] button:disabled { opacity: 0.5; }
        </style>
        """ + ("""
        <style>
        .ll-status--blue {
            background: #FBF1CF;
            border-color: #BDA567;
            color: #554B2E;
        }
        .ll-status--orange {
            background: #F7E1E8;
            border-color: #B98B9C;
            color: #5B3F4A;
        }
        </style>
        """ if review_queue else ""),
        unsafe_allow_html=True,
    )


def _show_status(message: object, *, tone: str, icon: str, role: str) -> None:
    text = escape(str(message))
    st.markdown(
        f'<div class="ll-status ll-status--{tone}" role="{role}">'
        f'<span class="ll-status__icon" aria-hidden="true">{icon}</span>'
        f'<span>{text}</span></div>',
        unsafe_allow_html=True,
    )


def show_approve(message: object) -> None:
    _show_status(message, tone="blue", icon="✓", role="status")


def show_reject(message: object) -> None:
    _show_status(message, tone="orange", icon="!", role="alert")


def show_error(message: object) -> None:
    show_reject(message)


def show_success(message: object) -> None:
    show_approve(message)


def show_reviewer_status(message: object, status: str) -> None:
    tone = STATUS_PALETTE[status]
    icon = next(item[1] for item in STATUS_LEGEND if item[0] == status)
    st.markdown(
        '<div class="ll-status" role="status" style="'
        f'background:{tone["background"]};color:{tone["text"]};'
        f'border-color:{tone["border"]}">'
        f'<span class="ll-status__icon" aria-hidden="true">{icon}</span>'
        f'<span>{escape(str(message))}</span></div>',
        unsafe_allow_html=True,
    )


def render_status_legend() -> None:
    """Show all four reviewer-status colours with text and shape cues."""
    columns = st.columns(len(STATUS_LEGEND))
    for column, (tone_name, icon, label, detail) in zip(columns, STATUS_LEGEND):
        tone = STATUS_PALETTE[tone_name]
        column.markdown(
            f'<div role="note" aria-label="{label}: {detail}" style="'
            f'background:{tone["background"]};color:{tone["text"]};'
            f'border:1px solid {tone["border"]};border-left-width:5px;'
            'border-radius:0.5rem;padding:0.55rem 0.7rem;line-height:1.35">'
            f'<strong>{icon} {label}</strong><br><span>{detail}</span></div>',
            unsafe_allow_html=True,
        )
