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
same modeling pipeline as `income_mixing_model.ipynb` in the main repo.

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

`data/venues_2026-0{5,6,7}.csv` -- one row per venue per month: location,
category, borough, device count, the raw mixing/balance scores, the model's
expected scores, the residual z-scores, and the bootstrap-stability /
cross-month-replication evidence tier. `data/month_stats.csv` holds each
month's overall cross-validated R².

These were exported from the same pickled model outputs described in the main
repo's `README.md` -- regenerate them with `export_streamlit_data.py` there if
the underlying model changes.

## Notes

- A segmented toggle above the map (next to the Month dropdown) switches
  between three views -- **Actual** mixing, **Expected** mixing (the model's
  baseline prediction), and **Residual** (actual minus expected, z-scored
  within borough). Actual and Expected share one pale-to-dark blue sequential
  scale, since they're the same kind of measurement shown twice; Residual
  uses a purple (less mixed than expected) <-> gray (as expected) <-> orange
  (more mixed than expected) diverging scale. Every color domain is that
  month's own 2nd-98th percentile range rather than a flat scale, since the
  underlying scores cluster near the top of their theoretical range and a
  flat domain made almost everything look the same shade. A one-sentence
  definition of whichever measure is selected appears under the toggle.
- Evidence-tier rings (thin ring = bootstrap-stable in that one month, thick
  ring = confirmed independently in 2-3 separate monthly rebuilds) only
  appear in the Residual view, since they describe a venue's *residual*
  stability -- on Actual/Expected every venue is drawn as the same plain dot,
  so the sizing doesn't imply something the map isn't actually showing.
- No borough or category filters -- residuals are already z-scored within
  borough, so a filter mostly just declutters rather than revealing anything
  new, and panning/zooming the map does the same job. The hover tooltip
  shows each venue's sub-category (falling back to its broader top-category
  for the ~7% of venues missing one) instead.
- The whole app (including the map's hover tooltip) uses a monospace/coding
  font stack, matching the HTML map. The pydeck map's scroll-zoom controller
  is tuned above deck.gl's default speed, with smooth interpolation, so it
  doesn't feel sluggish or snap in discrete steps.
- This was built and syntax-checked in an environment without network access
  to install Streamlit/pydeck, so it hasn't been run end-to-end here -- test
  it locally before relying on it. The color/radius/groupby logic was
  verified separately against the real CSV data with plain pandas/numpy.
