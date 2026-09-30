// Deterministic generator for the demo data in src/mock/.
// Story: blue (early comp) builds a lead, red (scaling comp) turns it around
// with a mid-game fight and Baron at 26 and wins at 32 minutes.
// Run: node scripts/generate-mock.mjs
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'mock');
const MATCH_ID = 'EUW1_7123456789';
const DURATION = 32;

let seed = 1337;
const rnd = () => {
  seed = (seed * 1664525 + 1013904223) % 4294967296;
  return seed / 4294967296;
};
const noise = (a) => (rnd() * 2 - 1) * a;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const round = (v, d = 3) => Math.round(v * 10 ** d) / 10 ** d;
const lerpKeys = (keys, m) => {
  for (let i = 1; i < keys.length; i++) {
    const [m0, v0] = keys[i - 1];
    const [m1, v1] = keys[i];
    if (m <= m1) return v0 + ((v1 - v0) * (m - m0)) / (m1 - m0);
  }
  return keys[keys.length - 1][1];
};
const countAt = (events, m) => events.filter((e) => e <= m).length;
const sigmoid = (z) => 1 / (1 + Math.exp(-z));

// participant_id, riot_id, champion, team, role, k, d, a, cs, vision, goldShare, dmg
const P = [
  [1, 'Kaelthorn#EUW', 'Aatrox', 'blue', 'TOP', 5, 5, 4, 231, 18, 0.21, 21840],
  [2, 'Nightfang#EUW', 'LeeSin', 'blue', 'JUNGLE', 4, 6, 9, 176, 31, 0.19, 15420],
  [3, 'Velmara#0420', 'Ahri', 'blue', 'MIDDLE', 6, 4, 6, 262, 22, 0.23, 26910],
  [4, 'Crit Happens#EUW', 'Jinx', 'blue', 'BOTTOM', 3, 9, 5, 281, 14, 0.25, 19880],
  [5, 'Lanternkeep#EUW', 'Thresh', 'blue', 'UTILITY', 1, 4, 11, 38, 71, 0.12, 6230],
  [6, 'Stonewall#EUNE', 'Ornn', 'red', 'TOP', 3, 4, 14, 214, 24, 0.19, 17650],
  [7, 'Hexbloom#EUW', 'Viego', 'red', 'JUNGLE', 7, 4, 12, 198, 35, 0.21, 22310],
  [8, 'Quiet Storm#EUW', 'Orianna', 'red', 'MIDDLE', 8, 3, 13, 271, 27, 0.22, 31270],
  [9, 'Farsight#EUW', 'Kaisa', 'red', 'BOTTOM', 9, 3, 10, 289, 19, 0.26, 29440],
  [10, 'Moonveil#EUW', 'Nautilus', 'red', 'UTILITY', 1, 5, 19, 41, 84, 0.12, 8120],
];

const goldDiffKeys = [[0, 0], [5, 600], [8, 1400], [12, 2600], [15, 3400], [18, 3800], [20, 2200], [23, 1000], [26, -2200], [28, -3500], [30, -5500], [32, -8000]];
const killsBlueKeys = [[0, 0], [3, 1], [8, 4], [12, 7], [15, 9], [18, 12], [20, 13], [23, 15], [26, 16], [28, 17], [30, 18], [32, 19]];
const killsRedKeys = [[0, 0], [3, 0], [8, 2], [12, 3], [15, 4], [18, 5], [20, 9], [23, 12], [26, 17], [28, 20], [30, 24], [32, 28]];
const ev = {
  dragons_blue: [5, 11], dragons_red: [17, 23, 29],
  barons_blue: [], barons_red: [26],
  heralds_blue: [15], heralds_red: [],
  voidgrubs_blue: [7, 7, 7], voidgrubs_red: [10, 10, 10],
  towers_blue: [12, 14, 18, 21], towers_red: [16, 20, 24, 27, 28, 30, 31, 31, 32],
  plates_blue: [6, 8, 9, 10, 12, 13, 13], plates_red: [9, 11, 14],
};

const FEATURES = [
  ['gold_diff', 'Gold difference', 0.28 / 1000],
  ['dragons_diff', 'Dragon difference', 0.25],
  ['barons_diff', 'Baron difference', 0.9],
  ['towers_diff', 'Tower difference', 0.1],
  ['voidgrubs_diff', 'Void Grub difference', 0.08],
  ['kills_diff', 'Kill difference', 0.03],
];

