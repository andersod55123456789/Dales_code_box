import pytest

from trainlog.engine import (accessory_sets, backoff_load, distribute, fartlek,
                             is_deload, landing_count, ohp_prescription,
                             program_week, pullup_total, rope_interval,
                             round_half_up, round_to, week_type, working_load)
from trainlog.program import load_program

P = load_program()
C = P["config"]
RATIOS = P["pullups"]["distribution_ratios"]
ROPE = next(i for i in P["anchor"] if i["key"] == "jump_rope")


@pytest.mark.parametrize("x,e", [(2.5, 3), (1.2, 1), (1.8, 2), (2.4, 2)])
def test_round_half_up(x, e):
    assert round_half_up(x) == e


@pytest.mark.parametrize("x,e", [(114, 115.0), (82.5, 82.5), (57.0, 57.5),
                                 (117.0, 117.5), (148.0, 147.5)])
def test_round_to(x, e):
    assert round_to(x) == e


@pytest.mark.parametrize("c,w,pw,wt", [(1, 1, 1, "A"), (1, 2, 2, "B"),
                                       (1, 3, 3, "A"), (1, 4, 4, "B"),
                                       (2, 1, 5, "A"), (2, 4, 8, "B"),
                                       (3, 3, 11, "A"), (6, 4, 24, "B")])
def test_position(c, w, pw, wt):
    assert program_week(c, w) == pw
    assert week_type(c, w) == wt
    assert is_deload(w) is (w == 4)


@pytest.mark.parametrize("c,w,e", [
    (1, 1, 185.0), (1, 2, 190.0), (1, 3, 190.0), (1, 4, 115.0),
    (2, 1, 190.0), (2, 2, 195.0), (2, 4, 117.5),
    (3, 1, 195.0), (3, 4, 120.0),
    (6, 1, 210.0), (6, 2, 215.0), (6, 4, 130.0)])
def test_back_squat(c, w, e):
    assert working_load(185, "lower", c, w, C) == e


@pytest.mark.parametrize("c,w,e", [
    (1, 1, 135.0), (1, 2, 137.5), (1, 3, 137.5), (1, 4, 82.5),
    (2, 1, 137.5), (2, 2, 140.0), (2, 4, 85.0)])
def test_barbell_row(c, w, e):
    assert working_load(135, "upper", c, w, C) == e


@pytest.mark.parametrize("base,prog,w,e", [
    (135, "lower", 4, 85.0), (185, "lower", 4, 115.0),
    (135, "lower", 2, 140.0), (185, "lower", 1, 185.0)])
def test_other_lifts(base, prog, w, e):
    assert working_load(base, prog, 1, w, C) == e


@pytest.mark.parametrize("wl,e", [(185.0, 147.5), (190.0, 152.5), (135.0, 107.5),
                                  (137.5, 110.0), (195.0, 155.0)])
def test_backoff(wl, e):
    assert backoff_load(wl, C) == e


@pytest.mark.parametrize("c,w,off,sets,load", [
    (1, 1, 0, 3, 95.0), (1, 4, 0, 3, 57.5), (2, 1, 0, 4, 95.0),
    (2, 2, 0, 4, 95.0), (3, 1, 0, 5, 95.0), (4, 1, 0, 5, 97.5),
    (4, 4, 0, 5, 57.5), (5, 1, 0, 5, 100.0), (6, 1, 0, 5, 102.5),
    (6, 1, 1, 5, 100.0), (2, 1, 1, 3, 95.0)])
def test_ohp_ramp(c, w, off, sets, load):
    o = ohp_prescription(c, w, off, C)
    assert (o["sets"], o["load"]) == (sets, load)


@pytest.mark.parametrize("t,e", [(38, [12, 10, 8, 8]), (39, [12, 10, 9, 8]),
                                 (40, [13, 10, 9, 8]), (42, [13, 11, 9, 9]),
                                 (48, [15, 12, 11, 10])])
def test_distribute(t, e):
    assert distribute(t, RATIOS) == e


def test_distribute_invariants():
    for t in range(30, 60):
        d = distribute(t, RATIOS)
        assert sum(d) == t
        assert d == sorted(d, reverse=True)


@pytest.mark.parametrize("c,w,e", [(1, 1, 38), (1, 2, 39), (1, 3, 40),
                                   (1, 4, None), (2, 1, 40), (2, 3, 42),
                                   (6, 1, 48)])
def test_pullup_total(c, w, e):
    assert pullup_total(c, w, P["pullups"]) == e


@pytest.mark.parametrize("ex,w,e", [
    ({"sets": 2, "week3_extra_set": True}, 3, 3),
    ({"sets": 2}, 4, 1),
    ({"sets": 3, "week3_extra_set": True}, 3, 4),
    ({"sets": 3}, 4, 2),
    ({"sets": 4}, 4, 2),
    ({"sets": 3, "protected": True}, 4, 3),
    ({"sets": 3}, 1, 3)])
def test_accessory_sets(ex, w, e):
    assert accessory_sets(ex, w, C) == e


@pytest.mark.parametrize("c,w,e", [
    (1, 1, "30s on / 30s off"), (2, 1, "45s on / 15s off"),
    (3, 1, "60s continuous"), (6, 2, "60s continuous"),
    (1, 4, "skill practice only, untimed"),
    (2, 4, "skill practice only, untimed")])
def test_rope(c, w, e):
    assert rope_interval(c, w, ROPE) == e


@pytest.mark.parametrize("c,w,pk,secs,place", [
    (1, 1, 6, 60, "saturday"), (1, 2, 7, 60, "thursday"),
    (1, 3, 8, 60, "saturday"), (1, 4, 0, 0, None),
    (2, 1, 7, 60, "saturday"), (2, 3, 9, 60, "saturday"),
    (3, 3, 10, 60, "saturday"), (4, 1, 8, 90, "saturday"),
    (6, 3, 10, 90, "saturday")])
def test_fartlek(c, w, pk, secs, place):
    f = fartlek(c, w, P["fartlek"])
    assert (f["pickups"], f["pickup_seconds"], f["placement"]) == (pk, secs, place)


def test_landings():
    tue = P["days"]["tuesday"]["exercises"]
    for week, expect in [(1, 30), (3, 30), (4, 20)]:
        pairs = [(e, accessory_sets(e, week, C)) for e in tue]
        assert landing_count(pairs) == expect
    assert landing_count([(e, 3) for e in P["days"]["monday"]["exercises"]]) == 0
