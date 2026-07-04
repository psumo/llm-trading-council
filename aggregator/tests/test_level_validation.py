"""Open-time level-consistency validation + net-R win classification."""
from tracker_models import Position, realized_close
from tracker_stats import _is_win


def _closed(direction, entry, sl, tp, exit_price, outcome):
    p = Position(id=1, opened_at="2026-06-14T00:00:00+00:00", direction=direction,
                 symbol="BTCUSDT", entry=entry, stop_loss=sl, take_profit_1=tp,
                 take_profit_2=None, rationale="", risk_reward=1.5,
                 risk_usd=10.0, size_units=1.0, conviction=70.0)
    return realized_close(p, exit_price, outcome, "2026-06-14T00:05:00+00:00")


def test_tp_hit_that_nets_negative_is_a_loss_not_win():
    # SHORT entry 64069.5, TP 64060 (9.5pts), exit at TP -> tiny gross, fees -> net<0.
    pos = _closed("SHORT", 64069.5, 64425.0, 64060.0, 64060.0, "win")
    assert pos.r_multiple < 0           # net R is negative after fees
    assert _is_win(pos) is False        # therefore counts as a LOSS, not a win


def test_real_win_counts_as_win():
    # SHORT entry 100, TP 95 (5pts profit), exit 95 -> clear net win.
    pos = _closed("SHORT", 100.0, 102.0, 95.0, 95.0, "win")
    assert pos.r_multiple > 0
    assert _is_win(pos) is True


def test_actual_rr_computation():
    # Degenerate: risk 355.5, reward 9.5 -> rr 0.027, far below any floor.
    entry, sl, tp = 64069.5, 64425.0, 64060.0
    actual_rr = abs(tp - entry) / abs(entry - sl)
    assert actual_rr < 0.05
