import pytest

from src.admin import tables


def test_get_rows_users_excludes_password_hash(users_db_path):
    from src.auth import db as auth_db

    auth_db.init_schema()
    auth_db.create_user("a@ex.fr", "secret-hash")

    rows = tables.get_rows("users")

    assert rows[0]["email"] == "a@ex.fr"
    assert "password_hash" not in rows[0]


def test_get_rows_subscriptions_includes_user_email(users_db_path):
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    auth_db.init_schema()
    sub_db.init_schema()
    uid = auth_db.create_user("a@ex.fr", "hash")
    sub_db.create_pending(uid, "cust-1", "simple")

    rows = tables.get_rows("subscriptions")

    assert rows[0]["email"] == "a@ex.fr"


def test_get_rows_subscriber_state_includes_user_email(users_db_path):
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    auth_db.init_schema()
    sub_db.init_schema()
    uid = auth_db.create_user("a@ex.fr", "hash")
    sub_db.create_pending(uid, "cust-1", "simple")

    rows = tables.get_rows("subscriber_state")

    assert rows[0]["email"] == "a@ex.fr"


def test_set_cell_rejects_unknown_table(users_db_path):
    with pytest.raises(ValueError):
        tables.set_cell("not_a_table", 1, "email", "x@ex.fr")


def test_set_cell_rejects_non_editable_column(users_db_path):
    from src.auth import db as auth_db

    auth_db.init_schema()
    uid = auth_db.create_user("a@ex.fr", "hash")

    with pytest.raises(ValueError):
        tables.set_cell("users", uid, "id", "999")


def test_set_cell_rejects_invalid_dropdown_value(users_db_path):
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    auth_db.init_schema()
    sub_db.init_schema()
    uid = auth_db.create_user("a@ex.fr", "hash")
    _handle, sub_id = sub_db.create_pending(uid, "cust-1", "simple")

    with pytest.raises(ValueError):
        tables.set_cell("subscriptions", sub_id, "status", "not_a_status")


def test_set_cell_rejects_bad_type(users_db_path):
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    auth_db.init_schema()
    sub_db.init_schema()
    uid = auth_db.create_user("a@ex.fr", "hash")
    _handle, sub_id = sub_db.create_pending(uid, "cust-1", "simple")

    with pytest.raises(ValueError):
        tables.set_cell("subscriptions", sub_id, "prix_ht", "not-a-number")


def test_set_cell_writes_valid_value(users_db_path):
    from src.auth import db as auth_db

    auth_db.init_schema()
    uid = auth_db.create_user("a@ex.fr", "hash")

    tables.set_cell("users", uid, "siret", "12345678900011")

    rows = tables.get_rows("users")
    assert rows[0]["siret"] == "12345678900011"


def test_set_cell_raises_valueerror_on_unique_constraint_violation(users_db_path):
    from src.auth import db as auth_db

    auth_db.init_schema()
    auth_db.create_user("first@ex.fr", "hash")
    second_uid = auth_db.create_user("second@ex.fr", "hash")

    with pytest.raises(ValueError):
        tables.set_cell("users", second_uid, "email", "first@ex.fr")


def test_set_cell_raises_valueerror_when_row_missing(users_db_path):
    from src.auth import db as auth_db

    auth_db.init_schema()
    uid = auth_db.create_user("a@ex.fr", "hash")
    auth_db.delete_user(uid)

    with pytest.raises(ValueError):
        tables.set_cell("users", uid, "email", "new@ex.fr")


def test_set_cell_coerces_numeric_type(users_db_path):
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    auth_db.init_schema()
    sub_db.init_schema()
    uid = auth_db.create_user("a@ex.fr", "hash")
    _handle, sub_id = sub_db.create_pending(uid, "cust-1", "simple")

    tables.set_cell("subscriptions", sub_id, "prix_ht", "30")

    rows = tables.get_rows("subscriptions")
    assert rows[0]["prix_ht"] == 30.0


def test_target_user_id_per_table():
    assert tables.TABLES["users"].target_user_id({"id": 7}) == 7
    assert tables.TABLES["subscriptions"].target_user_id({"user_id": 9}) == 9
    assert tables.TABLES["subscriber_state"].target_user_id({"user_id": 3}) == 3
    assert tables.TABLES["admin_actions"].target_user_id({"id": 1}) is None


# --- Auto-découverte des tables ---

