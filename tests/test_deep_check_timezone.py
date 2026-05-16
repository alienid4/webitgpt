from datetime import datetime, timezone

from webapp.services.deep_check_service import _display_timestamp, _normalize_report_doc


def test_deep_check_timestamp_displays_taipei_time():
    assert _display_timestamp(datetime(2026, 5, 16, 1, 11, 57, tzinfo=timezone.utc)) == "20260516 09:11"


def test_deep_check_naive_mongo_timestamp_is_treated_as_utc():
    assert _display_timestamp(datetime(2026, 5, 16, 1, 39, 1)) == "20260516 09:39"


def test_deep_check_report_prefers_stored_utc_timestamp_for_display():
    report = {
        "timestamp": datetime(2026, 5, 16, 1, 11, 57, tzinfo=timezone.utc),
        "parsed": {"timestamp": "20260516_011157", "display_timestamp": "20260516 01:11"},
    }

    normalized = _normalize_report_doc(report)

    assert normalized["parsed"]["display_timestamp"] == "20260516 09:11"
