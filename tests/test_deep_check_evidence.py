from webapp.services.deep_check_service import _evidence_summary


def test_pass_evidence_includes_returncode_and_sample_output():
    spec = {"idx": 1, "name": "效能"}
    evidence = _evidence_summary(
        spec,
        0,
        "top - 10:00:00 up 1 day, load average: 0.01, 0.02, 0.03\nMem: 2048 total 512 used",
        "PASS",
    )

    assert "rc=0" in evidence
    assert "判定=PASS" in evidence
    assert "load average" in evidence


def test_network_evidence_keeps_packet_loss_and_counters():
    spec = {"idx": 2, "name": "網路"}
    evidence = _evidence_summary(
        spec,
        0,
        "RX: bytes packets errors dropped missed mcast\n1000 10 0 0 0 0\n3 packets transmitted, 3 received, 0% packet loss",
        "PASS",
    )

    assert "rc=0" in evidence
    assert "packet loss" in evidence
    assert "RX:" in evidence


def test_network_evidence_includes_interface_and_counter_values():
    spec = {"idx": 2, "name": "網路"}
    evidence = _evidence_summary(
        spec,
        0,
        """2: ens33: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500
    RX: bytes packets errors dropped missed mcast
    615350 1035 0 4 0 0
    TX: bytes packets errors dropped carrier collsns
    129959 420 0 0 0 0
3 packets transmitted, 3 received, 0% packet loss""",
        "WARN",
    )

    assert "ens33" in evidence
    assert "615350 1035 0 4 0 0" in evidence
    assert "dropped=4" in evidence
    assert "lo:" not in evidence
