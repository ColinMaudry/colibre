"""Utilitaires partagés par les tests."""


def walk_components(component):
    """Parcourt récursivement l'arbre de composants Dash.

    Le `repr` d'un composant Dash tronque les longs sous-arbres : chercher une
    chaîne dans `str(layout)` donne des faux négatifs. On inspecte donc l'arbre.
    """
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if isinstance(child, str):
            yield child
        else:
            yield from walk_components(child)


def installer_espion_paq(driver):
    """Installe un faux `window._paq` avant chaque chargement de page.

    À appeler avant le premier chargement (donc avant `start_server`).
    """
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument", {"source": "window._paq = [];"}
    )


def appels_paq(driver, methode=None) -> list[list]:
    """Copie JSON des appels poussés dans `window._paq`, filtrés sur la méthode."""
    appels = driver.execute_script(
        "return JSON.parse(JSON.stringify(window._paq || []));"
    )
    if methode is None:
        return appels
    return [a for a in appels if a and a[0] == methode]
