// NOVA — adaptation tactile de God's Eye View pour l'écran 800x480.
//
// Pourquoi : l'interface de l'outil est pensée pour un écran de bureau ; sur
// le 5 pouces, même zoomée, ses panneaux s'empilent par-dessus le globe et
// leurs boutons sont trop petits pour un doigt. Ici, sans modifier le code de
// l'outil (ses mises à jour restent possibles) :
//   - une barre d'onglets à gauche, un onglet par panneau ;
//   - UN SEUL panneau affiché à la fois, en feuille défilante ;
//   - le HUD décoratif (« TOP SECRET », coordonnées) masqué, réaffichable ;
//   - un bouton ✕ pour fermer la fenêtre (pas de clavier sur NOVA).
// Les panneaux s'ouvrent par leurs propres boutons : toute la logique de
// l'outil (chargement des calques, etc.) reste celle d'origine.
(() => {
  'use strict';

  const ONGLETS = [
    { id: 'calques', icone: 'layers', libelle: 'Calques', panneau: '#data-panel' },
    { id: 'scenes', icone: 'movie', libelle: 'Scènes', panneau: '#scene-panel' },
    { id: 'lieu', icone: 'location_on', libelle: 'Lieu', panneau: '#location-bar' },
    { id: 'styles', icone: 'palette', libelle: 'Styles', panneau: '#control-panel' },
    { id: 'affichage', icone: 'tune', libelle: 'Affich.', panneau: '#pp-toggles' },
    { id: 'cctv', icone: 'videocam', libelle: 'CCTV', panneau: '#cctv-panel' },
    { id: 'contexte', icone: 'info', libelle: 'Infos', panneau: '#global-context-panel' },
    { id: 'voix', icone: 'mic', libelle: 'Voix', panneau: '#gev-voice-control' },
    { id: 'cles', icone: 'bolt', libelle: 'Clés', action: 'cles' },
    { id: 'hud', icone: 'visibility', libelle: 'HUD', action: 'hud' },
    { id: 'fermer', icone: 'close', libelle: 'Fermer', action: 'fermer' },
  ];
  // Icônes en SVG intégré (tracés Material Icons, licence Apache 2.0).
  // Pas de police d'icônes : en charger une seconde du même nom remplaçait
  // celle de la page et ses propres icônes s'affichaient en texte.
  const SVG = {
    layers: 'M11.99 18.54l-7.37-5.73L3 14.07l9 7 9-7-1.63-1.27-7.38 5.74zM12 16l7.36-5.73L21 9l-9-7-9 7 1.63 1.27L12 16z',
    movie: 'M18 4l2 4h-3l-2-4h-2l2 4h-3l-2-4H8l2 4H7L5 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V4h-4z',
    location_on: 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z',
    palette: 'M12 3a9 9 0 0 0 0 18c.83 0 1.5-.67 1.5-1.5 0-.39-.15-.74-.39-1.01-.23-.26-.38-.61-.38-.99 0-.83.67-1.5 1.5-1.5H16c2.76 0 5-2.24 5-5 0-4.42-4.03-8-9-8zm-5.5 9c-.83 0-1.5-.67-1.5-1.5S5.67 9 6.5 9 8 9.67 8 10.5 7.33 12 6.5 12zm3-4C8.67 8 8 7.33 8 6.5S8.67 5 9.5 5s1.5.67 1.5 1.5S10.33 8 9.5 8zm5 0c-.83 0-1.5-.67-1.5-1.5S13.67 5 14.5 5s1.5.67 1.5 1.5S15.33 8 14.5 8zm3 4c-.83 0-1.5-.67-1.5-1.5S16.67 9 17.5 9s1.5.67 1.5 1.5-.67 1.5-1.5 1.5z',
    tune: 'M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v-2h8v-2h-8v-2h-2v6h2zM7 9v2H3v2h4v2h2V9H7zm14 4v-2H11v2h10zm-6-4h2V7h4V5h-4V3h-2v6z',
    videocam: 'M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z',
    info: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z',
    mic: 'M12 14c1.66 0 2.99-1.34 2.99-3L15 5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z',
    bolt: 'M7 2v11h3v9l7-12h-4l4-8z',
    visibility: 'M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z',
    close: 'M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z',
  };
  const racine = document.documentElement;

  // N'agir que sur God's Eye View (le script est déclaré pour tout localhost)
  const estGodsEye = () =>
    document.getElementById('cesiumContainer') &&
    document.getElementById('command-dock');

  function attendreInterface(essais = 0) {
    if (estGodsEye()) return installer();
    if (essais < 120) setTimeout(() => attendreInterface(essais + 1), 500);
  }

  function ouvrirPanneau(panneau) {
    if (!panneau.classList.contains('collapsed')) return;
    // Le bouton de dépliage propre à l'outil, sinon un clic sur le panneau
    // (l'outil ouvre un panneau replié quand on clique dessus).
    const bouton =
      panneau.querySelector(`[data-dock-toggle-target="${panneau.id}"]`) ||
      panneau.querySelector(`[data-collapse-target="${panneau.id}"]`) ||
      panneau.querySelector('.dock-tray-toggle, .panel-collapse-btn');
    (bouton || panneau).click();
  }

  function installer() {
    racine.classList.add('nova-tactile');

    for (const o of ONGLETS) {
      const el = o.panneau && document.querySelector(o.panneau);
      if (el) el.classList.add('nova-gere');
    }

    const barre = document.createElement('nav');
    barre.id = 'nova-onglets';
    for (const o of ONGLETS) {
      const b = document.createElement('button');
      b.type = 'button';
      b.dataset.onglet = o.id;
      b.innerHTML =
        `<svg class="nova-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="${SVG[o.icone]}"/></svg>` +
        `<span class="nova-lib">${o.libelle}</span>`;
      b.setAttribute('aria-label', o.libelle);
      b.addEventListener('click', (e) => {
        e.stopPropagation();
        choisir(o);
      });
      barre.appendChild(b);
    }
    document.body.appendChild(barre);
  }

  let actif = null;

  function choisir(o) {
    if (o.action === 'fermer') {
      try {
        chrome.runtime.sendMessage('nova-fermer');
      } catch (_) {
        window.close();
      }
      return;
    }
    if (o.action === 'hud') {
      racine.classList.toggle('nova-hud');
      marquer();
      return;
    }
    if (o.action === 'cles') {
      fermerFeuille();
      document.getElementById('key-setup-chip')?.click();
      return;
    }
    if (actif === o.id) return fermerFeuille();

    fermerFeuille();
    const panneau = document.querySelector(o.panneau);
    if (!panneau) return;
    actif = o.id;
    racine.dataset.novaOnglet = o.id;
    panneau.setAttribute('data-nova-actif', '');
    ouvrirPanneau(panneau);
    marquer();
  }

  function fermerFeuille() {
    const precedent = document.querySelector('[data-nova-actif]');
    if (precedent) precedent.removeAttribute('data-nova-actif');
    actif = null;
    delete racine.dataset.novaOnglet;
    marquer();
  }

  function marquer() {
    for (const b of document.querySelectorAll('#nova-onglets button')) {
      const id = b.dataset.onglet;
      b.classList.toggle(
        'actif',
        id === actif || (id === 'hud' && racine.classList.contains('nova-hud')),
      );
    }
  }

  attendreInterface();
})();