# Colonnes qui ne doivent JAMAIS sortir de get_rows. Le masquage se fait dans la
# liste `columns` qui construit le SELECT : un secret listé ici qui apparaîtrait
# dans une ligne aurait donc été envoyé jusqu'au navigateur.
SECRET_COLUMNS = {
    "password_hash",
    "token_hash",
    "token_enc",
    "access_token_hash",
    "refresh_token_hash",
    "code_hash",
    "code_challenge",
    "token",
}


def test_all_tables_includes_tables_absent_from_config(users_db_path):
    from src.saved_views import db as views_db

    views_db.init_schema()

    noms = tables.all_tables()

    assert "saved_views" in noms
    assert "mcp_usage" in noms
    assert "oauth_tokens" in noms


def test_all_tables_skips_tables_with_only_secret_columns(users_db_path):
    from src.auth.db import get_conn

    # Sans exclusion, une telle table n'aurait aucune colonne à afficher et
    # ferait planter la page admin entière.
    get_conn().execute("CREATE TABLE coffre (token_hash TEXT, secret TEXT)")

    assert "coffre" not in tables.all_tables()


def test_all_tables_keeps_explicit_config_for_declared_tables(users_db_path):
    cfg = tables.all_tables()["users"]

    assert "email" in cfg.editable_columns
    assert cfg.dropdowns["email_verified"] == ["0", "1"]


def test_no_secret_column_is_exposed_by_any_table(users_db_path):
    from src.api import tokens_db
    from src.roadmap import db as roadmap_db
    from src.saved_views import db as views_db

    tokens_db.init_schema(users_db_path)
    views_db.init_schema()
    roadmap_db.init_schema()

    for nom, cfg in tables.all_tables().items():
        exposees = SECRET_COLUMNS & set(cfg.columns)
        assert not exposees, f"{nom} exposerait {sorted(exposees)}"


def test_get_rows_api_tokens_hides_token_columns(users_db_path):
    from src.api import tokens_db
    from src.auth import db as auth_db

    tokens_db.init_schema(users_db_path)
    uid = auth_db.create_user("a@ex.fr", "hash")
    tokens_db.create_token(users_db_path, "mon jeton", user_id=uid)

    rows = tables.get_rows("api_tokens")

    assert rows[0]["label"] == "mon jeton"
    assert "token_hash" not in rows[0]
    assert "token_enc" not in rows[0]


def test_get_rows_saved_views_hides_share_token(users_db_path):
    from src.auth import db as auth_db
    from src.saved_views import db as views_db

    views_db.init_schema()
    uid = auth_db.create_user("a@ex.fr", "hash")
    views_db.upsert(uid, "tableau", "ma vue", "?x=1")

    rows = tables.get_rows("saved_views")

    assert rows[0]["name"] == "ma vue"
    assert "token" not in rows[0]


def test_get_rows_mcp_usage_keeps_token_id(users_db_path):
    from src.auth.db import get_conn

    get_conn().execute(
        "INSERT INTO mcp_usage (user_id, token_id, kind, created_at) "
        "VALUES (1, 42, 'oauth', '2026-09-01T00:00:00+00:00')"
    )

    rows = tables.get_rows("mcp_usage")

    assert rows[0]["token_id"] == 42


def test_set_cell_rejects_auto_discovered_table(users_db_path):
    from src.auth.db import get_conn

    get_conn().execute(
        "INSERT INTO mcp_usage (id, user_id, token_id, kind, created_at) "
        "VALUES (1, 1, 42, 'oauth', '2026-09-01T00:00:00+00:00')"
    )

    # La table devient connue (auto-découverte) mais reste en lecture seule :
    # le refus doit venir de la non-éditabilité, pas d'un « table inconnue ».
    with pytest.raises(ValueError, match="non éditable"):
        tables.set_cell("mcp_usage", 1, "kind", "static")


def test_get_rows_caps_auto_discovered_tables_only(users_db_path, monkeypatch):
    from src.auth import db as auth_db
    from src.auth.db import get_conn

    assert tables.AUTO_ROW_LIMIT == 2000

    monkeypatch.setattr(tables, "AUTO_ROW_LIMIT", 2)
    get_conn().executemany(
        "INSERT INTO mcp_usage (user_id, token_id, kind, created_at) "
        "VALUES (?, ?, ?, ?)",
        [(1, 1, "static", f"2026-09-0{i}T00:00:00+00:00") for i in range(1, 4)],
    )
    for i in range(3):
        auth_db.create_user(f"u{i}@ex.fr", "hash")

    assert len(tables.get_rows("mcp_usage")) == 2
    assert len(tables.get_rows("users")) == 3
