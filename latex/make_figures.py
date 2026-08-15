"""Render the two data figures used by CSRS_Work_Record.tex.

Both figures are built from committed artefacts, not from transcribed numbers:

  * ``eval/final/summary.csv``  -> the five-model evaluation figure
  * ``alert_ranking_summary``  -> the v1/v2 alert-ranking figure, whose values
    come from the two published run reports under ``~/Projects/work/CIL/``.

Run with:  uv run --group eval python latex/make_figures.py
Output:    latex/figures/eval_models.pdf, latex/figures/alert_v1_v2.pdf
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIGURES = Path(__file__).resolve().parent / "figures"

# Light-mode categorical slots 1 and 2 of the validated default palette.
BLUE = "#2a78d6"
ORANGE = "#eb6834"
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


def alert_v1_v2_figure() -> Path:
    panels = [
        ("Exact rank matches", "of 50 alerts", 21, 32, "{:.0f}", 50),
        ("Rank mismatches", "lower is better", 23, 4, "{:.0f}", 50),
        ("Mean judge score", "0-1 rubric", 0.586, 0.868, "{:.3f}", 1.0),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(7.1, 2.3))

    for ax, (title, subtitle, v1, v2, fmt, ceiling) in zip(axes, panels, strict=True):
        bars = ax.bar([0, 1], [v1, v2], width=0.5, color=[BLUE, ORANGE])
        ax.set_title(title, fontsize=8.5, color=INK, pad=10, loc="left")
        ax.text(
            0,
            1.02,
            subtitle,
            transform=ax.transAxes,
            fontsize=7.5,
            color=INK_SOFT,
        )
        ax.set_ylim(0, ceiling * 1.12)
        ax.set_yticks([])
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["v1", "v2"], fontsize=8.5, color=INK)
        _style(ax)
        for bar, value in zip(bars, (v1, v2), strict=True):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value + ceiling * 0.03,
                fmt.format(value),
                ha="center",
                fontsize=8.5,
                color=INK_SOFT,
            )

    handles = [
        plt.Rectangle((0, 0), 1, 1, color=BLUE),
        plt.Rectangle((0, 0), 1, 1, color=ORANGE),
    ]
    fig.legend(
        handles,
        ["v1  gpt-oss-120b, self-judged", "v2  gpt-oss-120b, qwen3.6-27b judge"],
        loc="lower center",
        ncol=2,
        frameon=False,
        fontsize=8,
        labelcolor=INK_SOFT,
        bbox_to_anchor=(0.5, -0.06),
    )

    fig.tight_layout(pad=0.4, rect=(0, 0.06, 1, 1))
    out = FIGURES / "alert_v1_v2.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


if __name__ == "__main__":
    FIGURES.mkdir(parents=True, exist_ok=True)
    for path in (eval_models_figure(), alert_v1_v2_figure()):
        print(f"wrote {path.relative_to(PROJECT_ROOT)}")
