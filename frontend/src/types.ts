// Types mirroring the NexusPulse backend JSON contract.

export type Team = 'blue' | 'red';
export type Role = 'TOP' | 'JUNGLE' | 'MIDDLE' | 'BOTTOM' | 'UTILITY';
export type CollectState = 'cached' | 'ingested' | 'error';
export type AnomalyType = 'FARM_COLLAPSE' | 'ISOLATED_DEATHS' | 'XP_STALL' | 'VISION_DROP' | 'GENERAL_DEVIATION';
export type Severity = 'LOW' | 'MEDIUM' | 'HIGH';

export interface Health {
  status: string;
  models: { win_probability: boolean; power_scaling: boolean; tilt: boolean };
  riot_key_configured: boolean;
}

export interface MatchSummary {
  match_id: string;
  /** Epoch milliseconds. */
  game_creation: number;
  duration_min: number;
  winner: Team;
  source: 'riot' | 'synthetic';
}

export interface MatchList {
  matches: MatchSummary[];
}

export interface CollectResult {
  match_id: string;
  state: CollectState;
  detail: string;
}

export interface CollectPlayerResult {
  puuid: string;
  results: CollectResult[];
}

export interface Participant {
  participant_id: number;
  puuid: string;
  riot_id: string;
  champion: string;
  team: Team;
  role: Role;
  kills: number;
  deaths: number;
  assists: number;
  cs: number;
  gold: number;
  damage: number;
  vision_score: number;
  win: boolean;
}

export interface Overview {
  match_id: string;
  duration_min: number;
  winner: Team;
  game_version: string;
  queue_id: number;
  participants: Participant[];
}

export interface ShapFeature {
  feature: string;
  label: string;
  value: number;
  /** Signed change in blue win probability (0.14 = +14% for blue). */
  contribution: number;
}

export interface TeamState {
  gold_blue: number;
  gold_red: number;
  gold_diff: number;
  xp_diff: number;
  kills_blue: number;
  kills_red: number;
  dragons_blue: number;
  dragons_red: number;
  barons_blue: number;
  barons_red: number;
  heralds_blue: number;
  heralds_red: number;
  voidgrubs_blue: number;
  voidgrubs_red: number;
  towers_blue: number;
  towers_red: number;
  plates_blue: number;
  plates_red: number;
  items_completed_blue: number;
  items_completed_red: number;
}

export interface TimelinePoint {
  minute: number;
  team_blue_power_index: number;
  team_red_power_index: number;
  /** 0..1 */
  win_probability_blue: number;
  delta_win_probability: number;
  is_inflection_point: boolean;
  shap_summary: ShapFeature[];
  state: TeamState;
}

export interface PowerWindow {
  start: number;
  end: number;
}

export interface InflectionPoint {
  minute: number;
  delta: number;
  direction: Team;
  top_features: ShapFeature[];
  description: string;
}

export interface PlayerAnomaly {
  puuid: string;
  participant_id: number;
  champion: string;
  team: Team;
  minute: number;
  anomaly_type: AnomalyType;
  severity: Severity;
  description: string;
  score: number;
}

export interface PlayerStability {
  participant_id: number;
  puuid: string;
  champion: string;
  team: Team;
  role: Role;
  scores: { minute: number; stability: number }[];
}

export interface RadarMetrics {
  farming: number;
  fighting: number;
  vision: number;
  objectives: number;
  survival: number;
  stability: number;
}

export interface PlayerRadar {
  participant_id: number;
  metrics: RadarMetrics;
}

export interface TimelineDynamics {
  match_id: string;
  duration_min: number;
  power_windows: { blue: PowerWindow[]; red: PowerWindow[] };
  timeline: TimelinePoint[];
  inflection_points: InflectionPoint[];
  player_anomalies: PlayerAnomaly[];
  player_stability: PlayerStability[];
  player_radar: PlayerRadar[];
}