const states = [];
for (let m = 0; m <= DURATION; m++) {
  const gd = m === 0 ? 0 : Math.round(lerpKeys(goldDiffKeys, m) + noise(150));
  const base = 2500 + 1850 * m;
  const gb = Math.round(base + gd / 2);
  const gr = Math.round(base - gd / 2);
  const s = {
    gold_blue: gb, gold_red: gr, gold_diff: gb - gr,
    xp_diff: m === 0 ? 0 : Math.round(gd * 0.6 + noise(120)),
    kills_blue: Math.round(lerpKeys(killsBlueKeys, m)), kills_red: Math.round(lerpKeys(killsRedKeys, m)),
  };
  for (const [k, list] of Object.entries(ev)) s[k] = countAt(list, m);
  s.items_completed_blue = Math.max(0, Math.floor((gb - 2500) / 3000));
  s.items_completed_red = Math.max(0, Math.floor((gr - 2500) / 3000));
  states.push(s);
}

const featureValues = (s) => ({
  gold_diff: s.gold_diff,
  dragons_diff: s.dragons_blue - s.dragons_red,
  barons_diff: s.barons_blue - s.barons_red,
  towers_diff: s.towers_blue - s.towers_red,
  voidgrubs_diff: s.voidgrubs_blue - s.voidgrubs_red,
  kills_diff: s.kills_blue - s.kills_red,
});
const zOf = (fv) => FEATURES.reduce((z, [k, , w]) => z + w * fv[k], 0);

const timeline = [];
const inflections = [];
let prevP = 0.5;
let prevFv = featureValues(states[0]);
for (let m = 0; m <= DURATION; m++) {
  const s = states[m];
  const fv = featureValues(s);
  const p = round(clamp(sigmoid(zOf(fv)), 0.01, 0.99));
  const delta = m === 0 ? 0 : round(p - prevP);
  // Per-feature marginal contribution to the minute-over-minute change.
  const zPrev = zOf(prevFv);
  const shap = FEATURES.map(([k, label, w]) => ({
    feature: k, label, value: fv[k],
    contribution: round(sigmoid(zPrev + w * (fv[k] - prevFv[k])) - sigmoid(zPrev)),
  }))
    .filter((f) => Math.abs(f.contribution) >= 0.002)
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
    .slice(0, 3);
  const early = m < 18 ? 6 : -4;
  const late = m > 20 ? 7 : -3;
  const pb = round(clamp(50 + s.gold_diff / 120 + early + noise(3), 5, 95), 1);
  const pr = round(clamp(50 - s.gold_diff / 120 + late + noise(3), 5, 95), 1);
  const isInfl = Math.abs(delta) >= 0.06;
  timeline.push({
    minute: m, team_blue_power_index: pb, team_red_power_index: pr,
    win_probability_blue: p, delta_win_probability: delta, is_inflection_point: isInfl,
    shap_summary: m === 0 ? [] : shap, state: s,
  });
  if (isInfl) {
    const dir = delta > 0 ? 'blue' : 'red';
    const top = shap[0];
    const Team = dir === 'blue' ? 'Blue' : 'Red';
    const reason = {
      barons_diff: `${Team} secured Baron Nashor`,
      dragons_diff: `${Team} took the dragon`,
      towers_diff: `${Team} broke a turret`,
      voidgrubs_diff: `${Team} claimed the Void Grubs`,
      kills_diff: `${Team} won a teamfight`,
      gold_diff: `${Team} converted a gold swing`,
    }[top?.feature ?? 'gold_diff'];
    inflections.push({
      minute: m, delta, direction: dir, top_features: shap,
      description: `${reason}; blue win probability moved ${delta > 0 ? '+' : ''}${(delta * 100).toFixed(1)} pts to ${(p * 100).toFixed(0)}%.`,
    });
  }
  prevP = p;
  prevFv = fv;
}

const windows = (team) => {
  const out = [];
  let start = null;
  for (const t of timeline) {
    const adv = team === 'blue' ? t.team_blue_power_index - t.team_red_power_index : t.team_red_power_index - t.team_blue_power_index;
    if (adv >= 10 && start === null) start = t.minute;
    if (adv < 10 && start !== null) {
      if (t.minute - 1 - start >= 1) out.push({ start, end: t.minute - 1 });
      start = null;
    }
  }
  if (start !== null && DURATION - start >= 1) out.push({ start, end: DURATION });
  return out;
};

