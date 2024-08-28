import boa


def test_env_mgr_noctx():
    s = boa.env
    t = boa.Env()
    boa._TmpEnvMgr(t)
    assert boa.env is not s
    assert boa.env is t


def test_env_mgr_with_ctx():
    s = boa.env
    t = boa.Env()

    with boa._TmpEnvMgr(t):
        assert boa.env is not s
        assert boa.env is t

    assert boa.env is s
    assert boa.env is not t
