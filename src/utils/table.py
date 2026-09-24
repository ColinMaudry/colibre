import json
import os
import urllib.parse
import uuid

import polars as pl
import xlsxwriter
from dash import no_update
from polars import selectors as cs
from unidecode import unidecode

from src.db import count_marches, count_unique_marches, query_marches, schema
from src.utils import logger
from src.utils.cache import cache
from src.utils.data import DATA_SCHEMA
from src.utils.frontend import get_button_properties
from src.utils.tracking import track_search


def split_filter_part(filter_part):
    operators = [
        ["s<", "<"],
        ["s>", ">"],
        ["i<", "<"],
        ["i>", ">"],
        ["icontains", "contains"],
        # [" ", "contains"]
    ]
    logger.debug("filter part " + filter_part)
    for operator_group in operators:
        if operator_group[0] in filter_part:
            name_part, value_part = filter_part.split(operator_group[0], 1)
            name_part = name_part.strip()
            value = value_part.strip()
            name = name_part[name_part.find("{") + 1 : name_part.rfind("}")]
            logger.debug("=> " + " ".join([name, operator_group[1], value]))

            return name, operator_group[1], value

    return [None] * 3


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


def numbers_to_strings(lff: pl.LazyFrame) -> pl.LazyFrame:
    """
    Convert all numeric columns to string type.
    """
    lff = lff.with_columns(pl.col(pl.Float64, pl.Int16).cast(pl.String).fill_null(""))
    return lff


def dates_to_strings(lff: pl.LazyFrame, column: str) -> pl.LazyFrame:
    """
    Convert a date column to string type.
    """
    lff = lff.with_columns(pl.col(column).cast(pl.String).fill_null(""))
    return lff


def normalize_sort_by(sort_by) -> tuple:
    if not sort_by:
        return ()
    return tuple((entry["column_id"], entry["direction"]) for entry in sort_by)


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


_ACCENT_REPLACEMENTS = [
    ("[éèêëÉÈÊË]", "e"),
    ("[àâäÀÂÄ]", "a"),
    ("[ùûüÙÛÜ]", "u"),
    ("[îïÎÏ]", "i"),
    ("[ôöÔÖ]", "o"),
    ("[çÇ]", "c"),
    ("[ñÑ]", "n"),
    ("[æÆ]", "ae"),
    ("[œŒ]", "oe"),
]


def _deaccent_col(expr: pl.Expr) -> pl.Expr:
    for pattern, replacement in _ACCENT_REPLACEMENTS:
        expr = expr.str.replace_all(pattern, replacement)
    return expr


def filter_table_data(lff: pl.LazyFrame, filter_query: str) -> pl.LazyFrame:
    _schema = lff.collect_schema()
    filtering_expressions = filter_query.split(" && ")
    for filter_part in filtering_expressions:
        col_name, operator, filter_value = split_filter_part(filter_part)
        if not isinstance(col_name, str) or not isinstance(filter_value, str):
            continue
        col_type = str(_schema[col_name])
        # logger.debug("filter_value:", filter_value)
        # logger.debug("filter_value_type:", type(filter_value))
        # logger.debug("operator:", operator)
        # logger.debug("col_type:", col_type)

        lff = lff.filter(pl.col(col_name).is_not_null())

        if col_type == "Date":
            # Convertir la colonne date en chaînes de caractères
            lff = dates_to_strings(lff, col_name)
            col_type = "String"
        if col_type == "String":
            lff = lff.filter(pl.col(col_name) != pl.lit(""))

        elif col_type.startswith("Int") or col_type.startswith("Float"):
            try:
                filter_value = int(filter_value)
            except ValueError:
                logger.error(f"Invalid numeric filter value: {filter_value}")
                continue

        if operator in ("contains", "<", "<=", ">", ">="):
            if operator == "<":
                lff = lff.filter(pl.col(col_name) < filter_value)
            elif operator == ">":
                lff = lff.filter(pl.col(col_name) > filter_value)
            elif operator == ">=":
                lff = lff.filter(pl.col(col_name) >= filter_value)
            elif operator == "<=":
                lff = lff.filter(pl.col(col_name) <= filter_value)
            elif operator == "contains":
                if col_type in ["String", "Date"] and isinstance(filter_value, str):
                    filter_value = filter_value.strip('"')
                    normalized_value = unidecode(filter_value)
                    col_expr = _deaccent_col(pl.col(col_name))
                    if filter_value.endswith("*"):
                        lff = lff.filter(
                            col_expr.str.starts_with(normalized_value[:-1])
                        )
                    elif filter_value.startswith("*"):
                        lff = lff.filter(col_expr.str.ends_with(normalized_value[1:]))
                    else:
                        lff = lff.filter(
                            col_expr.str.contains("(?i)" + normalized_value)
                        )
                elif col_type.startswith("Int") or col_type.startswith("Float"):
                    lff = lff.filter(pl.col(col_name) == filter_value)
                else:
                    logger.error(f"Invalid column type: {col_type}")
        else:
            logger.error(f"Invalid operator: {operator}")

        # elif operator == 'datestartswith':
        # lff = lff.filter(pl.col(col_name).str.startswith(filter_value)")

    return lff


