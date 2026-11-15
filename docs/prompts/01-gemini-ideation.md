# Phase 0 – Ideation with Google Gemini

The user's prompts are quoted verbatim. Gemini's answers are condensed; the original chat is kept in the author's Gemini history.

## Prompt 1
> what interesting public APIs are there from which you could make interesting personal projects. like for example i want to make a stock exchange predictor ai, that connects to stock exchange api. what other possibilities that are interesing are out there?

**Gemini (summary):** It warned that stock prediction is hard because news drives markets. It then listed API categories with project ideas: NASA NeoWs and Open-Meteo, the Spotify Web API, sports and esports APIs (balldontlie, the Riot Games API with an "e-sports win probability tracker"), civic data (ProPublica, OpenFEMA, OpenStreetMap) and art/media APIs (the Met, TMDB, PokeAPI).

## Prompt 2
> the riot games api is intersting. i play league, what interesting projects can i make?

**Gemini (summary):** A tilt predictor built on Match-v5 Timeline, a duo-synergy tracker, a 10-minute win-probability engine (Random Forest/XGBoost) and LCU client automation. It also mentioned rate limits and API keys.

## Prompt 3
> Coming back to this chat because I found a use case for this. I have a university subject called Applied Artifical Inteligence Models in Practice where I have to make a project where you build some kind of AI application. I think I want to make it with the League API. Any interesting projects, ideas?

**Gemini (summary):** Four academically viable ideas: early-game win prediction with feature importance, player skill clustering (K-Means/DBSCAN), a composition synergy grader (one-hot encoding + NN, ablation study) and jungler pathing heatmaps (KDE/LSTM). It warned about the 100 requests / 2 minutes development-key limit, so data has to be scraped slowly into SQLite/CSV.

## Prompt 4
> I definetly want a web page where something is visualized

**Gemini:** Generated a single-file prototype dashboard (Tailwind + Chart.js) with a simulated live win-probability line chart and a cluster scatter plot. This prototype was attached to the topic-approval email to the lecturer.

## Prompt 5
> yeas something like this will work. think of projects like this where data or predictions,insights can be visualized

**Gemini (summary):** Four visual projects: a draft synergy and counter engine (radar, network graph, gauge), a jungler pathing heatmap on a map canvas with a time slider, a match momentum and anomaly tracker (win-probability line + Isolation Forest anomaly markers) and playstyle dimensionality reduction (PCA/t-SNE + K-Means). Suggested stack: FastAPI/Flask + Chart.js.

## Prompt 6 – topic sentence
> irj egy mondatot

**Gemini:** "A Riot Games API-ból kinyert mérkőzésadatok alapján egy in-game nyerési esélyeket becslő gépi tanulási modellt fejlesztek…" (plus two variants)

> nem feltétlen a win%ot akarom kinyerni, ennel legyel altalanosabb

**Gemini:** "A League of Legends API-ból kinyert mérkőzésadatok alapján gépi tanulási modelleket tanítok játékon belüli mintázatok és összefüggések feltárására, amelyeket egy interaktív webes felületen vizualizálok." → **this became the submitted topic.**

## Prompt 7
> ez lett végül a házibeadás: (topic sentence)

**Gemini:** Confirmed that the wording is general enough to choose the ML task later, and pointed out that data collection would be the bottleneck because of the rate limit.

## Prompt 8
> előbb kicsit pontosítsuk, hogy milyen érdekes projektet lehetne megvalósítani. sorolj fel 10 ilyet kezdésnek

**Gemini (summary):** Ten ideas: playstyle archetypes (clustering), time-series momentum with XGBoost + SHAP, spatial gank-risk heatmaps (KDE), a champion synergy recommender (association rules/GNN), tilt detection (Isolation Forest/One-Class SVM), objective value estimation (Random Forest), true-skill regression, scaling curves and power spikes (GAM), rune/item optimisation (decision trees) and gold-lead forecasting (LSTM).

## Prompt 9 – merging three ideas into one project
> ezek mind jül hangzanak, majd szerintem ha a kezdetben megtervezett dolgok működnek, akkor több dolog lesz beépítve a weboldalba. szerintem ez a 3 szorosan kapcsolódik egymáshoz: (2. Momentum, 5. Tilt, 8. Power Spike) … ebből a háromból alkossunk egy nagy projektet. Miután ezt kigondoltad, küldj el egy részletes, angol leírást amit majd beadhatok a kiro agentemnek és elkezdhetek rajta dolgozni

**Gemini:** It explained how the three layers fit together (theoretical scaling → empirical momentum → individual behaviour, all on one shared timeline). It then wrote the full English specification, which is saved in [02-nexuspulse-spec.md](02-nexuspulse-spec.md) and was handed to the Kiro agent unchanged.
