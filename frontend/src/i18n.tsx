// Minimal hand-written i18n: a typed dictionary, a React context and lookup
// tables for backend enums / feature names. Default language is Hungarian.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { AnomalyType, CollectState, InflectionPoint, RadarMetrics, Severity, ShapFeature, Team } from './types';

export type Lang = 'hu' | 'en';
const STORAGE_KEY = 'nexuspulse.lang';
const DEFAULT_LANG: Lang = 'hu';

const en = {
  // App
  skipToContent: 'Skip to content',
  backendDown: 'Backend unreachable.',
  backendDownDetail: 'The analytics API at /api is not responding (expected on http://127.0.0.1:8000).',
  retry: 'Retry',
  loadDemo: 'Load demo data',
  dismiss: 'Dismiss',
  dismissError: 'Dismiss error',
  loadingAnalysis: 'Loading match analysis…',
  noMatchLoaded: 'No match loaded',
  noMatchHint: 'Pick a stored match, collect one by ID or Riot ID, or explore the demo game.',
  couldNotLoad: 'Could not load {id}: {msg}',
  couldNotLoadDemo: 'Could not load demo data: {msg}',
  errTimeout: 'Request timed out',
  errUnreachable: 'Backend unreachable',
  errInvalidJson: 'Invalid JSON from backend',

  // Header
  apiOnline: 'API online · models: {models}',
  modelsNone: 'none',
  noRiotKey: 'no Riot key',
  apiOffline: 'API offline',
  checkingApi: 'Checking API…',
  demoBadge: 'DEMO DATA',
  matchLabel: 'Match',
  selectMatchAria: 'Select a stored match',
  selectMatch: 'Select a match…',
  noMatchesStored: 'No matches stored',
  synthetic: 'synthetic',
  minutesShort: '{n}m',
  collectMatchFormAria: 'Collect match by ID',
  matchIdAria: 'Match ID to collect',
  collecting: 'Collecting…',
  collectMatch: 'Collect match',
  collectPlayerFormAria: 'Collect recent matches by Riot ID',
  riotIdAria: 'Riot ID (Name#TAG)',
  riotIdPlaceholder: 'Name#TAG',
  countAria: 'Number of matches to collect',
  collectPlayer: 'Collect player',
  enterRiotId: 'Enter a Riot ID as Name#TAG.',
  playerProcessed: '{n} matches processed for {id}{failed}.',
  failedSuffix: ', {n} failed',
  langToggleAria: 'Switch language (Hungarian / English)',
  stateCached: 'cached',
  stateIngested: 'ingested',
  stateError: 'error',
  modelWinProbability: 'win probability',
  modelPowerScaling: 'power scaling',
  modelTilt: 'tilt',

  // Teams
  teamBlue: 'Blue',
  teamRed: 'Red',
  teamWin: '{team} win',
  teamSide: '{team} side',
  teamAria: '{team} team',
  scoreboardCaption: '{team} team scoreboard',

  // Overview
  killsGold: '{k} kills · {g} gold',
  victory: 'VICTORY',
  defeat: 'DEFEAT',
  colRole: 'Role',
  colPlayer: 'Player',
  colKda: 'KDA',
  colCs: 'CS',
  colGold: 'Gold',
  patchQueue: 'patch {patch} · queue {queue}',

  // Timeline
  whyMoved: 'Why it moved (SHAP)',
  minuteN: 'Minute {n}',
  inflectionTag: 'inflection',
  blueWinProbShort: 'Blue win prob',
  power: 'Power',
  versus: 'vs',
  gold: 'Gold',
  items: 'Items',
  kills: 'Kills',
  drakes: 'Drakes',
  barons: 'Barons',
  towers: 'Towers',
  powerWindow: '{team} power window',
  axisMinute: 'minute',
  blueWinProbability: 'Blue win probability',
  bluePowerIndex: 'Blue power index',
  redPowerIndex: 'Red power index',
  stability: 'Stability',
  anomalies: 'Anomalies',
  chartSummary:
    'Timeline of {d} minutes. Blue win probability ends at {p}. {i} inflection points and {a} player anomalies. Use the inflection cards and scoreboard for keyboard navigation.',
  notAvailable: 'n/a',
  timelineTitle: 'Match pulse & player stability',
  legendWinProb: 'Win prob',
  legendBluePower: 'Blue power',
  legendRedPower: 'Red power',
  legendInflection: 'Inflection / anomaly',
  lowHigh: 'low → high',
  resetZoom: 'Reset zoom',
  minShort: 'min {n}',
  hoverHint:
    'Hover an amber pill for anomaly details · click a lane to select a player · click a pin to inspect an inflection.',

  // Inflection panel
  inflectionsTitle: 'Inflection points',
  noSwings: 'No decisive swings detected in this match.',
  inflectionsListAria: 'Inflection points, select to zoom the timeline',
  shapTitle: 'SHAP decomposition',
  shapMinute: ' · minute {n}',
  close: 'Close',
  winProbChange: 'Blue win probability {from} → {to}',
  shapNote: 'Bars show signed change in blue win probability: cyan favours Blue, rose favours Red.',
  selectInflection: 'Select an inflection card (or a pin on the chart) to see what drove the swing.',
  inflectionDesc: '+{p}% {team} win probability at {m}:00 driven by: {drivers}',
  diffuseChange: 'diffuse state change',

  // SHAP bars
  noAttribution: 'No feature attribution for this minute.',
  shapListAria: 'Feature contributions to blue win probability',
  valueN: ' · value {v}',
  towardTeam: '{label}: {pct} toward {team}',

  // Player panel
  teamAverage: 'Team average',
  damage: 'Damage',
  vision: 'Vision',
  avgStability: 'Avg stability',
  radarAria: 'Radar for {c}: {metrics}. Dashed outline is the team average.',
  noRadarData: 'No radar data',
  selectPlayerHint: 'Select a player on the scoreboard or a stability lane to see their profile.',
  noRadarMetrics: 'No radar metrics for this player.',
  noAnomalies: 'No behavioural anomalies detected for this player.',
  anomalyAria: 'Minute {m}, {type}, severity {sev}. {desc} Select to zoom the timeline.',
  scoreN: 'score {s}',

  // Match summary
  sumTitle: 'Match summary',
  sumOutcome: '{winner} won after {d} minutes.',
  sumDecisive: 'The decisive moment came at minute {m}: {winner} win probability jumped from {from} to {to} in a single minute.',
  sumDrivers: 'Main drivers: {list}.',
  sumPnr: 'From minute {m} there was no way back: {winner} stayed above 50% for the rest of the game.',
  sumNoPnr: 'The model never had the winner above 50% at the end, so this was an upset.',
  sumPeakHigh: '{loser} was at {p} win probability at minute {m}, so this game was winnable.',
  sumPeakLow: "{loser}'s best chance was {p} (minute {m}); the winner controlled the game throughout.",
  sumThrow: 'The game turned between minute {s} and minute {e}: {loser} dropped from {from} to {to}.',
  sumDrops: 'Biggest drops: {list}.',
  sumDropItem: 'minute {m} ({d}; {drivers})',
  sumPower: "{team}'s theoretical power window was minutes {range} (mean power index {idx}).",
  sumPowerNone: '{team} had no detectable power window.',
  sumLoserWindowLost: '{loser} lost ground even inside its own power window ({d}).',
  sumLoserWindowGained: '{loser} gained during its own power window ({d}) but could not convert it into a win.',
  sumMvp: 'MVP: {player}, rated {r}/100.',
  sumLoserBest: 'Best player on the losing side: {player} ({r}/100).',
  sumShpbTitle: 'Should have performed better',
  sumShpb: '{player} ({r}/100) was the lowest-rated player on the losing side.',
  sumReasons: 'Reasons: {list}.',
  rDeaths: '{n} deaths',
  rLane: '{g} gold behind the lane opponent ({opp}) at minute {m}',
  rTilt: 'tilt events at minute {list}',
  rStab: 'low mean stability ({s}/100)',
  rDmg: 'only {p} of team damage',
  rWeak: 'weakest component: {c}',
  compKda: 'KDA',
  compEconomy: 'economy',
  compStability: 'stability',
  compComposure: 'composure (tilt)',
  compLane: 'laning',
  sumRatingNote: 'Rating 0-100 from KDA, gold and damage share, stability, tilt events and gold vs lane opponent at 15:00.',
  sumUnavailable: 'Match summary unavailable.',
  zoomTo: 'Zoom the timeline to minute {m}',
  staticNote: 'Static demo - live collection disabled',
} as const;

