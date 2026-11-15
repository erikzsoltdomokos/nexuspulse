# Prompt handed to the Kiro agent (written by Gemini, used unchanged)

Kiro prompt: "Start a new project with the following specification:" followed by the text below. Follow-up prompt after the agent asked clarifying questions: "no need to save tokens for now. do as much as you can, you have free rein"

---

# Project Specification: NexusPulse -- Multi-Scale LoL Timeline Analytics & Behavioral Forensics

## 1. Executive Summary & Objective
Build a full-stack, machine-learning-powered analytics platform for League of Legends that processes minute-by-minute timeline match data (`Match-v5 Timeline` from the Riot Games API).

The platform integrates three interdependent analytical layers into a synchronized, interactive dashboard:
1. **Compositional Power Spike Modeling (Macro Theoretical):** Modeling non-linear champion/team scaling curves over time based on level and item thresholds.
2. **Match Momentum & Win-Probability Inflection (Macro Empirical):** Tracking real-time win probability shifts minute-by-minute and using feature attribution (SHAP) to explain turning points.
3. **Player Stability & Tilt Anomaly Detection (Micro Behavioral):** Identifying statistically significant performance collapses and behavioral deviations in individual players following key macro events.

## 2. System Architecture

### 2.1 Backend Pipeline (Python)
- **Framework:** FastAPI or Flask (REST API).
- **Data Collection & Ingestion:**
  - Riot Games API client (`Summoner-v4`, `Match-v5`, `Match-v5 Timeline`).
  - Rate-limit handler (respecting Riot's default 100 requests / 2 minutes) with exponential backoff and caching.
  - Storage: SQLite / PostgreSQL with SQLAlchemy for caching match data, timeline frames, and processed features.
- **Machine Learning Tooling:** `scikit-learn`, `xgboost` / `lightgbm`, `shap`, `pygam` / `scipy` (for non-linear spline regression), `pandas`, `numpy`.

### 2.2 Frontend Client (Web)
- **Stack:** Modern responsive web interface (HTML5, Tailwind CSS, JavaScript/TypeScript or React).
- **Visualization Libraries:**
  - `Chart.js` with synchronized crosshairs (or `ECharts` / `Plotly.js`) to align power curves, win probability, and anomaly events on an identical time axis.
  - Radar chart for player breakdown and metric attribution bars for SHAP values.

## 3. Core Modules & ML Methodologies

### Module A: Non-Linear Compositional Power Spikes (Theoretical Baseline)
- **Purpose:** Model expected power output per champion and aggregate them into team-wide scaling trajectories across 0-40 minutes.
- **Features Extracted:** Level milestone timing (levels 6, 11, 16); completed item count (`totalDamage`, `health`, `abilityPower`, `itemCostSum`); baseline champion scaling coefficients (early, mid, late game tiers).
- **Algorithm:** Generalized Additive Models (GAM) with cubic splines or polynomial regression fitted against historic gold-to-damage efficiency per minute.
- **Output:** Normalized team scaling index [0, 100] evaluated per minute, delineating theoretical power windows (e.g., "Team Blue peak window: 18-26 minutes").

### Module B: Time-Series Match Momentum & Explainable Inflections (Empirical State)
- **Purpose:** Estimate cumulative win probability at minute t ∈ [1, N] and isolate game-breaking inflection points.
- **Features Extracted (Per-Minute Sliding Vector):** Gold difference (`totalGoldDiff`, `goldPerMinRatio`); objective differentials (dragons, barons, heralds, voidgrubs, turret plate counts); XP difference, alive team member count, kill/death differential.
- **Algorithm:** XGBoost / LightGBM Binary Classifier trained on high-tier match timeline snapshots.
- **Model Explainability:** TreeSHAP (`shap.TreeExplainer`) computed for high-gradient transitions where |ΔP(Win)| ≥ δ (inflection points).
- **Output:** Minute-by-minute win probability curve P(Win_t); anomaly markers on turning points with top-3 local SHAP feature contributions (e.g., *+22% Blue Win Probability driven by: Baron Kill (+14%), Tower Bounty (+6%), CS Differential (+2%)*).

### Module C: Player Tilt & Performance Anomaly Detection (Micro Layer)
- **Purpose:** Detect whether an individual player suffered an abnormal behavioral or mechanical collapse following a death or macro objective loss.
- **Features Extracted (Player Metrics Over 3-Minute Sliding Windows):** CS delta relative to lane baseline; isolated deaths in unwarded or deep enemy territory; experience gain velocity (ΔXP / Δt); vision placement frequency.
- **Algorithm:** Isolation Forest or One-Class SVM trained on normal player play patterns.
- **Output:** Continuous "Performance Stability Score" [0, 100]; anomaly flags timestamped on the timeline (e.g., *"Tilt event flagged at 17:00: CS dropped 68% and 2 isolated deaths logged post-dragon defeat"*).

## 4. REST API Endpoint Design

```text
GET /api/health
POST /api/collect-match
  Payload: { "match_id": "EUW1_123456789" }
  Response: Status confirmation, ingestion state.
GET /api/analysis/{match_id}/overview
  Response: Basic match meta (champions, outcome, duration, KDA).
GET /api/analysis/{match_id}/timeline-dynamics
  Response: { "timeline": [ { "minute", "team_blue_power_index", "team_red_power_index",
              "win_probability_blue", "is_inflection_point", "shap_summary" }, ... ],
              "player_anomalies": [ { "puuid", "champion", "minute", "anomaly_type",
              "severity", "description" } ] }
```

## 5. UI/UX Dashboard Requirements
- **Master Timeline Chart:** primary line: Win Probability (Blue vs. Red); secondary background area: Expected Team Power Spikes (Theoretical); interactive tooltips: hovering over any minute reveals the gold state, items completed, and live SHAP attribution breakdown.
- **Inflection Event Cards:** clicking a flagged momentum swing pans the timeline to that exact minute and opens the SHAP decomposition.
- **Player Stability Tracker:** visual lane ribbons below the main chart showing the 10 players; colored pills indicate moments of detected statistical collapse or "tilt."
- **Clean Esports Dark Theme:** slate/zinc background #0f172a, cyan #06b6d4 for Blue side, rose #f43f5e for Red side, amber #f59e0b for inflection/anomaly indicators.

## 6. Implementation Milestones
- **Phase 1: Ingestion & Storage:** Riot API client, rate limiting, cache raw match and timeline JSON to a local database.
- **Phase 2: Feature Engineering & Baseline Models:** timeline tabular dataset; XGBoost win-probability classifier; Isolation Forest for micro anomalies; non-linear scaling curves.
- **Phase 3: SHAP Integration & API Setup:** FastAPI endpoints exposing inference and SHAP explainability matrices.
- **Phase 4: Web Dashboard Development:** frontend visualization, REST integration, time-synchronized charting.
