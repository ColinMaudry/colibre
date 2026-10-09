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

  window.colibreSuivi = { evenement: evenement, recherche: recherche };
})();