def sort_table_data(lff: pl.LazyFrame, sort_by: list) -> pl.LazyFrame:
    lff = lff.sort(
        [col["column_id"] for col in sort_by],
        descending=[col["direction"] == "desc" for col in sort_by],
        nulls_last=True,
    )
    logger.debug(sort_by)
    return lff


def setup_table_columns(
    dff,
    hideable: bool = True,
    exclude: list | None = None,
) -> tuple:
    # Liste finale de colonnes
    markdown_exceptions = ["montant", "titulaire_distance", "distance", "dureeMois"]
    columns = []
    tooltip = {}
    for column_id in dff.columns:
        if exclude and column_id in exclude:
            continue
        column_object = DATA_SCHEMA.get(column_id)
        if column_object:
            column_name = column_object.get("title")
        else:
            # Si le champ est un champ créé par erreur lors d'une jointure, on le skip
            if column_id.endswith("_left") or column_id.endswith("_right"):
                logger.warning(f"Champ innatendu : {column_id}")
                continue
            column_name = column_id
            column_object = {"title": column_name, "description": ""}

        presentation = "input" if column_id in markdown_exceptions else "markdown"

        column = {
            "name": column_name,
            "id": column_id,
            "presentation": presentation,
            "type": "text",
            "format": {"nully": "N/A"},
            "hideable": hideable,
        }
        columns.append(column)
        if column_object:
            tooltip[column_id] = {
                "value": f"""**{column_object.get("title")}** ({column_id})

    """
                + column_object.get("description", ""),
                "type": "markdown",
            }
    return columns, tooltip


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


@cache.memoize()
def _fetch_page_sql(
    filter_query: str | None,
    sort_by_key: tuple,
    page_current: int,
    page_size: int,
    base_where_sql: str = "TRUE",
    base_params: tuple = (),
) -> tuple[pl.DataFrame, int, int]:
    """Chemin rapide : filtre/tri/pagine dans DuckDB, post-traite la page seule.

    `base_where_sql`/`base_params` permettent de scoper la requête (ex : un
    acheteur ou un titulaire précis) en plus du filtre saisi dans la table.

    Retourne (page_dataframe_post_traitée, total_count, total_unique_count).
    """
    # Import local pour éviter une dépendance circulaire
    # (src.utils.table_sql importe split_filter_part depuis src.utils.table).
    from src.utils.table_sql import filter_query_to_sql, sort_by_to_sql

    logger.debug(
        f"Cache miss SQL — filter={filter_query!r} sort={sort_by_key!r} "
        f"page={page_current} size={page_size}"
    )

    filter_where_sql, filter_params = filter_query_to_sql(filter_query or "", schema)
    where_sql = f"({base_where_sql}) AND ({filter_where_sql})"
    params = [*base_params, *filter_params]

    sort_by_dash = [
        {"column_id": col, "direction": direction} for col, direction in sort_by_key
    ]
    order_by = sort_by_to_sql(sort_by_dash, schema) or None

    total = count_marches(where_sql, params)
    total_unique = count_unique_marches(where_sql, params)

    page = query_marches(
        where_sql=where_sql,
        params=params,
        order_by=order_by,
        limit=page_size,
        offset=page_current * page_size,
    )

    page = postprocess_page(page)
    return page, total, total_unique


