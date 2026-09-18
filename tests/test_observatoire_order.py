"""Tests de la couche de persistance de l'ordre des cards (issue #107)."""

import pytest


@pytest.fixture(autouse=True)
def _table_creee():
    """La table vient de la migration 0015 ; on s'assure qu'elle existe."""
    from src.migrations import apply_pending

    apply_pending()


def test_get_card_order_returns_none_for_new_user():
    from src.observatoire_order import get_card_order

    assert get_card_order(999) is None


def test_save_and_get_card_order():
    from src.observatoire_order import get_card_order, save_card_order

    order = ["resume", "top-acheteurs", "cat-acheteur"]
    save_card_order(42, order)

    assert get_card_order(42) == order


def test_save_card_order_upserts():
    from src.observatoire_order import get_card_order, save_card_order

    save_card_order(1, ["resume", "top-acheteurs"])
    save_card_order(1, ["top-acheteurs", "resume"])

    assert get_card_order(1) == ["top-acheteurs", "resume"]


def test_default_card_order_is_complete():
    """DEFAULT_CARD_ORDER contient tous les card_ids fixes (hors cartes géo)."""
    from src.observatoire_order import DEFAULT_CARD_ORDER

    assert DEFAULT_CARD_ORDER == [
        "resume",
        "cat-acheteur",
        "cat-entreprise",
        "type-achat",
        "considerations",
        "distance",
        "top-acheteurs",
        "top-titulaires",
        "sources-donnees",
    ]
