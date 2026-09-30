"""Synthetic Match-v5 + Timeline generator.

Produces JSON in the *same shape* as the Riot API so the full pipeline (parsing, training,
inference, dashboard) runs without an API key. The simulation contains learnable structure:
a latent team advantage that drives kills/objectives/gold, champion scaling tiers that shift
power over time, and injected "tilt episodes" (farm/XP/vision collapse and isolated deaths
after a death). Synthetic matches are tagged ``source='synthetic'`` in the database.
"""

from __future__ import annotations

import math

import numpy as np

from .static_data import (
    AD_ITEMS, AP_ITEMS, BOOTS, BRUISER_ITEMS, FALLBACK_ITEMS, SUPPORT_ITEMS, TANK_ITEMS, champion_tier,
)

ROLES = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
CHAMPIONS = {
    "TOP": [("Darius", "bruiser"), ("Renekton", "bruiser"), ("Kayle", "ap"), ("Nasus", "bruiser"),
            ("Ornn", "tank"), ("Gwen", "ap"), ("Jayce", "ad"), ("Sion", "tank"), ("Camille", "bruiser")],
    "JUNGLE": [("LeeSin", "bruiser"), ("Elise", "ap"), ("MasterYi", "ad"), ("Kindred", "ad"),
               ("Graves", "ad"), ("XinZhao", "bruiser"), ("Sejuani", "tank"), ("Karthus", "ap")],
    "MIDDLE": [("Leblanc", "ap"), ("Kassadin", "ap"), ("Azir", "ap"), ("Zed", "ad"), ("Ahri", "ap"),
               ("Viktor", "ap"), ("Syndra", "ap"), ("Talon", "ad"), ("Orianna", "ap")],
    "BOTTOM": [("Draven", "ad"), ("Jinx", "ad"), ("Lucian", "ad"), ("Vayne", "ad"), ("Kaisa", "ad"),
               ("Caitlyn", "ad"), ("Ezreal", "ad"), ("Smolder", "ad"), ("Ashe", "ad")],
    "UTILITY": [("Leona", "support"), ("Thresh", "support"), ("Senna", "support"), ("Soraka", "support"),
                ("Nautilus", "support"), ("Lulu", "support"), ("Blitzcrank", "support"), ("Sona", "support")],
}
ITEM_POOLS = {"ad": AD_ITEMS, "ap": AP_ITEMS, "bruiser": BRUISER_ITEMS, "tank": TANK_ITEMS,
              "support": SUPPORT_ITEMS}
CS_RATE = {"TOP": 6.8, "JUNGLE": 5.4, "MIDDLE": 7.4, "BOTTOM": 7.9, "UTILITY": 1.0}
XP_RATE = {"TOP": 520, "JUNGLE": 440, "MIDDLE": 540, "BOTTOM": 390, "UTILITY": 340}
WARD_RATE = {"TOP": 0.3, "JUNGLE": 0.55, "MIDDLE": 0.35, "BOTTOM": 0.3, "UTILITY": 1.15}
# Cumulative XP needed for levels 2..18.
XP_TABLE = [280, 660, 1140, 1720, 2400, 3180, 4060, 5040, 6120, 7300, 8580, 9960, 11440,
            13020, 14700, 16480, 18360]
BLUE_LANE_POS = {"TOP": (1700, 10500), "MIDDLE": (6700, 6700), "BOTTOM": (10500, 1700),
                 "UTILITY": (10200, 2100)}


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def tier_factor(tier: int, minute: float) -> float:
    """Relative power multiplier of an early (0) / mid (1) / late (2) champion at a minute."""
    if tier == 0:
        return 1.18 - 0.30 * _sigmoid((minute - 20) / 4)
    if tier == 2:
        return 0.84 + 0.38 * _sigmoid((minute - 24) / 4)
    return 0.95 + 0.12 * math.exp(-((minute - 21) / 8) ** 2)


def _level(xp: float) -> int:
    return 1 + sum(1 for t in XP_TABLE if xp >= t)


def _mirror(pos: tuple[float, float]) -> tuple[float, float]:
    return (14800 - pos[0], 14800 - pos[1])


