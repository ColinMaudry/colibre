"""Analyse tolérante des filtres texte booléens (#97).

Syntaxe : mots juxtaposés (ET implicite), `ET`, `OU`, `PAS` en majuscules,
parenthèses et phrases entre guillemets. La saisie est toujours réparée :
`analyser` ne lève jamais d'erreur et note les corrections appliquées.
"""

import re
from dataclasses import dataclass, field

from unidecode import unidecode

from src.utils.text_normalization import (
    NORMALIZED_COLUMNS,
    normalized_target,
    normalized_term,
)

# Colonnes dont les valeurs sont déjà stockées sans accents (cf. #138) : seule
# la saisie utilisateur est désaccentuée pour matcher, comme sur /recherche.
_ACCENT_INSENSITIVE_COLUMNS = {"acheteur_nom", "titulaire_nom"}


def text_filter_target(column: str, quoted_col: str) -> str:
    """Colonne à comparer à la saisie renvoyée par `normalize_text_term` : la
    colonne précalculée pour les colonnes de `NORMALIZED_COLUMNS` (#147), sinon
    la colonne elle-même."""
    return normalized_target(column, quoted_col)


def normalize_text_term(column: str, term: str) -> str:
    """Saisie normalisée selon la colonne filtrée (cf. `text_filter_target`)."""
    if column in NORMALIZED_COLUMNS:
        return normalized_term(column, term)
    if column in _ACCENT_INSENSITIVE_COLUMNS:
        return unidecode(term)
    return term


_PROFONDEUR_MAX = 10
_MOTS_CLES = {"ET", "OU", "PAS"}


@dataclass
class Mot:
    texte: str


@dataclass
class Phrase:
    texte: str


@dataclass
class Et:
    enfants: list


@dataclass
class Ou:
    enfants: list


@dataclass
class Pas:
    enfant: object


@dataclass
class Expression:
    saisie: str
    arbre: object
    corrections: list[str] = field(default_factory=list)
    operateurs_ignores: bool = False


@dataclass
class _Jeton:
    # "mot", "phrase", "(", ")", "ET", "OU" ou "PAS"
    genre: str
    position: int
    texte: str = ""
    synthetique: bool = False


_DEBUTS = {"mot", "phrase", "(", "PAS"}
_FINS = {"mot", "phrase", ")"}


def _lexique(texte: str, operateurs: bool, corrections: list) -> list[_Jeton]:
    jetons = []
    i, n = 0, len(texte)
    while i < n:
        c = texte[i]
        if c.isspace():
            i += 1
        elif c == '"':
            fin = texte.find('"', i + 1)
            if fin == -1:
                corrections.append((i, "guillemet manquant"))
                fin = n
            contenu = texte[i + 1 : fin]
            if contenu.strip():
                jetons.append(_Jeton("phrase", i, contenu))
            else:
                corrections.append((i, "guillemets vides"))
            i = fin + 1
        elif operateurs and c in "()":
            jetons.append(_Jeton(c, i))
            i += 1
        else:
            debut = i
            while i < n and not (
                texte[i].isspace()
                or texte[i] == '"'
                or (operateurs and texte[i] in "()")
            ):
                i += 1
            mot = texte[debut:i]
            genre = mot if operateurs and mot in _MOTS_CLES else "mot"
            jetons.append(_Jeton(genre, debut, mot))
    return jetons


def _equilibrer(jetons: list[_Jeton], corrections: list) -> list[_Jeton]:
    """Supprime les `)` en trop et les `(` trop profondes, ferme les `(`
    restantes par des `)` synthétiques."""
    resultat = []
    # Pile de (jeton, conservée) pour chaque `(` ouverte.
    pile = []
    profondeur = 0
    for jeton in jetons:
        if jeton.genre == "(":
            if profondeur >= _PROFONDEUR_MAX:
                corrections.append((jeton.position, "trop de parenthèses imbriquées"))
                pile.append((jeton, False))
            else:
                profondeur += 1
                pile.append((jeton, True))
                resultat.append(jeton)
        elif jeton.genre == ")":
            if not pile:
                corrections.append((jeton.position, "parenthèse en trop"))
                continue
            _, conservee = pile.pop()
            if conservee:
                profondeur -= 1
                resultat.append(jeton)
        else:
            resultat.append(jeton)
    for ouvrante, conservee in reversed(pile):
        if conservee:
            corrections.append((ouvrante.position, "parenthèse manquante"))
            resultat.append(_Jeton(")", ouvrante.position, synthetique=True))
    return resultat


