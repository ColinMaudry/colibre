import polars as pl
import pytest


@pytest.fixture
def sample_lff():
    """Small LazyFrame with the columns needed by add_links / format_values."""
    return pl.LazyFrame(
        [
            {
                "uid": "u1",
                "id": "u1",
                "acheteur_id": "12345678900011",
                "acheteur_nom": "Mairie de Test",
                "titulaire_id": "98765432100022",
                "titulaire_nom": "Entreprise Test",
                "titulaire_typeIdentifiant": "SIRET",
                "objet": "Travaux divers",
                "montant": 12500.0,
                "dateNotification": "2025-03-15",
                "codeCPV": "45000000",
                "dureeRestanteMois": 6,
                "titulaire_distance": 42.0,
            }
        ]
    )


def test_postprocess_page_adds_marche_column():
    """postprocess_page doit créer une colonne 'marche' en première position,
    un lien 🔍 vers /marches/{uid}, tout en conservant la colonne uid."""
    from src.utils.table import postprocess_page

    dff = pl.DataFrame({"uid": ["abc"], "objet": ["Travaux divers"]})
    result = postprocess_page(dff)

    # 'marche' existe et est la première colonne
    assert result.columns[0] == "marche"
    # Lien loupe vers la fiche du marché
    assert "/marches/abc" in result["marche"][0]
    assert "🔍" in result["marche"][0]
    # uid est conservée et reste un lien affichant sa propre valeur
    assert "uid" in result.columns
    assert "abc" in result["uid"][0]


def test_postprocess_page_without_uid_has_no_marche():
    """Sans colonne uid, aucune colonne 'marche' n'est ajoutée."""
    from src.utils.table import postprocess_page

    dff = pl.DataFrame({"objet": ["Travaux divers"]})
    result = postprocess_page(dff)

    assert "marche" not in result.columns


# Sélecteur de colonnes en AG Grid (#141) : conversion entre les lignes cochées
# (`selectedRows`) et la liste des colonnes masquées du store.


def test_hidden_columns_from_selection_masque_les_colonnes_non_cochees():
    from src.utils.table import COLUMNS, hidden_columns_from_selection

    cochees = [COLUMNS[2], COLUMNS[0]]  # ordre volontairement inversé
    # Lignes telles qu'AG Grid les réémet : la ligne entière, pas que l'id.
    lignes = [{"id": c, "name": f"titre {c}", "description": "…"} for c in cochees]

    masquees = hidden_columns_from_selection(lignes)

    assert masquees == [c for c in COLUMNS if c not in cochees]
    assert COLUMNS[1] in masquees
    assert COLUMNS[0] not in masquees and COLUMNS[2] not in masquees


@pytest.mark.parametrize("selection", [[], None])
def test_hidden_columns_from_selection_vide_masque_tout(selection):
    """Tout décocher est un choix explicite : toutes les colonnes masquées."""
    from src.utils.table import COLUMNS, hidden_columns_from_selection

    assert len(COLUMNS) > 3
    assert hidden_columns_from_selection(selection) == COLUMNS


def test_selection_from_hidden_columns_coche_les_colonnes_visibles():
    from src.utils.table import COLUMNS, selection_from_hidden_columns

    masquees = [COLUMNS[3], COLUMNS[1]]

    selection = selection_from_hidden_columns(masquees)

    assert selection == {"ids": [c for c in COLUMNS if c not in masquees]}
    assert COLUMNS[0] in selection["ids"]


def test_selection_from_hidden_columns_vide_coche_tout():
    from src.utils.table import COLUMNS, selection_from_hidden_columns

    assert selection_from_hidden_columns([]) == {"ids": COLUMNS}


def test_selection_et_colonnes_masquees_aller_retour():
    from src.utils.table import (
        COLUMNS,
        hidden_columns_from_selection,
        selection_from_hidden_columns,
    )

    masquees = [COLUMNS[1], COLUMNS[4], COLUMNS[-1]]
    lignes = [{"id": i} for i in selection_from_hidden_columns(masquees)["ids"]]

    assert hidden_columns_from_selection(lignes) == masquees


def test_hidden_columns_from_selection_accepte_la_forme_ids():
    """La valeur posée par le serveur (`{"ids": [...]}`) redéclenche aussi le
    callback « cases → store » : Dash chaîne les callbacks sur la sortie écrite,
    avant qu'AG Grid ne réémette la sélection sous forme de lignes. Vu en
    navigateur : sans ce cas, le callback levait une erreur (HTTP 500)."""
    from src.utils.table import COLUMNS, hidden_columns_from_selection

    cochees = [COLUMNS[0], COLUMNS[2]]

    masquees = hidden_columns_from_selection({"ids": cochees})

    assert masquees == [c for c in COLUMNS if c not in cochees]
    assert COLUMNS[1] in masquees


def test_add_links_ajoute_le_raccourci_tableau(sample_lff):
    from src.utils.table import add_links

    dff = add_links(sample_lff.collect())
    cell_acheteur = dff["acheteur_nom"][0]
    cell_titulaire = dff["titulaire_nom"][0]
    # Lien vers la page Tableau avec le bon paramètre d'URL
    assert 'href="/tableau?acheteur_id=12345678900011"' in cell_acheteur
    assert 'href="/tableau?titulaire_id=98765432100022"' in cell_titulaire
    # L'icône porte le lien, avec une infobulle explicite
    assert "/assets/icone-tableau.svg" in cell_acheteur
    assert 'title="Voir dans le tableau"' in cell_acheteur
    # Le raccourci Observatoire est conservé à côté
    assert 'href="/observatoire?acheteur_id=12345678900011"' in cell_acheteur
    assert 'href="/observatoire?titulaire_id=98765432100022"' in cell_titulaire


def test_add_links_sans_raccourci_si_identifiant_non_siret():
    from src.utils.table import add_links

    dff = pl.DataFrame(
        {
            "titulaire_id": ["98765432100022"],
            "titulaire_nom": ["Entreprise Test"],
            "titulaire_typeIdentifiant": ["SIREN"],
        }
    )
    out = add_links(dff)
    assert "/tableau?" not in out["titulaire_nom"][0]
