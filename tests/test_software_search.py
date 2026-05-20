from webapp.services.legacy_parity_service import _software_change_matches, _software_record_matches
from webapp.services.legacy_parity_service import _software_host_lookup


def test_software_search_matches_package_version_source_and_host():
    record = {
        "hostname": "secansible",
        "asset_seq": "HW-00000221",
        "ip": "192.168.1.221",
        "ip_addresses": ["192.168.1.221", "10.10.1.221"],
        "host_type": "linux",
        "name": "python3-setuptools-wheel",
        "version": "53.0.0-15.el9",
        "source": "rpm",
        "status": "installed",
    }

    assert _software_record_matches(record, ["python3", "el9"])
    assert _software_record_matches(record, ["secansible", "rpm"])
    assert _software_record_matches(record, ["192.168.1.221"])
    assert _software_record_matches(record, ["10.10.1.221"])
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


def test_software_host_lookup_indexes_hostname_and_asset_seq(monkeypatch):
    monkeypatch.setattr(
        "webapp.services.legacy_parity_service._hosts",
        lambda: [{"hostname": "secansible", "asset_seq": "HW-00000221", "ip": "192.168.1.221"}],
    )

    lookup = _software_host_lookup()

    assert lookup["secansible"]["ip"] == "192.168.1.221"
    assert lookup["HW-00000221"]["ip"] == "192.168.1.221"
