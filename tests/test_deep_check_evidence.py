from pathlib import Path

from webapp.services.deep_check_service import (
    _ap_listener_verdict,
    _evidence_summary,
    _problem_summary,
    _recommendation,
    _session_verdict,
)


ROOT = Path(__file__).resolve().parents[1]


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


def test_session_one_close_wait_is_not_warn():
    text = "53 ESTAB\n22 TIME-WAIT\n12 LISTEN\n1 CLOSE-WAIT"
    assert _session_verdict(0, text) == "PASS"
    problem = _problem_summary({"idx": 5, "name": "Session"}, 0, text, "PASS")
    assert "CLOSE-WAIT=1" in problem
    assert "SYN-RECV=0" in problem


def test_ap_listener_warn_points_to_failed_unit_not_listen_lines():
    text = """
LISTEN 0 128 0.0.0.0:9444 0.0.0.0:*
UNIT LOAD ACTIVE SUB DESCRIPTION
setroubleshootd.service loaded failed failed SETroubleshoot daemon for processing new SELinux denial logs
"""
    assert _ap_listener_verdict(0, text) == "WARN"
    problem = _problem_summary({"idx": 3, "name": "AP Listener"}, 0, text, "WARN")
    evidence = _evidence_summary({"idx": 3, "name": "AP Listener"}, 0, text, "WARN")
    assert "setroubleshootd.service" in problem
    assert "setroubleshootd.service" in evidence
    assert "0.0.0.0:9444" not in evidence


def test_setroubleshootd_recommendation_is_manager_readable():
    text = "setroubleshootd.service loaded failed failed SETroubleshoot daemon for processing new SELinux denial logs"
    recommendation = _recommendation({"idx": 9, "name": "Infra"}, "WARN", text)

    assert "這不代表 SELinux 一定有開啟或關閉錯誤" in recommendation
    assert "輔助服務" in recommendation
    assert "需要就修復服務，不需要就可評估停用" in recommendation
    assert "journalctl" not in recommendation
    assert "systemctl" not in recommendation


def test_deep_check_preview_route_returns_plain_text():
    route = (ROOT / "webapp/routes/api_deep_check.py").read_text(encoding="utf-8")
    html = (ROOT / "webapp/templates/inspections.html").read_text(encoding="utf-8")

    assert "content_type=\"text/plain; charset=utf-8\"" in route
    assert "Content-Disposition" in route
    preview_block = route.split("def preview_api", 1)[1].split("def parsed_api", 1)[0]
    assert "return Response(" in preview_block
    assert "result.get(\"content\", \"\")" in preview_block
    assert "純文字摘要" in html
