/* Drag & drop des cards de l'observatoire (issue #107).
 *
 * Réordonne les cards par drag & drop HTML5 natif, puis pousse le nouvel ordre
 * dans un dcc.Store via window.dash_clientside.set_props — un callback serveur
 * le persiste ensuite en base.
 *
 * Deux conventions viennent de src/figures.py :
 *   - chaque card porte les classes `observatoire-card observatoire-card--<id>`
 *     (et non un data-card-id : dbc.Col n'accepte aucune prop wildcard) ;
 *   - un marqueur invisible `[data-observatoire-cards]` est rendu parmi les
 *     cards ; son parentElement est la liste à ordonner, et son attribut
 *     `data-card-order-store` donne l'id du dcc.Store à mettre à jour. Le
 *     serveur ne rend ce marqueur que pour les abonné·es : son absence suffit
 *     à désactiver la fonctionnalité, sans contrôle de droits côté client.
 *
 * Désactivé sur interfaces tactiles (pointer: coarse) et petits écrans.
 */
(function () {
  "use strict";

  var MIN_WIDTH = 768;
  var CARD_CLASS = "observatoire-card";
  var ID_PREFIX = CARD_CLASS + "--";

  function isTouchOrSmall() {
    return (
      window.matchMedia("(pointer: coarse)").matches ||
      window.innerWidth < MIN_WIDTH
    );
  }

  function cardId(el) {
    var classes = (el.className || "").split(/\s+/);
    for (var i = 0; i < classes.length; i++) {
      if (classes[i].indexOf(ID_PREFIX) === 0) {
        return classes[i].slice(ID_PREFIX.length);
      }
    }
    return null;
  }

  function pushOrder(marker, list) {
    var storeId = marker.getAttribute("data-card-order-store");
    if (
      !storeId ||
      !window.dash_clientside ||
      !window.dash_clientside.set_props
    ) {
      return;
    }
    var order = Array.prototype.slice
      .call(list.children)
      .map(cardId)
      .filter(Boolean);
    window.dash_clientside.set_props(storeId, { data: order });
  }

  function enable(marker) {
    if (isTouchOrSmall()) return;

    var list = marker.parentElement;
    if (!list || list.dataset.dragEnabled === "true") return;

    var cards = Array.prototype.slice.call(
      list.querySelectorAll("." + CARD_CLASS)
    );
    if (!cards.length) return;

    list.dataset.dragEnabled = "true";

    var dragSrc = null;

    cards.forEach(function (card) {
      card.draggable = true;
      card.classList.add("observatoire-card-draggable");
    });

    function clearHighlights() {
      cards.forEach(function (card) {
        card.classList.remove("drag-over");
      });
    }

    list.addEventListener("dragstart", function (e) {
      var card = e.target.closest("." + CARD_CLASS);
      if (!card) return;
      dragSrc = card;
      card.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      // Firefox n'amorce le drag que si dataTransfer porte une donnée.
      e.dataTransfer.setData("text/plain", cardId(card) || "");
    });

    list.addEventListener("dragend", function () {
      if (dragSrc) dragSrc.classList.remove("dragging");
      clearHighlights();
      dragSrc = null;
    });

    list.addEventListener("dragover", function (e) {
      if (!dragSrc) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      var target = e.target.closest("." + CARD_CLASS);
      if (!target || target === dragSrc) return;
      clearHighlights();
      target.classList.add("drag-over");
    });

    list.addEventListener("dragleave", function (e) {
      var target = e.target.closest("." + CARD_CLASS);
      if (target) target.classList.remove("drag-over");
    });

    list.addEventListener("drop", function (e) {
      e.preventDefault();
      var target = e.target.closest("." + CARD_CLASS);
      if (!target || !dragSrc || target === dragSrc) return;

      var siblings = Array.prototype.slice.call(list.children);
      if (siblings.indexOf(dragSrc) < siblings.indexOf(target)) {
        list.insertBefore(dragSrc, target.nextSibling);
      } else {
        list.insertBefore(dragSrc, target);
      }

      clearHighlights();
      pushOrder(marker, list);
    });
  }

  function init() {
    document.querySelectorAll("[data-observatoire-cards]").forEach(enable);
  }

  // Les cards sont re-rendues à chaque changement de filtre : on ré-arme le
  // drag sur la nouvelle liste. Le garde `dragEnabled` empêche la boucle —
  // nos propres mutations rappellent l'observer, qui ressort aussitôt.
  new MutationObserver(init).observe(document.body, {
    childList: true,
    subtree: true,
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