class _Player:
    def __init__(self, pid: int, team: str, role: str, champ: str, kind: str, rng: np.random.Generator):
        self.pid, self.team, self.role, self.champ, self.kind = pid, team, role, champ, kind
        self.tier = champion_tier(champ)
        self.puuid = "SYN-" + "".join(rng.choice(list("0123456789abcdef"), 40))
        self.name = f"Synth{role.title()}{pid}"
        self.gold = 500.0
        self.unspent = 500.0
        self.xp = 0.0
        self.cs = 0.0
        self.jcs = 0.0
        self.damage = 0.0
        self.obj_damage = 0.0
        self.items: list[int] = []
        self.kills = self.deaths = self.assists = self.wards = 0
        self.dead_until = 0.0
        self.tilt_until = -1
        self.tilt_prone = rng.random() < 0.35
        self.pos = (0.0, 0.0)
        self.pending_purchase: int | None = None

    @property
    def level(self) -> int:
        return _level(self.xp)

    @property
    def item_cost(self) -> float:
        return float(sum(FALLBACK_ITEMS[i].cost for i in self.items))

    def tilted(self, minute: int) -> bool:
        return minute <= self.tilt_until


def generate_match(seed: int, index: int = 0) -> tuple[dict, dict]:
    rng = np.random.default_rng(seed)
    match_id = f"SYN_{100000 + index}"
    players: list[_Player] = []
    for t_i, team in enumerate(("blue", "red")):
        for r_i, role in enumerate(ROLES):
            champ, kind = CHAMPIONS[role][rng.integers(len(CHAMPIONS[role]))]
            players.append(_Player(t_i * 5 + r_i + 1, team, role, champ, kind, rng))
    by_team = {t: [p for p in players if p.team == t] for t in ("blue", "red")}

    adv = rng.normal(0, 0.4)  # latent blue advantage
    counters = {t: {"towers": 0, "inhibs": 0, "dragons": 0, "grubs": 0} for t in ("blue", "red")}
    next_dragon, next_baron, grubs_left, herald_taken = 5, 20, 6, False
    baron_push = {"blue": -99, "red": -99}
    frames: list[dict] = []
    events_by_min: dict[int, list[dict]] = {}
    end_minute = 42

    def ts(minute: int) -> int:
        return int((minute - 1) * 60000 + rng.integers(1000, 59000))

    def add(minute: int, ev: dict) -> None:
        events_by_min.setdefault(minute, []).append(ev)

    def team_scale(team: str, minute: int) -> float:
        return float(np.mean([tier_factor(p.tier, minute) for p in by_team[team]]))

    frames.append(_frame(players, 0, []))
    for m in range(1, 43):
        # Latent momentum: composition scaling + noise.
        adv = 0.96 * adv + 0.6 * (team_scale("blue", m) - team_scale("red", m)) + rng.normal(0, 0.42)
        p_blue = _sigmoid(0.55 * adv)
        alive = {t: [p for p in by_team[t] if p.dead_until <= m - 1] for t in by_team}
        fought: set[int] = set()

        # --- Kills -----------------------------------------------------------------------
        if m >= 2:
            for _ in range(min(6, rng.poisson(0.35 + 0.05 * m))):
                win_team = "blue" if rng.random() < p_blue else "red"
                lose_team = "red" if win_team == "blue" else "blue"
                victims = [p for p in alive[lose_team] if p.dead_until <= m - 1]
                killers = [p for p in alive[win_team] if p.dead_until <= m - 1]
                if not victims or not killers:
                    continue
                weights = np.array([3.5 if v.tilted(m) else 1.0 for v in victims])
                victim = victims[rng.choice(len(victims), p=weights / weights.sum())]
                killer = killers[rng.integers(len(killers))]
                others = [k for k in killers if k is not killer]
                n_assist = int(rng.integers(0, min(3, len(others)) + 1)) if others else 0
                assisters = list(rng.choice(others, n_assist, replace=False)) if n_assist else []
                if victim.tilted(m):
                    pos = _deep_position(victim.team, rng)
                else:
                    pos = (victim.pos[0] + rng.normal(0, 300), victim.pos[1] + rng.normal(0, 300))
                t = ts(m)
                add(m, {"type": "CHAMPION_KILL", "timestamp": t, "killerId": killer.pid,
                        "victimId": victim.pid, "assistingParticipantIds": [a.pid for a in assisters],
                        "position": {"x": int(pos[0]), "y": int(pos[1])}})
                killer.kills += 1
                killer.gold += 300
                killer.unspent += 300
                for a in assisters:
                    a.assists += 1
                    a.gold += 150 / len(assisters)
                    a.unspent += 150 / len(assisters)
                victim.deaths += 1
                victim.dead_until = t / 60000 + (10 + 2.2 * victim.level) / 60 * (1 + max(0, m - 15) / 60)
                fought.update({killer.pid, victim.pid, *[a.pid for a in assisters]})
                adv += 0.08 if win_team == "blue" else -0.08
                if victim.tilt_prone and not victim.tilted(m) and rng.random() < 0.45 and m >= 4:
                    victim.tilt_until = m + int(rng.integers(3, 6))

        # --- Objectives ------------------------------------------------------------------
        if m >= next_dragon and rng.random() < 0.55:
            side = "blue" if rng.random() < _sigmoid(0.6 * adv) else "red"
            jungler = by_team[side][1]
            add(m, {"type": "ELITE_MONSTER_KILL", "timestamp": ts(m), "killerId": jungler.pid,
                    "killerTeamId": 100 if side == "blue" else 200, "monsterType": "DRAGON",
                    "monsterSubType": str(rng.choice(["FIRE_DRAGON", "WATER_DRAGON", "EARTH_DRAGON",
                                                      "AIR_DRAGON", "HEXTECH_DRAGON", "CHEMTECH_DRAGON"]))})
            counters[side]["dragons"] += 1
            adv += 0.15 if side == "blue" else -0.15
            next_dragon = m + 5
            _objective_damage(by_team[side], 6000, rng)
            _tilt_on_loss(by_team["red" if side == "blue" else "blue"], m, rng)
        if 6 <= m <= 13 and grubs_left > 0 and rng.random() < 0.25:
            side = "blue" if rng.random() < _sigmoid(0.5 * adv) else "red"
            for _ in range(3):
                add(m, {"type": "ELITE_MONSTER_KILL", "timestamp": ts(m), "killerId": by_team[side][1].pid,
                        "killerTeamId": 100 if side == "blue" else 200, "monsterType": "HORDE"})
            grubs_left -= 3
            adv += 0.08 if side == "blue" else -0.08
        if 15 <= m <= 19 and not herald_taken and rng.random() < 0.3:
            side = "blue" if rng.random() < _sigmoid(0.5 * adv) else "red"
            add(m, {"type": "ELITE_MONSTER_KILL", "timestamp": ts(m), "killerId": by_team[side][1].pid,
                    "killerTeamId": 100 if side == "blue" else 200, "monsterType": "RIFTHERALD"})
            herald_taken = True
            adv += 0.25 if side == "blue" else -0.25
        if m >= next_baron and rng.random() < 0.16 + 0.03 * min(abs(adv), 4):
            side = "blue" if rng.random() < _sigmoid(0.9 * adv) else "red"
            add(m, {"type": "ELITE_MONSTER_KILL", "timestamp": ts(m), "killerId": by_team[side][1].pid,
                    "killerTeamId": 100 if side == "blue" else 200, "monsterType": "BARON_NASHOR"})
            adv += 0.7 if side == "blue" else -0.7
            baron_push[side] = m
            next_baron = m + 6
            _objective_damage(by_team[side], 12000, rng)
            _tilt_on_loss(by_team["red" if side == "blue" else "blue"], m, rng)
        if 5 <= m <= 13:
            for side in ("blue", "red"):
                share = _sigmoid(0.6 * adv) if side == "blue" else 1 - _sigmoid(0.6 * adv)
                for _ in range(rng.poisson(0.7 * share * 2)):
                    owner = 200 if side == "blue" else 100
                    add(m, {"type": "TURRET_PLATE_DESTROYED", "timestamp": ts(m), "teamId": owner,
                            "laneType": str(rng.choice(["TOP_LANE", "MID_LANE", "BOT_LANE"]))})
                    lucky = by_team[side][rng.integers(5)]
                    lucky.gold += 125
                    lucky.unspent += 125
        if m >= 8:
            push = {s: 2.0 if m - baron_push[s] <= 3 else 0.0 for s in ("blue", "red")}
            p_tower = 0.12 + 0.03 * min(abs(adv), 5) + 0.25 * (push["blue"] + push["red"]) / 2
            for _ in range(1 + int(rng.random() < p_tower / 2)):
                if rng.random() >= p_tower:
                    continue
                side = "blue" if rng.random() < _sigmoid(0.9 * adv + push["blue"] - push["red"]) else "red"
                if counters[side]["towers"] >= 11:
                    continue
                owner = 200 if side == "blue" else 100
                counters[side]["towers"] += 1
                add(m, {"type": "BUILDING_KILL", "timestamp": ts(m), "teamId": owner,
                        "buildingType": "TOWER_BUILDING", "killerId": by_team[side][0].pid})
                for p in by_team[side]:
                    p.gold += 50
                    p.unspent += 50
                _objective_damage(by_team[side], 3000, rng)
                adv += 0.08 if side == "blue" else -0.08
                if counters[side]["towers"] >= 5 and counters[side]["inhibs"] < 3 and rng.random() < 0.35:
                    counters[side]["inhibs"] += 1
                    add(m, {"type": "BUILDING_KILL", "timestamp": ts(m), "teamId": owner,
                            "buildingType": "INHIBITOR_BUILDING", "killerId": by_team[side][0].pid})
                    adv += 0.25 if side == "blue" else -0.25

        # --- Economy, XP, items, vision, damage, positions ----------------------------------
        for p in players:
            ally_adv = adv if p.team == "blue" else -adv
            dead_frac = min(1.0, max(0.0, p.dead_until - (m - 1)))
            tilt = p.tilted(m)
            live = 1 - dead_frac
            lane_factor = 1 + 0.04 * np.clip(ally_adv, -3, 3)
            ramp = 0.0 if m == 1 else (0.55 if m == 2 else 1.0)
            cs_gain = max(0.0, rng.normal(CS_RATE[p.role], 0.9)) * ramp * live * lane_factor * (0.28 if tilt else 1)
            if p.role == "JUNGLE":
                p.jcs += cs_gain
            else:
                p.cs += cs_gain
            p.xp += max(0.0, rng.normal(XP_RATE[p.role] + 8 * m, 60)) * live * lane_factor * (0.5 if tilt else 1)
            passive = 122 if m >= 2 else 0
            income = passive + cs_gain * 21
            p.gold += income
            p.unspent += income
            new_wards = int(rng.poisson(WARD_RATE[p.role] * (0.1 if tilt else 1) * live))
            p.wards += new_wards
            for _ in range(new_wards):
                add(m, {"type": "WARD_PLACED", "timestamp": ts(m), "creatorId": p.pid,
                        "wardType": "SIGHT_WARD" if p.role != "UTILITY" else "CONTROL_WARD"})
            _buy(p, rng)
            fight = 1.0 if p.pid in fought else 0.0
            p.damage += (40 + 28 * p.level + 0.035 * p.item_cost) * tier_factor(p.tier, m) \
                * (0.7 + 0.8 * fight) * rng.uniform(0.7, 1.3) * live
            p.pos = _position(p, m, tilt, rng)

        # --- Game end ----------------------------------------------------------------------
        ended = False
        if m >= 22:
            p_end = 0.35 * _sigmoid(abs(adv) - 4.0) + (0.2 if m >= 35 else 0.0) + (0.04 if m >= 26 else 0.0)
            ended = rng.random() < p_end or m == 42
        if ended:
            end_minute = m
            duration_s = (m - 1) * 60 + int(rng.integers(5, 58))
            final = _frame(players, duration_s * 1000, sorted(events_by_min.get(m, []),
                                                               key=lambda e: e["timestamp"]))
            for e in final["events"]:
                e["timestamp"] = min(e["timestamp"], duration_s * 1000)
            frames.append(final)
            break
        frames.append(_frame(players, m * 60000, sorted(events_by_min.get(m, []), key=lambda e: e["timestamp"])))

    blue_win = rng.random() < _sigmoid(1.1 * adv)
    duration_s = int(frames[-1]["timestamp"] / 1000)
    game_creation = 1_727_000_000_000 + index * 3_600_000
    match = {
        "metadata": {"matchId": match_id, "participants": [p.puuid for p in players]},
        "info": {
            "gameCreation": game_creation,
            "gameDuration": duration_s,
            "gameVersion": "14.19.622.1234",
            "queueId": 420,
            "platformId": "SYN",
            "teams": [{"teamId": 100, "win": blue_win}, {"teamId": 200, "win": not blue_win}],
            "participants": [_participant_json(p, blue_win, duration_s) for p in players],
        },
    }
    timeline = {
        "metadata": {"matchId": match_id, "participants": [p.puuid for p in players]},
        "info": {"frameInterval": 60000, "frames": frames,
                 "participants": [{"participantId": p.pid, "puuid": p.puuid} for p in players]},
    }
    _ = end_minute
    return match, timeline


