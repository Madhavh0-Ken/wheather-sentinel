import pytest

from scripts.ingest_official import parse_assignments


def test_cli_assignment_parser_requires_explicit_unique_name_pairs():
    assert parse_assignments(["rain_rate=RR", "radar_reflectivity=DBZ"]) == {
        "rain_rate": "RR",
        "radar_reflectivity": "DBZ",
    }

    with pytest.raises(ValueError, match="NAME=SOURCE_NAME"):
        parse_assignments(["ambiguous"])
    with pytest.raises(ValueError, match="Duplicate"):
        parse_assignments(["rain_rate=A", "rain_rate=B"])
