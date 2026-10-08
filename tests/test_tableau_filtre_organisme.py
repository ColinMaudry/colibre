import dash  # noqa: F401  # dash.no_update utilisé à partir de la tâche 3

import src.app  # noqa: F401  # instancie l'app → register_page()
from src.pages import tableau


def test_filtre_org_depuis_url_acheteur():
    fm = tableau.filtre_org_depuis_url("?acheteur_id=21590350100017")
    assert fm == {
        "acheteur_id": {
            "filterType": "text",
            "type": "equals",
            "filter": "21590350100017",
        }
    }


def test_filtre_org_depuis_url_titulaire():
    fm = tableau.filtre_org_depuis_url("?titulaire_id=54202182900123")
    assert fm == {
        "titulaire_id": {
            "filterType": "text",
            "type": "equals",
            "filter": "54202182900123",
        }
    }


def test_filtre_org_depuis_url_les_deux():
    fm = tableau.filtre_org_depuis_url("?acheteur_id=1&titulaire_id=2")
    assert fm == {
        "acheteur_id": {"filterType": "text", "type": "equals", "filter": "1"},
        "titulaire_id": {"filterType": "text", "type": "equals", "filter": "2"},
    }


def test_filtre_org_depuis_url_sans_parametre():
    assert tableau.filtre_org_depuis_url("") is None
    assert tableau.filtre_org_depuis_url("?vue=abc123") is None


def test_filtre_org_depuis_url_valeur_vide_ignoree():
    assert tableau.filtre_org_depuis_url("?acheteur_id=%20") is None


def test_filtre_org_depuis_url_trimme_la_valeur():
    fm = tableau.filtre_org_depuis_url("?acheteur_id= 123 ")
    assert fm["acheteur_id"]["filter"] == "123"


def test_le_filtre_d_identifiant_passe_par_le_chemin_serveur():
    """La colonne n'a pas besoin d'être affichée : le filterModel est traduit
    en SQL côté serveur quel que soit l'état des columnDefs."""
    from src.db import schema
    from src.utils.query_ast import ast_to_sql, filtermodel_to_ast

    ast = filtermodel_to_ast(
        {"acheteur_id": {"filterType": "text", "type": "equals", "filter": "123"}},
        schema,
    )
    sql, params = ast_to_sql(ast, schema)
    assert "acheteur_id" in sql
    assert params == ["123"]


def test_store_vue_resolution_ecartee_si_filtre_org_present():
    # Les paramètres d'organisme priment sur une éventuelle vue partagée
    assert (
        tableau.store_vue_resolution("?vue=abc123_ma-vue&acheteur_id=123")
        is dash.no_update
    )


def test_apply_org_filter_renvoie_le_filtermodel():
    fm = {"acheteur_id": {"filterType": "text", "type": "equals", "filter": "123"}}
    assert tableau.apply_org_filter(fm) == fm


def test_apply_org_filter_sans_filtre_est_un_noop():
    assert tableau.apply_org_filter(None) is dash.no_update
