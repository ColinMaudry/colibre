from src.utils import suivi


def _capturer(monkeypatch):
    envois = []
    monkeypatch.setattr(
        suivi, "set_props", lambda cid, props: envois.append((cid, props["data"]))
    )
    return envois


def test_emettre_ecrit_l_evenement_dans_le_store(monkeypatch):
    envois = _capturer(monkeypatch)
    suivi.emettre("Tableau", "telechargement", "xlsx", 12)
    ((cid, data),) = envois
    assert cid == "suivi-matomo"
    assert {k: data[k] for k in ("type", "categorie", "action", "nom", "valeur")} == {
        "type": "evenement",
        "categorie": "Tableau",
        "action": "telechargement",
        "nom": "xlsx",
        "valeur": 12,
    }


def test_emettre_deux_fois_le_meme_evenement_change_la_donnee(monkeypatch):
    envois = _capturer(monkeypatch)
    suivi.emettre("Tableau", "reinitialisation")
    suivi.emettre("Tableau", "reinitialisation")
    assert envois[0][1]["nonce"] != envois[1][1]["nonce"]


def test_emettre_recherche(monkeypatch):
    envois = _capturer(monkeypatch)
    suivi.emettre_recherche("rennes", "accueil", 7)
    data = envois[0][1]
    assert (data["type"], data["mot_cle"], data["categorie"], data["nb_resultats"]) == (
        "recherche",
        "rennes",
        "accueil",
        7,
    )


def test_serialisation_observatoire_independante_de_l_ordre():
    a = {
        "marche_objet": "voirie",
        "annee": 2025,
        "acheteur_departement_code": ["44", "35"],
    }
    b = dict(reversed(list(a.items())))
    assert (
        suivi.serialiser_filtres_observatoire(a)
        == suivi.serialiser_filtres_observatoire(b)
        == (
            'acheteur_departement_code [35, 44] | annee = 2025 | marche_objet = "voirie"',
            3,
        )
    )


def test_serialisation_observatoire_ignore_les_vides():
    assert suivi.serialiser_filtres_observatoire(
        {"annee": None, "marche_objet": "", "marche_techniques": []}
    ) == ("", 0)


def test_serialisation_observatoire_tronque_a_500():
    chaine, n = suivi.serialiser_filtres_observatoire({"marche_objet": "x" * 600})
    assert len(chaine) == 500 and chaine.endswith("…") and n == 1
