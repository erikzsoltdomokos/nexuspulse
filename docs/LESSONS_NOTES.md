# Running notes for the submission document (tanulságok)

Collected during the project; turned into the Hungarian "Tanulságok" section at the end.

## Planning (Gemini ideation)
- Started broad ("interesting public APIs"), narrowed to the Riot API because of personal interest; Gemini generated a prototype dashboard used in the topic-approval email to the lecturer.
- The topic statement was deliberately kept general ("patterns and relationships", not just win%) so the exact ML task could be chosen later.
- Three ideas (momentum+SHAP, tilt anomaly detection, power-spike GAM) were merged into one spec because they share one data source (Match-v5 Timeline) and one time axis.
- Gemini wrote the detailed English spec that was handed to the Kiro coding agent unchanged.

## Building with Kiro (2026-09-30)
- The agent flagged spec gaps before coding: no ward positions in timeline data ("unwarded deaths" only approximable), no official champion scaling tiers (hand-curated), dev-key rate limit (100 req / 2 min, 24 h expiry), tilt baseline must be per role (otherwise supports look anomalous).
- Backend written by the main agent and React dashboard by a parallel subagent against a fixed API contract; the contract held, integration needed no changes on either side.
- No Riot key at build time -> a synthetic generator producing matches in Riot's exact JSON format let the whole pipeline (ingest, training, API, UI) be built and tested end to end first.
- Synthetic-data model scores (AUC 0.65 at min 5 -> 0.87 at min 25) say nothing about real games; real-data results must be reported separately.
- A Kiro Crew safety policy blocked a shell command (false positive on the scratch-dir variable in a redirected command); fixed by writing logs into the project's data/ folder and moving evaluation code into a script file.
- First integration bug: dashboard opened on an empty screen -> auto-select newest match / ?match=<id>.
- Verified only via static screenshots at first; hover/tooltips/click-zoom were not exercised.

## Finishing (2026-11-15, deadline day)
- Real data collection with a 24 h development key.
- Hungarian/English UI toggle added for the Hungarian submission.
- Multi-region: Match-v5 and Account-v1 use regional routing (EUW and EUNE both "europe"), so the user's own EUNE games worked without changes; only the Challenger ladder lookup (League-v4) is per server -> added a --platform flag, training corpus = EUW + EUNE Challenger.
- Key validated by pulling the author's own 20 EUNE ranked games first (Luda1060#ZSID).
- Running a long crawl as a detached background process failed silently (the agent's runtime kills child processes when the shell call returns; the gateway's command scheduler needs a POSIX shell, which Windows lacks) -> the crawl was run in foreground chunks of under 25 minutes by a subagent while the main agent wrote the documentation.
