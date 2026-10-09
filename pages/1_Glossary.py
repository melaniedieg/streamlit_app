"""
Glossary / methodology reference page for the NYC Mixing Map.

Streamlit auto-discovers any .py file under pages/ next to the main app.py
and adds it to the sidebar nav -- no routing code needed. This page is
self-contained (it re-declares its own page config and font CSS, since each
page in a Streamlit multipage app runs as its own script) so it works whether
someone lands here directly or clicks through from the map.
"""
import streamlit as st

st.set_page_config(page_title="NYC Mixing Map -- Glossary", layout="wide")

MONO = 'ui-monospace, "SF Mono", "Cascadia Code", "Roboto Mono", Consolas, "Liberation Mono", monospace'
st.markdown(
    f"""
    <style>
    html, body, [class*="css"], .stMarkdown {{
        font-family: {MONO} !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Glossary")
st.caption(
    "What every number, color, and ring on the map means. The map itself is on the "
    "other page in the sidebar."
)

st.markdown(
    """
### Scores (per venue, per period)

**Actual mixing score** -- how evenly this venue's visitors are spread across
NYC-wide income quintiles, estimated from each visitor's home Census block
group. It runs roughly 0-1; closer to 1 means visitors are spread evenly
across income levels, lower means visitors skew toward one or two income
groups. This is the venue's own observed score for that period -- nothing
modeled about it yet.

**Expected mixing score** -- the score a model predicts for this venue from
where it sits: its borough, neighborhood income and racial composition,
commercial density, subway access, and tourist proximity. It's a statistical
baseline for what a venue in that context *should* score, not the venue's own
actual behavior. The model is a Random Forest (300 trees, max depth 8,
min 20 samples/leaf), weighted by each venue's count of visitor devices with
a known home income.

**Residual** (`mixing_residual_z` in the data) -- actual minus expected,
z-scored *within borough* (not citywide) so a venue is only compared against
other venues in the same borough. Borough-proportional scoring matters
because a flat citywide cutoff undercounts small boroughs -- some genuinely
unusual venues are extreme for their own borough but wouldn't clear a flat
citywide threshold. Positive (orange) means more mixed than the model
expects for a venue in that spot; negative (purple) means less.

**Balance score** -- a secondary, simpler measure of how evenly visitor
income quintiles are spread, shown alongside the main mixing score in the
tooltip for cross-reference. It's not what the map colors or sizes by.

**Visitor devices** (`income_known_devices`) -- the count of distinct mobile
devices seen at that venue in that period for which a home income quintile
could be estimated. Venues below a minimum device floor aren't included at
all, since a handful of devices can't support a reliable mixing estimate.

---

### Cross-validation (Model CV R²)

The R² shown for each period comes from **spatially-blocked** cross-validation:
venues are grouped into roughly 610-meter grid cells, and each of 5 folds
holds out whole grid cells rather than a random 20% of individual venues. A
plain random split scores noticeably higher (and is reported nowhere in this
app) because nearby venues' residuals are correlated -- a venue's neighbors
leak information about it into a random training fold in a way they can't
when the whole neighborhood is held out together. The spatially-blocked
number is the more honest estimate of how well the model generalizes to a
genuinely new location.

---

### Persistence (across periods)

This project currently spans 8 independently-rebuilt periods (Dec 2025-Jul
2026). A venue's residual is pooled across every period it was eligible in,
using inverse-variance-weighted meta-analysis (REML-estimated
between-period variance, Hartung-Knapp adjustment for the small number of
periods), and that pooled result is what the persistence tier and
significance flag below describe. Pooling only tells you how consistent a
venue's residual has been across time -- it is a separate question from
whether that pooled residual is large enough to call a real effect, which is
what FDR significance (next section) answers.

**Persistence tier** (ring size on the map; Residual view only):

- *Single period, not yet tested* -- eligible in only one period so far;
  nothing to pool yet. No ring.
- *Seen in 2 periods* -- smallest ring.
- *Persists across 3 periods* -- medium ring.
- *Persists across 4+ periods* -- largest ring. Note this is explicitly
  **not** "annual persistence" -- the project doesn't yet span a full
  seasonal cycle.

**Significant, FDR q < .05 (HK)** -- a solid black ring (vs. a thin gray one)
marks that a venue's pooled residual clears a Benjamini-Hochberg false-discovery-rate
correction at q < .05, applied across every pooled venue at once (not a
per-venue p < .05, which would produce far too many false positives across
tens of thousands of venues). This is the strictest bar used anywhere in this
project. A venue can have the largest ring (persisting all 8 periods) and
still not be black-ringed, if its pooled effect size never clears that bar --
that's deliberate: being observed a long time isn't the same as being an
unusual venue, only enough data to test whether it is one.

---

### Categories

**Top category / sub-category** -- the venue's broad and specific business
category (e.g. top category "Museums, Historical Sites, and Similar
Institutions", sub-category "Nature Parks and Other Similar Institutions").
About 7% of venues are missing a sub-category and fall back to showing their
top category instead, both in this data and in the map's tooltip.
"""
)

st.page_link("app.py", label="Back to the map", icon="🗺️")
