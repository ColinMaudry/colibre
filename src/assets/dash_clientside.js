// --- Garde du Leaflet global (issue #121) ---
// Le bundle dash-ag-grid (async-community.js) fuit un helper esbuild sous le
// nom global `L`, écrasant le `window.L` de Leaflet. Nos fonctions
// pointToLayer/clusterToLayer (ci-dessous) ont besoin du vrai Leaflet. Comme
// dash-leaflet ne passe pas Leaflet en argument, on capture en privé la
// dernière valeur de `window.L` exposant `circleMarker` (= le vrai Leaflet) en
// écoutant les affectations, SANS modifier ce que `window.L` renvoie (AG Grid
// continue d'utiliser son helper). `leafletReal()` renvoie ce vrai Leaflet.
(function () {
  var real = window.L && window.L.circleMarker ? window.L : null;
  var last = window.L;
  try {
    Object.defineProperty(window, "L", {
      configurable: true,
      get: function () {
        return last;
      },
      set: function (v) {
        last = v;
        if (v && v.circleMarker) real = v;
      },
    });
  } catch (e) {
    /* propriété non configurable : on garde le comportement natif */
  }
  window.leafletReal = function () {
    return real || last;
  };
})();

window.dash_clientside = Object.assign({}, window.dash_clientside, {
  leaflet: {
    pointToLayer: function (feature, latlng, context) {
      const L = window.leafletReal ? window.leafletReal() : window.L;
      // Le point de l'organisme consulté (is_home) est rendu comme une
      // icône (comme les clusters), pas comme un circleMarker SVG : les
      // icônes vivent dans le markerPane, toujours au-dessus du overlayPane
      // (SVG) où se trouvent les circleMarkers, et gardent une taille CSS
      // fixe (contrairement aux tracés SVG, redimensionnés visuellement
      // pendant l'animation de zoom).
      if (feature.properties.is_home) {
        const size = 22;
        const icon = L.divIcon({
          html: `<div style="background-color: ${feature.properties.marker_color}; width: ${size}px; height: ${size}px; border-radius: 50%; border: 2px solid white; box-sizing: border-box;"></div>`,
          className: "org-home-marker",
          iconSize: L.point(size, size),
        });
        return L.marker(latlng, { icon: icon, zIndexOffset: 1000 }).bindTooltip(
          feature.properties.tooltip
        );
      }
      return L.circleMarker(latlng, {
        radius: 5,
        fillColor: feature.properties.marker_color,
        color: "white",
        weight: 1,
        opacity: 1,
        fillOpacity: 0.8,
        className: "org-point",
      }).bindTooltip(feature.properties.tooltip);
    },
    clusterToLayer: function (feature, latlng, index, context) {
      const L = window.leafletReal ? window.leafletReal() : window.L;
      const count = feature.properties.point_count;
      const size = count < 100 ? 30 : count < 1000 ? 40 : 50;
      const icon = L.divIcon({
        html: `<div style="background-color: ${context.fillColor}; width: ${size}px; height: ${size}px; border-radius: 50%; display: flex; align-items:center; justify-content:center; color: white; border: 2px solid white; font-weight: bold;">${count}</div>`,
        className: "marker-cluster",
        iconSize: L.point(size, size),
      });
      return L.marker(latlng, { icon: icon });
    },
  },
  clientside: {
    clean_filters: function (trigger) {
      if (!trigger) {
        return window.dash_clientside.no_update;
      }

      // Helper to set value on a React text input
      const setNativeValue = (element, value) => {
        const valueSetter = Object.getOwnPropertyDescriptor(
          element,
          "value"
        ).set;
        const prototype = Object.getPrototypeOf(element);
        const prototypeValueSetter = Object.getOwnPropertyDescriptor(
          prototype,
          "value"
        ).set;

        if (valueSetter && valueSetter !== prototypeValueSetter) {
          prototypeValueSetter.call(element, value);
        } else {
          valueSetter.call(element, value);
        }

        element.dispatchEvent(new Event("input", { bubbles: true }));
      };

      const cleanInputs = () => {
        const inputs = document.querySelectorAll(
          '.dash-filter input[type="text"]'
        );
        inputs.forEach((input) => {
          let val = input.value;
          let original = val;

          // Remove "icontains " prefix
          if (/^icontains\s+/i.test(val)) {
            val = val.replace(/^icontains\s+/i, "");
            // Check for surrounding quotes (single or double) and remove them
            if (
              (val.startsWith('"') && val.endsWith('"')) ||
              (val.startsWith("'") && val.endsWith("'"))
            ) {
              val = val.substring(1, val.length - 1);
            }
          }
          // Handle relational operators (i<, s>, i<=, etc.)
          else if (/^[is][<>]=?/i.test(val)) {
            val = val.substring(1);
          }

          if (val !== original) {
            try {
              // Try setting it the React-friendly way
              setNativeValue(input, val);
            } catch (e) {
              // Fallback to direct assignment if fancy way fails
              input.value = val;
            }
          }
        });
      };

      // Use MutationObserver to wait for table to appear/update
      const observer = new MutationObserver((mutations) => {
        cleanInputs();
      });

      const target = document.querySelector(".dash-table-container");
      if (target) {
        observer.observe(target, {
          childList: true,
          subtree: true,
          attributes: true,
          attributeFilter: ["value"],
        });

        // Disconnect after 5 seconds
        setTimeout(() => {
          observer.disconnect();
        }, 5000);

        // Also try immediately just in case
        cleanInputs();
      } else {
        // Poll briefly if container not found yet
        const checkInterval = setInterval(() => {
          const t = document.querySelector(".dash-table-container");
          if (t) {
            clearInterval(checkInterval);
            observer.observe(t, { childList: true, subtree: true });
            setTimeout(() => observer.disconnect(), 5000);
            cleanInputs();
          }
        }, 200);

        // Stop polling after 2s if still nothing
        setTimeout(() => clearInterval(checkInterval), 2000);
      }

      return window.dash_clientside.no_update;
    },
  },
});
