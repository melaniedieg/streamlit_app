---
title: NYC Mixing Map
emoji: 🗺️
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 8501
pinned: false
---

<!-- The YAML block above is Hugging Face Spaces metadata -- it's what tells
     a Space to build this repo's Dockerfile and which port to route traffic
     to. It's inert/ignored everywhere else this README is read (GitHub,
     local viewing, etc.), so it's safe to leave in even if you're not using
     Spaces. -->

# NYC Mixing Map (Streamlit)

A Streamlit + pydeck version of the interactive venue-mixing map, built from the
same modeling pipeline as the `income_mixing_methodology/` notebooks and scripts
in the main repo.

## Run locally

```
pip install -r requirements.txt
streamlit run app.py
```

Opens at `http://localhost:8501`. No API keys or tokens required -- pydeck's
default basemap (CARTO) works without one.

## Deploy for free

The easiest option is [Streamlit Community Cloud](https://streamlit.io/cloud):
push this folder to a GitHub repo (it can live inside `public_life`, e.g. as a
`streamlit_app/` subfolder), sign in at share.streamlit.io with that GitHub
account, and point it at `streamlit_app/app.py`. It redeploys automatically on
every push.

**Note:** Community Cloud's free tier runs on a small shared resource pool
(around 1 CPU / 1GB RAM), which can make the app feel sluggish or unresponsive
under real use even after the code itself is optimized -- see the Hugging
Face Spaces option below for a free tier with meaningfully more headroom
(2 vCPU / 16GB RAM as of this writing).

### Hugging Face Spaces (more resources, still free)

1. Create a Space at [huggingface.co/new-space](https://huggingface.co/new-space):
   pick a name, choose **Docker** as the Space SDK, and **CPU basic (free)**
   as the hardware.
2. Hugging Face gives the new Space its own git remote
   (`https://huggingface.co/spaces/<your-username>/<space-name>`). Add it
   alongside this repo's existing remote and push:
   ```
   git remote add space https://huggingface.co/spaces/<your-username>/<space-name>
   git push space main
   ```
   (You'll be prompted for a Hugging Face access token as the password --
   generate one under Settings -> Access Tokens if you don't have one.)
3. This repo already has the `Dockerfile` and README frontmatter Spaces
   needs (`sdk: docker`, `app_port: 8501`) -- pushing triggers an automatic
   build. Watch progress under the Space's "Logs" tab; once it says
   "Running," the app is live at the Space's URL.
4. Every future `git push space main` rebuilds and redeploys automatically,
   same as Community Cloud.

## Data

`data/venues_<period>.csv` -- one row per venue per period, for all 8 periods
currently pooled in the project (`2025-12`, `2026-01` through `2026-07`):
location, category, borough, device count, the raw mixing/balance scores, the
model's expected score from a **spatially-blocked** cross-validation (grouped
by ~610m grid cell -- not a plain random split, since nearby venues'
residuals are correlated 0.52-0.61 and a random split overstates fit), the
residual z-score (within borough), and that venue's cross-period persistence
evidence: `persistence_tier` (`single_month_not_tested` / `repeated_evidence`
/ `provisional_persistence` / `current_period_persistence`, by how many of
the 8 periods it's been pooled across), `n_months` and `months` (which ones),
and `mu_hk` / `q_bh_hk` / `fdr_sig_05_hk` -- the REML+Hartung-Knapp pooled
residual and its Benjamini-Hochberg FDR-corrected significance, the
strictest bar used anywhere in this project. Also `display_category`, which
equals `top_category` except for one relabeled case (see Notes below).
A `placekey` is a group id (`GRP#####`), not a raw POI id, for the ~265
venues that are really several merged POI records -- see Notes. `data/month_stats.csv`
holds each period's cross-validated R² (mean and fold range).

These are exported from the same pickled model + persistence-pooling outputs
described in `income_mixing_methodology/README.md` -- regenerate them with
`income_mixing_methodology/export_streamlit_data.py` if the underlying model
or pooling changes. That script also documents, in its own header comment,
why it reads `expected_mixing_cv`/`cv_full` and not a separately-refit model.

## Notes

- A segmented toggle above the map (next to the Month dropdown) switches
  between three views -- **Actual** mixing, **Expected** mixing (the model's
  baseline prediction), and **Residual** (actual minus expected, z-scored
  within borough). Actual and Expected share one pale-to-dark blue sequential
  scale, since they're the same kind of measurement shown twice; Residual
  uses a purple (less mixed than expected) <-> gray (as expected) <-> orange
  (more mixed than expected) diverging scale. Every color domain is that
  period's own 2nd-98th percentile range rather than a flat scale, since the
  underlying scores cluster near the top of their theoretical range and a
  flat domain made almost everything look the same shade. A one-sentence
  definition of whichever measure is selected appears under the toggle.
- The map itself only colors by residual now -- persistence tier and FDR
  significance used to be drawn as rings on the dots (size for tier, a black
  vs. gray stroke for significance), but color + size + two ring styles all
  on one small dot read as crowded. That evidence moved into an "Evidence
  breakdown" section below the map instead: a tier-and-significance bar
  chart, mean residual by category, significance/persistence rate by
  borough, and a table of the period's top FDR-significant venues (most
  mixed and most segregated beyond expectation). A venue can be in the
  largest persistence tier (pooled across all 8 periods) and still not be
  significant, if its pooled effect size never clears the FDR bar -- that
  distinction is deliberate, since persistence alone isn't evidence of an
  unusual venue, only enough data to test whether it is one.
- Two known data issues were found and fixed during a defensibility review:
  a handful of venues (265 groups -- places with inconsistent POI names over
  time, like Jacob Riis Park) used to draw as 2-3 separate dots for one
  physical place; they're now collapsed to one row per period. And the
  category breakdown relabels one specific case -- venues filed under
  "Museums, Historical Sites, and Similar Institutions" are ~91% nature
  parks by sub-category, not museums -- so that chart doesn't read as a
  museum pattern when it's really a park one. Both are explained in the
  Glossary page and in `export_streamlit_data.py`'s header comment.
- No borough or category filters -- residuals are already z-scored within
  borough, so a filter mostly just declutters rather than revealing anything
  new, and panning/zooming the map does the same job. The hover tooltip
  shows each venue's sub-category (falling back to its broader top-category
  for the ~7% of venues missing one) instead.
- The whole app (including the map's hover tooltip) uses a monospace/coding
  font stack, matching the HTML map. The pydeck map's scroll-zoom controller
  is tuned above deck.gl's default speed, with smooth interpolation, so it
  doesn't feel sluggish or snap in discrete steps.
- This version has been run end-to-end with Streamlit's `AppTest` harness
  (full script execution with no exceptions, correct computed stats checked
  against the exported CSVs) and as a live local server, which the original
  three-month version hadn't been -- still worth a quick click-through
  locally after any further change, since `AppTest` doesn't drive the actual
  browser/deck.gl rendering. The color/radius/tier/tooltip logic was also
  verified directly against the real CSV data for all 8 periods with plain
  pandas/numpy.