export type TKey = keyof typeof en;

const hu: Record<TKey, string> = {
  skipToContent: 'Ugrás a tartalomra',
  backendDown: 'A backend nem érhető el.',
  backendDownDetail: 'Az elemző API (/api) nem válaszol (várt cím: http://127.0.0.1:8000).',
  retry: 'Újra',
  loadDemo: 'Demóadatok betöltése',
  dismiss: 'Bezárás',
  dismissError: 'Hibaüzenet bezárása',
  loadingAnalysis: 'Meccselemzés betöltése…',
  noMatchLoaded: 'Nincs betöltött meccs',
  noMatchHint: 'Válassz egy tárolt meccset, gyűjts be egyet azonosító vagy Riot ID alapján, vagy nézd meg a demómeccset.',
  couldNotLoad: 'Nem sikerült betölteni: {id} – {msg}',
  couldNotLoadDemo: 'Nem sikerült betölteni a demóadatokat: {msg}',
  errTimeout: 'A kérés túllépte az időkorlátot',
  errUnreachable: 'A backend nem érhető el',
  errInvalidJson: 'Érvénytelen JSON a backendtől',

  apiOnline: 'API elérhető · modellek: {models}',
  modelsNone: 'nincs',
  noRiotKey: 'nincs Riot API-kulcs',
  apiOffline: 'API nem elérhető',
  checkingApi: 'API ellenőrzése…',
  demoBadge: 'DEMÓADAT',
  matchLabel: 'Meccs',
  selectMatchAria: 'Tárolt meccs kiválasztása',
  selectMatch: 'Válassz meccset…',
  noMatchesStored: 'Nincs tárolt meccs',
  synthetic: 'szintetikus',
  minutesShort: '{n} perc',
  collectMatchFormAria: 'Meccs begyűjtése azonosító alapján',
  matchIdAria: 'Begyűjtendő meccsazonosító',
  collecting: 'Begyűjtés…',
  collectMatch: 'Meccs begyűjtése',
  collectPlayerFormAria: 'Legutóbbi meccsek begyűjtése Riot ID alapján',
  riotIdAria: 'Riot ID (Név#TAG)',
  riotIdPlaceholder: 'Név#TAG',
  countAria: 'Begyűjtendő meccsek száma',
  collectPlayer: 'Játékos begyűjtése',
  enterRiotId: 'Add meg a Riot ID-t Név#TAG formában.',
  playerProcessed: '{n} meccs feldolgozva ({id}){failed}.',
  failedSuffix: ', ebből {n} sikertelen',
  langToggleAria: 'Nyelv váltása (magyar / angol)',
  stateCached: 'már tárolva',
  stateIngested: 'begyűjtve',
  stateError: 'hiba',
  modelWinProbability: 'győzelmi esély',
  modelPowerScaling: 'erőskálázás',
  modelTilt: 'tilt',

  teamBlue: 'Kék',
  teamRed: 'Piros',
  teamWin: '{team} győzelem',
  teamSide: '{team} oldal',
  teamAria: '{team} csapat',
  scoreboardCaption: '{team} csapat eredménytáblája',

  killsGold: '{k} kill · {g} arany',
  victory: 'GYŐZELEM',
  defeat: 'VERESÉG',
  colRole: 'Szerep',
  colPlayer: 'Játékos',
  colKda: 'KDA',
  colCs: 'CS',
  colGold: 'Arany',
  patchQueue: 'patch {patch} · queue {queue}',

  whyMoved: 'Mi mozdította el (SHAP)',
  minuteN: '{n}. perc',
  inflectionTag: 'fordulópont',
  blueWinProbShort: 'Kék győzelmi esély',
  power: 'Erő',
  versus: 'vs',
  gold: 'Arany',
  items: 'Tárgyak',
  kills: 'Killek',
  drakes: 'Sárkányok',
  barons: 'Baronok',
  towers: 'Tornyok',
  powerWindow: '{team} power spike',
  axisMinute: 'perc',
  blueWinProbability: 'Kék győzelmi esély',
  bluePowerIndex: 'Kék erőindex',
  redPowerIndex: 'Piros erőindex',
  stability: 'Stabilitás',
  anomalies: 'Anomáliák',
  chartSummary:
    '{d} perces idővonal. A kék győzelmi esély végső értéke {p}. {i} fordulópont és {a} játékosanomália. Billentyűzetes navigációhoz használd a fordulópont-kártyákat és az eredménytáblát.',
  notAvailable: 'n. a.',
  timelineTitle: 'A meccs pulzusa és a játékosok stabilitása',
  legendWinProb: 'Győzelmi esély',
  legendBluePower: 'Kék erő',
  legendRedPower: 'Piros erő',
  legendInflection: 'Fordulópont / anomália',
  lowHigh: 'alacsony → magas',
  resetZoom: 'Nagyítás visszaállítása',
  minShort: '{n}. perc',
  hoverHint:
    'Vidd az egeret egy borostyánszínű jelölőre az anomália részleteiért · kattints egy sávra a játékos kiválasztásához · kattints egy tűre a fordulópont megnyitásához.',

  inflectionsTitle: 'Fordulópontok',
  noSwings: 'Ebben a meccsben nem volt döntő fordulat.',
  inflectionsListAria: 'Fordulópontok – kiválasztással ráközelít az idővonalra',
  shapTitle: 'SHAP-felbontás',
  shapMinute: ' · {n}. perc',
  close: 'Bezárás',
  winProbChange: 'Kék győzelmi esély: {from} → {to}',
  shapNote: 'A sávok a kék győzelmi esély előjeles változását mutatják: a ciánkék a Kéknek, a rózsaszín a Pirosnak kedvez.',
  selectInflection: 'Válassz egy fordulópont-kártyát (vagy egy tűt a grafikonon), hogy lásd, mi okozta a fordulatot.',
  inflectionDesc: '+{p}% győzelmi esély a {team} oldal javára ({m}:00), fő tényezők: {drivers}',
  diffuseChange: 'nincs kiemelkedő tényező',

  noAttribution: 'Ehhez a perchez nincs tényezőbontás.',
  shapListAria: 'A tényezők hozzájárulása a kék győzelmi esélyhez',
  valueN: ' · érték: {v}',
  towardTeam: '{label}: {pct} a {team} javára',

  teamAverage: 'Csapatátlag',
  damage: 'Sebzés',
  vision: 'Vision',
  avgStability: 'Átl. stabilitás',
  radarAria: '{c} radardiagramja: {metrics}. A szaggatott vonal a csapatátlag.',
  noRadarData: 'Nincs radaradat',
  selectPlayerHint: 'Válassz egy játékost az eredménytáblán vagy egy stabilitási sávon a profilja megtekintéséhez.',
  noRadarMetrics: 'Ehhez a játékoshoz nincsenek radarmutatók.',
  noAnomalies: 'Ennél a játékosnál nem észleltünk viselkedési anomáliát.',
  anomalyAria: '{m}. perc, {type}, súlyosság: {sev}. {desc} Kiválasztással ráközelít az idővonalra.',
  scoreN: 'pontszám: {s}',

  sumTitle: 'Meccs-összefoglaló',
  sumOutcome: 'A {winner} csapat nyert {d} perc után.',
  sumDecisive: 'A döntő pillanat {am} percben jött: a {winner} csapat győzelmi esélye egyetlen perc alatt {from}-ról {to}-ra ugrott.',
  sumDrivers: 'Fő okok: {list}.',
  sumPnr: '{Am} perctől nem volt visszaút: onnantól a {winner} csapat esélye végig 50% felett maradt.',
  sumNoPnr: 'A modell szerint a győztes esélye a végén sem volt 50% felett, ez meglepetésgyőzelem volt.',
  sumPeakHigh: 'A {loser} csapat {am} percben {p}-os győzelmi esélyen állt, vagyis ezt a meccset meg lehetett volna nyerni.',
  sumPeakLow: 'A {loser} csapat legjobb esélye {p} volt ({am} percben), a győztes végig kézben tartotta a meccset.',
  sumThrow: 'A meccs {as} és {ae} perc között fordult meg: a {loser} csapat esélye {from}-ról {to}-ra zuhant.',
  sumDrops: 'A legnagyobb esések: {list}.',
  sumDropItem: '{mm} perc ({d}; {drivers})',
  sumPower: 'A {team} csapat elméleti erőablaka {range} perc volt (átlagos erőindex: {idx}).',
  sumPowerNone: 'A {team} csapatnak nem volt kimutatható erőablaka.',
  sumLoserWindowLost: 'A {loser} csapat még a saját erőablakában is veszített az esélyéből ({d}).',
  sumLoserWindowGained: 'A {loser} csapat a saját erőablakában javított az esélyén ({d}), de ezt nem tudta győzelemre váltani.',
  sumMvp: 'MVP: {player}, {r}/100 pontos értékeléssel.',
  sumLoserBest: 'A vesztes csapat legjobbja: {player} ({r}/100).',
  sumShpbTitle: 'Többet kellett volna hoznia',
  sumShpb: '{player} ({r}/100) a vesztes csapat legalacsonyabb értékelésű játékosa.',
  sumReasons: 'Okok: {list}.',
  rDeaths: '{n} halál',
  rLane: '{g} arannyal lemaradt a sávellenfelétől ({opp}) {am} percben',
  rTilt: 'tilt-esemény: {list} perc',
  rStab: 'alacsony átlagos stabilitás ({s}/100)',
  rDmg: 'a csapat sebzésének csak {p}-át adta',
  rWeak: 'leggyengébb mutató: {c}',
  compKda: 'KDA',
  compEconomy: 'gazdaság',
  compStability: 'stabilitás',
  compComposure: 'higgadtság (tilt)',
  compLane: 'sávjáték',
  sumRatingNote: 'Értékelés 0–100 között: KDA, arany- és sebzésrészesedés, stabilitás, tilt-események és a sávellenféllel szembeni aranykülönbség a 15. percben.',
  sumUnavailable: 'A meccs-összefoglaló nem érhető el.',
  zoomTo: 'Idővonal ráközelítése a(z) {m}. percre',
  staticNote: 'Statikus bemutató - élő adatgyűjtés kikapcsolva',
};