def prepare_table_data(
    data,
    data_timestamp,
    filter_query,
    page_current,
    page_size,
    sort_by,
    source_table,
    base_where_sql: str = "TRUE",
    base_params: tuple = (),
):
    """
    Fonction de préparation des données pour les datatables, afin de permettre une gestion fine des logiques,
    notamment pour les filtres et les tris.
    :param data
    :param data_timestamp:
    :param filter_query:
    :param page_current:
    :param page_size:
    :param sort_by:
    :param source_table:
    :param base_where_sql: scope SQL additionnel (ex : un acheteur/titulaire précis)
    :param base_params: paramètres liés à base_where_sql
    :return:
    """
    logger.debug(" + + + + + + + + + + + + + + + + + + ")

    if filter_query:
        track_search(filter_query, source_table)

    trigger_cleanup = no_update if source_table == "tableau" else str(uuid.uuid4())

    if data is None:
        # Chemin rapide SQL : tableau, acheteur, titulaire (scope éventuel via
        # base_where_sql/base_params)
        sort_by_key = normalize_sort_by(sort_by)
        dff, height, total_unique = _fetch_page_sql(
            filter_query=filter_query,
            sort_by_key=sort_by_key,
            page_current=page_current,
            page_size=page_size,
            base_where_sql=base_where_sql,
            base_params=tuple(base_params),
        )
    else:
        if isinstance(data, list):
            lff: pl.LazyFrame = pl.LazyFrame(
                data, strict=False, infer_schema_length=5000
            )
        elif isinstance(data, pl.LazyFrame):
            lff = data
        else:
            lff = query_marches().lazy()

        if filter_query:
            lff = filter_table_data(lff, filter_query)

        df_height = lff.select("uid").collect(engine="streaming")
        height = df_height.height
        total_unique = df_height["uid"].n_unique()

        if sort_by and len(sort_by) > 0:
            lff = sort_table_data(lff, sort_by)

        start_row = page_current * page_size
        lff = lff.slice(start_row, page_size)
        dff = lff.collect(engine="streaming")
        dff: pl.DataFrame = postprocess_page(dff)

    if height > 0:
        nb_rows = (
            f"{format_number(height)} lignes ({format_number(total_unique)} marchés)"
        )
    else:
        nb_rows = "0 lignes (0 marchés)"

    table_columns, tooltip = setup_table_columns(dff)

    dicts = dff.to_dicts()

    # Le format (xlsx/csv) n'est pas utilisé ici : prepare_table_data ne
    # pilote pas l'export, seulement l'état du bouton (voir les callbacks
    # download_* de chaque page pour le choix du format).
    download_disabled, download_text, download_title, _download_format = (
        get_button_properties(height)
    )

    return (
        dicts,
        table_columns,
        tooltip,
        data_timestamp + 1,
        nb_rows,
        download_disabled,
        download_text,
        download_title,
        trigger_cleanup,
    )


def invert_columns(columns):
    """
    Renvoie les colonnes du schéma non spécifiées en paramètre. Utile pour passer d'une colonnes masquées à une liste de colonnes affichées, et vice versa.

    :param columns:
    :return:
    """
    inverted_columns = []
    for column in schema.names():
        if column not in columns:
            inverted_columns.append(column)
    return inverted_columns


def build_view_query(filter_query, sort_by, hidden_columns) -> str:
    """
    Construit la query string d'une vue Tableau (filtres + tris + colonnes),
    identique à celle produite par le bouton « Partager la vue ».

    hidden_columns : colonnes masquées ; on stocke les colonnes visibles.
    """
    params = {}
    if filter_query:
        params["filtres"] = filter_query
    if sort_by:
        params["tris"] = json.dumps(sort_by)
    if hidden_columns:
        params["colonnes"] = ",".join(invert_columns(hidden_columns))
    return urllib.parse.urlencode(params)


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
