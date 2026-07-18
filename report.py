"""
report.py — builds PDF reports of the current dashboard view.

Pure functions (matplotlib + pandas only, no Streamlit) so they can be unit
tested and cached. app.py wraps these with st.cache_data.

Every chart/table reflects the *already-filtered* dataframe passed in, so the
PDF always matches whatever the user is currently looking at.
"""

import io
from datetime import datetime

import matplotlib
matplotlib.use("Agg")  # headless, safe on Streamlit Cloud
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

TEAL = "#0C7C7C"
NAVY = "#12324B"
GOLD = "#C79A3B"
PALETTE = [TEAL, NAVY, GOLD, "#2AA6A6", "#1F6F8B", "#E0B85A",
           "#0E5C5C", "#3E5C76", "#A8842E", "#5FBDBD"]
A4_W = 8.27  # inches


def fmt_inr(x) -> str:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "-"
    if abs(x) >= 1e7:
        return f"Rs {x/1e7:,.2f} Cr"
    if abs(x) >= 1e5:
        return f"Rs {x/1e5:,.2f} L"
    if abs(x) >= 1e3:
        return f"Rs {x/1e3:,.1f} K"
    return f"Rs {x:,.0f}"


# ---- figure builders -------------------------------------------------------
def _cover_fig(title, subtitle, kpis):
    fig = plt.figure(figsize=(A4_W, 3.4))
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.text(0.03, 0.88, title, fontsize=19, fontweight="bold", color=NAVY)
    ax.text(0.03, 0.72, subtitle, fontsize=8.5, color="#555555",
            va="top", wrap=True)

    n = max(1, len(kpis))
    gap = 0.02
    w = (0.94 - gap * (n - 1)) / n
    for i, (label, val) in enumerate(kpis):
        cx = 0.03 + i * (w + gap)
        ax.add_patch(plt.Rectangle((cx, 0.14), w, 0.34,
                                   facecolor="#F2F6F6", edgecolor=TEAL,
                                   linewidth=1.2, transform=ax.transAxes))
        ax.text(cx + w / 2, 0.38, str(label), fontsize=8, color="#555555",
                ha="center", va="center", transform=ax.transAxes)
        ax.text(cx + w / 2, 0.26, str(val), fontsize=13, fontweight="bold",
                color=TEAL, ha="center", va="center", transform=ax.transAxes)
    return fig


def _barh_fig(title, labels, values, color, value_fmt):
    labels = list(labels)
    values = list(values)
    h = max(2.4, 0.34 * len(labels) + 1.2)
    fig, ax = plt.subplots(figsize=(A4_W, min(10.5, h)))
    y = range(len(labels))
    ax.barh(list(y), values[::-1], color=color)
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels[::-1], fontsize=8)
    ax.set_title(title, color=NAVY, fontsize=12, fontweight="bold", loc="left")
    vmax = max(values) if values else 0
    for i, v in enumerate(values[::-1]):
        ax.text(v + vmax * 0.01, i, value_fmt(v), va="center", fontsize=7,
                color="#333333")
    ax.spines[["top", "right"]].set_visible(False)
    ax.margins(x=0.15)
    fig.tight_layout()
    return fig


