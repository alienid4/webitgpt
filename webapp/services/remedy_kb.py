from __future__ import annotations

from typing import Any


def _entry(face: int, key: str, title: str, keywords: list[str], commands: list[str], risks: list[str], verify: list[str]) -> dict[str, Any]:
    return {
        "face": face,
        "key": key,
        "title": title,
        "keywords": keywords,
        "commands": commands,
        "risks": risks,
        "verify": verify,
    }


REMEDY_KB: list[dict[str, Any]] = [
    _entry(1, "load_high", "Load 過高 / CPU idle 偏低", ["load", "idle", "cpu"], ["ps aux --sort=-pcpu | head -10", "top -bn1 | head -20"], ["不要直接 kill 不明程序，需先確認服務角色與變更窗口。"], ["uptime", "top -bn1 | head -5"]),
    _entry(1, "swap_high", "Swap 使用偏高", ["swap"], ["free -m", "vmstat 1 5"], ["清 cache 或重啟服務可能影響交易或批次。"], ["free -m"]),
    _entry(2, "conntrack", "conntrack 使用率偏高", ["conntrack"], ["sysctl net.netfilter.nf_conntrack_count net.netfilter.nf_conntrack_max"], ["調整核心參數前需確認容量與資安規範。"], ["sysctl net.netfilter.nf_conntrack_count"]),
    _entry(2, "time_wait", "TIME_WAIT 過多", ["time_wait"], ["ss -tan state time-wait | wc -l", "cat /proc/sys/net/ipv4/ip_local_port_range"], ["不要任意縮短 TCP timeout，可能影響連線穩定。"], ["ss -s"]),
    _entry(2, "syn_drop", "SYN / Listen drops", ["syn", "listen", "drop"], ["netstat -s | egrep -i 'listen|syn|drop'", "ss -ltn"], ["調整 backlog 前需確認 AP 是否承受流量。"], ["netstat -s | egrep -i 'listen|syn|drop'"]),
    _entry(2, "nic_error", "NIC error / dropped", ["error", "dropped", "nic"], ["ip -s link", "ethtool -S <nic> | head"], ["網卡或交換器異常需跨團隊確認。"], ["ip -s link"]),
    _entry(3, "ap_listener", "AP listener 不存在", ["listener", "port", "not listening"], ["ss -ltnp", "systemctl status <unit>"], ["啟停服務前需確認是否有正式變更單。"], ["ss -ltnp | grep <port>"]),
    _entry(3, "ap_journal", "AP 近期錯誤", ["journal", "error"], ["journalctl -u <unit> -n 100 --no-pager"], ["清 log 會影響事後追蹤，不可直接刪除。"], ["journalctl -u <unit> -p warning -n 20 --no-pager"]),
    _entry(4, "health_port", "健康檢查 port 異常", ["health", "port"], ["curl -sS http://127.0.0.1:<port>/health", "ss -ltnp | grep <port>"], ["不要把 health check 異常直接視為服務全掛，需比對 AP log。"], ["curl -sS http://127.0.0.1:<port>/health"]),
    _entry(5, "session_close_wait", "CLOSE_WAIT 過多", ["close_wait"], ["ss -tan state close-wait | wc -l", "ss -tan state close-wait | head"], ["通常需修 AP 連線釋放邏輯，重啟只是暫解。"], ["ss -s"]),
    _entry(5, "top_client", "來源 IP 連線集中", ["top", "client", "established"], ["ss -tan state established | awk '{print $5}' | cut -d: -f1 | sort | uniq -c | sort -nr | head"], ["封鎖 IP 前需確認是否為正常批次或代理來源。"], ["ss -s"]),
    _entry(6, "disk_full", "磁碟或 inode 偏高", ["disk", "inode", "full"], ["df -h", "df -i", "du -xhd1 /var | sort -h"], ["刪檔前需確認保留規範，log 建議先壓縮或歸檔。"], ["df -h", "df -i"]),
    _entry(6, "tmp_full", "/tmp 使用率偏高", ["tmp"], ["df -h /tmp", "find /tmp -xdev -type f -mtime +7 -ls | head"], ["不可刪除正在被程序使用的暫存檔。"], ["df -h /tmp"]),
    _entry(7, "ntp", "NTP 時間不同步", ["ntp", "chrony", "offset"], ["chronyc tracking || ntpq -p", "timedatectl"], ["時間校正可能影響憑證、交易時間戳與排程。"], ["timedatectl", "chronyc tracking || true"]),
    _entry(7, "cert_expire", "憑證即將到期", ["cert", "expire", "keystore"], ["keytool -list -v -keystore $JAVA_HOME/lib/security/cacerts | grep -i 'until' | head"], ["更新憑證需確認 trust chain 與回復計畫。"], ["keytool -list -keystore $JAVA_HOME/lib/security/cacerts | head"]),
    _entry(8, "oracle", "Oracle listener / process 異常", ["oracle", "1521", "tns"], ["ps -ef | grep -i ora_", "ss -ltnp | grep 1521"], ["不可直接重啟 DB，需 DBA 確認。"], ["ss -ltnp | grep 1521"]),
    _entry(8, "mssql", "MSSQL process / port 異常", ["mssql", "1433", "sqlservr"], ["ps -ef | grep sqlservr", "ss -ltnp | grep 1433"], ["需 DBA 確認資料庫狀態。"], ["ss -ltnp | grep 1433"]),
    _entry(8, "mysql", "MySQL/MariaDB process / port 異常", ["mysql", "mariadb", "3306"], ["ps -ef | egrep 'mysqld|mariadbd'", "ss -ltnp | grep 3306"], ["需先確認 replication 與備份狀態。"], ["ss -ltnp | grep 3306"]),
    _entry(8, "db2", "DB2 process / port 異常", ["db2", "50000"], ["ps -ef | grep db2sysc", "ss -ltnp | grep 50000"], ["需 DBA 確認 instance。"], ["ss -ltnp | grep 50000"]),
    _entry(8, "postgres", "PostgreSQL process / port 異常", ["postgres", "5432"], ["ps -ef | grep postgres", "ss -ltnp | grep 5432"], ["需確認資料庫角色與連線池。"], ["ss -ltnp | grep 5432"]),
    _entry(8, "mongo", "MongoDB process / port 異常", ["mongo", "27017"], ["ps -ef | grep mongod", "ss -ltnp | grep 27017"], ["不可任意重啟，需確認 replica set 或容器狀態。"], ["ss -ltnp | grep 27017"]),
    _entry(9, "oom", "OOM kill 紀錄", ["oom"], ["dmesg -T | grep -i oom | tail -20", "journalctl -k -g oom -n 20 --no-pager"], ["需先找出記憶體消耗來源，不可只重啟。"], ["journalctl -k -g oom -n 5 --no-pager"]),
    _entry(9, "failed_unit", "systemd failed units", ["failed", "systemd"], ["systemctl --failed --no-pager"], ["啟停服務前需確認服務歸屬。"], ["systemctl --failed --no-pager"]),
    _entry(9, "kernel_tainted", "Kernel tainted", ["tainted"], ["cat /proc/sys/kernel/tainted"], ["可能涉及 driver 或 kernel module，需保留證據。"], ["cat /proc/sys/kernel/tainted"]),
    _entry(9, "mce", "Machine Check Exception", ["mce", "machine check"], ["dmesg -T | egrep -i 'mce|machine check'"], ["可能是硬體異常，需通知主機或虛擬化團隊。"], ["dmesg -T | egrep -i 'mce|machine check' | tail"]),
    _entry(10, "login_trace", "登入軌跡異常", ["login", "failed"], ["last -n 20", "journalctl _COMM=sshd -n 50 --no-pager"], ["不要刪除 auth log，需保留稽核證據。"], ["last -n 5"]),
    _entry(10, "change_trace", "近期異動軌跡", ["change", "modified"], ["find /etc /opt -xdev -mtime -1 -type f 2>/dev/null | head -50"], ["檔案異動需比對變更單。"], ["find /etc /opt -xdev -mtime -1 -type f 2>/dev/null | head"]),
    _entry(10, "service_restart_trace", "服務重啟軌跡", ["restart", "start"], ["journalctl -u '*' --since '24 hours ago' | egrep -i 'started|stopped|restart' | tail -50"], ["需確認是否為預期排程或人工操作。"], ["journalctl --since '24 hours ago' -p warning --no-pager | tail"]),
    _entry(6, "large_log", "大型 log 檔案", ["log", "large"], ["find /var/log -xdev -type f -size +500M -ls"], ["不可直接清空仍被程序開啟的 log。"], ["find /var/log -xdev -type f -size +500M -ls"]),
    _entry(2, "ping_loss", "Ping 延遲或遺失", ["ping", "loss"], ["ping -c 5 ${PING_TGT:-127.0.0.1}"], ["網路延遲需比對同網段與跨網段結果。"], ["ping -c 3 ${PING_TGT:-127.0.0.1}"]),
]


def match_remedies(item: dict[str, Any]) -> list[dict[str, Any]]:
    if item.get("verdict") not in {"WARN", "FAIL"}:
        return []
    text = " ".join(str(item.get(key, "")) for key in ("name", "actual", "impact", "action")).lower()
    matched = []
    for entry in REMEDY_KB:
        if entry["face"] != item.get("idx"):
            continue
        if any(keyword.lower() in text for keyword in entry["keywords"]):
            matched.append({key: entry[key] for key in ("key", "title", "commands", "risks", "verify")})
    return matched
