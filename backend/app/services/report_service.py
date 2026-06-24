from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.fsm import SimulationEvent
from app.services.metrics_service import compute_session_metrics


_INK = colors.HexColor("#172026")
_GREEN = colors.HexColor("#0f766e")
_PANEL = colors.HexColor("#f7faf9")
_LINE = colors.HexColor("#d7e2de")
_MUTED = colors.HexColor("#64748b")


def compute_training_score(
    no_transition_count: int,
    instructor_intervention_count: int,
) -> int:
    score = 100 - instructor_intervention_count * 5 - no_transition_count * 2
    return max(score, 0)


def generate_session_pdf(
    session_id: str,
    scenario_id: str,
    scenario_name: str,
    history: list[SimulationEvent],
    current_state_id: str,
) -> bytes:
    metrics = compute_session_metrics(history=history, current_state_id=current_state_id)
    score = compute_training_score(
        no_transition_count=metrics["no_transition_count"],
        instructor_intervention_count=metrics["instructor_intervention_count"],
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    base = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "NRSTitle", parent=base["Heading1"],
        fontSize=18, textColor=_GREEN, spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "NRSSubtitle", parent=base["Normal"],
        fontSize=11, textColor=_MUTED, spaceAfter=4,
    )
    section_style = ParagraphStyle(
        "NRSSection", parent=base["Heading2"],
        fontSize=12, textColor=_INK, spaceBefore=10, spaceAfter=5,
    )
    body_style = ParagraphStyle(
        "NRSBody", parent=base["Normal"],
        fontSize=9, textColor=_INK,
    )

    score_color = (
        _GREEN if score >= 80
        else colors.HexColor("#d97706") if score >= 60
        else colors.HexColor("#be123c")
    )
    score_style = ParagraphStyle(
        "NRSScore", parent=base["Normal"],
        fontSize=32, textColor=score_color, alignment=TA_CENTER, spaceAfter=2,
    )
    score_label_style = ParagraphStyle(
        "NRSScoreLabel", parent=base["Normal"],
        fontSize=10, textColor=_MUTED, alignment=TA_CENTER, spaceAfter=6,
    )

    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(Paragraph("Neonatal Resuscitation Simulator", title_style))
    story.append(Paragraph("Session Performance Report", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=_LINE, spaceAfter=6))

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    meta_rows = [
        ["Session ID", str(session_id)],
        ["Scenario", f"{scenario_name} ({scenario_id})"],
        ["Generated", generated_at],
        ["Status", metrics["completion_status"].replace("_", " ").title()],
    ]
    meta_table = Table(meta_rows, colWidths=[3.5 * cm, None])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), _MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), _INK),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.5 * cm))

    # ── Training score ────────────────────────────────────────────────────────
    story.append(Paragraph(str(score), score_style))
    story.append(Paragraph("Training Performance Score / 100", score_label_style))
    story.append(HRFlowable(width="100%", thickness=1, color=_LINE, spaceAfter=4))

    # ── Metrics table ─────────────────────────────────────────────────────────
    story.append(Paragraph("Performance Metrics", section_style))

    def _fmt(secs: float) -> str:
        if secs < 1:
            return "< 1s"
        m, s = divmod(int(secs), 60)
        return f"{m}m {s}s" if m else f"{s}s"

    metric_rows = [
        ["Metric", "Value"],
        ["Total Duration", _fmt(metrics["total_duration_seconds"])],
        ["Student Inputs", str(metrics["student_input_count"])],
        ["Voice Inputs", str(metrics["voice_input_count"])],
        ["Successful Transitions", str(metrics["successful_transition_count"])],
        ["Unmatched Inputs", str(metrics["no_transition_count"])],
        ["Instructor Interventions", str(metrics["instructor_intervention_count"])],
        ["Timer Events", str(metrics["timer_event_count"])],
    ]
    m_table = Table(metric_rows, colWidths=[8 * cm, None])
    m_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _PANEL]),
        ("GRID", (0, 0), (-1, -1), 0.5, _LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(m_table)
    story.append(Spacer(1, 0.4 * cm))

    # Score breakdown note
    story.append(Paragraph(
        f"Score breakdown: 100 base"
        f" − {metrics['instructor_intervention_count'] * 5} pts"
        f" (interventions × 5)"
        f" − {metrics['no_transition_count'] * 2} pts"
        f" (unmatched × 2)"
        f" = {score}",
        body_style,
    ))
    story.append(Spacer(1, 0.6 * cm))

    # ── Event timeline ────────────────────────────────────────────────────────
    story.append(Paragraph("Event Timeline", section_style))

    if not history:
        story.append(Paragraph("No events recorded.", body_style))
    else:
        t0 = history[0].timestamp
        timeline_rows = [["#", "Elapsed", "Event Type", "State", "Target"]]
        for i, ev in enumerate(history, 1):
            elapsed = f"+{(ev.timestamp - t0).total_seconds():.1f}s"
            timeline_rows.append([
                str(i),
                elapsed,
                ev.type,
                ev.state_id,
                ev.target_state_id or "—",
            ])

        t_table = Table(
            timeline_rows,
            colWidths=[0.8 * cm, 1.8 * cm, 4 * cm, 4.5 * cm, 4.5 * cm],
        )
        t_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _GREEN),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _PANEL]),
            ("GRID", (0, 0), (-1, -1), 0.5, _LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("ALIGN", (0, 0), (1, -1), "RIGHT"),
        ]))
        story.append(t_table)

    doc.build(story)
    return buf.getvalue()