def _nettoyer(jetons: list[_Jeton], corrections: list) -> None:
    """Supprime les opérateurs orphelins et les parenthèses vides jusqu'à
    stabilité. Après une suppression, l'examen reprend juste avant elle :
    seuls les voisins du trou peuvent être devenus invalides (coût linéaire)."""
    i = 0
    while i < len(jetons):
        jeton = jetons[i]
        precedent = jetons[i - 1].genre if i > 0 else None
        suivant = jetons[i + 1] if i + 1 < len(jetons) else None
        genre_suivant = suivant.genre if suivant else None
        if jeton.genre in ("ET", "OU") and (
            precedent not in _FINS or genre_suivant not in _DEBUTS
        ):
            corrections.append((jeton.position, f"{jeton.genre} orphelin"))
            del jetons[i]
        elif jeton.genre == "PAS" and genre_suivant not in _DEBUTS:
            corrections.append((jeton.position, "PAS orphelin"))
            if precedent in ("ET", "OU"):
                i -= 1
            del jetons[i : i + (2 if precedent in ("ET", "OU") else 1)]
        elif jeton.genre == "(" and genre_suivant == ")":
            if not suivant.synthetique:
                corrections.append((jeton.position, "parenthèses vides"))
            del jetons[i : i + 2]
        else:
            i += 1
            continue
        i = max(i - 2, 0)


def _aplatir(classe, enfants: list):
    return enfants[0] if len(enfants) == 1 else classe(enfants)


class _Analyseur:
    """Descente récursive sur un flux de jetons déjà grammatical."""

    def __init__(self, jetons: list[_Jeton]):
        self.jetons = jetons
        self.i = 0

    def _genre(self):
        return self.jetons[self.i].genre if self.i < len(self.jetons) else None

    def ou(self):
        enfants = [self.et()]
        while self._genre() == "OU":
            self.i += 1
            enfants.append(self.et())
        return _aplatir(Ou, enfants)

    def et(self):
        enfants = [self.pas()]
        while self._genre() in ("ET", *_DEBUTS):
            if self._genre() == "ET":
                self.i += 1
            enfants.append(self.pas())
        return _aplatir(Et, enfants)

    def pas(self):
        # Les PAS consécutifs se réduisent selon leur parité, pour qu'aucune
        # chaîne de nœuds ne croisse avec la longueur de la saisie.
        negations = 0
        while self._genre() == "PAS":
            negations += 1
            self.i += 1
        noeud = self.atome()
        return Pas(noeud) if negations % 2 else noeud

    def atome(self):
        jeton = self.jetons[self.i]
        self.i += 1
        if jeton.genre == "mot":
            return Mot(jeton.texte)
        if jeton.genre == "phrase":
            return Phrase(jeton.texte)
        noeud = self.ou()  # jeton "("
        self.i += 1  # ")"
        return noeud


def analyser(texte: str, operateurs: bool) -> Expression:
    """Analyse une saisie de filtre texte en arbre booléen, en réparant les
    erreurs. Sans `operateurs`, tous les mots et phrases sont combinés par ET
    et aucune correction n'est notée."""
    corrections = []
    jetons = _lexique(texte, operateurs, corrections)
    if not operateurs:
        ignores = any(
            j.texte in _MOTS_CLES or "(" in j.texte or ")" in j.texte
            for j in jetons
            if j.genre == "mot"
        )
        feuilles = [
            Mot(j.texte) if j.genre == "mot" else Phrase(j.texte) for j in jetons
        ]
        arbre = _aplatir(Et, feuilles) if feuilles else None
        return Expression(texte, arbre, [], ignores)

    jetons = _equilibrer(jetons, corrections)
    _nettoyer(jetons, corrections)
    arbre = _Analyseur(jetons).ou() if jetons else None

    libelles = []
    for _, libelle in sorted(corrections, key=lambda c: c[0]):
        if libelle not in libelles:
            libelles.append(libelle)
    return Expression(texte, arbre, libelles, False)


