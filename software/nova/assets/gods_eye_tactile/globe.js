// NOVA — netteté du globe et boutons de zoom (s'exécute DANS la page,
// world: MAIN, car il faut accéder au moteur 3D Cesium de l'outil).
//
// Netteté : Cesium dessine par défaut en « résolution recommandée par le
// navigateur », c'est-à-dire en pixels CSS. Avec le zoom 1.5 de NOVA la page
// fait 534x320 pixels CSS : le globe était calculé en 534x320 puis étiré sur
// les 800x480 de l'écran, d'où l'image floue. On force la résolution réelle.
//
// L'outil ne publie pas son « viewer » : on récupère le module Cesium qu'il a
// déjà chargé (même URL => même instance) et on intercepte une fois le rendu
// pour attraper l'objet. Rien n'est modifié dans le code de l'outil.
(() => {
  'use strict';
  if (window.__novaGlobe) return;
  window.__novaGlobe = { widget: null };

  // URL exacte du module Cesium chargé par l'outil (elle porte un numéro de
  // version : ?v=...). On la lit dans un module de l'outil tel que le serveur
  // le sert, plutôt que dans la liste des ressources du navigateur : cette
  // liste est limitée à 250 entrées et l'URL n'y figurait pas toujours.
  async function urlCesium() {
    try {
      const source = await (await fetch('/src/app/viewer.js')).text();
      const trouve = source.match(/from\s+["']([^"']*\/cesium\.js[^"']*)["']/);
      if (trouve) return new URL(trouve[1], location.href).href;
    } catch (_) {
      /* serveur pas prêt : on réessaiera */
    }
    return performance
      .getEntriesByType('resource')
      .map((e) => e.name)
      .find((n) => /\/cesium\.js(\?|$)/.test(n));
  }

  async function attraperCesium(essais = 0) {
    const url = await urlCesium();
    if (!url) {
      if (essais < 240) setTimeout(() => attraperCesium(essais + 1), 500);
      return;
    }
    let Cesium;
    try {
      Cesium = await import(url);
    } catch (erreur) {
      console.warn('[NOVA] module Cesium inaccessible :', erreur);
      return;
    }
    const proto = Cesium.CesiumWidget?.prototype;
    if (!proto || proto.__novaPatch) return;
    proto.__novaPatch = true;
    const renduOrigine = proto.render;
    proto.render = function () {
      if (window.__novaGlobe.widget !== this) {
        window.__novaGlobe.widget = this;
        // Résolution réelle de l'écran au lieu des pixels CSS
        this.useBrowserRecommendedResolution = false;
      }
      return renduOrigine.apply(this, arguments);
    };
  }

  // ── Boutons + / − : zoom sans pincement (secours si le multitouch du
  // bureau n'est pas actif, et plus précis qu'un pincement sur 5 pouces).
  function zoomer(facteur) {
    const camera = window.__novaGlobe.widget?.scene?.camera;
    if (!camera) return;
    const hauteur = camera.positionCartographic?.height;
    if (!Number.isFinite(hauteur)) return;
    // Pas proportionnel à l'altitude : même sensation près du sol et de loin
    if (facteur > 0) camera.zoomIn(hauteur * facteur);
    else camera.zoomOut(hauteur * -facteur);
  }

  function installerBoutons(essais = 0) {
    // Seulement sur God's Eye View (le script est déclaré pour tout localhost)
    if (!document.getElementById('cesiumContainer')) {
      if (essais < 120) setTimeout(() => installerBoutons(essais + 1), 500);
      return;
    }
    const barre = document.createElement('div');
    barre.id = 'nova-zoom';
    for (const [texte, facteur, nom] of [
      ['+', 0.35, 'Zoomer'],
      ['−', -0.6, 'Reculer'],
    ]) {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = texte;
      b.setAttribute('aria-label', nom);
      // Appui maintenu = zoom continu
      let minuterie = null;
      const arreter = () => {
        clearInterval(minuterie);
        minuterie = null;
      };
      b.addEventListener('pointerdown', (e) => {
        e.preventDefault();
        e.stopPropagation();
        zoomer(facteur);
        arreter();
        minuterie = setInterval(() => zoomer(facteur * 0.5), 160);
      });
      for (const fin of ['pointerup', 'pointerleave', 'pointercancel'])
        b.addEventListener(fin, arreter);
      barre.appendChild(b);
    }
    document.body.appendChild(barre);
  }

  attraperCesium();
  installerBoutons();
})();
