from nexuspulse.models.registry import is_remake


def test_short_game_is_remake():
    assert is_remake({"info": {"gameDuration": 180, "participants": []}})


def test_early_surrender_flag_is_remake():
    match = {"info": {"gameDuration": 900, "participants": [{"gameEndedInEarlySurrender": True}]}}
    assert is_remake(match)


def test_normal_game_is_kept():
    match = {"info": {"gameDuration": 1700, "participants": [{"gameEndedInEarlySurrender": False}]}}
    assert not is_remake(match)
