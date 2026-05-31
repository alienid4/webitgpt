import pytest

from webapp.services.host_schema import ValidationError, assert_valid_host_doc


def test_minimal_host_doc_is_valid():
    warnings = assert_valid_host_doc(
        {
            "division": "IT",
            "department": "Operations",
            "asset_seq": "HW-00000221",
            "status": "active",
            "group_name": "H9",
            "asset_name": "Inspection host",
            "device_type": "VM",
            "quantity": 1,
            "owner": "IT",
            "environment": "DEV",
            "hostname": "secansible",
            "os": "Debian 13",
            "custodian": "Alienlee",
            "company": "example-corp",
            "integrity": 1,
            "confidentiality": 2,
            "availability": 1,
            "host_type": "linux",
            "dc": "dunan",
            "connection": "local",
        }
    )
    assert warnings == []


def test_draft_like_hosts_allow_partial_cmdb_fields():
    warnings = assert_valid_host_doc(
        {
            "asset_seq": "DISC-202605310001-10-1-1-10",
            "hostname": "scan-10-1-1-10",
            "status": "pending_data",
            "host_type": "linux",
            "ip": "10.1.1.10",
        },
        partial=True,
    )
    assert warnings == ["asset_seq should look like HW-XXXXXXXX"]


def test_active_hosts_still_require_formal_cmdb_fields():
    with pytest.raises(ValidationError) as exc:
        assert_valid_host_doc(
            {
                "asset_seq": "DISC-202605310001-10-1-1-10",
                "hostname": "scan-10-1-1-10",
                "status": "active",
                "host_type": "linux",
                "ip": "10.1.1.10",
            }
        )

    assert "division is required" in exc.value.errors
    assert "server hosts require connection" in exc.value.errors
