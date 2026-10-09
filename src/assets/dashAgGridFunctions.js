// Fonctions AG Grid exposées à Dash AG Grid via le namespace
// window.dashAgGridFunctions (cf. eventListeners de la grille du Tableau).
var dagfuncs = (window.dashAgGridFunctions = window.dashAgGridFunctions || {});

// Sources d'événements AG Grid qui ne correspondent PAS à une action de
// l'utilisateur : application programmatique d'une vue (props filterModel /
// columnState → source 'api') et initialisation de la grille. On les ignore ;
// toute autre source (ex. 'columnFilter', 'uiColumnSorted', 'toolPanelUi',
// 'columnMenu') est une modification volontaire de l'état par l'utilisateur.
var SHARE_PROGRAMMATIC_SOURCES = [
  "api",
  "gridInitializing",
  "gridOptionsChanged",
  "gridOptionsUpdated",
  "columnDefsUpdated",
];

// Masque le bloc « URL directe » (share-url-box) dès que l'utilisateur modifie
// filtre / tri / visibilité de colonne, en effaçant le store active-view.
// L'écho de l'application d'une vue (source 'api') est ignoré : plus de course
// d'ordonnancement ni de diff d'état fragile.
dagfuncs.hideShareOnUserAction = function (params) {
  var source = params && params.source;
  if (SHARE_PROGRAMMATIC_SOURCES.indexOf(source) !== -1) {
    return;
  }
  if (window.dash_clientside && window.dash_clientside.set_props) {
    window.dash_clientside.set_props("active-view", { data: null });
  }
};

// Suivi Matomo des filtres de grille (issue #149). La saisie dans un filtre
// flottant produit un filterChanged par frappe : anti-rebond de 3 s par grille,
// puis envoi du jeu de filtres stable, lu au moment de l'envoi. Les sources
// programmatiques (vue partagée, filtre d'URL, localStorage, réinitialisation)
// sont ignorées ; un jeu vide n'est pas envoyé. window.colibreSuivi est lu à
// l'échéance, donc indépendamment de l'ordre de chargement des assets.
var SUIVI_FILTRES_DELAI_MS = 3000;
var suiviFiltresMinuteries = new WeakMap();

dagfuncs.suivreFiltres = function (params, categorie) {
  var source = params && params.source;
  if (SHARE_PROGRAMMATIC_SOURCES.indexOf(source) !== -1) {
    return;
  }
  var api = params.api;
  clearTimeout(suiviFiltresMinuteries.get(api));
  suiviFiltresMinuteries.set(
    api,
    setTimeout(function () {
      suiviFiltresMinuteries.delete(api);
      if (api.isDestroyed && api.isDestroyed()) return;
      var fm = api.getFilterModel() || {};
      var nb = Object.keys(fm).length;
      if (nb === 0 || !window.colibreSuivi) return;
      window.colibreSuivi.evenement(
        categorie,
        "filtres",
        window.colibreSuivi.serialiserFiltres(fm),
        nb
      );
    }, SUIVI_FILTRES_DELAI_MS)
  );
};
