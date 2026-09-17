from core.normalization import percentile_scores


def test_percentile_scores_preserve_missing_values():
    assert percentile_scores([1, None, 3]) == [0.0, None, 1.0]


def test_percentile_scores_use_neutral_value_when_all_equal():
    assert percentile_scores([0, 0, None]) == [0.5, 0.5, None]
