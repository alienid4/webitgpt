from webapp.services.deep_check_service import _network_verdict


def test_loopback_and_zero_link_counters_are_not_warn():
    text = """
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN mode DEFAULT group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    RX: bytes  packets  errors  dropped missed  mcast
    1000       10       0       0       0       0
    TX: bytes  packets  errors  dropped carrier collsns
    1000       10       0       0       0       0
3 packets transmitted, 3 received, 0% packet loss, time 2041ms
"""
    assert _network_verdict(0, text) == "PASS"


def test_nonzero_link_drop_without_growth_is_not_warn():
    text = """
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500
    RX: bytes  packets  errors  dropped missed  mcast
    1000       10       0       2       0       0
"""
    assert _network_verdict(0, text) == "PASS"


def test_ping_loss_is_warn():
    assert _network_verdict(0, "3 packets transmitted, 2 received, 33% packet loss") == "WARN"


def test_ssh_route_error_is_warn():
    assert _network_verdict(255, "ssh: connect to host 192.168.1.223 port 22: No route to host") == "WARN"
