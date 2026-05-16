from webapp.services.legacy_parity_service import _build_diagnostic_check, DIAGNOSTIC_ASPECTS


def test_connectivity_detail_is_human_readable():
    raw = "secansible\n 10:23:01 up 7:02,  0 users,  load average: 0.09, 0.10, 0.04"

    check = _build_diagnostic_check("connectivity", "連線狀態", 0, raw, "")

    assert check["status"] == "ok"
    assert check["detail"] == "連線:可連線\n開機:7 小時 2 分鐘\n登入:0人"
    assert "load average" not in check["detail"]
    assert check["raw_detail"] == raw


def test_all_opening_aspects_use_human_summary_not_raw_output():
    samples = {
        "connectivity": "secansible\n 10:23:01 up 7:02,  0 users,  load average: 0.09, 0.10, 0.04",
        "resource": "%Cpu(s): 12.0 us, 88.0 id, 2.0 wa\nMem: 100 36 64\nSwap: 100 2 98\nFilesystem 1K-blocks Used Available Use% Mounted on\n/dev/sda1 100 60 40 60% /",
        "filesystem": "Filesystem Type Size Used Avail Use% Mounted on\n/dev/sda1 ext4 20G 3G 17G 15% /\n%Cpu(s): 1.0 us, 99.0 id, 2.0 wa",
        "process": "PID USER COMMAND %CPU\n1 root systemd 0.0",
        "service": "0 loaded units listed.",
        "account": "users=42\nsudo/wheel=wheel:x:10:sysinfra",
        "security": "LISTEN 0 128 0.0.0.0:22 0.0.0.0:*",
        "package": "bash 5.1\npython3 3.9",
        "log": "",
    }
    raw_tokens = {
        "connectivity": "load average",
        "resource": "%Cpu",
        "filesystem": "Filesystem Type",
        "process": "PID USER COMMAND",
        "service": "loaded units listed",
        "account": "sudo/wheel=",
        "security": "LISTEN 0",
        "package": "bash 5.1",
    }

    for key, label in DIAGNOSTIC_ASPECTS:
        check = _build_diagnostic_check(key, label, 0, samples[key], "")
        assert check["detail"]
        if key in raw_tokens:
            assert raw_tokens[key] not in check["detail"], key
        assert check["raw_detail"] == samples[key]


def test_resource_and_filesystem_cards_are_compact_metrics():
    resource = _build_diagnostic_check(
        "resource",
        "CPU / 記憶體 / 磁碟",
        0,
        "%Cpu(s): 12.0 us, 88.0 id, 2.0 wa\nMem: 100 36 64\nSwap: 100 2 98",
        "",
    )
    filesystem = _build_diagnostic_check(
        "filesystem",
        "檔案系統",
        0,
        "Filesystem Type Size Used Avail Use% Mounted on\n/dev/sda1 ext4 20G 3G 17G 15% /\n%Cpu(s): 1.0 us, 99.0 id, 2.0 wa",
        "",
    )

    assert resource["detail"] == "CPU:12%\nMEMORY:36%\nSWAP:2%"
    assert filesystem["detail"] == "Filesystem:15%\nIO:2%"
    assert "建議處置" not in resource["detail"]
    assert "建議處置" not in filesystem["detail"]


def test_opening_normal_cards_stay_compact():
    samples = {
        "process": "PID COMMAND %CPU %MEM\n1 systemd 0.0 1.0\n2 python 5.0 3.0\n3 java 2.0 9.0",
        "service": "0 loaded units listed.\n__IMPORTANT_SERVICES__\nsshd=active\ncron=active",
        "account": "users=29\n",
        "security": "FIREWALL_PORTS=22/tcp 8002/tcp\nJAVA_CERT=not_installed",
        "package": "packages=200\nchanged_7d=0",
        "log": "",
    }
    expected = {
        "process": "CPU最高:python 5%\nMEM最高:java 9%",
        "service": "失敗服務:無\n重要服務未啟動:無",
        "account": "帳號總數:29\n鎖定帳號:無",
        "security": "防火牆Port:22, 8002\nJava憑證:未安裝",
        "package": "套件總數:200\n近7日異動:0",
        "log": "警示:無",
    }

    for key, raw in samples.items():
        check = _build_diagnostic_check(key, key, 0, raw, "")
        assert check["detail"] == expected[key]
        assert "建議處置" not in check["detail"]
