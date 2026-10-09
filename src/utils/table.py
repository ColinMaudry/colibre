import os

import polars as pl
import xlsxwriter
from polars import selectors as cs

from src.db import schema
from src.utils import logger


def add_resource_link(dff: pl.DataFrame) -> pl.DataFrame:
    dff = dff.with_columns(
        (
            '<a href="' + pl.col("sourceFile") + '">' + pl.col("sourceDataset") + "</a>"
        ).alias("sourceDataset")
    )
    dff = dff.drop(["sourceFile"])
    return dff


_TOOLTIP_SHADOW_COLUMNS = [
    "acheteur_nom",
    "titulaire_nom",
    "acheteur_id",
    "titulaire_id",
]


def add_links(dff: pl.DataFrame):
    # Copie du texte brut avant réécriture en HTML ci-dessous, pour que la
    # grille AG Grid (cf. grid_column_defs dans src.utils.grid) puisse
    # afficher une infobulle lisible sur ces colonnes plutôt que le balisage
    # <a href=...> brut.
    dff = dff.with_columns(
        [
            pl.col(c).alias(f"{c}_tooltip")
            for c in _TOOLTIP_SHADOW_COLUMNS
            if c in dff.columns
        ]
    )
    for col in ["uid", "acheteur_nom", "titulaire_nom", "acheteur_id", "titulaire_id"]:
        if col in dff.columns:
            if col.startswith("titulaire_"):
                detail_link = (
                    '<a href = "/titulaires/'
                    + pl.col("titulaire_id")
                    + '">'
                    + pl.col(col)
                    + "</a>"
                )
                if col == "titulaire_nom":
                    detail_link = (
                        detail_link
                        + ' <a href="/observatoire?titulaire_id='
                        + pl.col("titulaire_id")
                        + '" title="Voir dans l\'observatoire">📊</a>'
                    )
                    detail_link = (
                        detail_link
                        + ' <a href="/tableau?titulaire_id='
                        + pl.col("titulaire_id")
                        + '" title="Voir dans le tableau">'
                        + '<img src="/assets/icone-tableau.svg" '
                        + 'alt="Voir dans le tableau" '
                        + 'style="height:14px;vertical-align:middle;" /></a>'
                    )
                dff = dff.with_columns(
                    pl.when(
                        pl.Expr.or_(
                            pl.col("titulaire_typeIdentifiant").is_null(),
                            pl.col("titulaire_typeIdentifiant") == "SIRET",
                        )
                    )
                    .then(detail_link)
                    .otherwise(pl.col(col))
                    .alias(col)
                )
            if col.startswith("acheteur_"):
                detail_link = (
                    '<a href = "/acheteurs/'
                    + pl.col("acheteur_id")
                    + '">'
                    + pl.col(col)
                    + "</a>"
                )
                if col == "acheteur_nom":
                    detail_link = (
                        detail_link
                        + ' <a href="/observatoire?acheteur_id='
                        + pl.col("acheteur_id")
                        + '" title="Voir dans l\'observatoire">📊</a>'
                    )
                    detail_link = (
                        detail_link
                        + ' <a href="/tableau?acheteur_id='
                        + pl.col("acheteur_id")
                        + '" title="Voir dans le tableau">'
                        + '<img src="/assets/icone-tableau.svg" '
                        + 'alt="Voir dans le tableau" '
                        + 'style="height:14px;vertical-align:middle;" /></a>'
                    )
                dff = dff.with_columns(detail_link.alias(col))
            if col == "uid":
                dff = dff.with_columns(
                    (
                        '<a href = "/marches/'
                        + pl.col("uid")
                        + '">'
                        + pl.col("uid")
                        + "</a>"
                    ).alias("uid")
                )
    return dff


def add_links_in_dict(data: list[dict], org_type: str) -> list:
    new_data = []
    for marche in data:
        org_id = marche[org_type + "_id"]
        marche[org_type + "_nom"] = (
            f'<a href="/{org_type}s/{org_id}">{marche[org_type + "_nom"]}</a>'
        )
        if marche.get("uid"):
            marche["id"] = f'<a href="/marches/{marche["uid"]}">{marche["id"]}</a>'
            marche["uid"] = f'<a href="/marches/{marche["uid"]}">{marche["uid"]}</a>'
        new_data.append(marche)
    return new_data


def booleans_to_strings(lff: pl.LazyFrame) -> pl.LazyFrame:
    """
    Convert all boolean columns to string type.
    """
    lff = lff.with_columns(
        pl.col(cs.Boolean)
        .cast(pl.String)
        .str.replace("true", "oui")
        .str.replace("false", "non")
    )
    return lff


def format_number(number) -> str:
    if not number:
        return ""
    number = "{:,}".format(number).replace(",", chr(160))
    return number


def unformat_montant(number: str) -> float:
    number = number.replace(" €", "")
    number = number.replace(" €", "").replace(" ", "")
    number = number.replace(",", ".")
    number = number.strip()
    return float(number)


