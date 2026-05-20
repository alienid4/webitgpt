from __future__ import annotations

from webapp.services.nmon_raw_service import parse_nmon_raw


def test_parse_nmon_raw_extracts_cpu_memory_disk_samples():
    raw = "\n".join(
        [
            "AAA,host,secansible",
            "ZZZZ,T0001,09:10:00,17-MAY-2026",
            "CPU_ALL,CPU Total sec,User%,Sys%,Wait%,Idle%,Busy,CPUs",
            "CPU_ALL,T0001,1.0,2.0,0.0,92.0,8.0,4",
            "MEM,Memory MB,memtotal,memfree,memavailable",
            "MEM,T0001,1000,200,640",
            "DISKBUSY,Disk Busy %,sda,sdb",
            "DISKBUSY,T0001,12.5,3.0",
        ]
    )

    parsed = parse_nmon_raw(raw)

    assert parsed["hostname"] == "secansible"
    assert parsed["sample_count"] == 1
    sample = parsed["samples"][0]
    assert sample["cpu_pct"] == 8.0
    assert sample["mem_pct"] == 36.0
    assert sample["disk_pct"] == 12.5
