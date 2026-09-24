import io

import polars as pl

from src.utils.table import write_csv


def test_write_csv_starts_with_utf8_bom():
    df = pl.DataFrame({"objet": ["marché A"]})
    buf = io.BytesIO()
    write_csv(df, buf)
    buf.seek(0)
    assert buf.read(3) == b"\xef\xbb\xbf"


def test_write_csv_uses_semicolon_separator():
    df = pl.DataFrame({"objet": ["marché A"], "montant": [1000.0]})
    buf = io.BytesIO()
    write_csv(df, buf)
    buf.seek(0)
    contenu = buf.read().decode("utf-8-sig")
    entete = contenu.splitlines()[0]
    assert entete == "objet;montant"


def test_write_csv_writes_expected_row():
    df = pl.DataFrame({"objet": ["marché A"]})
    buf = io.BytesIO()
    write_csv(df, buf)
    buf.seek(0)
    lignes = buf.read().decode("utf-8-sig").splitlines()
    assert lignes[1] == "marché A"
