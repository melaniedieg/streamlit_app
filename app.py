"""
NYC Mixing Map -- Streamlit + pydeck version

Interactive map of venue-level income mixing across eight independently-rebuilt
periods (Dec 2025-Jul 2026). Reads the per-period CSVs in data/ (built by
export_streamlit_data.py in income_mixing_methodology/ from the modeling
pipeline's pickled outputs -- see the main repo's README.md for what those
scores mean and how they're built).

Run with:
    pip install -r requirements.txt
    streamlit run app.py
"""
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

st.set_page_config(page_title="NYC Mixing Map", layout="wide")

MONTH_LABELS = {
    "December 2025": "2025-12",
    "January 2026": "2026-01",
    "February 2026": "2026-02",
    "March 2026": "2026-03",
    "April 2026": "2026-04",
    "May 2026": "2026-05",
    "June 2026": "2026-06",
    "July 2026": "2026-07",
}

# A coding-style monospace stack, applied to the whole app (including the
# pydeck tooltip, which is styled separately below since it isn't plain HTML
# Streamlit controls).
MONO = 'ui-monospace, "SF Mono", "Cascadia Code", "Roboto Mono", Consolas, "Liberation Mono", monospace'
st.markdown(
    f"""
    <style>
    html, body, [class*="css"], .stMarkdown, .stMetric, .stDataFrame, .stSelectbox, .stMultiSelect, .stRadio {{
        font-family: {MONO} !important;
    }}

    /* The rule above doesn't reach Streamlit's actual selectbox internals
       (BaseWeb components set their own font-family), so target those by
       their stable data-testid/ARIA attributes instead -- this is what
       actually makes "Month" match the monospace look used everywhere else,
       including its own dropdown list when opened (which renders in a
       portal, not nested under the selectbox, hence the separate rule). */
    div[data-testid="stSelectbox"] *,
    div[data-testid="stWidgetLabel"] *,
    div[data-testid="stMultiSelect"] *,
    div[data-testid="stCheckbox"] *,
    div[data-testid="stSegmentedControl"] * {{
        font-family: {MONO} !important;
    }}
    ul[role="listbox"] * {{
        font-family: {MONO} !important;
    }}

    /* Styles any st.popover trigger to look like an ordinary select box
       (same fill, border, radius, text color) instead of Streamlit's default
       red-outlined button style. Not currently used by any control on screen
       (the old borough/category filters that used it were removed) -- left
       in place since dropdown_multiselect()/dropdown_checklist() below still
       build on st.popover and may get reused for a future filter. */
    div[data-testid="stPopover"] > div > button {{
        font-family: {MONO} !important;
        background-color: rgb(240, 242, 246) !important;
        border: 1px solid rgba(49, 51, 63, 0.2) !important;
        border-radius: 8px !important;
        color: rgb(49, 51, 63) !important;
        justify-content: space-between !important;
        font-weight: 400 !important;
        box-shadow: none !important;
    }}
    div[data-testid="stPopover"] > div > button:hover,
    div[data-testid="stPopover"] > div > button:focus,
    div[data-testid="stPopover"] > div > button:active,
    div[data-testid="stPopover"] > div > button:focus:not(:active) {{
        background-color: rgb(240, 242, 246) !important;
        border-color: rgba(49, 51, 63, 0.4) !important;
        color: rgb(49, 51, 63) !important;
    }}
    div[data-testid="stPopover"] > div > button p {{
        color: rgb(49, 51, 63) !important;
        font-family: {MONO} !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------- data -----

@st.cache_data
def load_month(month_key: str) -> pd.DataFrame:
    df = pd.read_csv(f"data/venues_{month_key}.csv")
    df["persistence_tier"] = df["persistence_tier"].fillna("single_month_not_tested")
    df["fdr_sig_05_hk"] = df["fdr_sig_05_hk"].fillna(False).astype(bool)
    return df

@st.cache_data
def load_stats() -> pd.DataFrame:
    return pd.read_csv("data/month_stats.csv").set_index("month")

# ------------------------------------------------------------- colors ------
# The map only colors by residual now: a diverging purple (less mixed than
# expected) <-> neutral gray (expected) <-> orange (more mixed than expected)
# scale, z-scored within borough.

RES_PURPLE = np.array([142, 84, 186], dtype=float)
RES_ORANGE = np.array([227, 132, 36], dtype=float)
NEUTRAL = np.array([225, 223, 219], dtype=float)
# Used only by the evidence charts below the map now (persistence/significance
# used to be drawn as rings on the dots themselves -- moved into charts/a
# table instead, since encoding color + size + ring + stroke all on one dot
# read as crowded).
CHART_SIG_COLOR = "#0b0b0b"
CHART_NONSIG_COLOR = "#c9c7c0"


def hex_of(rgb) -> str:
    r, g, b = (int(round(c)) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def div_color(z: np.ndarray) -> np.ndarray:
    """Diverging purple (less mixed) <-> neutral gray (expected) <-> orange (more mixed)."""
    z = np.clip(z, -4, 4) / 4.0
    out = np.tile(NEUTRAL, (len(z), 1))
    neg = z < 0
    pos = z >= 0
    t_neg = (-z[neg])[:, None]
    t_pos = (z[pos])[:, None]
    out[neg] = NEUTRAL * (1 - t_neg) + RES_PURPLE * t_neg
    out[pos] = NEUTRAL * (1 - t_pos) + RES_ORANGE * t_pos
    return out


# The "Actual" and "Expected" views both plot a mixing-score-shaped value
# (0-1, clustered near the top of that range), so they share one pale-to-dark
# blue sequential scale -- same kind of measurement, shown twice, so it reads
# as directly comparable when you toggle between them.
SEQ_LOW = np.array([222, 235, 247], dtype=float)
SEQ_HIGH = np.array([8, 48, 107], dtype=float)


def seq_color(values: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Sequential pale-to-dark blue, scaled to a given [lo, hi] range -- pass
    each month's own 2nd-98th percentile range rather than a flat 0-1 domain,
    since both scores cluster near the top of their theoretical range and a
    flat domain would make almost everything look the same shade."""
    span = max(hi - lo, 1e-9)
    t = np.clip((values - lo) / span, 0, 1)[:, None]
    return SEQ_LOW * (1 - t) + SEQ_HIGH * t


# ------------------------------------------------------- dropdown filter ---
# A popover button that shows a compact summary ("All boroughs", "3 boroughs
# selected", ...) and opens into a searchable multiselect -- gives the
# collapsed "dropdown" feel while keeping multiselect's built-in search for
# long lists like subcategories.

def dropdown_multiselect(label: str, options: list, state_key: str, field_label: str = "") -> list:
    if state_key not in st.session_state:
        st.session_state[state_key] = list(options)
    else:
        # keep only selections still valid for this option set (e.g. after
        # switching months), defaulting back to "all" if nothing survives
        kept = [v for v in st.session_state[state_key] if v in options]
        st.session_state[state_key] = kept if kept else list(options)

    selected = st.session_state[state_key]
    if len(selected) == len(options):
        summary = f"All {label}"
    elif len(selected) == 0:
        summary = f"No {label}"
    elif len(selected) == 1:
        summary = selected[0]
    else:
        summary = f"{len(selected)} {label} selected"

    if field_label:
        # Mimics Streamlit's own widget label (e.g. the "Month" caption above
        # the month selectbox) so this popover-based control reads as the
        # same kind of field, just with a custom dropdown underneath.
        st.markdown(
            f'<div style="font-size:14px; color:rgb(49,51,63); margin-bottom:0.25rem; '
            f'font-family:{MONO};">{field_label}</div>',
            unsafe_allow_html=True,
        )

    with st.popover(summary, use_container_width=True):
        st.caption(label)
        b1, b2 = st.columns(2)
        if b1.button("All", key=f"{state_key}_all_btn", use_container_width=True):
            st.session_state[state_key] = list(options)
            st.rerun()
        if b2.button("None", key=f"{state_key}_none_btn", use_container_width=True):
            st.session_state[state_key] = []
            st.rerun()
        new_selected = st.multiselect(
            label, options, default=selected, key=f"{state_key}_ms", label_visibility="collapsed"
        )
        if new_selected != selected:
            st.session_state[state_key] = new_selected
            st.rerun()
    return st.session_state[state_key]


def dropdown_checklist(label: str, options: list, state_key: str, height: int = 260) -> list:
    """Same collapsed dropdown-button shell as dropdown_multiselect, but the
    panel is a scrollable checkbox list -- one row per option -- rather than
    a search box, for a longer list you want to just click down."""
    if state_key not in st.session_state:
        st.session_state[state_key] = list(options)
    else:
        kept = [v for v in st.session_state[state_key] if v in options]
        st.session_state[state_key] = kept if kept else list(options)
    selected = st.session_state[state_key]

    for opt in options:
        cb_key = f"{state_key}_cb_{opt}"
        if cb_key not in st.session_state:
            st.session_state[cb_key] = opt in selected

    if len(selected) == len(options):
        summary = f"All {label}"
    elif len(selected) == 0:
        summary = f"No {label}"
    elif len(selected) == 1:
        summary = selected[0]
    else:
        summary = f"{len(selected)} {label} selected"

    with st.popover(summary, use_container_width=True):
        st.caption(label)
        b1, b2 = st.columns(2)
        if b1.button("All", key=f"{state_key}_all_btn", use_container_width=True):
            for opt in options:
                st.session_state[f"{state_key}_cb_{opt}"] = True
            st.session_state[state_key] = list(options)
            st.rerun()
        if b2.button("None", key=f"{state_key}_none_btn", use_container_width=True):
            for opt in options:
                st.session_state[f"{state_key}_cb_{opt}"] = False
            st.session_state[state_key] = []
            st.rerun()
        with st.container(height=height):
            for opt in options:
                st.checkbox(opt, key=f"{state_key}_cb_{opt}")
        new_selected = [opt for opt in options if st.session_state.get(f"{state_key}_cb_{opt}")]
        if new_selected != selected:
            st.session_state[state_key] = new_selected
    return st.session_state[state_key]


# --------------------------------------------------------------- UI --------

st.title("Where Do New Yorkers Mingle?")
st.caption(
    "Venue-level model residuals across eight independently-rebuilt periods "
    "(Dec 2025-Jul 2026). The map colors each venue by its residual; "
    "cross-period persistence and FDR-corrected significance are broken out "
    "in the charts and table below it instead. See the Glossary page for "
    "what every term means."
)
st.page_link("pages/1_Glossary.py", label="Glossary -- what every term means", icon="ℹ️")

top1, top2, _ = st.columns([1.0, 1.4, 1.2])
with top1:
    month_choice = st.selectbox("Month", list(MONTH_LABELS.keys()), index=len(MONTH_LABELS) - 1)
with top2:
    st.markdown(
        f'<div style="font-size:14px; color:rgb(49,51,63); margin-bottom:0.25rem; '
        f'font-family:{MONO};">View</div>',
        unsafe_allow_html=True,
    )
    view_mode = st.segmented_control(
        "View", ["Residual", "Actual", "Expected"], default="Residual",
        label_visibility="collapsed",
    )
    if view_mode is None:  # a single-select segmented control can be clicked off
        view_mode = "Residual"

month_key = MONTH_LABELS[month_choice]
df_full = load_month(month_key)

VIEW_DEFINITIONS = {
    "Actual": (
        "**Actual mixing** = how evenly this venue's visitors are spread across income "
        "quintiles, estimated from each visitor's home Census block group -- closer to 1 means "
        "visitors are spread evenly across income levels, lower means visitors skew toward one "
        "or two income groups."
    ),
    "Expected": (
        "**Expected mixing** = the score a model predicts for a venue from its borough, "
        "neighborhood income and race, commercial density, subway access, and tourist "
        "proximity -- a statistical baseline for what its mixing should look like given where "
        "it sits, not the venue's own actual score."
    ),
    "Residual": (
        "**Residual** = a venue's actual mixing score minus the score a model predicts from its "
        "borough, neighborhood income and race, commercial density, subway access, and tourist "
        "proximity, z-scored within borough."
    ),
}
st.caption(VIEW_DEFINITIONS[view_mode])

stats = load_stats()
df = df_full.copy()

if df.empty:
    st.warning("No venues match the current filters.")
    st.stop()

# ------------------------------------------------------------- styling -----

if view_mode == "Residual":
    colors = div_color(df["mixing_residual_z"].to_numpy())
elif view_mode == "Actual":
    lo, hi = df["income_mixing_score"].quantile([0.02, 0.98])
    colors = seq_color(df["income_mixing_score"].to_numpy(), lo, hi)
else:  # Expected
    lo, hi = df["expected_mixing_score"].quantile([0.02, 0.98])
    colors = seq_color(df["expected_mixing_score"].to_numpy(), lo, hi)

colors_int = colors.round().astype(int)
# Vectorized instead of a row-wise .apply(axis=1): that Python-level loop over
# every venue (~28k+ rows) re-ran on *every* interaction -- fine on a fast
# local machine, but ~40x slower than needed, which is exactly the kind of
# cost that turns into a visible stall on Streamlit Community Cloud's
# weaker/shared free-tier CPU. np.hstack + .tolist() does the same [r,g,b,190]
# list-per-row shape pydeck wants, just without the per-row Python overhead.
alpha_col = np.full((len(df), 1), 190, dtype=int)
df["fill_color"] = np.hstack([colors_int, alpha_col]).tolist()

# Every dot is now drawn at the same size, on all three views -- persistence
# tier and FDR significance used to be drawn as rings here (size + stroke on
# top of the residual color), which read as crowded with color, size, and two
# different ring styles all on one small dot. That information still exists;
# it's just in the evidence charts and the top-venues table below the map
# instead of encoded onto the dot itself.
BASE_RADIUS = 5
df["radius"] = BASE_RADIUS

# sub_category is missing for a small share of venues (~7%, already
# back-filled with top_category in the export script) -- kept as its own
# column so the tooltip always has something to show.
df["tooltip_category"] = df["sub_category"]

# A small colored +/- next to the name flags the residual's direction at a
# glance: orange + for more mixed than expected, purple - for less --
# matching the same purple/orange used for the Residual color scale.
df["residual_sign_html"] = np.where(
    df["mixing_residual_z"] >= 0,
    f'<span style="color:{hex_of(RES_ORANGE)}; font-weight:700;">&#43;</span>',
    f'<span style="color:{hex_of(RES_PURPLE)}; font-weight:700;">&#8722;</span>',
)

TOOLTIP = {
    "html": (
        "<b>{location_name}</b> {residual_sign_html}<br/>"
        "{tooltip_category}<br/>"
        "{income_known_devices} visitor devices<br/>"
        "Mixing {income_mixing_score} (expected {expected_mixing_score}) &middot; "
        "Balance {balance_score}<br/>"
        "Residual z {mixing_residual_z}"
    ),
    "style": {
        "backgroundColor": "#0b0b0b",
        "color": "#fcfcfb",
        "fontSize": "12px",
        "fontFamily": MONO,
    },
}

# pydeck ships every column of whatever DataFrame it's given to the browser
# as JSON, on every rerun -- not just the columns actually referenced by the
# layer's accessors/tooltip. The venue CSVs carry a bunch of modeling columns
# (placekey, top_category, borough, months, persistence_tier, mu_hk, q_bh_hk,
# ...) that the map itself never uses (the evidence charts below read them
# straight from df, not from the map layer), so trimming to just what's drawn
# or shown in the tooltip cuts that payload substantially -- on a
# resource-constrained free host, less data serialized and shipped per
# interaction is a real win on top of the fill_color vectorization fix.
MAP_COLS = [
    "lon", "lat", "fill_color", "radius",
    "location_name", "residual_sign_html", "tooltip_category", "income_known_devices",
    "income_mixing_score", "expected_mixing_score", "balance_score", "mixing_residual_z",
]

# Every view draws the same way now: one layer, one size, color varying by
# view mode. radius_min/max_pixels caps how big a dot gets on screen
# regardless of zoom -- get_radius is in meters, so without a cap, zooming in
# on a dense cluster blew every dot up to the point of solid overlap.
layers = [
    pdk.Layer(
        "ScatterplotLayer", df[MAP_COLS], get_position=["lon", "lat"], get_fill_color="fill_color",
        get_radius="radius", radius_units="meters", radius_min_pixels=2, radius_max_pixels=9,
        pickable=True,
    ),
]
# No static on-map name labels -- venue names only ever show in the hover
# tooltip, not as always-on text painted over the map.

view_state = pdk.ViewState(latitude=40.70, longitude=-73.95, zoom=9.6, pitch=0)

# deck.gl's default scroll-zoom is speed 0.01; the first pass here (0.006) was
# actually *below* that default, which is why it felt sluggish rather than
# less sticky. Bumping speed well above default gets more zoom per tick, kept
# smooth (continuous interpolation instead of discrete snapping) so it still
# doesn't feel jumpy at the higher speed.
view = pdk.View(
    type="MapView",
    controller={"scrollZoom": {"speed": 0.03, "smooth": True}, "inertia": 150},
)

st.pydeck_chart(
    # "light" asks pydeck for its built-in light/gray Carto basemap (no Mapbox
    # token needed) instead of the darker default -- a plainer, lighter
    # background so the venue colors read clearly against it.
    pdk.Deck(
        layers=layers,
        views=[view],
        initial_view_state=view_state,
        tooltip=TOOLTIP,
        map_style="light",
    ),
    use_container_width=True,
    height=640,
)


def render_legend(mode: str):
    """A drawn gradient-bar legend (not text): the diverging purple/orange bar
    for Residual, or the sequential blue bar for Actual/Expected. Every dot is
    the same size now -- persistence/significance moved to the evidence
    charts and table below, so there's no ring swatch to explain here."""
    if mode == "Residual":
        gradient = f"linear-gradient(90deg, {hex_of(RES_PURPLE)}, {hex_of(NEUTRAL)}, {hex_of(RES_ORANGE)})"
        caption = "Residual vs. expected mixing"
        left_label, mid_label, right_label = "less mixed", "expected", "more mixed"
    else:
        gradient = f"linear-gradient(90deg, {hex_of(SEQ_LOW)}, {hex_of(SEQ_HIGH)})"
        caption = f"{mode} mixing score (this period's 2nd&ndash;98th percentile range)"
        left_label, mid_label, right_label = "lower mixing", "", "higher mixing"

    mid_html = f"<span>{mid_label}</span>" if mid_label else "<span></span>"
    st.markdown(
        f"""
        <div style="font-family:{MONO}; margin-top:2px;">
          <div style="font-weight:600; text-transform:uppercase; letter-spacing:0.03em;
                      font-size:10.5px; color:#8a8a86; margin-bottom:6px;">{caption}</div>
          <div style="height:10px; border-radius:5px; background:{gradient};
                      border:1px solid rgba(0,0,0,0.15);"></div>
          <div style="display:flex; justify-content:space-between; font-size:10.5px;
                      color:#8a8a86; margin-top:4px;">
            <span>{left_label}</span>{mid_html}<span>{right_label}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


render_legend(view_mode)

# ------------------------------------------------------------- stats -------

s = stats.loc[month_key]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Venues shown", f"{len(df):,}")
c2.metric(
    "Model CV R²",
    f"{s['cv_r2']:.3f}",
    help="Mean over 5 spatially-blocked folds (grouped by ~610m grid cell), "
         f"range {s['cv_r2_fold_min']:.3f}–{s['cv_r2_fold_max']:.3f} this period.",
)
c3.metric(
    "Significant (FDR q<.05)",
    int(df["fdr_sig_05_hk"].sum()),
    help="REML+Hartung-Knapp pooled residual, Benjamini-Hochberg corrected across all "
         "pooled venues -- the strictest bar used in this project.",
)
c4.metric(
    "Persists 4+ periods",
    int((df["persistence_tier"] == "current_period_persistence").sum()),
    help="Pooled across 4 or more of the project's 8 periods (not a full annual cycle yet).",
)

# ------------------------------------------------------- evidence charts ---
# Persistence tier and FDR significance used to be drawn as rings on the map
# dots; they're broken out here instead, as charts and a table, for this
# period's venues (df, same filtering as the map above).

TIER_ORDER = [
    ("single_month_not_tested", "1. Not yet tested"),
    ("repeated_evidence", "2. Seen 2 periods"),
    ("provisional_persistence", "3. Persists 3 periods"),
    ("current_period_persistence", "4. Persists 4+ periods"),
]
TIER_LABEL = dict(TIER_ORDER)
TIER_LABEL_ORDER = [lbl for _, lbl in TIER_ORDER]
SIG_LABEL = {True: "Significant (FDR q<.05)", False: "Not (yet) significant"}

st.divider()
st.subheader("Evidence breakdown")
st.caption(f"All for {month_choice}'s {len(df):,} venues -- same scope as the map above.")

tab_tier, tab_cat, tab_borough, tab_table = st.tabs(
    ["Tier & significance", "By category", "By borough", "Top significant venues"]
)

with tab_tier:
    tier_df = df.copy()
    tier_df["Tier"] = pd.Categorical(
        tier_df["persistence_tier"].map(TIER_LABEL), categories=TIER_LABEL_ORDER, ordered=True
    )
    tier_df["Significance"] = tier_df["fdr_sig_05_hk"].map(SIG_LABEL)
    tier_counts = (
        tier_df.groupby(["Tier", "Significance"], observed=True).size().reset_index(name="Venues")
    )
    st.bar_chart(tier_counts, x="Tier", y="Venues", color="Significance")
    st.caption(
        "How many venues have reached each stage of cross-period pooling, split by whether "
        "their pooled residual clears the FDR-corrected significance bar. A venue can reach "
        "the top tier (pooled across all periods it's been eligible for) without ever turning "
        "significant -- persistence alone isn't evidence of an unusual venue, only enough data "
        "to test whether it is one."
    )

with tab_cat:
    cat_stats = (
        df.groupby("top_category")
        .agg(n=("placekey", "size"), mean_resid=("mixing_residual_z", "mean"),
             pct_sig=("fdr_sig_05_hk", "mean"))
        .reset_index()
    )
    cat_stats = cat_stats[cat_stats["n"] >= 30].sort_values("n", ascending=False).head(15)
    cat_stats["pct_sig"] = (cat_stats["pct_sig"] * 100).round(1)
    cat_stats = cat_stats.sort_values("mean_resid")
    cat_stats["top_category"] = pd.Categorical(
        cat_stats["top_category"], categories=cat_stats["top_category"], ordered=True
    )
    st.bar_chart(cat_stats, x="top_category", y="mean_resid", horizontal=True)
    st.caption(
        "Mean residual z-score by top category, for the 15 categories with the most venues "
        "this period (at least 30). Positive (right) means that category tends to mix more "
        "than the model expects for where its venues sit; negative (left) means less. "
        "This is top_category, not sub_category, since sub_category is missing for ~7% of "
        "venues and top_category is always present."
    )

with tab_borough:
    borough_stats = (
        df.groupby("borough")
        .agg(n=("placekey", "size"), pct_sig=("fdr_sig_05_hk", "mean"),
             pct_persist4=("persistence_tier", lambda s: (s == "current_period_persistence").mean()))
        .reset_index()
    )
    borough_stats["pct_sig"] = (borough_stats["pct_sig"] * 100).round(1)
    borough_stats["pct_persist4"] = (borough_stats["pct_persist4"] * 100).round(1)
    bc1, bc2 = st.columns(2)
    with bc1:
        st.bar_chart(borough_stats, x="borough", y="pct_sig", y_label="% significant")
    with bc2:
        st.bar_chart(borough_stats, x="borough", y="pct_persist4", y_label="% persisting 4+ periods")
    st.caption(
        "Not mean residual by borough -- residuals are z-scored *within* borough, so that "
        "mean is ~0 everywhere by construction. These instead show the share of each "
        "borough's venues that clear FDR significance, and the share that have persisted "
        "4 or more periods."
    )

with tab_table:
    sig_df = df[df["fdr_sig_05_hk"]].copy()
    if sig_df.empty:
        st.info("No FDR-significant venues this period.")
    else:
        sig_df["Tier"] = sig_df["persistence_tier"].map(TIER_LABEL)
        show_cols = {
            "location_name": "Venue", "borough": "Borough", "top_category": "Category",
            "mixing_residual_z": "Residual z", "Tier": "Tier", "n_months": "Periods pooled",
            "q_bh_hk": "FDR q",
        }
        top_pos = sig_df.nlargest(15, "mixing_residual_z")[list(show_cols)].rename(columns=show_cols)
        top_neg = sig_df.nsmallest(15, "mixing_residual_z")[list(show_cols)].rename(columns=show_cols)
        st.markdown("**Most mixed beyond expectation**")
        st.dataframe(top_pos, hide_index=True, use_container_width=True)
        st.markdown("**Most segregated beyond expectation**")
        st.dataframe(top_neg, hide_index=True, use_container_width=True)
        st.caption(
            "Top 15 each way among this period's FDR-significant venues, by residual z-score."
        )
