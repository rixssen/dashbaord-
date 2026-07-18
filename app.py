"""
Mibish / Dokitti — Interactive Sales Dashboard
================================================
One app, two data "presets", auto-detected on upload:

  1. SALES  preset  -> party / salesperson / geography monthly time-series
                       (matches Sales_Data_.csv)
  2. PRODUCT preset -> brand / category / product Qty + Sales
                       (matches the PAN_India sheet)

Upload a CSV (or XLSX) of either shape and the app figures out which one it is.
Everything is filterable, and the main breakdown chart is click-to-drill.

Run locally:   streamlit run app.py
Deploy free:   push to GitHub -> share.streamlit.io  (see README.md)
"""

import io
import re
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px

import report  # pure PDF builders (matplotlib)

# ----------------------------------------------------------------------------
# Page config + light branding (teal / navy / gold)
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="Mibish • Dokitti Sales Dashboard",
    page_icon="🐾",
    layout="wide",
)

TEAL = "#0C7C7C"
NAVY = "#12324B"
GOLD = "#C79A3B"
PALETTE = [TEAL, NAVY, GOLD, "#2AA6A6", "#1F6F8B", "#E0B85A",
           "#0E5C5C", "#3E5C76", "#A8842E", "#5FBDBD"]

st.markdown(
    f"""
    <style>
      .block-container {{padding-top: 1.4rem;}}
      h1, h2, h3 {{color: {NAVY};}}
      div[data-testid="stMetricValue"] {{color: {TEAL}; font-weight: 700;}}
      .stTabs [data-baseweb="tab-list"] {{gap: 4px;}}
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
MONTH_TOKENS = ("jan", "feb", "mar", "apr", "may", "jun",
                "jul", "aug", "sep", "oct", "nov", "dec")


def to_number(series: pd.Series) -> pd.Series:
    """Turn Indian-formatted strings like '3,75,971.61' / '(1,200)' into floats."""
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce").fillna(0.0)
    s = (
        series.astype(str)
        .str.strip()
        .str.replace(",", "", regex=False)
        .str.replace("₹", "", regex=False)
        .str.replace("(", "-", regex=False)
        .str.replace(")", "", regex=False)
        .replace({"": np.nan, "nan": np.nan, "-": np.nan, "None": np.nan})
    )
    return pd.to_numeric(s, errors="coerce").fillna(0.0)


def fmt_inr(x) -> str:
    """Compact Indian-style money label."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "-"
    if abs(x) >= 1e7:
        return f"₹{x/1e7:,.2f} Cr"
    if abs(x) >= 1e5:
        return f"₹{x/1e5:,.2f} L"
    if abs(x) >= 1e3:
        return f"₹{x/1e3:,.1f} K"
    return f"₹{x:,.0f}"


def is_month_col(name: str) -> bool:
    low = str(name).lower()
    return any(tok in low for tok in MONTH_TOKENS)


@st.cache_data(show_spinner=False)
def read_any(file_bytes: bytes, filename: str):
    """Return {sheet_name: dataframe}. CSV -> single 'data' sheet."""
    name = filename.lower()
    if name.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(file_bytes))
        return {"data": df}
    # xlsx / xls
    xl = pd.ExcelFile(io.BytesIO(file_bytes))
    return {s: pd.read_excel(xl, sheet_name=s) for s in xl.sheet_names}


def detect_preset(df: pd.DataFrame) -> str:
    cols = {str(c).strip().lower() for c in df.columns}
    if "sales person" in cols or "salesperson" in cols:
        return "sales"
    if {"brand", "product code"} & cols or {"brand", "product name"} & cols:
        return "product"
    if "party name" in cols and any(is_month_col(c) for c in df.columns):
        return "sales"
    # fallback guess
    return "sales" if "party name" in cols else "product"