def _line_fig(title, x, y, color, ylabel):
    fig, ax = plt.subplots(figsize=(A4_W, 3.1))
    ax.plot(list(x), list(y), marker="o", color=color, linewidth=2.5)
    ax.set_title(title, color=NAVY, fontsize=12, fontweight="bold", loc="left")
    ax.set_ylabel(ylabel, fontsize=8)
    ax.tick_params(labelsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    plt.xticks(rotation=45, ha="right")
    fig.tight_layout()
    return fig


def _pie_fig(title, labels, values):
    fig, ax = plt.subplots(figsize=(A4_W, 3.8))
    ax.pie(values, labels=labels, autopct="%1.0f%%", startangle=90,
           colors=PALETTE, textprops={"fontsize": 8},
           wedgeprops={"width": 0.55})
    ax.set_title(title, color=NAVY, fontsize=12, fontweight="bold", loc="left")
    fig.tight_layout()
    return fig


def _table_fig(title, df_show, note):
    rows = df_show.astype(str).values.tolist()
    cols = list(df_show.columns)
    h = max(2.0, 0.28 * len(rows) + 1.6)
    fig, ax = plt.subplots(figsize=(A4_W, min(10.5, h)))
    ax.axis("off")
    ax.set_title(title, color=NAVY, fontsize=12, fontweight="bold",
                 loc="left", pad=14)
    if note:
        ax.text(0, 1.0, note, transform=ax.transAxes, fontsize=7.5,
                color="#777777", va="bottom")
    if not rows:
        ax.text(0.5, 0.5, "No rows for the current filters.",
                ha="center", va="center", fontsize=10, color="#999999")
        return fig
    tbl = ax.table(cellText=rows, colLabels=cols, loc="upper center",
                   cellLoc="left")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(7)
    tbl.scale(1, 1.25)
    for j in range(len(cols)):
        c = tbl[0, j]
        c.set_facecolor(NAVY)
        c.set_text_props(color="white", fontweight="bold")
    for i in range(1, len(rows) + 1):
        for j in range(len(cols)):
            tbl[i, j].set_facecolor("#FFFFFF" if i % 2 else "#F2F6F6")
    fig.tight_layout()
    return fig


def _write(figs):
    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        for f in figs:
            pdf.savefig(f, bbox_inches="tight")
            plt.close(f)
    buf.seek(0)
    return buf.getvalue()


# ---- public builders -------------------------------------------------------
def build_sales_pdf(d, sel_months, kpis, filters_desc):
    stamp = datetime.now().strftime("%d %b %Y, %H:%M")
    subtitle = f"Generated {stamp}\nView: {filters_desc}"
    figs = [_cover_fig("Mibish - Dokitti  |  Sales Report", subtitle, kpis)]

    if len(d) == 0:
        figs.append(_table_fig("Data", d.head(0), "No rows for current filters."))
        return _write(figs)

    if sel_months:
        monthly = d[sel_months].sum()
        figs.append(_line_fig("Monthly Sales Trend", monthly.index.tolist(),
                              monthly.values.tolist(), TEAL, "Sales (Rs)"))

    if "Sales Person" in d.columns:
        g = (d.groupby("Sales Person")["Period Total"].sum()
             .sort_values(ascending=False).head(15))
        figs.append(_barh_fig("Sales by Salesperson", g.index.tolist(),
                              g.values.tolist(), NAVY, fmt_inr))

    if "State" in d.columns:
        g = (d.groupby("State")["Period Total"].sum()
             .sort_values(ascending=False).head(12))
        figs.append(_barh_fig("Top States", g.index.tolist(),
                              g.values.tolist(), TEAL, fmt_inr))

    if "Party Name" in d.columns:
        g = (d.groupby("Party Name")["Period Total"].sum()
             .sort_values(ascending=False).head(30).reset_index())
        g["Period Total"] = g["Period Total"].map(fmt_inr)
        g.columns = ["Party Name", "Sales"]
        figs.append(_table_fig("Top Parties", g,
                               f"Showing top {len(g)} of "
                               f"{d['Party Name'].nunique()} parties."))
    return _write(figs)


def build_product_pdf(d, qty_cols, sales_cols, mcol, metric, kpis, filters_desc):
    stamp = datetime.now().strftime("%d %b %Y, %H:%M")
    subtitle = f"Generated {stamp}\nView: {filters_desc}"
    figs = [_cover_fig("Mibish - Dokitti  |  Product Report", subtitle, kpis)]

    is_sales = metric.lower().startswith("sales")
    vfmt = fmt_inr if is_sales else (lambda v: f"{v:,.0f}")

    if len(d) == 0:
        figs.append(_table_fig("Data", d.head(0), "No rows for current filters."))
        return _write(figs)

    if "Category" in d.columns:
        g = (d.groupby("Category")[mcol].sum()
             .sort_values(ascending=False).head(15))
        figs.append(_barh_fig(f"{metric} by Category", g.index.tolist(),
                              g.values.tolist(), NAVY, vfmt))

    if "Brand" in d.columns:
        g = d.groupby("Brand")[mcol].sum()
        g = g[g > 0]
        if len(g):
            figs.append(_pie_fig(f"{metric} by Brand", g.index.tolist(),
                                 g.values.tolist()))

    namecol = "Product Name" if "Product Name" in d.columns else d.columns[0]
    g = (d.groupby(namecol)[mcol].sum()
         .sort_values(ascending=False).head(15))
    figs.append(_barh_fig(f"Top Products by {metric}", g.index.tolist(),
                          g.values.tolist(), GOLD, vfmt))

    gt = (d.groupby(namecol)[mcol].sum()
          .sort_values(ascending=False).head(30).reset_index())
    gt[mcol] = gt[mcol].map(vfmt)
    gt.columns = [namecol, metric]
    figs.append(_table_fig("Top Products (table)", gt,
                           f"Showing top {len(gt)} of {d[namecol].nunique()} products."))
    return _write(figs)