const DICT: Record<Lang, Record<TKey, string>> = { en, hu };

// Display names for backend SHAP features (keys from backend/nexuspulse/timeline.py FEATURE_LABELS).
const FEATURE_HU: Record<string, string> = {
  minute: 'Játékidő',
  gold_diff: 'Aranykülönbség',
  gold_share: 'Arany-részesedés',
  xp_diff: 'XP-különbség',
  cs_diff: 'CS-különbség',
  level_diff: 'Szintelőny',
  kill_diff: 'Kill-különbség',
  dragon_diff: 'Sárkányok',
  baron_diff: 'Baron-killek',
  herald_diff: 'Rift Herald',
  voidgrub_diff: 'Voidgrubok',
  tower_diff: 'Tornyok',
  plate_diff: 'Toronypáncélok (plate)',
  inhib_diff: 'Inhibitorok',
  alive_diff: 'Élő játékosok',
  baron_buff_diff: 'Aktív Baron buff',
};

const ANOMALY: Record<Lang, Record<AnomalyType, string>> = {
  en: {
    FARM_COLLAPSE: 'Farm collapse',
    ISOLATED_DEATHS: 'Isolated deaths',
    XP_STALL: 'XP stall',
    VISION_DROP: 'Vision drop',
    GENERAL_DEVIATION: 'General deviation',
  },
  hu: {
    FARM_COLLAPSE: 'Farm-összeomlás',
    ISOLATED_DEATHS: 'Elszigetelt halálok',
    XP_STALL: 'XP-megtorpanás',
    VISION_DROP: 'Vision-visszaesés',
    GENERAL_DEVIATION: 'Általános eltérés',
  },
};

