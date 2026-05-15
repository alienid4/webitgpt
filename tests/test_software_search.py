from webapp.services.legacy_parity_service import _software_change_matches, _software_record_matches


def test_software_search_matches_package_version_source_and_host():
    record = {
        "hostname": "secansible",
        "asset_seq": "HW-00000221",
        "host_type": "linux",
        "name": "python3-setuptools-wheel",
        "version": "53.0.0-15.el9",
        "source": "rpm",
        "status": "installed",
    }

    assert _software_record_matches(record, ["python3", "el9"])
    assert _software_record_matches(record, ["secansible", "rpm"])
    assert _software_record_matches(record, ["installed"])
    assert not _software_record_matches(record, ["debian"])


def test_software_change_search_matches_changed_package():
    change = {
        "hostname": "secansible",
        "changes": [{"type": "版本變更", "name": "openssl", "before": "1.1", "after": "3.0"}],
    }

    assert _software_change_matches(change, ["openssl"])
    assert _software_change_matches(change, ["版本變更", "3.0"])
    assert not _software_change_matches(change, ["nginx"])
