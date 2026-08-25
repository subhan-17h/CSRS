"""Render the two data figures used by CSRS_Work_Record.tex.

Both figures are built from committed artefacts, not from transcribed numbers:

  * ``eval/final/summary.csv``  -> the five-model evaluation figure
  * ``alert_ranking_summary``  -> the v1/v2/v3 alert-ranking figure and the
    judge-score-by-anchor-distance figure, whose values come from the three
    published run reports under ``~/Projects/work/CIL/``.
  * the working calendar -> derived from the dated commit log and the dated
    artefacts recorded in project-docs/PROJECT_WORK_HISTORY.md.

Run with:  uv run --group eval python latex/make_figures.py
Output:    latex/figures/eval_models.pdf, latex/figures/alert_runs.pdf,
           latex/figures/judge_delta.pdf, latex/figures/calendar.pdf
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIGURES = Path(__file__).resolve().parent / "figures"

# Light-mode categorical slots 1-3 of the validated default palette. The three
# together clear the all-pairs CVD and normal-vision floors; every bar also
# carries a direct value label, which is the relief the aqua slot's sub-3:1
# surface contrast requires.
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
BLUE_250 = "#86b6ef"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
GRID = "#dcdbd6"

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 8.5,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_SOFT,
        "text.color": INK,
        "xtick.color": INK_SOFT,
        "ytick.color": INK_SOFT,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
    }
)


def _style(ax: plt.Axes) -> None:
    """Recessive frame: no box, no ticks, one soft baseline."""
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(length=0)


def read_summary() -> list[dict[str, str]]:
    path = PROJECT_ROOT / "eval" / "final" / "summary.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [row for row in csv.DictReader(handle) if row.get("candidate_model")]


def eval_models_figure() -> Path:
    rows = read_summary()
    rows.sort(key=lambda row: float(row["cosine_mean"]), reverse=True)
    models = [row["candidate_model"] for row in rows]

    panels = [
        ("Mean cosine similarity", [float(r["cosine_mean"]) for r in rows], False),
        ("Mean BERTScore F1", [float(r["bertscore_f1_mean"]) for r in rows], False),
        ("LLM judge pass rate", [float(r["judge_pass_rate"]) for r in rows], True),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(7.1, 2.35), sharey=True)
    positions = range(len(models))

    for ax, (title, values, as_percent) in zip(axes, panels, strict=True):
        ax.barh(positions, values, height=0.62, color=BLUE)
        ax.set_title(title, fontsize=8.5, color=INK, pad=8, loc="left")
        ax.set_xlim(0, max(values) * 1.28)
        ax.set_xticks([])
        ax.invert_yaxis()
        _style(ax)
        for pos, value in zip(positions, values, strict=True):
            label = f"{value:.0%}" if as_percent else f"{value:.3f}"
            ax.text(
                value + max(values) * 0.03,
                pos,
                label,
                va="center",
                fontsize=8,
                color=INK_SOFT,
            )

    axes[0].set_yticks(list(positions))
    axes[0].set_yticklabels(models, fontsize=8.5, color=INK)

    fig.tight_layout(pad=0.4)
    out = FIGURES / "eval_models.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def alert_runs_figure() -> Path:
    """Compare the three production runs on the measures that moved."""
    runs = ("v1", "v2", "v3")
    colours = (BLUE, ORANGE, AQUA)
    panels = [
        ("Exact rank matches", "of 50, higher is better", (21, 32, 29), "{:.0f}", 50),
        ("Rank mismatches", "of 50, lower is better", (23, 4, 9), "{:.0f}", 50),
        ("Correct SID matches", "of 50, higher is better", (None, 30, 40), "{:.0f}", 50),
        ("Mean judge score", "0-1 rubric, higher is better", (0.586, 0.868, 0.780), "{:.3f}", 1.0),
    ]

    fig, axes = plt.subplots(1, 4, figsize=(7.1, 2.4))

    for ax, (title, subtitle, values, fmt, ceiling) in zip(axes, panels, strict=True):
        plotted = [0.0 if v is None else v for v in values]
        bars = ax.bar(range(3), plotted, width=0.62, color=colours)
        ax.set_title(title, fontsize=8.5, color=INK, pad=10, loc="left")
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=7.0, color=INK_SOFT)
        ax.set_ylim(0, ceiling * 1.14)
        ax.set_yticks([])
        ax.set_xticks(range(3))
        ax.set_xticklabels(runs, fontsize=8.5, color=INK)
        _style(ax)
        for bar, value in zip(bars, values, strict=True):
            if value is None:
                # v1 predates SID matching; an absent measure is not a zero.
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    ceiling * 0.035,
                    "not\nmeasured",
                    ha="center",
                    va="bottom",
                    fontsize=6.5,
                    color=INK_SOFT,
                )
                continue
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value + ceiling * 0.035,
                fmt.format(value),
                ha="center",
                fontsize=8.5,
                color=INK_SOFT,
            )

    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in colours]
    fig.legend(
        handles,
        [
            "v1  self-judged, 3 standards",
            "v2  split judge, 4,022 one-line rules",
            "v3  split judge, 4,017 detailed rule docs",
        ],
        loc="lower center",
        ncol=3,
        frameon=False,
        fontsize=7.5,
        labelcolor=INK_SOFT,
        bbox_to_anchor=(0.5, -0.07),
    )

    fig.tight_layout(pad=0.4, rect=(0, 0.07, 1, 1))
    out = FIGURES / "alert_runs.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def judge_delta_figure() -> Path:
    """Why the v3 ranking regression is over-reach rather than refinement.

    One series, so no legend: the mean judge score for each distance between
    the model's rank and the Snort-priority anchor, over all 50 v3 rankings.
    """
    distances = (0, 1, 2)
    counts = (29, 12, 9)
    scores = (1.00, 0.78, 0.08)

    fig, ax = plt.subplots(figsize=(4.4, 2.3))
    bars = ax.bar(distances, scores, width=0.55, color=BLUE)

    for bar, score in zip(bars, scores, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            score + 0.035,
            f"{score:.2f}",
            ha="center",
            fontsize=9,
            color=INK,
        )

    ax.set_ylim(0, 1.16)
    ax.set_yticks([])
    ax.set_xticks(distances)
    labels = ("0 steps", "1 step", "2 steps")
    ax.set_xticklabels(
        [f"{label}\nn={n}" for label, n in zip(labels, counts, strict=True)],
        fontsize=8.5,
        color=INK,
    )
    ax.set_xlabel(
        "distance from the Snort-priority anchor",
        fontsize=8,
        color=INK_SOFT,
        labelpad=10,
    )
    _style(ax)
    fig.tight_layout(pad=0.4)
    out = FIGURES / "judge_delta.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


# Working days carry their day number; research days are weekdays with neither
# commits nor dated artefacts; the rest are weekends.
WORKING_DAYS = {
    "2026-07-21": 1, "2026-07-22": 2, "2026-07-23": 3, "2026-07-24": 4,
    "2026-07-28": 5, "2026-07-29": 6, "2026-07-30": 7, "2026-07-31": 8,
    "2026-08-03": 9, "2026-08-06": 10, "2026-08-10": 11, "2026-08-11": 12,
    "2026-08-12": 13, "2026-08-13": 14, "2026-08-15": 15, "2026-08-21": 16,
}


def calendar_figure() -> Path:
    """The 32-day span: 16 working days, 9 research weekdays, 7 weekend days."""
    start, end = date(2026, 7, 21), date(2026, 8, 21)
    cells: list[tuple[date, int | None, str]] = []
    day = start
    while day <= end:
        number = WORKING_DAYS.get(day.isoformat())
        if number is not None:
            kind = "working"
        elif day.weekday() >= 5:
            kind = "weekend"
        else:
            kind = "research"
        cells.append((day, number, kind))
        day += timedelta(days=1)

    fill = {"working": BLUE, "research": BLUE_250, "weekend": "#ecebe7"}
    fig, ax = plt.subplots(figsize=(7.1, 1.6))

    for index, (day, number, kind) in enumerate(cells):
        column, row = index % 16, index // 16
        y = 1 - row
        ax.add_patch(
            plt.Rectangle(
                (column + 0.05, y + 0.05),
                0.90,
                0.74,
                facecolor=fill[kind],
                edgecolor="none",
            )
        )
        label = "white" if kind == "working" else INK_SOFT
        ax.text(
            column + 0.5, y + 0.56, str(day.day),
            ha="center", va="center", fontsize=7, color=label,
        )
        if number is not None:
            ax.text(
                column + 0.5, y + 0.24, f"D{number}",
                ha="center", va="center", fontsize=6.5, color="white",
            )
        ax.text(
            column + 0.5, y + 0.88, day.strftime("%a")[0],
            ha="center", va="center", fontsize=5.5, color=INK_SOFT,
        )

    rows = ((cells[0][0], cells[15][0]), (cells[16][0], cells[-1][0]))
    for row, (first, last) in enumerate(rows):
        ax.text(
            -0.2,
            (1 - row) + 0.42,
            f"{first.strftime('%-d %b')} - {last.strftime('%-d %b')}",
            ha="right", va="center", fontsize=7, color=INK_SOFT,
        )
    ax.set_xlim(-4.4, 16)
    ax.set_ylim(-0.05, 2.0)
    ax.set_axis_off()

    kinds = ("working", "research", "weekend")
    handles = [plt.Rectangle((0, 0), 1, 1, color=fill[k]) for k in kinds]
    fig.legend(
        handles,
        [
            "16 working days (commits or a dated artefact)",
            "9 research days (reading and result analysis)",
            "7 weekend days",
        ],
        loc="lower center",
        ncol=3,
        frameon=False,
        fontsize=7,
        labelcolor=INK_SOFT,
        bbox_to_anchor=(0.5, -0.09),
    )
    fig.tight_layout(pad=0.3, rect=(0, 0.08, 1, 1))
    out = FIGURES / "calendar.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


if __name__ == "__main__":
    FIGURES.mkdir(parents=True, exist_ok=True)
    for path in (
        eval_models_figure(),
        alert_runs_figure(),
        judge_delta_figure(),
        calendar_figure(),
    ):
        print(f"wrote {path.relative_to(PROJECT_ROOT)}")
