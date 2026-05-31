# 2026-05-31 現場查詢：證券阿發資產與核心影響圖主機數不一致

用途：一次收集 `10.92.198.14` 上 webitgpt 實際資料，判斷「資產管理看到 6 台，但核心影響圖只畫 4 台」是資料欄位、系統同步、host_refs、還是拓撲 API 過濾造成。

注意：

- 請在 `10.92.198.14` 主機上執行，不是在 221。
- 不需要貼密碼、API Token、私鑰。
- 輸出檔會放在 `/tmp/webitgpt_topology_asset_afah_<時間>.txt`。
- 執行後把整份 `.txt` 回傳即可。

## 一次性查詢指令

```bash
cat >/tmp/webitgpt_topology_asset_afah_check.sh <<'SH'
#!/usr/bin/env bash
set -u

STAMP="$(date +%Y%m%d%H%M%S)"
OUT="/tmp/webitgpt_topology_asset_afah_${STAMP}.txt"
exec > >(tee "${OUT}") 2>&1

echo "==== BASIC ===="
date
hostname -f 2>/dev/null || hostname
cat /etc/redhat-release 2>/dev/null || true
id

echo
echo "==== SERVICE ===="
systemctl status webitgpt --no-pager 2>/dev/null || true
ss -ltnp 2>/dev/null | grep -E '8002|27017' || true

echo
echo "==== HEALTH ===="
curl -sS http://127.0.0.1:8002/health || true
echo

echo
echo "==== PYTHON / MONGO / TOPOLOGY ===="
cd /opt/webitgpt || exit 1
PYBIN="/opt/webitgpt/venv/bin/python"
if [ ! -x "${PYBIN}" ]; then
  PYBIN="python3"
fi

"${PYBIN}" - <<'PY'
from pprint import pprint

from webapp import config
from webapp.services.mongo_service import get_db
from webapp.services import dependency_service

db = get_db()
terms = ["證券阿發", "阿發", "發"]
focus_system_id = "SYS-6FC6D394"
host_fields = {
    "_id": 0,
    "asset_seq": 1,
    "asset_name": 1,
    "system_name": 1,
    "hostname": 1,
    "ip": 1,
    "status": 1,
    "host_type": 1,
    "device_type": 1,
    "group_name": 1,
    "apid": 1,
}
system_fields = {
    "_id": 0,
    "system_id": 1,
    "display_name": 1,
    "host_refs": 1,
    "metadata": 1,
    "description": 1,
    "owner": 1,
}

def text_hit(doc):
    searchable_keys = ["asset_seq", "asset_name", "system_name", "hostname", "ip", "group_name", "apid"]
    blob = " ".join(str(doc.get(key) or "") for key in searchable_keys)
    return any(term in blob for term in terms)

def host_key(doc):
    return str(doc.get("asset_seq") or doc.get("hostname") or doc.get("ip") or "").strip()

print("CONFIG")
print({"version": config.VERSION, "patch_id": config.PATCH_ID, "build_time": config.BUILD_TIME})

hosts = list(db.hosts.find({}, host_fields).sort("ip", 1))
matched_hosts = [host for host in hosts if text_hit(host)]
print("\nHOST COLLECTION COUNTS")
print({"hosts_total": len(hosts), "matched_by_terms": len(matched_hosts), "terms": terms})
print("\nMATCHED HOSTS")
for host in matched_hosts:
    pprint(host)

systems = list(db.dependency_systems.find({}, system_fields).sort("system_id", 1))
matched_host_keys = {host_key(host) for host in matched_hosts if host_key(host)}
related_systems = []
for system in systems:
    display = str(system.get("display_name") or "")
    refs = {str(item) for item in system.get("host_refs") or []}
    if system.get("system_id") == focus_system_id or any(term in display for term in terms) or refs.intersection(matched_host_keys):
        related_systems.append(system)

print("\nDEPENDENCY SYSTEM COUNTS")
print({"dependency_systems_total": len(systems), "related_systems": len(related_systems), "focus_system_id": focus_system_id})
print("\nRELATED DEPENDENCY SYSTEMS")
for system in related_systems:
    pprint(system)

print("\nTOPOLOGY API DATA")
topology = dependency_service.topology(view="core_impact", center=focus_system_id, limit=200)
nodes = topology.get("nodes") or []
edges = topology.get("edges") or []
host_nodes = [node for node in nodes if str(node.get("id") or "").startswith("host:")]
system_nodes = [node for node in nodes if not str(node.get("id") or "").startswith(("host:", "core:"))]
print("meta:")
pprint(topology.get("meta"))
print("system_nodes:")
for node in system_nodes:
    pprint(node)
print("host_nodes:")
for node in host_nodes:
    pprint(node)
print("edges:")
for edge in edges:
    pprint(edge)

drawn_keys = {
    str(node.get("id") or "").replace("host:", "", 1)
    for node in host_nodes
}
expected_keys = matched_host_keys
print("\nCOMPARE")
print({
    "matched_host_keys": sorted(expected_keys),
    "drawn_host_keys": sorted(drawn_keys),
    "missing_in_topology": sorted(expected_keys - drawn_keys),
    "extra_in_topology": sorted(drawn_keys - expected_keys),
})
PY

echo
echo "==== PAGE SMOKE ===="
curl -sS -o /tmp/webitgpt_core_impact_${STAMP}.html -w "core_impact_http=%{http_code}\n" "http://127.0.0.1:8002/dependencies?view=core_impact&center=SYS-6FC6D394" || true
grep -o 'host:[^"]*' /tmp/webitgpt_core_impact_${STAMP}.html 2>/dev/null | head -30 || true

echo
echo "==== OUTPUT FILE ===="
echo "${OUT}"
SH

bash /tmp/webitgpt_topology_asset_afah_check.sh
```

## 回傳方式

請回傳最後顯示的檔案內容，例如：

```bash
cat /tmp/webitgpt_topology_asset_afah_YYYYMMDDHHMMSS.txt
```

或直接上傳該 `.txt` 檔。
