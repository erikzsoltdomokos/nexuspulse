from nexuspulse.static_data import FALLBACK_ITEMS
from nexuspulse.synthetic import generate_match
from nexuspulse.timeline import WIN_FEATURES, parse_match


def _timeline(events, n_frames=4):
    frames = []
    for m in range(n_frames):
        pf = {str(pid): {"totalGold": 500 + m * 300, "xp": m * 400, "level": 1 + m,
                         "minionsKilled": m * 7, "jungleMinionsKilled": 0,
                         "position": {"x": 1000 * pid, "y": 1000}, "damageStats": {}}
              for pid in range(1, 11)}
        frames.append({"timestamp": m * 60000, "participantFrames": pf,
                       "events": [e for e in events if (m - 1) * 60000 < e["timestamp"] <= m * 60000]})
    return {"info": {"frames": frames}}


def _match():
    parts = [{"participantId": pid, "puuid": f"p{pid}", "championName": "Ahri",
              "teamId": 100 if pid <= 5 else 200, "teamPosition": "MIDDLE", "win": pid <= 5}
             for pid in range(1, 11)]
    return {"metadata": {"matchId": "EUW1_1"},
            "info": {"gameDuration": 180, "gameVersion": "", "participants": parts,
                     "teams": [{"teamId": 100, "win": True}, {"teamId": 200, "win": False}]}}


def test_event_accounting():
    events = [
        {"type": "CHAMPION_KILL", "timestamp": 70000, "killerId": 1, "victimId": 6,
         "assistingParticipantIds": [2], "position": {"x": 5000, "y": 5000}},
        {"type": "ELITE_MONSTER_KILL", "timestamp": 90000, "killerTeamId": 200, "killerId": 7,
         "monsterType": "DRAGON"},
        {"type": "BUILDING_KILL", "timestamp": 130000, "teamId": 200, "buildingType": "TOWER_BUILDING"},
        {"type": "TURRET_PLATE_DESTROYED", "timestamp": 140000, "teamId": 100},
        {"type": "ITEM_PURCHASED", "timestamp": 150000, "participantId": 1, "itemId": 3031},
        {"type": "ITEM_PURCHASED", "timestamp": 151000, "participantId": 2, "itemId": 3089},
        {"type": "ITEM_UNDO", "timestamp": 152000, "participantId": 2, "beforeId": 3089, "afterId": 0},
        {"type": "WARD_PLACED", "timestamp": 160000, "creatorId": 5, "wardType": "SIGHT_WARD"},
    ]
    pm = parse_match(_match(), _timeline(events), FALLBACK_ITEMS)
    last = pm.team_minutes.iloc[-1]
    assert last["kill_diff"] == 1
    assert last["dragon_diff"] == -1
    assert last["tower_diff"] == 1          # red tower died -> blue took it
    assert last["plate_diff"] == -1         # blue plate died -> red took it
    assert last["items_completed_blue"] == 1  # the undone Rabadon's does not count
    p5 = pm.player_minutes[(pm.player_minutes.participant_id == 5)].iloc[-1]
    assert p5["wards_placed"] == 1
    # Minute 1 is before the kill (70 s), so red still has all five alive.
    assert pm.team_minutes.iloc[0]["alive_red"] == 5
    assert len(pm.deaths) == 1 and "isolated" in pm.deaths[0]
    assert pm.winner == "blue"


def test_synthetic_match_parses_with_all_features():
    match, timeline = generate_match(3, 3)
    pm = parse_match(match, timeline, FALLBACK_ITEMS)
    assert pm.duration_min >= 20
    assert set(WIN_FEATURES) <= set(pm.team_minutes.columns)
    assert len(pm.participants) == 10
    assert pm.player_minutes["cs"].max() > 0
