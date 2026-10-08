// Pastilles des filtres appliqués (#148) : un clic sur une pastille place le
// curseur dans le filtre flottant de la colonne. Si la colonne était masquée,
// un callback serveur l'affiche (store {page}-hidden-columns) : on attend
// donc qu'AG Grid l'affiche avant de chercher le champ.
(function () {
  var DELAI_MAX_MS = 5000;
  var PAS_MS = 50;

  // Même sérialisation que le stringifyId du renderer Dash : id DOM d'un
  // composant à id dict (clés triées).
  function stringifyId(id) {
    if (typeof id !== "object" || id === null) {
      return id;
    }
    return (
      "{" +
      Object.keys(id)
        .sort()
        .map(function (k) {
          return JSON.stringify(k) + ":" + JSON.stringify(id[k]);
        })
        .join(",") +
      "}"
    );
  }

  function champDuFiltre(grille, col) {
    var cellule = grille.querySelector(
      '.ag-floating-filter[col-id="' + CSS.escape(col) + '"]'
    );
    return cellule && cellule.querySelector("input");
  }

  function focaliser(api, grille, col) {
    api.ensureColumnVisible(col);
    // Colonnes virtualisées : l'en-tête n'existe qu'une fois la colonne
    // amenée dans la zone visible.
    requestAnimationFrame(function () {
      var champ = champDuFiltre(grille, col);
      if (champ && !champ.disabled && !champ.readOnly) {
        champ.focus();
      } else {
        // Filtre flottant en lecture seule (plusieurs conditions, plage,
        // vide) : on ouvre le filtre complet de la colonne.
        api.showColumnFilter(col);
      }
    });
  }

  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    filterPills: {
      focusFilter: function (_nClicks, gridIds) {
        var cbx = window.dash_clientside.callback_context;
        var declencheur = cbx.triggered && cbx.triggered[0];
        var id = cbx.triggered_id;
        if (!declencheur || !declencheur.value || !id || !id.col) {
          return; // (re)rendu des pastilles, pas un clic
        }
        var gridId = Array.isArray(gridIds) ? gridIds[0] : gridIds;
        if (!gridId) {
          return;
        }
        var api;
        try {
          api = dash_ag_grid.getApi(gridId);
        } catch (e) {
          return; // grille pas encore montée
        }
        var grille = document.getElementById(stringifyId(gridId));
        var col = id.col;
        var limite = Date.now() + DELAI_MAX_MS;
        (function attendre() {
          var colonne = api.getColumn(col);
          if (colonne && colonne.isVisible()) {
            focaliser(api, grille, col);
          } else if (Date.now() < limite) {
            setTimeout(attendre, PAS_MS);
          }
        })();
      },
    },
  });
})();
