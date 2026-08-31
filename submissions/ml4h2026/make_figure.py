"""Figure 1 for the ML4H 2026 Findings submission.

Form: magnitude comparison across a small set of named conditions -> bars.
Colour: categorical slots 1 and 2 of the validated reference palette, in fixed
order, one hue per *design* (not per bar). Every bar is directly labelled and the
old-design bar is hatched, so identity and magnitude survive greyscale printing
and CVD without relying on colour.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SERIES_1 = "#2a78d6"   # blue   - database-resolved design
SERIES_2 = "#eb6834"   # orange - literal-code design
INK      = "#0b0b0b"
MUTED    = "#52514e"

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 8,
    "axes.edgecolor": MUTED,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
})

labels = ["SFT\n(literal-code gold)", "Frozen\n(full schema)", "SFT\n(this work)"]
vals   = [20.7, 60.8, 89.1]
colors = [SERIES_2, SERIES_1, SERIES_1]
alphas = [1.0, 0.45, 1.0]
hatch  = ["///", None, None]

fig, ax = plt.subplots(figsize=(3.35, 2.35))
bars = ax.bar(range(3), vals, width=0.62, color=colors, hatch=hatch,
              edgecolor="white", linewidth=1.2, zorder=3)
for b, a in zip(bars, alphas):
    b.set_alpha(a)

# lower bound of the 81.4-89.1 bracket on the final bar
ax.hlines(81.4, 1.69, 2.31, color=INK, linewidth=1.0, linestyle=(0, (3, 2)), zorder=5)
ax.annotate("81.4 lower bound\n(text match)", xy=(2.34, 81.4), xytext=(2.40, 62),
            fontsize=6.2, color=MUTED, ha="left", va="center",
            arrowprops=dict(arrowstyle="-", color=MUTED, linewidth=0.6))

for b, v in zip(bars, vals):
    ax.text(b.get_x() + b.get_width() / 2, v + 2.2, f"{v:.1f}",
            ha="center", va="bottom", fontsize=8.5, color=INK, zorder=6)

# design separator
ax.axvline(0.5, color=MUTED, linewidth=0.6, linestyle=":", zorder=1)
ax.text(0.0, 103, "literal-code\nterminology", ha="center", va="bottom",
        fontsize=6.2, color=MUTED)
ax.text(1.5, 103, "terminology resolved in the database",
        ha="center", va="bottom", fontsize=6.2, color=MUTED)

ax.set_xticks(range(3))
ax.set_xticklabels(labels, fontsize=7)
ax.set_ylabel("Execution match, unseen concepts (%)", fontsize=7.5)
ax.set_ylim(0, 118)
ax.set_yticks([0, 25, 50, 75, 100])
ax.set_xlim(-0.6, 3.02)
ax.grid(axis="y", color=MUTED, alpha=0.18, linewidth=0.5, zorder=0)
ax.set_axisbelow(True)
for side in ("top", "right"):
    ax.spines[side].set_visible(False)
ax.spines["left"].set_linewidth(0.6)
ax.spines["bottom"].set_linewidth(0.6)

fig.tight_layout(pad=0.3)
fig.savefig("fig1_unseen.pdf", bbox_inches="tight", transparent=True)
fig.savefig("fig1_unseen.png", dpi=300, bbox_inches="tight")
print("wrote fig1_unseen.pdf / .png")
