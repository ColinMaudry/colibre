from datetime import datetime
from zoneinfo import ZoneInfo

from src.utils.data import DATA_SCHEMA

_PARIS = ZoneInfo("Europe/Paris")

DROPDOWN_LABELS_FR = {
    "select_all": "Tout sélectionner",
    "deselect_all": "Tout désélectionner",
    "selected_count": "{num_selected} sélectionné(s)",
    "search": "Rechercher...",
    "clear_search": "Effacer la recherche",
    "clear_selection": "Effacer la sélection",
    "no_options_found": "Aucun résultat",
}


def format_date_french(date_input) -> str:
    """Format a date as 'jour mois' (e.g., '1er janvier', '15 décembre')."""
    if isinstance(date_input, str):
        try:
            date_obj = datetime.fromisoformat(date_input)
        except (ValueError, TypeError):
            return str(date_input)
    elif isinstance(date_input, datetime):
        date_obj = date_input
    else:
        return str(date_input)

    day = date_obj.day
    month_names = [
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ]
    month = month_names[date_obj.month - 1]

    if day == 1:
        return f"1er {month}"
    else:
        return f"{day} {month}"


def format_datetime_french(date_input) -> str:
    """Format a datetime as '29 juillet 2026 à 15h57', heure de Paris.

    Les horodatages Frisbii arrivent en UTC : ils sont convertis vers
    Europe/Paris avant affichage, sans quoi une fin de période d'essai est
    annoncée avec une à deux heures d'écart selon la saison.
    """
    if isinstance(date_input, datetime):
        date_obj = date_input
    elif isinstance(date_input, str):
        try:
            date_obj = datetime.fromisoformat(date_input.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return str(date_input)
    else:
        return str(date_input)

    if date_obj.tzinfo is not None:
        date_obj = date_obj.astimezone(_PARIS)
    jour = format_date_french(date_obj)
    return f"{jour} {date_obj.year} à {date_obj.hour}h{date_obj.minute:02d}"


EXCEL_MAX_ROWS = 100_000

_CSV_DOWNLOAD_TITLE = (
    "À partir de 100 000 lignes, le téléchargement se fait au format CSV, "
    "en raison des limites du serveur."
)


def get_button_properties(height):
    """État, texte, infobulle et format du bouton de téléchargement.

    Au-delà de EXCEL_MAX_ROWS lignes, bascule du format Excel vers CSV au
    lieu de désactiver le téléchargement (#142) : d'après des mesures faites
    en production, Excel devient très lent et gourmand en mémoire au-delà de
    100 000 lignes, alors que l'écriture CSV reste quasi instantanée. Le
    bouton n'est donc plus jamais désactivé, sauf s'il n'y a aucune ligne à
    télécharger.

    Renvoie (disabled, text, title, format), format valant "xlsx" ou "csv".
    """
    if height == 0:
        return True, "Pas de données à télécharger", "", "xlsx"
    if height <= EXCEL_MAX_ROWS:
        # Le bouton se suffit à lui-même : pas d'infobulle.
        return False, "Télécharger au format Excel", "", "xlsx"
    return False, "Télécharger au format CSV", _CSV_DOWNLOAD_TITLE, "csv"


def get_enum_values_as_dict(column_name):
    try:
        options = {}
        for value in DATA_SCHEMA[column_name]["enum"]:
            options[value] = value
        return options
    except KeyError:
        return {"not_found": "not found"}
