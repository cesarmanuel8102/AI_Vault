import pytest

from brain_v9.agent import tools


@pytest.mark.asyncio
async def test_detect_local_network_prefers_wifi_over_vethernet(monkeypatch):
    monkeypatch.setattr(
        tools,
        "_list_local_interfaces",
        lambda: [
            {"name": "vEthernet (WSL)", "ip": "172.17.176.1", "netmask": "255.255.240.0", "broadcast": None, "is_up": True, "is_loopback": False},
            {"name": "Wi-Fi", "ip": "172.20.10.8", "netmask": "255.255.255.240", "broadcast": None, "is_up": True, "is_loopback": False},
        ],
    )

    result = await tools.detect_local_network()
    assert result["success"] is True
    assert result["primary_ip"] == "172.20.10.8"
    assert result["primary_cidr"] == "172.20.10.0/28"

@pytest.mark.asyncio
async def test_scan_local_network_accepts_auto_keyword(monkeypatch):
    async def fake_detect_local_network():
        return {
            "success": True,
            "primary_cidr": "192.168.1.0/24",
        }

    async def fake_to_thread(fn, *args, **kwargs):
        return None

    monkeypatch.setattr(tools, "detect_local_network", fake_detect_local_network)
    monkeypatch.setattr(tools.asyncio, "to_thread", fake_to_thread)

    result = await tools.scan_local_network(cidr="auto", max_hosts=4, max_total_hosts=4)

    assert result["success"] is True
    assert result["cidr"] == "192.168.1.0/24"
    assert result["hosts_probed"] == 4
    assert result["live_count"] == 0


@pytest.mark.asyncio
async def test_scan_local_network_accepts_auto_alias(monkeypatch):
    async def fake_detect_local_network():
        return {
            "success": True,
            "primary_cidr": "10.0.0.0/24",
        }

    async def fake_to_thread(fn, *args, **kwargs):
        return None

    monkeypatch.setattr(tools, "detect_local_network", fake_detect_local_network)
    monkeypatch.setattr(tools.asyncio, "to_thread", fake_to_thread)

    result = await tools.scan_local_network(network="auto", max_hosts=3, max_total_hosts=3)

    assert result["success"] is True
    assert result["cidr"] == "10.0.0.0/24"
    assert result["hosts_probed"] == 3
    assert result["live_count"] == 0