def _rendre(noeud, parent=None) -> str:
    if isinstance(noeud, Mot):
        return noeud.texte
    if isinstance(noeud, Phrase):
        return f'"{noeud.texte}"'
    if isinstance(noeud, Pas):
        return f"PAS {_rendre(noeud.enfant, Pas)}"
    if isinstance(noeud, Ou):
        texte = " OU ".join(_rendre(e, Ou) for e in noeud.enfants)
        return f"({texte})" if parent in (Et, Pas) else texte
    texte = " ET ".join(_rendre(e, Et) for e in noeud.enfants)
    return f"({texte})" if parent is Pas else texte


def _normaliser_blancs(saisie: str) -> str:
    """Réduit les suites de blancs hors guillemets ; le contenu d'une phrase
    (jusqu'à la fin de la saisie si le guillemet n'est pas fermé, comme le
    lexer) reste littéral, à l'image du SQL appliqué."""
    morceaux = saisie.split('"')
    for i in range(0, len(morceaux), 2):
        morceaux[i] = re.sub(r"\s+", " ", morceaux[i])
    texte = '"'.join(morceaux).lstrip()
    # Nombre impair de morceaux : le dernier est hors guillemets.
    return texte.rstrip() if len(morceaux) % 2 else texte


def en_texte(expression: Expression) -> str:
    """Saisie telle quelle (blancs normalisés hors guillemets) si rien n'a été
    corrigé, sinon forme canonique de l'arbre réparé."""
    if not expression.corrections:
        return _normaliser_blancs(expression.saisie)
    if expression.arbre is None:
        return ""
    return _rendre(expression.arbre)


def libelle_corrections(expression: Expression) -> str:
    return ", ".join(expression.corrections)


def _motif(terme: str, jokers: bool) -> str:
    """Motif `ILIKE` d'une feuille déjà normalisée : pour un mot (`jokers`)
    qui commence ou finit par `*`, tous ses `*` deviennent `%`
    (préfixe/suffixe), sinon sous-chaîne ; une phrase est toujours une
    sous-chaîne, `*` littéral."""
    if jokers and (terme.startswith("*") or terme.endswith("*")):
        return terme.replace("*", "%")
    return f"%{terme}%"


def _compiler(noeud, colonne: str, cible: str, params: list) -> str:
    if isinstance(noeud, (Mot, Phrase)):
        terme = normalize_text_term(colonne, noeud.texte)
        params.append(_motif(terme, isinstance(noeud, Mot)))
        return f"{cible} ILIKE ?"
    if isinstance(noeud, Pas):
        return f"NOT ({_compiler(noeud.enfant, colonne, cible, params)})"
    liaison = " AND " if isinstance(noeud, Et) else " OR "
    return liaison.join(
        f"({_compiler(e, colonne, cible, params)})" for e in noeud.enfants
    )


def en_sql(
    expression: Expression, colonne: str, col_is_date: bool = False
) -> tuple[str, list]:
    """Clause SQL paramétrée du filtre _contient_ : la garde « non vide »
    suivie de l'expression compilée, chaque feuille étant un `ILIKE ?` sur
    la colonne cible. Expression vide : la garde seule."""
    quoted_col = f'CAST("{colonne}" AS VARCHAR)' if col_is_date else f'"{colonne}"'
    garde = f"\"{colonne}\" IS NOT NULL AND {quoted_col} <> ''"
    if expression.arbre is None:
        return garde, []
    params: list = []
    cible = text_filter_target(colonne, quoted_col)
    clause = _compiler(expression.arbre, colonne, cible, params)
    return f"{garde} AND ({clause})", params
