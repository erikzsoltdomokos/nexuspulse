"""Parse Match-v5 + Match-v5 Timeline JSON into tidy per-minute player and team tables.

Every analytical module consumes the ``ParsedMatch`` produced here, so real Riot data and
synthetic data go through exactly the same code path.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .static_data import ItemInfo, champion_tier, load_items

TEAM_BY_ID = {100: "blue", 200: "red"}
OTHER = {"blue": "red", "red": "blue"}
ROLES = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]

# Approximate base respawn timer (seconds) by level 1..18.
_RESPAWN = [6, 6, 8, 8, 10, 12, 16, 21, 26, 32.5, 35, 37.5, 40, 42.5, 45, 47.5, 50, 52.5]

# Features of the per-minute win-probability vector, in model column order.
WIN_FEATURES = [
    "minute", "gold_diff", "gold_share", "xp_diff", "cs_diff", "level_diff", "kill_diff",
    "dragon_diff", "baron_diff", "herald_diff", "voidgrub_diff", "tower_diff", "plate_diff",
    "inhib_diff", "alive_diff", "baron_buff_diff",
]
FEATURE_LABELS = {
    "minute": "Game Time", "gold_diff": "Gold Difference", "gold_share": "Gold Share",
    "xp_diff": "XP Difference", "cs_diff": "CS Differential", "level_diff": "Level Lead",
    "kill_diff": "Kill Differential", "dragon_diff": "Dragons", "baron_diff": "Baron Kills",
    "herald_diff": "Rift Herald", "voidgrub_diff": "Voidgrubs", "tower_diff": "Towers",
    "plate_diff": "Turret Plates", "inhib_diff": "Inhibitors", "alive_diff": "Players Alive",
    "baron_buff_diff": "Baron Buff Active",
}

TEAM_COUNTERS = ["kills", "dragons", "barons", "heralds", "voidgrubs", "towers", "plates", "inhibs"]


@dataclass
class ParsedMatch:
    match_id: str
    duration_min: int
    winner: str
    game_version: str
    queue_id: int
    game_creation: int
    participants: list[dict]
    player_minutes: pd.DataFrame
    team_minutes: pd.DataFrame
    deaths: list[dict] = field(default_factory=list)
    objectives: list[dict] = field(default_factory=list)

    def participant(self, pid: int) -> dict:
        return next(p for p in self.participants if p["participant_id"] == pid)


def _respawn_seconds(level: int, minute: float) -> float:
    base = _RESPAWN[max(1, min(level, 18)) - 1]
    # Late-game time impact factor, roughly +0-50% after minute 15.
    factor = 1.0 + min(max(minute - 15.0, 0.0), 30.0) * (0.5 / 30.0)
    return base * factor


def _participants(match: dict) -> list[dict]:
    out = []
    info = match["info"]
    duration_min = max(1.0, info.get("gameDuration", 1) / 60.0)
    for p in info["participants"]:
        name = p.get("riotIdGameName") or p.get("summonerName") or f"Player{p['participantId']}"
        tag = p.get("riotIdTagline") or ""
        role = p.get("teamPosition") or p.get("individualPosition") or "UNKNOWN"
        out.append({
            "participant_id": int(p["participantId"]),
            "puuid": p.get("puuid", ""),
            "riot_id": f"{name}#{tag}" if tag else name,
            "champion": p.get("championName", "Unknown"),
            "team": TEAM_BY_ID.get(p.get("teamId"), "blue"),
            "role": role if role in ROLES else "UNKNOWN",
            "kills": int(p.get("kills", 0)),
            "deaths": int(p.get("deaths", 0)),
            "assists": int(p.get("assists", 0)),
            "cs": int(p.get("totalMinionsKilled", 0)) + int(p.get("neutralMinionsKilled", 0)),
            "gold": int(p.get("goldEarned", 0)),
            "damage": int(p.get("totalDamageDealtToChampions", 0)),
            "damage_to_objectives": int(p.get("damageDealtToObjectives", 0)),
            "vision_score": int(p.get("visionScore", 0)),
            "win": bool(p.get("win", False)),
            "tier": champion_tier(p.get("championName", "")),
            "duration_min": duration_min,
        })
    return sorted(out, key=lambda x: x["participant_id"])


def _item_totals(inventory: Counter, items: dict[int, ItemInfo]) -> tuple[int, float, float, float, float]:
    completed = 0
    cost = ad = hp = ap = 0.0
    for item_id, qty in inventory.items():
        info = items.get(item_id)
        if info is None or qty <= 0:
            continue
        cost += info.cost * qty
        ad += info.attack_damage * qty
        hp += info.health * qty
        ap += info.ability_power * qty
        if info.completed:
            completed += qty
    return completed, cost, ad, hp, ap


def parse_match(match: dict, timeline: dict, items: dict[int, ItemInfo] | None = None) -> ParsedMatch:
    info = match["info"]
    items = items if items is not None else load_items(str(info.get("gameVersion", "")))
    participants = _participants(match)
    pid_team = {p["participant_id"]: p["team"] for p in participants}
    pids = sorted(pid_team)

    frames = timeline["info"]["frames"]
    events = sorted(
        (e for f in frames for e in f.get("events", [])), key=lambda e: e.get("timestamp", 0)
    )

    inventory = {pid: Counter() for pid in pids}
    p_kills, p_deaths, p_assists, p_wards = (Counter() for _ in range(4))
    team = {t: Counter() for t in ("blue", "red")}
    last_baron_ms = {"blue": -10**9, "red": -10**9}
    last_level = {pid: 1 for pid in pids}
    deaths: list[dict] = []
    objectives: list[dict] = []

    player_rows: list[dict] = []
    team_rows: list[dict] = []
    ev_idx = 0

    for minute, frame in enumerate(frames):
        cutoff = int(frame.get("timestamp", minute * 60000))
        if minute < len(frames) - 1:
            cutoff = max(cutoff, minute * 60000)
        while ev_idx < len(events) and events[ev_idx].get("timestamp", 0) <= cutoff:
            _apply_event(
                events[ev_idx], pid_team, inventory, p_kills, p_deaths, p_assists, p_wards,
                team, last_baron_ms, last_level, deaths, objectives,
            )
            ev_idx += 1
        if minute == 0:
            continue

        cutoff_min = cutoff / 60000.0
        dead_now = {
            d["victim"] for d in deaths if d["minute"] <= cutoff_min < d["respawn_minute"]
        }
        pframes = frame.get("participantFrames", {})
        agg = {t: Counter() for t in ("blue", "red")}
        for pid in pids:
            pf = pframes.get(str(pid), {})
            level = int(pf.get("level", last_level[pid]))
            last_level[pid] = level
            completed, cost, ad, hp, ap = _item_totals(inventory[pid], items)
            pos = pf.get("position", {})
            row = {
                "minute": minute,
                "participant_id": pid,
                "team": pid_team[pid],
                "total_gold": int(pf.get("totalGold", 0)),
                "xp": int(pf.get("xp", 0)),
                "level": level,
                "cs": int(pf.get("minionsKilled", 0)) + int(pf.get("jungleMinionsKilled", 0)),
                "damage_to_champions": int(pf.get("damageStats", {}).get("totalDamageDoneToChampions", 0)),
                "x": float(pos.get("x", 0)),
                "y": float(pos.get("y", 0)),
                "items_completed": completed,
                "item_cost": cost,
                "item_ad": ad,
                "item_hp": hp,
                "item_ap": ap,
                "kills": p_kills[pid],
                "deaths": p_deaths[pid],
                "assists": p_assists[pid],
                "wards_placed": p_wards[pid],
                "alive": int(pid not in dead_now),
            }
            player_rows.append(row)
            a = agg[pid_team[pid]]
            for key in ("total_gold", "xp", "cs", "level", "items_completed", "alive"):
                a[key] += row[key]

        trow: dict = {"minute": minute}
        for side in ("blue", "red"):
            trow[f"gold_{side}"] = agg[side]["total_gold"]
            trow[f"xp_{side}"] = agg[side]["xp"]
            trow[f"cs_{side}"] = agg[side]["cs"]
            trow[f"level_{side}"] = agg[side]["level"]
            trow[f"items_completed_{side}"] = agg[side]["items_completed"]
            trow[f"alive_{side}"] = agg[side]["alive"]
            trow[f"baron_buff_{side}"] = int(cutoff - last_baron_ms[side] <= 180_000)
            for c in TEAM_COUNTERS:
                trow[f"{c}_{side}"] = team[side][c]
        team_rows.append(trow)

    player_minutes = pd.DataFrame(player_rows)
    team_minutes = pd.DataFrame(team_rows)
    team_minutes = add_diff_features(team_minutes)
    _classify_deaths(deaths, player_minutes, pid_team)

    winner = next(
        (TEAM_BY_ID[t["teamId"]] for t in info.get("teams", []) if t.get("win")),
        "blue" if any(p["win"] and p["team"] == "blue" for p in participants) else "red",
    )
    return ParsedMatch(
        match_id=match["metadata"]["matchId"],
        duration_min=int(team_minutes["minute"].max()) if len(team_minutes) else 0,
        winner=winner,
        game_version=str(info.get("gameVersion", "")),
        queue_id=int(info.get("queueId", 0)),
        game_creation=int(info.get("gameCreation", 0)),
        participants=participants,
        player_minutes=player_minutes,
        team_minutes=team_minutes,
        deaths=deaths,
        objectives=objectives,
    )


def _apply_event(e, pid_team, inventory, p_kills, p_deaths, p_assists, p_wards, team,
                 last_baron_ms, last_level, deaths, objectives) -> None:
    etype = e.get("type")
    ts = int(e.get("timestamp", 0))
    if etype == "CHAMPION_KILL":
        victim = int(e.get("victimId", 0))
        killer = int(e.get("killerId", 0))
        if victim not in pid_team:
            return
        victim_team = pid_team[victim]
        killer_team = pid_team.get(killer, OTHER[victim_team])
        if killer_team != victim_team:
            team[killer_team]["kills"] += 1
        if killer in pid_team:
            p_kills[killer] += 1
        p_deaths[victim] += 1
        assisters = [int(a) for a in e.get("assistingParticipantIds", []) or []]
        for a in assisters:
            p_assists[a] += 1
        minute = ts / 60000.0
        pos = e.get("position", {})
        deaths.append({
            "minute": minute,
            "victim": victim,
            "victim_team": victim_team,
            "killer": killer,
            "assisters": assisters,
            "x": float(pos.get("x", 0)),
            "y": float(pos.get("y", 0)),
            "respawn_minute": minute + _respawn_seconds(last_level.get(victim, 1), minute) / 60.0,
        })
    elif etype == "ELITE_MONSTER_KILL":
        side = TEAM_BY_ID.get(e.get("killerTeamId")) or pid_team.get(int(e.get("killerId", 0)))
        if side is None:
            return
        monster = e.get("monsterType")
        key = {"DRAGON": "dragons", "BARON_NASHOR": "barons", "RIFTHERALD": "heralds",
               "HORDE": "voidgrubs"}.get(monster)
        if key:
            team[side][key] += 1
        if monster == "BARON_NASHOR":
            last_baron_ms[side] = ts
        objectives.append({"minute": ts / 60000.0, "type": monster, "team": side,
                           "subtype": e.get("monsterSubType", "")})
    elif etype == "BUILDING_KILL":
        owner = TEAM_BY_ID.get(e.get("teamId"))
        if owner is None:
            return
        taker = OTHER[owner]
        btype = e.get("buildingType")
        if btype == "TOWER_BUILDING":
            team[taker]["towers"] += 1
        elif btype == "INHIBITOR_BUILDING":
            team[taker]["inhibs"] += 1
        objectives.append({"minute": ts / 60000.0, "type": btype, "team": taker, "subtype": ""})
    elif etype == "TURRET_PLATE_DESTROYED":
        owner = TEAM_BY_ID.get(e.get("teamId"))
        if owner:
            team[OTHER[owner]]["plates"] += 1
    elif etype == "ITEM_PURCHASED":
        pid = int(e.get("participantId", 0))
        if pid in inventory:
            inventory[pid][int(e.get("itemId", 0))] += 1
    elif etype in ("ITEM_SOLD", "ITEM_DESTROYED"):
        pid = int(e.get("participantId", 0))
        item_id = int(e.get("itemId", 0))
        if pid in inventory and inventory[pid][item_id] > 0:
            inventory[pid][item_id] -= 1
    elif etype == "ITEM_UNDO":
        pid = int(e.get("participantId", 0))
        if pid not in inventory:
            return
        before, after = int(e.get("beforeId", 0)), int(e.get("afterId", 0))
        if before and inventory[pid][before] > 0:
            inventory[pid][before] -= 1
        if after:
            inventory[pid][after] += 1
    elif etype == "WARD_PLACED":
        pid = int(e.get("creatorId", 0))
        if pid in pid_team and e.get("wardType") != "UNDEFINED":
            p_wards[pid] += 1


def add_diff_features(tm: pd.DataFrame) -> pd.DataFrame:
    if tm.empty:
        return tm
    tm = tm.copy()
    tm["gold_diff"] = tm["gold_blue"] - tm["gold_red"]
    tm["gold_share"] = tm["gold_blue"] / (tm["gold_blue"] + tm["gold_red"]).clip(lower=1)
    tm["xp_diff"] = tm["xp_blue"] - tm["xp_red"]
    tm["cs_diff"] = tm["cs_blue"] - tm["cs_red"]
    tm["level_diff"] = tm["level_blue"] - tm["level_red"]
    tm["kill_diff"] = tm["kills_blue"] - tm["kills_red"]
    tm["dragon_diff"] = tm["dragons_blue"] - tm["dragons_red"]
    tm["baron_diff"] = tm["barons_blue"] - tm["barons_red"]
    tm["herald_diff"] = tm["heralds_blue"] - tm["heralds_red"]
    tm["voidgrub_diff"] = tm["voidgrubs_blue"] - tm["voidgrubs_red"]
    tm["tower_diff"] = tm["towers_blue"] - tm["towers_red"]
    tm["plate_diff"] = tm["plates_blue"] - tm["plates_red"]
    tm["inhib_diff"] = tm["inhibs_blue"] - tm["inhibs_red"]
    tm["alive_diff"] = tm["alive_blue"] - tm["alive_red"]
    tm["baron_buff_diff"] = tm["baron_buff_blue"] - tm["baron_buff_red"]
    return tm


def _in_enemy_territory(team: str, x: float, y: float) -> bool:
    # Summoner's Rift: blue base bottom-left, red base top-right, river along x + y ~= 14800.
    return (x + y > 17000) if team == "blue" else (x + y < 12600)


def _classify_deaths(deaths: list[dict], pm: pd.DataFrame, pid_team: dict[int, str]) -> None:
    """Flag deaths as isolated (no living ally within 2500 units) and/or deep in enemy territory."""
    if pm.empty:
        return
    max_minute = int(pm["minute"].max())
    by_minute = {m: g for m, g in pm.groupby("minute")}
    for d in deaths:
        m = min(max(1, int(round(d["minute"]))), max_minute)
        frame = by_minute.get(m)
        allies = frame[(frame["team"] == d["victim_team"]) & (frame["participant_id"] != d["victim"])
                       & (frame["alive"] == 1)] if frame is not None else None
        if allies is None or allies.empty or (d["x"] == 0 and d["y"] == 0):
            nearest = math.inf
        else:
            nearest = float(np.min(np.hypot(allies["x"] - d["x"], allies["y"] - d["y"])))
        d["nearest_ally"] = nearest
        d["deep"] = _in_enemy_territory(d["victim_team"], d["x"], d["y"])
        d["isolated"] = bool(nearest > 2500 or (d["deep"] and nearest > 1500))


def win_feature_frame(tm: pd.DataFrame) -> pd.DataFrame:
    return tm[WIN_FEATURES].astype(float)
