"""Multi-TF blend logic for the orderflow voice."""
from sources.orderflow import _blend_bias, _flow_bias


def test_flow_bias_directions():
    assert _flow_bias(True, False, 100.0, 0.0) == 1      # stacked buy + pos delta
    assert _flow_bias(False, True, -100.0, 0.0) == -1    # stacked sell + neg delta
    assert _flow_bias(False, False, 0.0, 0.0) == 0       # nothing
    assert _flow_bias(True, False, -50.0, 0.0) == 0      # stack vs delta conflict


def test_blend_all_aligned_long():
    direction, conf, score = _blend_bias(1, [1, 1])
    assert direction == "long" and score == 1.0 and conf > 0.8


def test_blend_fast_alone_is_not_enough():
    # Fast long but both higher TFs flat -> 0.5/1.0 = 0.5 -> still long but weaker;
    # fast long with higher TFs short -> neutral/short, never long.
    d_conflict, _, s_conflict = _blend_bias(1, [-1, -1])
    assert d_conflict != "long" and s_conflict == 0.0
    d_opposed, _, _ = _blend_bias(1, [-1, None])
    assert d_opposed == "neutral"


def test_blend_missing_tf_drops_weight():
    # 15m missing: fast long + 1h long -> (0.5+0.2)/(0.7) = 1.0
    direction, _, score = _blend_bias(1, [None, 1])
    assert direction == "long" and score == 1.0


def test_blend_neutral_band():
    direction, _, score = _blend_bias(0, [1, -1])
    assert direction == "neutral" and abs(score) < 0.35
