from webapp.services.host_schema import assert_valid_host_doc


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