# ----------------------------------------------------------------------------
# Export panel (always visible in the sidebar) + cached PDF builders
# ----------------------------------------------------------------------------
@st.cache_data(max_entries=6, show_spinner="Preparing PDF…")
def _sales_pdf(d, sel_months, kpis, filters_desc):
    return report.build_sales_pdf(d, list(sel_months), list(kpis), filters_desc)


@st.cache_data(max_entries=6, show_spinner="Preparing PDF…")
def _product_pdf(d, qty_cols, sales_cols, mcol, metric, kpis, filters_desc):
    return report.build_product_pdf(d, list(qty_cols), list(sales_cols),
                                    mcol, metric, list(kpis), filters_desc)


def export_panel(kind, d, pdf_args, file_stem):
    """Render an always-visible download panel in the sidebar.
    kind: 'sales' | 'product'. pdf_args: tuple passed to the cached builder."""
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📥 Export current view")
    fmt = st.sidebar.radio("Download format",
                           ["PDF report", "CSV (data)", "Excel (data)"],
                           key=f"exp_{kind}")
    if fmt == "CSV (data)":
        st.sidebar.download_button(
            "⬇ Download CSV", d.to_csv(index=False).encode("utf-8"),
            f"{file_stem}.csv", "text/csv", use_container_width=True)
    elif fmt == "Excel (data)":
        xbuf = io.BytesIO()
        with pd.ExcelWriter(xbuf, engine="openpyxl") as w:
            d.to_excel(w, index=False, sheet_name=kind.title())
        st.sidebar.download_button(
            "⬇ Download Excel", xbuf.getvalue(), f"{file_stem}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True)
    else:
        try:
            pdf_bytes = (_sales_pdf(*pdf_args) if kind == "sales"
                         else _product_pdf(*pdf_args))
            st.sidebar.download_button(
                "⬇ Download PDF", pdf_bytes, f"{file_stem}.pdf",
                "application/pdf", use_container_width=True)
        except Exception as e:  # never let export break the dashboard
            st.sidebar.error(f"Couldn't build the PDF: {e}")
    st.sidebar.caption("Reflects your current filters, drill-down and tab data.")


# ----------------------------------------------------------------------------
# SALES preset parsing
# ----------------------------------------------------------------------------
def prep_sales(df: pd.DataFrame):
    df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")].copy()
    df.columns = [str(c).strip() for c in df.columns]

    # identify dimension columns present
    dim_map = {}
    for want in ["Party Name", "Sales Person", "City", "State"]:
        for c in df.columns:
            if c.lower() == want.lower():
                dim_map[want] = c
                break

    total_col = next((c for c in df.columns if c.lower() in
                      ("grand total", "total", "grand_total")), None)

    month_cols = [c for c in df.columns
                  if is_month_col(c) and c != total_col
                  and c not in dim_map.values()]

    # clean numeric
    for c in month_cols:
        df[c] = to_number(df[c])
    df["Total"] = df[month_cols].sum(axis=1) if month_cols else (
        to_number(df[total_col]) if total_col else 0)

    # normalize salesperson casing (AJAY SHAH -> Ajay Shah)
    if "Sales Person" in dim_map:
        df["Sales Person"] = (df[dim_map["Sales Person"]].astype(str)
                              .str.strip().str.title())
    if "State" in dim_map:
        df["State"] = df[dim_map["State"]].astype(str).str.strip().str.title()
    if "City" in dim_map:
        df["City"] = df[dim_map["City"]].astype(str).str.strip().str.title()
    if "Party Name" in dim_map:
        df["Party Name"] = df[dim_map["Party Name"]].astype(str).str.strip()

    # drop rows with no name and no sales
    df = df[~((df.get("Party Name", "").eq("")) & (df["Total"] == 0))]
    return df, month_cols


def render_sales(df: pd.DataFrame, month_cols):
    st.sidebar.header("🔎 Filters")

    def msel(label, col):
        if col not in df.columns:
            return None
        opts = sorted([o for o in df[col].dropna().unique() if str(o) != ""])
        return st.sidebar.multiselect(label, opts, default=[])

    f_sp = msel("Sales Person", "Sales Person")
    f_state = msel("State", "State")
    f_city = msel("City", "City")

    # month range slider
    sel_months = month_cols
    if len(month_cols) > 1:
        i, j = st.sidebar.select_slider(
            "Month range",
            options=list(range(len(month_cols))),
            value=(0, len(month_cols) - 1),
            format_func=lambda k: month_cols[k],
        )
        sel_months = month_cols[i:j + 1]

    # click-to-drill from the chart (stored in session)
    drill = st.session_state.get("sales_drill")

    d = df.copy()
    if f_sp:
        d = d[d["Sales Person"].isin(f_sp)]
    if f_state:
        d = d[d["State"].isin(f_state)]
    if f_city:
        d = d[d["City"].isin(f_city)]
    if drill and "Sales Person" in d.columns:
        d = d[d["Sales Person"] == drill]
        st.info(f"Drilled into salesperson: **{drill}**  ·  "
                "clear it from the sidebar button.")
        if st.sidebar.button("↩ Clear drill-down"):
            st.session_state.pop("sales_drill", None)
            st.rerun()

    d["Period Total"] = d[sel_months].sum(axis=1) if sel_months else d["Total"]

    # ---- KPIs ----
    total = d["Period Total"].sum()
    n_parties = d["Party Name"].nunique() if "Party Name" in d else len(d)
    n_sp = d["Sales Person"].nunique() if "Sales Person" in d else 0
    monthly = d[sel_months].sum() if sel_months else pd.Series(dtype=float)
    best_month = monthly.idxmax() if len(monthly) and monthly.max() > 0 else "-"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Sales", fmt_inr(total))
    c2.metric("Parties", f"{n_parties:,}")
    c3.metric("Salespeople", f"{n_sp:,}")
    c4.metric("Best Month", best_month)

    # ---- always-visible export panel ----
    parts = []
    if f_sp:
        parts.append("Salesperson: " + ", ".join(f_sp))
    if f_state:
        parts.append("State: " + ", ".join(f_state))
    if f_city:
        parts.append("City: " + ", ".join(f_city))
    if drill:
        parts.append(f"Drill: {drill}")
    if sel_months:
        parts.append(f"Months: {sel_months[0]}–{sel_months[-1]}")
    filters_desc = "  •  ".join(parts) if parts else "All salespeople, all months"
    kpis = (("Total Sales", fmt_inr(total)), ("Parties", f"{n_parties:,}"),
            ("Salespeople", f"{n_sp:,}"), ("Best Month", str(best_month)))
    export_panel("sales", d,
                 (d, tuple(sel_months), kpis, filters_desc),
                 "dokitti_sales_view")

    st.divider()
    tab1, tab2, tab3, tab4 = st.tabs(
        ["📈 Trend", "👤 Salesperson", "🗺️ Geography", "📋 Data"])

    # ---- Trend ----
    with tab1:
        if sel_months:
            trend = (d[sel_months].sum()
                     .reset_index().rename(columns={"index": "Month", 0: "Sales"}))
            trend.columns = ["Month", "Sales"]
            fig = px.line(trend, x="Month", y="Sales", markers=True,
                          color_discrete_sequence=[TEAL])
            fig.update_traces(line_width=3)
            fig.update_layout(height=420, yaxis_title="Sales (₹)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No monthly columns detected for a trend.")

    # ---- Salesperson (click to drill) ----
    with tab2:
        if "Sales Person" in d.columns:
            g = (d.groupby("Sales Person", as_index=False)["Period Total"]
                 .sum().sort_values("Period Total", ascending=False))
            fig = px.bar(g, x="Period Total", y="Sales Person", orientation="h",
                         color="Period Total",
                         color_continuous_scale=[NAVY, TEAL, GOLD],
                         text=g["Period Total"].map(fmt_inr))
            fig.update_layout(height=max(360, 26 * len(g)),
                              yaxis={"categoryorder": "total ascending"},
                              coloraxis_showscale=False,
                              xaxis_title="Sales (₹)")
            ev = st.plotly_chart(fig, use_container_width=True,
                                 on_select="rerun", key="sp_bar")
            # capture click
            try:
                pts = ev["selection"]["points"]
                if pts:
                    picked = pts[0]["y"]
                    if picked != st.session_state.get("sales_drill"):
                        st.session_state["sales_drill"] = picked
                        st.rerun()
            except (KeyError, TypeError, IndexError):
                pass
            st.caption("Tip: click a bar to drill into that salesperson.")

    # ---- Geography ----
    with tab3:
        colA, colB = st.columns(2)
        if "State" in d.columns:
            gs = (d.groupby("State", as_index=False)["Period Total"]
                  .sum().sort_values("Period Total", ascending=False).head(15))
            fig = px.bar(gs, x="Period Total", y="State", orientation="h",
                         color_discrete_sequence=[TEAL],
                         text=gs["Period Total"].map(fmt_inr))
            fig.update_layout(height=430, yaxis={"categoryorder": "total ascending"},
                              xaxis_title="Sales (₹)", title="Top States")
            colA.plotly_chart(fig, use_container_width=True)
        if "City" in d.columns:
            gc = (d.groupby("City", as_index=False)["Period Total"]
                  .sum().sort_values("Period Total", ascending=False).head(15))
            fig = px.bar(gc, x="Period Total", y="City", orientation="h",
                         color_discrete_sequence=[NAVY],
                         text=gc["Period Total"].map(fmt_inr))
            fig.update_layout(height=430, yaxis={"categoryorder": "total ascending"},
                              xaxis_title="Sales (₹)", title="Top Cities")
            colB.plotly_chart(fig, use_container_width=True)

        st.subheader("Top Parties")
        gp = (d.groupby("Party Name", as_index=False)["Period Total"]
              .sum().sort_values("Period Total", ascending=False).head(20))
        fig = px.bar(gp, x="Period Total", y="Party Name", orientation="h",
                     color_discrete_sequence=[GOLD],
                     text=gp["Period Total"].map(fmt_inr))
        fig.update_layout(height=max(360, 24 * len(gp)),
                          yaxis={"categoryorder": "total ascending"},
                          xaxis_title="Sales (₹)")
        st.plotly_chart(fig, use_container_width=True)

    # ---- Data ----
    with tab4:
        show = d.drop(columns=[c for c in ["Total"] if c in d.columns])
        st.dataframe(show, use_container_width=True, height=520)
        st.download_button("⬇ Download filtered CSV",
                           d.to_csv(index=False).encode("utf-8"),
                           "filtered_sales.csv", "text/csv")


# ----------------------------------------------------------------------------
# PRODUCT preset parsing
# ----------------------------------------------------------------------------
def prep_product(df: pd.DataFrame):
    df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")].copy()
    df.columns = [str(c).strip() for c in df.columns]

    qty_cols = [c for c in df.columns
                if is_month_col(c) and "qty" in c.lower()]
    sales_cols = [c for c in df.columns
                  if is_month_col(c) and ("sales" in c.lower()
                                          or "amt" in c.lower()
                                          or "amount" in c.lower())]
    for c in qty_cols + sales_cols:
        df[c] = to_number(df[c])

    # compute totals ourselves (source totals are often blank)
    df["Total Qty (calc)"] = df[qty_cols].sum(axis=1) if qty_cols else 0
    df["Total Sales (calc)"] = df[sales_cols].sum(axis=1) if sales_cols else 0

    for dim in ["Brand", "Category", "SubCategory"]:
        if dim in df.columns:
            df[dim] = df[dim].astype(str).str.strip().replace("nan", "—")
    # keep only rows with any activity
    df = df[(df["Total Qty (calc)"] != 0) | (df["Total Sales (calc)"] != 0)]
    return df, qty_cols, sales_cols


def render_product(df: pd.DataFrame, qty_cols, sales_cols):
    st.sidebar.header("🔎 Filters")

    def msel(label, col):
        if col not in df.columns:
            return None
        opts = sorted([o for o in df[col].dropna().unique() if str(o) not in ("", "—")])
        return st.sidebar.multiselect(label, opts, default=[])

    f_brand = msel("Brand", "Brand")
    f_cat = msel("Category", "Category")
    metric = st.sidebar.radio("Measure by", ["Sales (₹)", "Quantity"], horizontal=False)
    mcol = "Total Sales (calc)" if metric.startswith("Sales") else "Total Qty (calc)"

    drill = st.session_state.get("prod_drill")

    d = df.copy()
    if f_brand:
        d = d[d["Brand"].isin(f_brand)]
    if f_cat:
        d = d[d["Category"].isin(f_cat)]
    if drill and "Category" in d.columns:
        d = d[d["Category"] == drill]
        st.info(f"Drilled into category: **{drill}**")
        if st.sidebar.button("↩ Clear drill-down"):
            st.session_state.pop("prod_drill", None)
            st.rerun()

    total_sales = d["Total Sales (calc)"].sum()
    total_qty = d["Total Qty (calc)"].sum()
    n_prod = len(d)
    n_brand = d["Brand"].nunique() if "Brand" in d else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Sales", fmt_inr(total_sales))
    c2.metric("Total Qty", f"{total_qty:,.0f}")
    c3.metric("Products", f"{n_prod:,}")
    c4.metric("Brands", f"{n_brand:,}")

    # ---- always-visible export panel ----
    parts = []
    if f_brand:
        parts.append("Brand: " + ", ".join(f_brand))
    if f_cat:
        parts.append("Category: " + ", ".join(f_cat))
    if drill:
        parts.append(f"Drill: {drill}")
    parts.append(f"Measure: {metric}")
    filters_desc = "  •  ".join(parts)
    kpis = (("Total Sales", fmt_inr(total_sales)),
            ("Total Qty", f"{total_qty:,.0f}"),
            ("Products", f"{n_prod:,}"), ("Brands", f"{n_brand:,}"))
    export_panel("product", d,
                 (d, tuple(qty_cols), tuple(sales_cols), mcol, metric,
                  kpis, filters_desc),
                 "dokitti_product_view")

    st.divider()
    tab1, tab2, tab3, tab4 = st.tabs(
        ["🏷️ Category", "🏭 Brand", "📈 Trend", "📋 Data"])

    with tab1:
        if "Category" in d.columns:
            g = (d.groupby("Category", as_index=False)[mcol]
                 .sum().sort_values(mcol, ascending=False))
            label = g[mcol].map(fmt_inr) if metric.startswith("Sales") else g[mcol].map("{:,.0f}".format)
            fig = px.bar(g, x=mcol, y="Category", orientation="h",
                         color=mcol, color_continuous_scale=[NAVY, TEAL, GOLD],
                         text=label)
            fig.update_layout(height=max(400, 26 * len(g)),
                              yaxis={"categoryorder": "total ascending"},
                              coloraxis_showscale=False, xaxis_title=metric)
            ev = st.plotly_chart(fig, use_container_width=True,
                                 on_select="rerun", key="cat_bar")
            try:
                pts = ev["selection"]["points"]
                if pts:
                    picked = pts[0]["y"]
                    if picked != st.session_state.get("prod_drill"):
                        st.session_state["prod_drill"] = picked
                        st.rerun()
            except (KeyError, TypeError, IndexError):
                pass
            st.caption("Tip: click a category bar to drill in.")

    with tab2:
        if "Brand" in d.columns:
            g = d.groupby("Brand", as_index=False)[mcol].sum()
            gp = g[g[mcol] > 0]  # pie needs non-negative values
            if len(gp):
                fig = px.pie(gp, values=mcol, names="Brand", hole=0.45,
                             color_discrete_sequence=PALETTE)
                fig.update_layout(height=430)
                st.plotly_chart(fig, use_container_width=True)

        st.subheader(f"Top Products by {metric}")
        namecol = "Product Name" if "Product Name" in d.columns else d.columns[0]
        gp = (d.groupby(namecol, as_index=False)[mcol]
              .sum().sort_values(mcol, ascending=False).head(20))
        label = gp[mcol].map(fmt_inr) if metric.startswith("Sales") else gp[mcol].map("{:,.0f}".format)
        fig = px.bar(gp, x=mcol, y=namecol, orientation="h",
                     color_discrete_sequence=[GOLD], text=label)
        fig.update_layout(height=max(360, 24 * len(gp)),
                          yaxis={"categoryorder": "total ascending"},
                          xaxis_title=metric)
        st.plotly_chart(fig, use_container_width=True)

    with tab3:
        cols = sales_cols if metric.startswith("Sales") else qty_cols
        if cols:
            trend = d[cols].sum().reset_index()
            trend.columns = ["Month", "Value"]
            # tidy the month label (strip 'Qty'/'Sales')
            trend["Month"] = trend["Month"].str.replace(
                r"(?i)\s*(qty|sales|amt|amount)\s*", "", regex=True).str.strip()
            fig = px.line(trend, x="Month", y="Value", markers=True,
                          color_discrete_sequence=[TEAL])
            fig.update_traces(line_width=3)
            fig.update_layout(height=420, yaxis_title=metric)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No monthly columns detected for a trend.")

    with tab4:
        st.dataframe(d, use_container_width=True, height=520)
        st.download_button("⬇ Download filtered CSV",
                           d.to_csv(index=False).encode("utf-8"),
                           "filtered_products.csv", "text/csv")


# ----------------------------------------------------------------------------
# App shell
# ----------------------------------------------------------------------------
st.title("🐾 Mibish • Dokitti Sales Dashboard")
st.caption("Upload a CSV/XLSX — the app auto-detects whether it's a "
           "**Salesperson** file or a **Product** file.")

with st.sidebar:
    st.markdown("### 📁 Data")
    up = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx", "xls"])
    st.markdown("---")

# load: uploaded file, else bundled samples
sheets = None
source_label = ""
if up is not None:
    sheets = read_any(up.getvalue(), up.name)
    source_label = up.name
else:
    st.info("👈 Upload a file to begin, or explore the bundled sample below.")
    sample_choice = st.radio(
        "Try a sample dataset:",
        ["Sales (salesperson) sample", "Product (category) sample"],
        horizontal=True,
    )
    try:
        if sample_choice.startswith("Sales"):
            sheets = {"data": pd.read_csv("sample_data/sales_sample.csv")}
            source_label = "sales_sample.csv"
        else:
            sheets = {"data": pd.read_csv("sample_data/product_sample.csv")}
            source_label = "product_sample.csv"
    except FileNotFoundError:
        st.stop()

# pick a sheet if the workbook has several
if len(sheets) > 1:
    sheet_name = st.sidebar.selectbox("Sheet", list(sheets.keys()))
else:
    sheet_name = list(sheets.keys())[0]
raw = sheets[sheet_name]

# preset detection + manual override
auto = detect_preset(raw)
preset = st.sidebar.radio(
    "Data type (preset)",
    ["Auto-detect", "Sales (salesperson)", "Product (category)"],
    index=0,
)
resolved = auto if preset == "Auto-detect" else (
    "sales" if preset.startswith("Sales") else "product")

st.sidebar.success(f"Loaded **{source_label}** → **{resolved.upper()}** preset")

# reset drill state when the resolved preset changes
if st.session_state.get("_last_preset") != resolved:
    st.session_state.pop("sales_drill", None)
    st.session_state.pop("prod_drill", None)
    st.session_state["_last_preset"] = resolved

if resolved == "sales":
    d, months = prep_sales(raw)
    render_sales(d, months)
else:
    d, qty, sales = prep_product(raw)
    render_product(d, qty, sales)
