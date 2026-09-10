"""
NYC Mixing Map -- Streamlit + pydeck version

Interactive map of venue-level income mixing across three independently-rebuilt
months (May-Jul 2026). Reads the per-month CSVs in data/ (built by
export_streamlit_data.py from the modeling pipeline's pickled outputs -- see
the main repo's README.md for what those scores mean and how they're built).

Run with:
    pip install -r requirements.txt
    streamlit run app.py
"""
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

st.set_page_config(page_title="NYC Mixing Map", layout="wide")

MONTH_LABELS = {"May 2026": "2026-05", "June 2026": "2026-06", "July 2026": "2026-07"}

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
    df["evidence_tier"] = df["evidence_tier"].fillna("none")
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

st.title("Where Did New Yorkers Mingle this Summer?")
st.caption(
    "Venue-level model residuals across three independently-rebuilt months "
    "(May-Jul 2026). See the methodology notebook in this repo for how the "
    "score and the model are built."
)

top1, top2, _ = st.columns([1.0, 1.4, 1.2])
with top1:
    month_choice = st.selectbox("Month", list(MONTH_LABELS.keys()), index=1)
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

# Evidence-tier sizing/rings are a Residual-view thing -- they mark venues
# whose *residual* is a stable statistical outlier, which isn't a meaningful
# annotation on a plain Actual/Expected mixing map, so those two views draw
# every venue at the same plain size with no ring.
BASE_RADIUS = 7
if view_mode == "Residual":
    radius_map = {"none": BASE_RADIUS, "stable_single_month": 12, "confirmed_multi_month": 16}
    df["radius"] = df["evidence_tier"].map(radius_map)
else:
    df["radius"] = BASE_RADIUS

tier_note_map = {
    "none": "",
    "stable_single_month": "<br/><i>Bootstrap-stable this month</i>",
    "confirmed_multi_month": "<br/><i>Confirmed 2&ndash;3 independent months</i>",
}
df["tier_note"] = df["evidence_tier"].map(tier_note_map)

# sub_category is missing for a small share of venues (~7%) -- fall back to
# top_category rather than leaving that tooltip line blank.
df["tooltip_category"] = df["sub_category"].fillna(df["top_category"])

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
        "{tier_note}"
    ),
    "style": {
        "backgroundColor": "#0b0b0b",
        "color": "#fcfcfb",
        "fontSize": "12px",
        "fontFamily": MONO,
    },
}

if view_mode == "Residual":
    # split by evidence tier so rings paint above the plain dots
    base_df = df[df["evidence_tier"] == "none"]
    stable_df = df[df["evidence_tier"] == "stable_single_month"]
    confirmed_df = df[df["evidence_tier"] == "confirmed_multi_month"]
    layers = [
        pdk.Layer(
            "ScatterplotLayer", base_df, get_position=["lon", "lat"], get_fill_color="fill_color",
            get_radius="radius", radius_units="meters", pickable=True,
        ),
        pdk.Layer(
            "ScatterplotLayer", stable_df, get_position=["lon", "lat"], get_fill_color="fill_color",
            get_radius="radius", radius_units="meters", pickable=True,
            stroked=True, get_line_color=[11, 11, 11, 200], line_width_min_pixels=1,
        ),
        pdk.Layer(
            "ScatterplotLayer", confirmed_df, get_position=["lon", "lat"], get_fill_color="fill_color",
            get_radius="radius", radius_units="meters", pickable=True,
            stroked=True, get_line_color=[11, 11, 11, 230], line_width_min_pixels=2,
        ),
    ]
else:
    # Actual / Expected: every venue symbolized the same way, no tier rings
    layers = [
        pdk.Layer(
            "ScatterplotLayer", df, get_position=["lon", "lat"], get_fill_color="fill_color",
            get_radius="radius", radius_units="meters", pickable=True,
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
    for Residual, or the sequential blue bar for Actual/Expected. The ring
    swatches only apply to Residual -- Actual/Expected draw every venue the
    same way, so there's nothing on the map for them to explain there."""
    if mode == "Residual":
        gradient = f"linear-gradient(90deg, {hex_of(RES_PURPLE)}, {hex_of(NEUTRAL)}, {hex_of(RES_ORANGE)})"
        caption = "Residual vs. expected mixing"
        left_label, mid_label, right_label = "less mixed", "expected", "more mixed"
    else:
        gradient = f"linear-gradient(90deg, {hex_of(SEQ_LOW)}, {hex_of(SEQ_HIGH)})"
        caption = f"{mode} mixing score (this month's 2nd&ndash;98th percentile range)"
        left_label, mid_label, right_label = "lower mixing", "", "higher mixing"

    mid_html = f"<span>{mid_label}</span>" if mid_label else "<span></span>"
    rings_html = (
        """
          <div style="display:flex; gap:20px; margin-top:10px; flex-wrap:wrap;">
            <div style="display:flex; align-items:center; gap:6px;">
              <span style="width:12px;height:12px;border-radius:50%;border:1.4px solid #52514e;
                           display:inline-block;"></span>
              <span style="font-size:10.5px; color:#52514e;">Bootstrap-stable this month</span>
            </div>
            <div style="display:flex; align-items:center; gap:6px;">
              <span style="width:12px;height:12px;border-radius:50%;border:2px solid #0b0b0b;
                           display:inline-block;"></span>
              <span style="font-size:10.5px; color:#52514e;">Confirmed 2&ndash;3 months</span>
            </div>
          </div>
        """
        if mode == "Residual"
        else ""
    )
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
          {rings_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


render_legend(view_mode)

# ------------------------------------------------------------- stats -------

s = stats.loc[month_key]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Venues shown", f"{len(df):,}")
c2.metric("Model CV R²", f"{s['cv_r2']:.3f}")
c3.metric("Stable, 1 month", int((df["evidence_tier"] == "stable_single_month").sum()))
c4.metric("Confirmed, 2–3 months", int((df["evidence_tier"] == "confirmed_multi_month").sum()))
