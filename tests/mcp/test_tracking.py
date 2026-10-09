import src.utils.tracking as tracking


def _activer(monkeypatch):
    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    monkeypatch.setenv("MATOMO_URL", "https://matomo.example/matomo.php")
    monkeypatch.setenv("MATOMO_SITE_ID", "1")


def test_track_mcp_tool_sends_action_and_dimension(monkeypatch):
    captured = {}

    def fake_post(url, data, timeout=None):
        captured["url"] = url
        captured["data"] = data
        captured["timeout"] = timeout

    _activer(monkeypatch)
    monkeypatch.setattr(tracking, "post", fake_post)

    tracking.track_mcp_tool("rechercher_marches", query="informatique")

    assert captured["url"] == "https://matomo.example/matomo.php"
    assert captured["data"]["idsite"] == "1"
    assert captured["data"]["action_name"] == "MCP / rechercher_marches"
    assert captured["data"]["dimension1"] == "rechercher_marches"
    assert captured["data"]["search"] == "informatique"
    assert set(captured["data"]) >= {"rand", "apiv", "h", "m", "s", "rec"}
    assert captured["timeout"] == 2.0


def test_aucun_token_auth_envoye(monkeypatch):
    """Le token n'est requis que pour cip/cdt/géoloc, et fuitait dans les logs."""
    captured = {}

    _activer(monkeypatch)
    monkeypatch.setenv("MATOMO_TOKEN", "ne-doit-pas-etre-envoye")
    monkeypatch.setattr(
        tracking, "post", lambda url, data, timeout=None: captured.update(data)
    )

    tracking.track_mcp_tool("stats_acheteur")

    assert captured["action_name"] == "MCP / stats_acheteur"
    assert "token_auth" not in captured


def test_track_mcp_tool_muet_en_development(monkeypatch):
    called = False

    def fake_post(url, data, timeout=None):
        nonlocal called
        called = True

    _activer(monkeypatch)
    monkeypatch.setenv("DEVELOPMENT", "true")
    monkeypatch.setattr(tracking, "post", fake_post)

    tracking.track_mcp_tool("stats_acheteur")

    assert called is False


def test_track_mcp_tool_muet_si_config_incomplete(monkeypatch):
    called = False

    def fake_post(url, data, timeout=None):
        nonlocal called
        called = True

    _activer(monkeypatch)
    monkeypatch.delenv("MATOMO_URL", raising=False)
    monkeypatch.setattr(tracking, "post", fake_post)

    tracking.track_mcp_tool("stats_acheteur")

    assert called is False


def test_track_mcp_tool_n_exceptionne_pas(monkeypatch):
    """Une panne Matomo ne doit jamais casser l'appel de l'outil."""

    def fake_post(url, data, timeout=None):
        raise RuntimeError("matomo est tombé")

    _activer(monkeypatch)
    monkeypatch.setattr(tracking, "post", fake_post)

    tracking.track_mcp_tool("stats_acheteur")  # ne lève pas