def format_values(dff: pl.DataFrame) -> pl.DataFrame:
    def format_montant(expr):
        # https://stackoverflow.com/a/78636786
        expr = expr.cast(pl.String)
        expr = expr.str.splitn(".", 2)

        num = expr.struct[0]
        frac = expr.struct[1]

        # Ajout des espaces
        num = (
            num.str.reverse()
            .str.replace_all(r"\d{3}", "$0 ")
            .str.reverse()
            .str.replace(r"^ ", "")
        )

        frac: pl.Expr = (
            pl.when(frac.is_not_null() & ~frac.is_in(["0"]))
            .then("," + frac.str.head(2))
            .otherwise(pl.lit(""))
        )

        montant: pl.Expr = (
            pl.when((num + frac) == pl.lit(""))
            .then(pl.lit(""))
            .otherwise(num + frac + pl.lit(" €"))
        )

        return montant

    def format_distance(expr):
        expr = expr.cast(pl.String)
        return pl.concat_str(expr, pl.lit(" km"))

    if "montant" in dff.columns:
        dff = dff.with_columns(pl.col("montant").pipe(format_montant).alias("montant"))
    if "titulaire_distance" in dff.columns:
        dff = dff.with_columns(
            pl.col("titulaire_distance")
            .pipe(format_distance)
            .alias("titulaire_distance")
        )

    return dff


def get_default_hidden_columns(page):
    if page == "acheteur":
        displayed_columns = [
            "objet",
            "dateNotification",
            "titulaire_nom",
            "titulaire_distance",
            "montant",
            "codeCPV",
            "dureeRestanteMois",
        ]
    elif page == "titulaire":
        displayed_columns = [
            "objet",
            "dateNotification",
            "acheteur_nom",
            "titulaire_distance",
            "montant",
            "codeCPV",
            "dureeRestanteMois",
        ]
    elif page == "tableau":
        displayed_columns = [
            c.strip() for c in os.getenv("DISPLAYED_COLUMNS", "").split(",")
        ]
    else:
        displayed_columns = [
            c.strip() for c in os.getenv("DISPLAYED_COLUMNS", "").split(",")
        ]
        logger.warning(f"Invalid page: {page}")

    hidden_columns = []

    for col in schema.names():
        if col in displayed_columns:
            continue
        else:
            hidden_columns.append(col)
    return hidden_columns


def hidden_columns_from_selection(selected_rows):
    """Colonnes masquées déduites des lignes cochées du sélecteur (AG Grid).

    [] (tout décoché) est un choix explicite : toutes les colonnes masquées.

    Accepte aussi la forme `{"ids": [...]}` posée par le serveur
    (selection_from_hidden_columns) : Dash chaîne ce callback sur cette
    écriture avant qu'AG Grid ne réémette la sélection en lignes.
    """
    if isinstance(selected_rows, dict):
        selected = set(selected_rows.get("ids") or [])
    else:
        selected = {row["id"] for row in (selected_rows or [])}
    return [col for col in COLUMNS if col not in selected]


def selection_from_hidden_columns(hidden_columns):
    """Valeur de `selectedRows` cochant les colonnes visibles (par id de ligne)."""
    hidden = set(hidden_columns)
    return {"ids": [col for col in COLUMNS if col not in hidden]}


def postprocess_page(dff: pl.DataFrame) -> pl.DataFrame:
    """Post-traitement à appliquer sur une page déjà paginée.

    À appeler après la pagination.
    """
    dff = dff.with_columns(pl.all().cast(pl.String).fill_null(""))
    if "uid" in dff.columns:
        dff = dff.with_columns(
            (
                '<a href="/marches/' + pl.col("uid") + '" title="Voir le marché">🔍</a>'
            ).alias("marche")
        )
        dff = dff.select(["marche"] + [c for c in dff.columns if c != "marche"])
    dff = add_links(dff)
    if "sourceFile" in dff.columns:
        dff = add_resource_link(dff)
    if dff.height > 0:
        dff = format_values(dff)
    return dff


COLUMNS = schema.names()

_EXCEL_MIN_COLUMN_WIDTH = 132  # ≈ 3.5 cm à 96 DPI
_EXCEL_HEADER_FORMAT = {
    "bold": True,
    "bg_color": "#b33821",
    "font_color": "white",
}
_EXCEL_COLUMN_WIDTHS = {
    "objet": 350,
    "acheteur_nom": 250,
    "titulaire_nom": 250,
    "acheteur_id": 160,
}


def write_styled_excel(df: pl.DataFrame, buffer, worksheet: str = "DECP") -> None:
    col_widths = {
        col: max(_EXCEL_MIN_COLUMN_WIDTH, _EXCEL_COLUMN_WIDTHS.get(col, 0))
        for col in df.columns
    }
    wb = xlsxwriter.Workbook(buffer, {"default_format_properties": {"text_wrap": True}})
    try:
        ws = wb.add_worksheet(worksheet)
        df.write_excel(
            workbook=wb,
            worksheet=ws,
            header_format=_EXCEL_HEADER_FORMAT,
            column_widths=col_widths,
        )
    finally:
        wb.close()


def write_csv(df: pl.DataFrame, buffer) -> None:
    """Écrit un CSV point-virgule avec BOM UTF-8, pour l'export au-delà de
    EXCEL_MAX_ROWS lignes (#142).

    Le point-virgule est le séparateur attendu par Excel en localisation
    française (la virgule y sert de séparateur décimal). Le BOM UTF-8
    (b"\\xef\\xbb\\xbf") permet à Excel de détecter l'encodage à l'ouverture
    par double-clic ; sans lui, les caractères accentués sont mal interprétés.
    """
    buffer.write(b"\xef\xbb\xbf")
    df.write_csv(buffer, separator=";")