def _objective_damage(team: list[_Player], amount: float, rng) -> None:
    shares = rng.dirichlet(np.ones(len(team)))
    for p, s in zip(team, shares):
        p.obj_damage += amount * s


def _tilt_on_loss(team: list[_Player], minute: int, rng) -> None:
    """Objective losses can also trigger tilt in tilt-prone players."""
    for p in team:
        if p.tilt_prone and not p.tilted(minute) and rng.random() < 0.15:
            p.tilt_until = minute + int(rng.integers(3, 5))


def _buy(p: _Player, rng) -> None:
    if len(p.items) >= 6:
        return
    has_boots = any(i in BOOTS for i in p.items)
    if not has_boots and p.unspent >= 1100 and len(p.items) >= 1:
        item = BOOTS[rng.integers(len(BOOTS))]
    else:
        pool = [i for i in ITEM_POOLS[p.kind] if i not in p.items] or ITEM_POOLS[p.kind]
        item = pool[rng.integers(len(pool))]
    cost = FALLBACK_ITEMS[item].cost
    if p.unspent >= cost:
        p.unspent -= cost
        p.items.append(item)
        p.pending_purchase = item  # emitted into the next frame by _frame()


def _deep_position(team: str, rng) -> tuple[float, float]:
    base = (10500, 9500) if team == "blue" else (4300, 5300)
    return (base[0] + rng.normal(0, 700), base[1] + rng.normal(0, 700))