const SEVERITY: Record<Lang, Record<Severity, string>> = {
  en: { LOW: 'LOW', MEDIUM: 'MEDIUM', HIGH: 'HIGH' },
  hu: { LOW: 'ALACSONY', MEDIUM: 'KÖZEPES', HIGH: 'MAGAS' },
};

const RADAR: Record<Lang, Record<keyof RadarMetrics, string>> = {
  en: { farming: 'Farming', fighting: 'Fighting', vision: 'Vision', objectives: 'Objectives', survival: 'Survival', stability: 'Stability' },
  hu: { farming: 'Farm', fighting: 'Harc', vision: 'Vision', objectives: 'Objektívek', survival: 'Túlélés', stability: 'Stabilitás' },
};

const STATE_KEY: Record<CollectState, TKey> = { cached: 'stateCached', ingested: 'stateIngested', error: 'stateError' };
const MODEL_KEY: Record<string, TKey> = {
  win_probability: 'modelWinProbability',
  power_scaling: 'modelPowerScaling',
  tilt: 'modelTilt',
};
const ERROR_KEY: Record<string, TKey> = {
  'Request timed out': 'errTimeout',
  'Backend unreachable': 'errUnreachable',
  'Invalid JSON from backend': 'errInvalidJson',
};

function format(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}