const puuid = (id) => `mock-puuid-${String(id).padStart(2, '0')}-${(id * 2654435761 % 0xffffffff).toString(16)}`;
const anomalies = [
  [9, 9, 'FARM_COLLAPSE', 'LOW', 'CS/min fell to 4.1 (expected 7.2) under early lane pressure.', 0.41],
  [7, 13, 'GENERAL_DEVIATION', 'LOW', 'Jungle pathing diverged from role baseline; low camp uptime.', 0.38],
  [4, 20, 'ISOLATED_DEATHS', 'HIGH', 'Died twice alone in the river between 19–21 min without vision cover.', 0.91],
  [2, 22, 'ISOLATED_DEATHS', 'MEDIUM', 'Caught face-checking red jungle with no allies within 2,000 units.', 0.67],
  [3, 24, 'FARM_COLLAPSE', 'MEDIUM', 'Missed 18 waves-worth of CS while grouping mid; gold/min −35%.', 0.62],
  [5, 25, 'VISION_DROP', 'HIGH', 'Placed 0 wards in the 4 minutes before Baron; control wards expired.', 0.88],
  [1, 27, 'XP_STALL', 'MEDIUM', 'XP gain stalled for 3 min while split-pushing into a lost side lane.', 0.59],
].map(([id, minute, type, sev, desc, score]) => {
  const p = P[id - 1];
  return { puuid: puuid(id), participant_id: id, champion: p[2], team: p[3], minute, anomaly_type: type, severity: sev, description: desc, score };
});

const depth = { HIGH: 45, MEDIUM: 30, LOW: 18 };
const stability = P.map(([id, , champ, team, role]) => ({
  participant_id: id, puuid: puuid(id), champion: champ, team, role,
  scores: timeline.map(({ minute }) => {
    let v = 80 + noise(6);
    if (team === 'blue' && minute > 22) v -= (minute - 22) * 1.4;
    if (team === 'red' && minute > 20) v += 4;
    for (const a of anomalies.filter((x) => x.participant_id === id)) {
      const dist = Math.abs(minute - a.minute);
      if (dist <= 2) v -= depth[a.severity] * (1 - dist / 3);
    }
    return { minute, stability: round(clamp(v, 0, 100), 1) };
  }),
}));

const radarSeed = {
  1: [72, 68, 35, 55, 52], 2: [48, 64, 70, 66, 41], 3: [84, 77, 52, 58, 70], 4: [88, 58, 31, 49, 28], 5: [12, 60, 92, 71, 64],
  6: [69, 62, 48, 74, 78], 7: [70, 83, 66, 88, 74], 8: [86, 88, 57, 72, 85], 9: [90, 91, 44, 69, 82], 10: [14, 79, 95, 80, 69],
};
const radar = P.map(([id]) => {
  const [farming, fighting, vision, objectives, survival] = radarSeed[id];
  const sc = stability[id - 1].scores;
  const stab = Math.round(sc.reduce((a, b) => a + b.stability, 0) / sc.length);
  return { participant_id: id, metrics: { farming, fighting, vision, objectives, survival, stability: stab } };
});

const dynamics = {
  match_id: MATCH_ID, duration_min: DURATION,
  power_windows: { blue: windows('blue'), red: windows('red') },
  timeline, inflection_points: inflections, player_anomalies: anomalies,
  player_stability: stability, player_radar: radar,
};

const finalGold = { blue: states[DURATION].gold_blue, red: states[DURATION].gold_red };
const overview = {
  match_id: MATCH_ID, duration_min: DURATION, winner: 'red', game_version: '14.18.612.3456', queue_id: 420,
  participants: P.map(([id, riot, champ, team, role, k, d, a, cs, vis, share, dmg]) => ({
    participant_id: id, puuid: puuid(id), riot_id: riot, champion: champ, team, role,
    kills: k, deaths: d, assists: a, cs, gold: Math.round(finalGold[team] * share), damage: dmg, vision_score: vis, win: team === 'red',
  })),
};

mkdirSync(OUT, { recursive: true });
writeFileSync(join(OUT, 'sampleDynamics.json'), JSON.stringify(dynamics, null, 2) + '\n');
writeFileSync(join(OUT, 'sampleOverview.json'), JSON.stringify(overview, null, 2) + '\n');
console.log(`wrote mock: ${timeline.length} minutes, ${inflections.length} inflections, ${anomalies.length} anomalies`);
console.log('inflections:', inflections.map((i) => `${i.minute}:${i.direction}:${i.delta}`).join(' '));
console.log('windows:', JSON.stringify(dynamics.power_windows));