def _position(p: _Player, minute: int, tilt: bool, rng) -> tuple[float, float]:
    if tilt:
        return _deep_position(p.team, rng)
    if minute >= 20:
        center = (7400, 7400)
        return (center[0] + rng.normal(0, 900), center[1] + rng.normal(0, 900))
    if p.role == "JUNGLE":
        pos = (rng.uniform(3500, 8000), rng.uniform(3500, 7500))
    else:
        pos = BLUE_LANE_POS[p.role]
        pos = (pos[0] + rng.normal(0, 400), pos[1] + rng.normal(0, 400))
    return pos if p.team == "blue" else _mirror(pos)


def _frame(players: list[_Player], timestamp: int, events: list[dict]) -> dict:
    extra = []
    for p in players:
        item = getattr(p, "pending_purchase", None)
        if item is not None:
            extra.append({"type": "ITEM_PURCHASED", "timestamp": max(0, timestamp - 30000),
                          "participantId": p.pid, "itemId": item})
            p.pending_purchase = None
    pframes = {}
    for p in players:
        pframes[str(p.pid)] = {
            "participantId": p.pid,
            "totalGold": int(p.gold),
            "currentGold": int(p.unspent),
            "xp": int(p.xp),
            "level": p.level,
            "minionsKilled": int(p.cs),
            "jungleMinionsKilled": int(p.jcs),
            "position": {"x": int(p.pos[0]), "y": int(p.pos[1])},
            "damageStats": {"totalDamageDoneToChampions": int(p.damage)},
        }
    return {"timestamp": timestamp, "participantFrames": pframes,
            "events": sorted(events + extra, key=lambda e: e["timestamp"])}


def _participant_json(p: _Player, blue_win: bool, duration_s: int) -> dict:
    return {
        "participantId": p.pid,
        "puuid": p.puuid,
        "riotIdGameName": p.name,
        "riotIdTagline": "SYN",
        "championName": p.champ,
        "teamId": 100 if p.team == "blue" else 200,
        "teamPosition": p.role,
        "kills": p.kills,
        "deaths": p.deaths,
        "assists": p.assists,
        "totalMinionsKilled": int(p.cs),
        "neutralMinionsKilled": int(p.jcs),
        "goldEarned": int(p.gold),
        "totalDamageDealtToChampions": int(p.damage),
        "damageDealtToObjectives": int(p.obj_damage),
        "visionScore": int(p.wards * 1.6 + duration_s / 60 * 0.3),
        "win": blue_win if p.team == "blue" else not blue_win,
        "item0": p.items[0] if p.items else 0,
    }
