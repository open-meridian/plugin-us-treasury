"""The catalogue, from code, as the deployment approves it."""

from __future__ import annotations

from meridian.plugin.v1 import operations_pb2 as ops

from us_treasury.declaration import DECLARATION
from us_treasury.declared import CATALOGUE


def test_three_daily_datasets_of_rates() -> None:
    assert [d.key for d in DECLARATION.catalogue] == ["ust_par", "ust_real", "ust_bills"]
    for dataset in CATALOGUE:
        assert list(dataset.data_types) == ["meridian.v1.Rate"]
        modes = [ops.ObservationMode.Name(m) for m in dataset.modes]
        assert modes == ["OBSERVATION_MODE_PUSH", "OBSERVATION_MODE_PULL"]
        assert dataset.day_time_zone == "America/New_York" and dataset.day_end_minute == 0
        assert dataset.cadence == 86_400
        # No calendar until one of the US government securities market is
        # curated (the spec's Q15); no venue; no aggregator.
        assert not dataset.calendar_id and not dataset.venue_id and not dataset.aggregator
        assert dataset.vendor == "U.S. Department of the Treasury"
    assert [d.history for d in CATALOGUE] == [13_400, 8_400, 8_700]


def test_us_government_work_is_not_one_persons() -> None:
    for dataset in CATALOGUE:
        licence = dataset.licence_default
        assert licence is not None
        assert licence.kept and licence.display
        assert licence.derived_use and licence.derived_use_terms == "not_restricted"
        assert not licence.personal_use and licence.retention_days == 0


def test_the_answers_are_kept_in_storage() -> None:
    assert DECLARATION.storage is not None
    assert [k.name for k in DECLARATION.storage.kinds] == ["responses"]