// --- Tilt description translation -------------------------------------------
// Mirrors the deterministic sentence built in backend/nexuspulse/models/tilt.py.
// Anything that does not match the known grammar is returned unchanged (English).
const TILT_RE = /^Tilt event flagged at (\d+:\d\d) \(([^)]*)\): (.*?)(?: following (.+))?$/;
const OBJECTIVE_HU: Record<string, string> = {
  dragon: 'elvesztett sárkány',
  Baron: 'elvesztett Baron',
  'Rift Herald': 'elvesztett Rift Herald',
  voidgrub: 'elvesztett voidgrubok',
  tower: 'elvesztett torony',
};

function tiltDetailHu(d: string): string | null {
  let m: RegExpMatchArray | null;
  if ((m = d.match(/^CS dropped (\d+)% vs role baseline$/))) return `a CS ${m[1]}%-kal a szerepkör alapértéke alatt`;
  if ((m = d.match(/^XP gain down (\d+)%$/))) return `az XP-szerzés ${m[1]}%-kal visszaesett`;
  if ((m = d.match(/^(\d+) isolated deaths? logged$/))) return `${m[1]} elszigetelt halál`;
  if ((m = d.match(/^(\d+) deaths in 3 minutes$/))) return `${m[1]} halál 3 percen belül`;
  if (d === 'vision placement collapsed') return 'a wardolás összeomlott';
  if (d === 'multi-metric deviation from normal play') return 'több mutatóban is eltér a szokásos játéktól';
  return null;
}

