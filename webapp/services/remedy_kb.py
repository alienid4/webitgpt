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
    _entry(1, "cpu_load", "CPU / Load 偏高", ["load", "cpu", "idle"], ["uptime", "ps aux --sort=-pcpu | head -10", "top -bn1 | head -20"], ["不要直接 kill 不明程序，先確認服務歸屬與異動窗口。"], ["uptime", "top -bn1 | head -5"]),
    _entry(1, "memory_swap", "記憶體或 Swap 壓力", ["memory", "swap", "free"], ["free -m", "vmstat 1 5", "ps aux --sort=-pmem | head -10"], ["清 cache 或重啟服務前需確認是否影響交易服務。"], ["free -m"]),
    _entry(2, "nic_error", "網卡 error / drop", ["error", "drop", "nic"], ["ip -s link", "ethtool -S <nic> | head -30"], ["需與網路團隊確認 switch port，不要單邊更改網卡設定。"], ["ip -s link"]),
    _entry(2, "tcp_retransmit", "TCP retransmit / listen drop", ["retrans", "listen", "drop"], ["ss -s", "netstat -s | egrep -i 'retrans|listen|drop'"], ["調整 kernel 參數前要先保留現值並建立 rollback。"], ["ss -s"]),
    _entry(2, "conntrack", "Conntrack 容量接近上限", ["conntrack"], ["sysctl net.netfilter.nf_conntrack_count net.netfilter.nf_conntrack_max"], ["提高上限會增加記憶體使用，需評估主機資源。"], ["sysctl net.netfilter.nf_conntrack_count"]),
    _entry(2, "time_wait", "TIME_WAIT 過多", ["time_wait", "time-wait"], ["ss -tan state time-wait | wc -l", "cat /proc/sys/net/ipv4/ip_local_port_range"], ["不要直接縮短 TCP timeout，先確認連線模式。"], ["ss -s"]),
    _entry(2, "ping_loss", "Ping 延遲或遺失", ["loss", "ping"], ["ping -c 5 ${PING_TGT:-127.0.0.1}", "tracepath ${PING_TGT:-127.0.0.1}"], ["跨網段問題需與網路團隊共同確認。"], ["ping -c 3 ${PING_TGT:-127.0.0.1}"]),
    _entry(3, "ap_listener", "AP listener 未開或異常", ["listener", "port", "listen"], ["ss -ltnp", "systemctl --failed --no-pager"], ["重啟 AP 前需確認是否有交易或批次作業。"], ["ss -ltnp | grep <port>"]),
    _entry(3, "ap_process", "AP 程序資源偏高", ["process", "fd", "thread"], ["ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -15", "ls /proc/<pid>/fd | wc -l"], ["調整 process 前需先確認 owner 與近期異動。"], ["ps -p <pid> -o pid,comm,%cpu,%mem"]),
    _entry(3, "ap_journal", "AP 近期 journal 警告", ["journal", "error", "failed"], ["journalctl -u <unit> -p warning -n 100 --no-pager"], ["不要只清 log，需先保留異常證據。"], ["journalctl -u <unit> -p warning -n 20 --no-pager"]),
    _entry(4, "health_check", "Health check port 異常", ["health", "curl", "port"], ["curl -fsS http://127.0.0.1:<port>/health", "ss -ltnp | grep <port>"], ["改 health endpoint 前需同步監控與 LB 設定。"], ["curl -fsS http://127.0.0.1:<port>/health"]),
    _entry(4, "remote_port", "遠端服務 port 無法連線", ["connect", "timeout", "refused"], ["nc -vz <ip> <port>", "ss -tan | grep <port>"], ["開防火牆需走變更流程並記錄來源目的。"], ["nc -vz <ip> <port>"]),
    _entry(4, "lb_backend", "LB backend 健康異常", ["backend", "vip", "lb"], ["curl -I http://127.0.0.1:<port>/", "ss -ltnp"], ["先確認是否為單節點移除，避免誤判整體服務中斷。"], ["curl -I http://127.0.0.1:<port>/"]),
    _entry(5, "close_wait", "CLOSE_WAIT 過多", ["close_wait"], ["ss -tan state close-wait | wc -l", "ss -tan state close-wait | head"], ["通常是應用未關閉 socket，重啟前需先抓 thread dump。"], ["ss -s"]),
    _entry(5, "top_client", "單一來源連線過多", ["established", "client", "top"], ["ss -tan state established | awk '{print $5}' | cut -d: -f1 | sort | uniq -c | sort -nr | head"], ["封鎖來源前需確認是否為合法批次或監控。"], ["ss -tan state established | wc -l"]),
    _entry(5, "syn_recv", "SYN_RECV 堆積", ["syn_recv", "syn-recv"], ["ss -tan state syn-recv | wc -l", "netstat -s | grep -i syn"], ["可能涉及流量尖峰或攻擊，需同步網路與資安。"], ["ss -s"]),
    _entry(6, "disk_full", "磁碟或 inode 使用率過高", ["disk", "inode", "df"], ["df -h", "df -i", "du -xhd1 /var | sort -h | tail"], ["清檔前需確認保留政策，禁止刪除未知資料。"], ["df -h", "df -i"]),
    _entry(6, "tmp_full", "/tmp 空間不足", ["tmp"], ["df -h /tmp", "find /tmp -xdev -type f -mtime +7 -ls | head"], ["刪除 tmp 前需確認是否有執行中程序使用。"], ["df -h /tmp"]),
    _entry(6, "large_log", "大型 log 檔案", ["log", "large"], ["find /var/log -xdev -type f -size +500M -ls", "journalctl --disk-usage"], ["壓縮或清理前需保留稽核必要紀錄。"], ["journalctl --disk-usage"]),
    _entry(7, "ntp", "時間同步異常", ["ntp", "chrony", "offset"], ["timedatectl", "chronyc tracking || ntpq -p"], ["時間異常會影響憑證、交易排序與稽核時間戳。"], ["timedatectl"]),
    _entry(7, "cert_expire", "憑證即將到期", ["cert", "expire", "keystore"], ["find /etc/pki /opt -name '*.crt' -o -name '*.pem' 2>/dev/null | head", "openssl x509 -in <cert> -noout -dates"], ["換憑證需同步 AP、LB、監控與回滾憑證。"], ["openssl x509 -in <cert> -noout -dates"]),
    _entry(7, "timezone", "時區設定不一致", ["timezone", "time zone"], ["timedatectl", "date"], ["調整時區會影響排程與日誌判讀。"], ["timedatectl"]),
    _entry(8, "oracle", "Oracle listener / process 異常", ["oracle", "1521", "tns"], ["ps -ef | grep -i ora_", "ss -ltnp | grep 1521"], ["DB 修復需 DBA 共同確認，不由巡檢系統直接改。"], ["ss -ltnp | grep 1521"]),
    _entry(8, "mssql", "MSSQL process / port 異常", ["mssql", "1433", "sqlservr"], ["ps -ef | grep sqlservr", "ss -ltnp | grep 1433"], ["需確認資料庫維護窗口。"], ["ss -ltnp | grep 1433"]),
    _entry(8, "mysql", "MySQL/MariaDB process / port 異常", ["mysql", "mariadb", "3306"], ["ps -ef | egrep 'mysqld|mariadbd'", "ss -ltnp | grep 3306"], ["調整前需先備份設定與確認 replication。"], ["ss -ltnp | grep 3306"]),
    _entry(8, "db2", "DB2 process / port 異常", ["db2", "50000"], ["ps -ef | grep db2sysc", "ss -ltnp | grep 50000"], ["需 DBA 確認 instance 狀態。"], ["ss -ltnp | grep 50000"]),
    _entry(8, "postgres", "PostgreSQL process / port 異常", ["postgres", "5432"], ["ps -ef | grep postgres", "ss -ltnp | grep 5432"], ["重啟前需確認 WAL、replication 與連線數。"], ["ss -ltnp | grep 5432"]),
    _entry(8, "mongo", "MongoDB process / port 異常", ["mongo", "27017"], ["ps -ef | grep mongod", "ss -ltnp | grep 27017"], ["需確認 replica set 狀態與備份。"], ["ss -ltnp | grep 27017"]),
    _entry(9, "oom", "OOM kill 紀錄", ["oom"], ["dmesg -T | grep -i oom | tail -20", "journalctl -k -g oom -n 20 --no-pager"], ["需確認被殺程序與記憶體尖峰來源。"], ["journalctl -k -g oom -n 5 --no-pager"]),
    _entry(9, "failed_unit", "systemd failed units", ["failed", "systemd"], ["systemctl --failed --no-pager"], ["清 failed 前先確認 root cause。"], ["systemctl --failed --no-pager"]),
    _entry(9, "kernel_tainted", "Kernel tainted", ["tainted"], ["cat /proc/sys/kernel/tainted"], ["可能涉及 driver 或 kernel module，需保留版本資訊。"], ["cat /proc/sys/kernel/tainted"]),
    _entry(9, "mce", "Machine Check Exception", ["mce", "machine check"], ["dmesg -T | egrep -i 'mce|machine check'"], ["硬體錯誤需通知平台或虛擬化團隊。"], ["dmesg -T | egrep -i 'mce|machine check' | tail"]),
    _entry(10, "login_trace", "登入軌跡異常", ["login", "failed"], ["last -n 20", "journalctl _COMM=sshd -n 50 --no-pager"], ["涉及帳號安全時需保留 audit log。"], ["last -n 5"]),
    _entry(10, "change_trace", "近期設定異動", ["change", "modified"], ["find /etc /opt -xdev -mtime -1 -type f 2>/dev/null | head -50"], ["異動檔案需對照變更單與備份。"], ["find /etc /opt -xdev -mtime -1 -type f 2>/dev/null | head"]),
    _entry(10, "service_restart_trace", "服務啟停軌跡", ["restart", "start", "stop"], ["journalctl --since '24 hours ago' | egrep -i 'started|stopped|restart' | tail -50"], ["需確認是否為排程、手動異動或異常重啟。"], ["journalctl --since '24 hours ago' -p warning --no-pager | tail"]),
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
