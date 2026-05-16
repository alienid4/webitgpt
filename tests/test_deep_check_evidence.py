from pathlib import Path

from webapp.services.deep_check_service import (
    NETWORK_CHECKPOINTS,
    _ap_endpoint_verdict,
    _ap_listener_verdict,
    _customer_impact_lines,
    _evidence_summary,
    _display_timestamp,
    _network_verdict,
    _performance_verdict,
    _problem_summary,
    _recommendation,
    _session_verdict,
    _storage_verdict,
    _threshold_summary,
    _network_checkpoint_lines,
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


def test_performance_warn_explains_exact_metric_and_action():
    spec = {"idx": 1, "name": "效能"}
    text = "load average: 9.00, 4.00, 2.00\n%Cpu(s): 80.0 us, 10.0 sy, 10.0 id\nSwap: 1024 700 324"

    assert _performance_verdict(0, text) == "WARN"
    problem = _problem_summary(spec, 0, text, "WARN")
    recommendation = _recommendation(spec, "WARN", text)

    assert "CPU idle=10.0%" in problem
    assert "Swap 使用率" in problem
    assert "top -bn1" in recommendation
    assert "free -m" in recommendation


def test_network_evidence_keeps_packet_loss_and_counters():
    spec = {"idx": 2, "name": "網路"}
    evidence = _evidence_summary(
        spec,
        0,
        "RX: bytes packets errors dropped missed mcast\n1000 10 0 0 0 0\n3 packets transmitted, 3 received, 0% packet loss",
        "PASS",
    )

    assert "rc=0" in evidence
    assert "NET-04 Ping loss" in evidence
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
    assert "NET-02 網卡 dropped：WARN" in evidence
    assert "615350 1035 0 4 0 0" in evidence
    assert "dropped=4" in evidence
    assert "lo:" not in evidence


def test_network_loopback_only_is_not_warn_and_is_explained():
    spec = {"idx": 2, "name": "網路"}
    text = """1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536
RX: bytes packets errors dropped missed mcast
1000 10 0 0 0 0
TX: bytes packets errors dropped carrier collsns
1000 10 0 0 0 0"""

    assert _network_verdict(0, text) == "PASS"
    problem = _problem_summary(spec, 0, text, "PASS")
    evidence = _evidence_summary(spec, 0, text, "PASS")
    threshold = _threshold_summary(spec, text)

    assert "目的" in problem
    assert "lo" in problem
    assert "本機迴圈介面" in problem
    assert "不代表對外網路異常" in evidence
    assert "忽略 lo" in threshold


def test_network_has_seven_sn_checkpoints():
    assert len(NETWORK_CHECKPOINTS) == 7
    assert [item[0] for item in NETWORK_CHECKPOINTS] == [f"NET-0{i}" for i in range(1, 8)]
    lines = _network_checkpoint_lines("3 packets transmitted, 2 received, 33% packet loss")
    assert len(lines) == 7
    assert any(line.startswith("NET-04 Ping loss：WARN") for line in lines)


def test_network_conntrack_checkpoint_has_sn_and_commands():
    spec = {"idx": 2, "name": "網路"}
    text = "net.netfilter.nf_conntrack_count = 900\nnet.netfilter.nf_conntrack_max = 1000"

    assert _network_verdict(0, text) == "WARN"
    problem = _problem_summary(spec, 0, text, "WARN")
    evidence = _evidence_summary(spec, 0, text, "WARN")
    recommendation = _recommendation(spec, "WARN", text)

    assert "NET-05" in problem
    assert "NET-05 conntrack 用量：WARN" in evidence
    assert "900/1000" in recommendation
    assert "nf_conntrack_count" in recommendation
    assert "ss -tan" in recommendation


def test_network_time_wait_checkpoint_has_sn_and_commands():
    spec = {"idx": 2, "name": "網路"}
    text = "2500 TIME-WAIT\n10 ESTAB\n"

    assert _network_verdict(0, text) == "WARN"
    problem = _problem_summary(spec, 0, text, "WARN")
    recommendation = _recommendation(spec, "WARN", text)

    assert "NET-06" in problem
    assert "TIME_WAIT=2500" in recommendation
    assert "ss -tan state time-wait" in recommendation
    assert "ip_local_port_range" in recommendation


def test_ap_endpoint_warn_gives_health_and_port_commands():
    spec = {"idx": 4, "name": "AP 連線"}
    text = "curl: (7) Failed to connect to 127.0.0.1 port 8002: Connection refused"

    assert _ap_endpoint_verdict(0, text) == "WARN"
    problem = _problem_summary(spec, 0, text, "WARN")
    recommendation = _recommendation(spec, "WARN", text)

    assert "health endpoint" in problem
    assert "ss -ltnp" in recommendation
    assert "curl -v" in recommendation


def test_session_one_close_wait_is_not_warn():
    text = "53 ESTAB\n22 TIME-WAIT\n12 LISTEN\n1 CLOSE-WAIT"
    assert _session_verdict(0, text) == "PASS"
    problem = _problem_summary({"idx": 5, "name": "Session"}, 0, text, "PASS")
    assert "CLOSE-WAIT=1" in problem
    assert "SYN-RECV=0" in problem


def test_time_cert_pass_explains_what_was_checked():
    spec = {"idx": 7, "name": "時間與憑證"}
    text = """Sat 2026-05-16 07:20:00 CST
System clock synchronized: yes
NTP service: active
Reference ID    : C0A80101 (192.168.1.1)
Leap status     : Normal
/etc/pki/tls/certs/ca-bundle.crt"""

    assert _problem_summary(spec, 0, text, "PASS").startswith("時間與憑證檢查目的")
    problem = _problem_summary(spec, 0, text, "PASS")
    evidence = _evidence_summary(spec, 0, text, "PASS")
    recommendation = _recommendation(spec, "PASS", text)

    assert "PASS 證據" in problem
    assert "System clock synchronized: yes" in problem
    assert "Leap status     : Normal" in evidence
    assert "憑證檔清單可讀" in evidence
    assert "PASS 證明" in recommendation
    assert "openssl x509 -enddate" in recommendation


def test_deep_check_display_timestamp_uses_readable_minutes():
    assert _display_timestamp("20260516_011157") == "20260516 01:11"
    assert _display_timestamp("20260516 091257") == "20260516 09:12"
    html = (ROOT / "webapp/templates/inspections.html").read_text(encoding="utf-8")
    assert "l3.parsed.display_timestamp or l3.parsed.timestamp" in html


def test_storage_warn_names_mount_and_cleanup_safely():
    spec = {"idx": 6, "name": "Storage"}
    text = "Filesystem Size Used Avail Use% Mounted on\n/dev/sda1 20G 19G 1G 95% /var"

    assert _storage_verdict(0, text) == "WARN"
    problem = _problem_summary(spec, 0, text, "WARN")
    recommendation = _recommendation(spec, "WARN", text)

    assert "/var 使用率 95%" in problem
    assert "df -h" in recommendation
    assert "不要直接刪除未知檔案" in recommendation


def test_ap_listener_ignores_unrelated_failed_unit_when_listener_exists():
    text = """
LISTEN 0 128 0.0.0.0:9444 0.0.0.0:*
UNIT LOAD ACTIVE SUB DESCRIPTION
setroubleshootd.service loaded failed failed SETroubleshoot daemon for processing new SELinux denial logs
"""
    assert _ap_listener_verdict(0, text) == "PASS"
    problem = _problem_summary({"idx": 3, "name": "AP Listener"}, 0, text, "PASS")
    evidence = _evidence_summary({"idx": 3, "name": "AP Listener"}, 0, text, "PASS")
    assert "LISTEN" in problem
    assert "0.0.0.0:9444" in evidence


def test_infra_recommendation_is_emergency_os_focused():
    text = "setroubleshootd.service loaded failed failed SETroubleshoot daemon for processing new SELinux denial logs"
    recommendation = _recommendation({"idx": 9, "name": "Infra"}, "WARN", text)

    assert "OOM" in recommendation
    assert "machine check" in recommendation
    assert "sudo systemctl stop firewalld" in recommendation
    assert "sudo systemctl start firewalld" in recommendation


def test_locked_account_recommendation_lists_real_accounts():
    text = "ACCOUNT_LOCKED appsvc\nACCOUNT_LOCKED batch01\nACCOUNT_LOCKED appsvc\n"
    spec = {"idx": 10, "name": "運維軌跡"}

    problem = _problem_summary(spec, 0, text, "WARN")
    recommendation = _recommendation(spec, "WARN", text)
    evidence = _evidence_summary(spec, 0, text, "WARN")

    assert "appsvc、batch01" in problem
    assert "<account>" not in recommendation
    assert "1. 先確認帳號用途" in recommendation
    assert "可直接執行指令" in recommendation
    assert "id appsvc" in recommendation
    assert "id batch01" in recommendation
    assert "# appsvc" in recommendation
    assert "sudo passwd -u appsvc" in recommendation
    assert "sudo usermod -U batch01" in recommendation
    assert "passwd -S batch01" in recommendation
    assert "appsvc 被鎖定" in evidence
    assert "batch01 被鎖定" in evidence


def test_locked_account_without_name_does_not_offer_placeholder_unlock():
    recommendation = _recommendation({"idx": 10, "name": "運維軌跡"}, "WARN", "bash: -c: line 1: syntax error")

    assert "1. 不能使用 <account>" in recommendation
    assert "sudo passwd -u <account>" not in recommendation
    assert "sudo awk -F:" in recommendation


def test_network_counter_recommendation_includes_interface_commands():
    spec = {"idx": 2, "name": "網路"}
    text = """2: ens33: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500
RX: bytes packets errors dropped missed mcast
615350 1035 0 17 0 0
TX: bytes packets errors dropped carrier collsns
129959 420 0 0 0 0"""
    recommendation = _recommendation(spec, "WARN", text)

    assert "NET-02" in recommendation
    assert "1. 先確認是哪張網卡" in recommendation
    assert "ip -s link show dev ens33" in recommendation
    assert "ethtool -S ens33" in recommendation
    assert "<nic>" not in recommendation


def test_network_counter_recommendation_keeps_other_sn_commands():
    spec = {"idx": 2, "name": "網路"}
    text = """2: ens33: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500
RX: bytes packets errors dropped missed mcast
615350 1035 0 17 0 0
net.netfilter.nf_conntrack_count = 900
net.netfilter.nf_conntrack_max = 1000
2500 TIME-WAIT"""
    recommendation = _recommendation(spec, "WARN", text)

    assert "NET-02" in recommendation
    assert "# NET-05 conntrack 用量" in recommendation
    assert "# NET-06 TIME_WAIT / port range" in recommendation
    assert "nf_conntrack_count" in recommendation
    assert "ss -tan state time-wait" in recommendation


def test_inspection_template_preserves_recommendation_line_breaks():
    html = (ROOT / "webapp/templates/inspections.html").read_text(encoding="utf-8")
    css = (ROOT / "webapp/static/css/cathay.css").read_text(encoding="utf-8")

    assert '<div class="l3-recommendation"><strong>建議處置：</strong><pre>' in html
    assert ".l3-recommendation pre" in css
    assert "white-space: pre-wrap" in css


def test_l3_evidence_boxes_do_not_overflow_panel():
    css = (ROOT / "webapp/static/css/cathay.css").read_text(encoding="utf-8")

    assert ".l3-evidence .detail" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
    assert "overflow-wrap: anywhere" in css
    assert "box-sizing: border-box" in css


def test_l3_customer_impact_summary_is_line_based():
    items = [
        {"idx": 1, "name": "效能", "verdict": "PASS", "impact": "正常"},
        {"idx": 2, "name": "網路", "verdict": "WARN", "impact": "dropped=17"},
        {"idx": 4, "name": "AP 連線", "verdict": "WARN", "impact": "curl failed"},
    ]

    assert _customer_impact_lines(items) == ["2. 網路：dropped=17", "4. AP 連線：curl failed"]


def test_deep_check_preview_route_returns_plain_text():
    route = (ROOT / "webapp/routes/api_deep_check.py").read_text(encoding="utf-8")
    html = (ROOT / "webapp/templates/inspections.html").read_text(encoding="utf-8")

    assert "content_type=\"text/plain; charset=utf-8\"" in route
    assert "Content-Disposition" in route
    preview_block = route.split("def preview_api", 1)[1].split("def parsed_api", 1)[0]
    assert "return Response(" in preview_block
    assert "result.get(\"content\", \"\")" in preview_block
    assert "純文字摘要" in html
