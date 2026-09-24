def test_format_datetime_french_converts_utc_to_paris():
    from src.utils.frontend import format_datetime_french

    # 13h57 UTC un 29 juillet = 15h57 à Paris (UTC+2 en été)
    assert (
        format_datetime_french("2026-07-29T13:57:43.177+00:00")
        == "29 juillet 2026 à 15h57"
    )


def test_format_datetime_french_handles_z_suffix_and_winter_offset():
    from src.utils.frontend import format_datetime_french

    assert format_datetime_french("2026-01-15T09:05:00Z") == "15 janvier 2026 à 10h05"


def test_format_datetime_french_uses_1er():
    from src.utils.frontend import format_datetime_french

    assert format_datetime_french("2026-03-01T00:30:00Z") == "1er mars 2026 à 1h30"


def test_format_datetime_french_passthrough_on_garbage():
    from src.utils.frontend import format_datetime_french

    assert format_datetime_french("pas une date") == "pas une date"


_CSV_DOWNLOAD_TITLE = (
    "À partir de 100 000 lignes, le téléchargement se fait au format CSV, "
    "en raison des limites du serveur."
)


def test_get_button_properties_zero_height_disables_download():
    from src.utils.frontend import get_button_properties

    disabled, text, title, fmt = get_button_properties(0)

    assert disabled is True
    assert text == "Pas de données à télécharger"
    assert title == ""
    assert fmt == "xlsx"


def test_get_button_properties_excel_below_threshold_has_no_tooltip():
    from src.utils.frontend import get_button_properties

    disabled, text, title, fmt = get_button_properties(1)

    assert disabled is False
    assert text == "Télécharger au format Excel"
    assert title == ""
    assert fmt == "xlsx"


def test_get_button_properties_excel_at_exact_threshold():
    from src.utils.frontend import EXCEL_MAX_ROWS, get_button_properties

    disabled, text, title, fmt = get_button_properties(EXCEL_MAX_ROWS)

    assert disabled is False
    assert text == "Télécharger au format Excel"
    assert title == ""
    assert fmt == "xlsx"


def test_get_button_properties_csv_just_above_threshold():
    from src.utils.frontend import EXCEL_MAX_ROWS, get_button_properties

    disabled, text, title, fmt = get_button_properties(EXCEL_MAX_ROWS + 1)

    assert disabled is False
    assert text == "Télécharger au format CSV"
    assert title == _CSV_DOWNLOAD_TITLE
    assert fmt == "csv"


def test_get_button_properties_csv_large_height_never_disables():
    from src.utils.frontend import get_button_properties

    disabled, _text, _title, fmt = get_button_properties(3_190_000)

    assert disabled is False
    assert fmt == "csv"
