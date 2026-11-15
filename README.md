# NexusPulse

Multi-scale League of Legends timeline analytics: power-spike modeling, win-probability
momentum with SHAP explanations, and player tilt detection, in one synchronized dashboard.

**Live demo:** [erikzsoltdomokos.github.io/nexuspulse](https://erikzsoltdomokos.github.io/nexuspulse/)
(static build with 46 precomputed real matches; live data collection is disabled there).

## Static demo (GitHub Pages)

The demo is the normal dashboard built with `vite build --mode static` (`VITE_STATIC=1`, base
`/nexuspulse/`): every `GET /api/...` call reads `<base>api/....json` instead of the backend.
`backend/scripts/export_static.py` produces those files by calling the real endpoints in-process
for the author's games plus the most interesting real games (comebacks, many inflections).
No Riot key or `.env` content is exported.

Rebuild and publish (needs the trained models in `backend/data/`, `gh` logged in):

```powershell
powershell -ExecutionPolicy Bypass -File backend\scripts\deploy_pages.ps1          # build, export, commit, push
powershell -ExecutionPolicy Bypass -File backend\scripts\deploy_pages.ps1 -NoPush  # stop before the push
```

The script keeps a worktree of the orphan `gh-pages` branch in `backend\data\gh-pages`, replaces
its contents with `frontend\dist-static` (+ `.nojekyll`), commits, runs `git push origin gh-pages`
and makes sure Pages serves `gh-pages:/`. To preview locally: `cd frontend; npm run build:static`,
then export with `backend\.venv\Scripts\python.exe backend\scripts\export_static.py`.

## Layout

```
backend/   Python 3.14, FastAPI, SQLAlchemy (SQLite default), XGBoost, SHAP, pygam, scikit-learn
frontend/  Vite + React + TypeScript + Tailwind + ECharts dashboard
```

## Quick start (Windows PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env          # optional: add RIOT_API_KEY
.\.venv\Scripts\python.exe -m nexuspulse serve    # http://127.0.0.1:8000

cd ..\frontend
npm.cmd install
npm.cmd run dev                                   # http://127.0.0.1:5173 (proxies /api)
```

On first start with no trained models, the server seeds 1,000 synthetic Riot-format matches
and trains all three models in the background (~1 minute). `npm.cmd run build` produces
`frontend/dist`, which the API then also serves at http://127.0.0.1:8000.

## CLI

```powershell
python -m nexuspulse seed-synthetic --n 1000       # synthetic corpus (source=synthetic)
python -m nexuspulse collect-match EUW1_1234567890 # one match + timeline (needs RIOT_API_KEY)
python -m nexuspulse collect-player "Name#TAG" --count 20
python -m nexuspulse crawl --max-matches 1000 --tier challenger   # high-tier training data
python -m nexuspulse train [--source riot|synthetic]
python -m nexuspulse serve [--port 8000]
```

Training uses Riot matches alone once 200+ are cached, otherwise everything in the cache.
At the dev-key limit (100 requests / 2 min, 2 requests per match) 1,000 matches take ~40 min.

## Models

| Layer | Method | Output |
|---|---|---|
| A. Power spikes | `pygam` LinearGAM: splines on level, item gold, item stats + tensor term minute x champion tier (spline-ridge fallback). Target: damage to champions per minute over the next 2 min | Team power share index 0-100 per minute, peak windows |
| B. Momentum | XGBoost classifier on 16 per-minute differentials, monotone constraints, match-grouped holdout | P(blue win) per minute; TreeSHAP state attribution; transition attribution at inflections (abs(dP) >= 0.08, minute >= 3), scaled to probability points |
| C. Tilt | Isolation Forest per role on 3-min windows: CS/XP/ward ratios vs role-minute baseline (capped at ~1 so only collapses are anomalous), isolated deaths, deaths | Stability score 0-100 (empirical CDF), typed anomaly events with trigger (own death / objective loss) |

Evaluation on the synthetic corpus (1,000 matches): win-prob holdout AUC 0.77 overall,
per-minute AUC 0.65 @5 -> 0.72 @10 -> 0.80 @15 -> 0.85 @20 -> 0.87 @25
(`scripts/evaluate.py`, run with `PYTHONPATH=.`). Re-check on real data after crawling.

## Known limitations

- Timeline data has kill positions but no ward positions: "isolated death" = no living ally
  within 2,500 units or deep in enemy territory, not true vision coverage.
- Champion scaling tiers are a curated heuristic (`static_data.py`), not Riot data.
- Synthetic matches are for development and demos only; their dynamics are simulated.
- The API has no authentication; it binds to 127.0.0.1. Public deployment needs auth and a
  Riot production key (Riot's developer policies apply).

## Tests

```powershell
cd backend; .\.venv\Scripts\python.exe -m pytest -q
```
