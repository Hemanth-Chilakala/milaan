import pytest

from milaan.matching import jaro_winkler, unique_subset


@pytest.mark.parametrize(
    "left,right,expected",
    [("MARTHA", "MARHTA", 0.961111), ("DWAYNE", "DUANE", 0.84), ("", "A", 0), ("A", "A", 1)],
)
def test_similarity_reference_examples(left, right, expected):
    assert jaro_winkler(left, right) == pytest.approx(expected, abs=1e-6)


def test_only_unique_subset_is_accepted():
    assert unique_subset(100, [("B", 40), ("A", 60)]) == ("A", "B")
    assert unique_subset(100, [("A", 50), ("B", 50), ("C", 50)]) is None
    assert unique_subset(100, [(str(i), 1) for i in range(13)]) is None
    assert unique_subset(100, [("A", 60), ("B", 30)]) is None
    assert unique_subset(100, [("A", 50), ("A", 50)]) is None
