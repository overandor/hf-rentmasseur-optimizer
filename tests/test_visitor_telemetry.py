from __future__ import annotations

from pathlib import Path

from rm_traffic.visitor_telemetry import ProfileObservation, TelemetryStore, normalize_location


def make_observation(username: str, observed_at: str, *, online: bool | None, location: str = "Manhattan, NY", reciprocal: bool = False) -> ProfileObservation:
    city, state, in_nyc, in_new_york = normalize_location(location)
    return ProfileObservation(username=username, profile_url=f"https://rentmasseur.com/{username}", observed_at=observed_at, location_text=location, city=city, state=state, in_nyc=in_nyc, in_new_york=in_new_york, is_online=online, last_online_at=observed_at if online else None, reciprocal_visit_performed=reciprocal, has_message_control=True, can_message=True, profile_hash=f"hash-{observed_at}")


def test_new_york_location_normalization():
    assert normalize_location("Manhattan, NY")[2:] == (True, True)
    assert normalize_location("Buffalo, New York")[2:] == (False, True)
    assert normalize_location("Jersey City, NJ")[2:] == (False, False)


def test_profile_counts_and_reciprocal_visits(tmp_path: Path):
    store = TelemetryStore(tmp_path / "telemetry.sqlite3")
    run_id = store.begin_run()
    store.record(run_id, make_observation("client1", "2026-07-19T12:00:00+00:00", online=False, reciprocal=True))
    store.finish_run(run_id, "success", {"discovered_count": 1, "scanned_count": 1, "ny_count": 1, "online_count": 0, "contactable_count": 1, "reciprocal_visits": 1}, [])
    run_id = store.begin_run()
    store.record(run_id, make_observation("client1", "2026-07-19T13:00:00+00:00", online=False, reciprocal=False))
    rows = store.profile_rows("new-york")
    assert rows[0]["observed_visitor_runs"] == 2
    assert rows[0]["reciprocal_visits"] == 1
    assert rows[0]["can_message"] == 1
    store.close()


def test_online_session_is_closed_and_summarized(tmp_path: Path):
    store = TelemetryStore(tmp_path / "telemetry.sqlite3")
    run_id = store.begin_run()
    store.record(run_id, make_observation("client2", "2026-07-19T12:00:00+00:00", online=True))
    store.record(run_id, make_observation("client2", "2026-07-19T12:30:00+00:00", online=True))
    store.record(run_id, make_observation("client2", "2026-07-19T12:45:00+00:00", online=False))
    rows = store.profile_rows("new-york")
    assert rows[0]["average_online_seconds"] == 1800.0
    assert rows[0]["median_online_seconds"] == 1800.0
    assert rows[0]["usual_online_hours"]
    store.close()
