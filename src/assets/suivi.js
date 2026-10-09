// Envoi des gestes utilisateur à Matomo (issue #149).
// Sans traqueur (développement, bloqueur de publicité), rien n'est envoyé.
(function () {
  function evenement(categorie, action, nom, valeur) {
    if (!window._paq) return;
    const appel = ["trackEvent", categorie, action];
    if (nom !== null && nom !== undefined) {
      appel.push(nom);
      if (valeur !== null && valeur !== undefined) appel.push(valeur);
    } else if (valeur !== null && valeur !== undefined) {
      appel.push(undefined, valeur);
    }
    window._paq.push(appel);
  }

  function recherche(motCle, categorie, nbResultats) {
    if (!window._paq) return;
    window._paq.push(["trackSiteSearch", motCle, categorie, nbResultats]);
  }

  // Jeu de filtres AG Grid (filterModel) → chaîne stable : même jeu, même
  // chaîne, une seule ligne dans les rapports Matomo. Même convention que
  // src/utils/suivi.py (colonnes triées, « | », 500 caractères).
  const OPERATEURS = {
    contains: "contient",
    notContains: "ne contient pas",
    equals: "=",
    notEqual: "≠",
    startsWith: "commence par",
    endsWith: "finit par",
    lessThan: "<",
    lessThanOrEqual: "≤",
    greaterThan: ">",
    greaterThanOrEqual: "≥",
    blank: "vide",
    notBlank: "non vide",
  };
  const LONGUEUR_MAX = 500;

  function valeur(condition, cle) {
    if (condition.filterType === "text") return '"' + condition[cle] + '"';
    if (condition.filterType === "date") {
      const date = cle === "filterTo" ? condition.dateTo : condition.dateFrom;
      return String(date || "").split(" ")[0];
    }
    return String(condition[cle]);
  }

  function serialiserCondition(condition) {
    const type = condition.type;
    if (type === "blank" || type === "notBlank") return OPERATEURS[type];
    if (type === "inRange") {
      return (
        "entre " +
        valeur(condition, "filter") +
        " et " +
        valeur(condition, "filterTo")
      );
    }
    return (OPERATEURS[type] || type) + " " + valeur(condition, "filter");
  }

  function serialiserColonne(modele) {
    if (modele.operator && Array.isArray(modele.conditions)) {
      const liaison = modele.operator === "OR" ? " OU " : " ET ";
      return (
        "(" + modele.conditions.map(serialiserCondition).join(liaison) + ")"
      );
    }
    return serialiserCondition(modele);
  }

  function serialiserFiltres(filterModel) {
    const chaine = Object.keys(filterModel || {})
      .sort()
      .map(function (colonne) {
        return colonne + " " + serialiserColonne(filterModel[colonne]);
      })
      .join(" | ");
    if (chaine.length <= LONGUEUR_MAX) return chaine;
    return chaine.slice(0, LONGUEUR_MAX - 1) + "…";
  }

  window.colibreSuivi = {
    evenement: evenement,
    recherche: recherche,
    serialiserFiltres: serialiserFiltres,
  };
})();