function tiltTriggerHu(tr: string): string | null {
  let m: RegExpMatchArray | null;
  if ((m = tr.match(/^a (solo )?death at (\d+:\d\d)$/))) return `${m[1] ? 'solo ' : ''}halál (${m[2]})`;
  if ((m = tr.match(/^(dragon|Baron|Rift Herald|voidgrub|tower) defeat at (\d+:\d\d)$/))) return `${OBJECTIVE_HU[m[1]]} (${m[2]})`;
  return null;
}

function translateTiltHu(desc: string): string {
  const m = desc.match(TILT_RE);
  if (!m) return desc;
  const [, minute, span, detailStr, trigger] = m;
  const details = detailStr.split(', ').map(tiltDetailHu);
  if (details.some((d) => d === null)) return desc;
  let out = `Tilt-esemény (${span === minute ? minute : `${minute}, időszak: ${span}`}): ${details.join(', ')}`;
  if (trigger) {
    const tr = tiltTriggerHu(trigger);
    if (tr === null) return desc;
    out += `; előzmény: ${tr}`;
  }
  return out;
}

// --- Context ------------------------------------------------------------------
function readInitialLang(): Lang {
  try {
    const q = new URLSearchParams(window.location.search).get('lang');
    if (q === 'hu' || q === 'en') {
      window.localStorage.setItem(STORAGE_KEY, q);
      return q;
    }
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === 'hu' || stored === 'en') return stored;
  } catch {
    // Storage may be unavailable (privacy mode); fall back to the default.
  }
  return DEFAULT_LANG;
}

