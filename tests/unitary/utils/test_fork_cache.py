import pytest

from boa.vm.fork import CachingRPC, _is_loopback


class TestIsLoopback:
    """Test _is_loopback detection for cache isolation logic."""

    def test_localhost(self):
        assert _is_loopback("http://localhost:8545") is True

    def test_localhost_no_port(self):
        assert _is_loopback("http://localhost") is True

    def test_ipv4_loopback(self):
        assert _is_loopback("http://127.0.0.1:8545") is True

    def test_ipv4_loopback_other(self):
        # 127.x.x.x range is all loopback
        assert _is_loopback("http://127.0.0.2:8545") is True
        assert _is_loopback("http://127.255.255.255:8545") is True

    def test_ipv6_loopback(self):
        assert _is_loopback("http://[::1]:8545") is True

    def test_no_host(self):
        # No host = local (e.g., unix socket)
        assert _is_loopback("file:///var/run/geth.sock") is True

    def test_unspecified_address(self):
        # 0.0.0.0 is "unspecified", not loopback
        assert _is_loopback("http://0.0.0.0:8545") is False

    def test_remote_infura(self):
        assert _is_loopback("https://mainnet.infura.io/v3/xxx") is False

    def test_remote_alchemy(self):
        assert _is_loopback("https://eth-mainnet.g.alchemy.com/v2/yyy") is False

    def test_private_ip(self):
        # Private IPs are not loopback
        assert _is_loopback("http://192.168.1.100:8545") is False
        assert _is_loopback("http://10.0.0.1:8545") is False
        assert _is_loopback("http://172.16.0.1:8545") is False


class TestCacheFilepath:
    """Test cache filepath generation logic."""

    def test_localhost_isolated(self):
        """Different localhost ports should get different cache files."""
        path1 = CachingRPC._cache_filepath(
            "/tmp/cache", 31337, "http://localhost:8545"
        )
        path2 = CachingRPC._cache_filepath(
            "/tmp/cache", 31337, "http://localhost:8546"
        )
        assert path1 != path2
        assert "chainid_0x7a69" in str(path1)
        assert "chainid_0x7a69" in str(path2)

    def test_remote_shared(self):
        """Different remote RPCs with same chain_id should share cache."""
        path1 = CachingRPC._cache_filepath(
            "/tmp/cache", 1, "https://mainnet.infura.io/v3/xxx"
        )
        path2 = CachingRPC._cache_filepath(
            "/tmp/cache", 1, "https://eth-mainnet.g.alchemy.com/v2/yyy"
        )
        assert path1 == path2
        assert str(path1) == "/tmp/cache/chainid_0x1.sqlite.db"

    def test_forked_anvil_isolated(self):
        """
        anvil --fork-url mainnet reports chain_id=1 but is still local,
        so it should be isolated from production mainnet cache.
        """
        # Local anvil forking mainnet (chain_id=1, but localhost)
        local_path = CachingRPC._cache_filepath(
            "/tmp/cache", 1, "http://localhost:8545"
        )
        # Remote mainnet
        remote_path = CachingRPC._cache_filepath(
            "/tmp/cache", 1, "https://mainnet.infura.io/v3/xxx"
        )
        assert local_path != remote_path
        # Local has hash in filename, remote doesn't
        assert "chainid_0x1-" in str(local_path)  # has rpc hash
        assert str(remote_path).endswith("chainid_0x1.sqlite.db")  # no hash

    def test_different_chain_ids(self):
        """Different chain_ids should always get different cache files."""
        path1 = CachingRPC._cache_filepath(
            "/tmp/cache", 1, "https://mainnet.infura.io/v3/xxx"
        )
        path2 = CachingRPC._cache_filepath(
            "/tmp/cache", 137, "https://polygon-mainnet.infura.io/v3/xxx"
        )
        assert path1 != path2
