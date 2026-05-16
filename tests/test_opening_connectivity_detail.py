from webapp.services.legacy_parity_service import _build_diagnostic_check, DIAGNOSTIC_ASPECTS


def test_connectivity_detail_is_human_readable():
    raw = "secansible\n 10:23:01 up 7:02,  0 users,  load average: 0.09, 0.10, 0.04"

    check = _build_diagnostic_check("connectivity", "連線狀態", 0, raw, "")

    assert check["status"] == "ok"
    assert "連線狀態：主機可連線。" in check["detail"]
    assert "開機狀態：已開機 7 小時 2 分鐘。" in check["detail"]
    assert "使用者：目前無登入使用者。" in check["detail"]
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