export interface I18n {
  lang: Lang;
  setLang: (l: Lang) => void;
  toggleLang: () => void;
  /** BCP 47 locale for number/date formatting. */
  locale: string;
  t: (key: TKey, vars?: Record<string, string | number>) => string;
  /** Raw template for rich (node) interpolation. */
  raw: (key: TKey) => string;
  team: (t: Team) => string;
  feature: (f: Pick<ShapFeature, 'feature' | 'label'>) => string;
  anomalyType: (a: AnomalyType) => string;
  severity: (s: Severity) => string;
  radarAxis: (k: keyof RadarMetrics) => string;
  collectState: (s: CollectState) => string;
  modelName: (name: string) => string;
  errorText: (msg: string) => string;
  inflectionDescription: (ip: InflectionPoint) => string;
  anomalyDescription: (desc: string) => string;
}

const I18nContext = createContext<I18n | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(readInitialLang);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      window.localStorage.setItem(STORAGE_KEY, l);
    } catch {
      // ignore
    }
    // Keep an explicit ?lang= in the URL in sync so a reload does not revert the choice.
    const url = new URL(window.location.href);
    if (url.searchParams.has('lang')) {
      url.searchParams.set('lang', l);
      window.history.replaceState(null, '', url);
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const value = useMemo<I18n>(() => {
    const dict = DICT[lang];
    const t = (key: TKey, vars?: Record<string, string | number>) => format(dict[key], vars);
    const team = (tm: Team) => t(tm === 'blue' ? 'teamBlue' : 'teamRed');
    const feature = (f: Pick<ShapFeature, 'feature' | 'label'>) => (lang === 'hu' ? FEATURE_HU[f.feature] ?? f.label : f.label);
    return {
      lang,
      setLang,
      toggleLang: () => setLang(lang === 'hu' ? 'en' : 'hu'),
      locale: lang === 'hu' ? 'hu-HU' : 'en-US',
      t,
      raw: (key) => dict[key],
      team,
      feature,
      anomalyType: (a) => ANOMALY[lang][a] ?? a,
      severity: (s) => SEVERITY[lang][s] ?? s,
      radarAxis: (k) => RADAR[lang][k] ?? k,
      collectState: (s) => (STATE_KEY[s] ? t(STATE_KEY[s]) : s),
      modelName: (n) => (MODEL_KEY[n] ? t(MODEL_KEY[n]) : n.replace(/_/g, ' ')),
      errorText: (msg) => (ERROR_KEY[msg] ? t(ERROR_KEY[msg]) : msg),
      inflectionDescription: (ip) => {
        if (lang === 'en') return ip.description;
        const drivers = ip.top_features
          .map((f) => {
            const sign = (f.contribution > 0) === (ip.direction === 'blue') ? '+' : '-';
            return `${feature(f)} (${sign}${Math.round(Math.abs(f.contribution) * 100)}%)`;
          })
          .join(', ');
        return t('inflectionDesc', {
          p: Math.round(Math.abs(ip.delta) * 100),
          team: team(ip.direction),
          m: ip.minute,
          drivers: drivers || t('diffuseChange'),
        });
      },
      anomalyDescription: (desc) => (lang === 'hu' ? translateTiltHu(desc) : desc),
    };
  }, [lang, setLang]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error('useI18n must be used inside <I18nProvider>');
  return ctx;
}

/** Shorthand for the translate function only. */
export const useT = () => useI18n().t;
