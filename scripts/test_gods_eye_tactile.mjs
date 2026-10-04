// Vérifie l'adaptation tactile de God's Eye View (software/nova/assets/
// gods_eye_tactile) sans écran : ouvre l'outil dans un Chromium sans tête à
// la taille de l'écran NOVA, ouvre chaque onglet, capture une image et mesure
// les boutons (trop petits pour un doigt ? coupés hors de la feuille ?).
//
// Usage (serveur God's Eye démarré : scripts/gods_eye.sh demarrer) :
//   external/node/bin/node scripts/test_gods_eye_tactile.mjs <dossier_captures> [zoom] [--dom onglet]
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const RACINE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const puppeteer = createRequire(`${RACINE}/external/gods-eye-view/package.json`)('puppeteer');
const EXT = `${RACINE}/software/nova/assets/gods_eye_tactile`;
const args = process.argv.slice(2);
const SORTIE = args[0] || '/tmp/gods_eye_tactile';
const z = Number(args[1]) || 1.5;
const dom = args.includes('--dom') ? args[args.indexOf('--dom') + 1] : null;
// 800x480 moins la barre de titre de la fenêtre (~30 px)
const L = 800, H = 450;
const pause = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({
  executablePath: '/usr/lib/chromium/chromium', headless: true,
  args: ['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
});
const page = await browser.newPage();
await page.setViewport({ width: Math.round(L / z), height: Math.round(H / z), deviceScaleFactor: z, hasTouch: true });
await page.goto('http://localhost:4173', { waitUntil: 'domcontentloaded' });
await pause(12000);
// Les scripts de contenu d'une extension ne se chargent pas en mode sans
// tête de cette façon : on injecte les mêmes fichiers directement.
await page.addStyleTag({ path: `${EXT}/tactile.css` });
await page.addScriptTag({ path: `${EXT}/tactile.js` });
await pause(2500);
await page.screenshot({ path: `${SORTIE}/base.png` });

const onglets = await page.$$eval('#nova-onglets button', (bs) => bs.map((b) => b.dataset.onglet));
const rail = await page.$$eval('#nova-onglets button', (bs, z) => bs.map((b) => {
  const r = b.getBoundingClientRect();
  return { id: b.dataset.onglet, h: Math.round(r.height * z), visible: r.bottom <= innerHeight + 1 };
}), z);
console.log('onglets:', rail.map((r) => `${r.id}:${r.h}px${r.visible ? '' : ' HORS ÉCRAN'}`).join(' '));
console.log('premier lancement visible:', await page.evaluate(() => {
  const d = document.querySelector('[role=dialog], dialog[open]'); if (!d) return 'aucune fenêtre';
  const r = d.getBoundingClientRect(); return `${d.id || d.className} ${Math.round(r.width)}x${Math.round(r.height)} @${Math.round(r.left)},${Math.round(r.top)}`;
}));

for (const id of onglets) {
  if (['fermer', 'hud', 'cles'].includes(id)) continue;
  await page.tap(`#nova-onglets button[data-onglet="${id}"]`);
  await pause(1500);
  await page.screenshot({ path: `${SORTIE}/${id}.png` });
  const r = await page.evaluate((z) => {
    const p = document.querySelector('[data-nova-actif]');
    if (!p) return 'AUCUN PANNEAU ACTIF';
    const cont = p.parentElement.closest('#left-panel-stack,#right-context-rail,#command-dock') || p;
    const cr = cont.getBoundingClientRect();
    const res = { replie: p.classList.contains('collapsed'), hauteur: Math.round(p.scrollHeight), feuille: Math.round(cont.clientHeight), controles: 0, petits: [], coupes: [] };
    for (const el of p.querySelectorAll('button, input, select, [role=button], [role=switch]')) {
      const b = el.getBoundingClientRect(), cs = getComputedStyle(el);
      if (!b.width || !b.height || cs.visibility === 'hidden') continue;
      res.controles++;
      const nom = (el.getAttribute('aria-label') || el.textContent || el.id).trim().replace(/\s+/g, ' ').slice(0, 22);
      if (Math.min(b.width, b.height) * z < 40) res.petits.push(`${nom}:${Math.round(b.width * z)}x${Math.round(b.height * z)}`);
      if (b.right > cr.right + 2 || b.left < cr.left - 2) res.coupes.push(nom);
    }
    return res;
  }, z);
  console.log(id.padEnd(10), JSON.stringify(r));
  if (dom === id) {
    console.log(await page.evaluate(() => {
      const out = []; const p = document.querySelector('[data-nova-actif]');
      const walk = (el, d) => { if (d > 6) return; for (const c of el.children) {
        const r = c.getBoundingClientRect(), cs = getComputedStyle(c);
        if (cs.display === 'none' || ['svg', 'path'].includes(c.tagName)) continue;
        out.push(`${'  '.repeat(d)}${c.tagName.toLowerCase()}${c.id ? '#' + c.id : ''}.${[...c.classList].join('.')} [${Math.round(r.left)},${Math.round(r.top)} ${Math.round(r.width)}x${Math.round(r.height)}] ${cs.display}/${cs.position}/${cs.flexWrap} ${c.childNodes[0]?.nodeType === 3 ? c.childNodes[0].textContent.trim().slice(0, 14) : ''}`);
        walk(c, d + 1); } };
      walk(p, 0); return out.join('\n'); }));
  }
}
// Fermer la feuille : le globe doit redevenir entièrement libre
await page.tap('#nova-onglets button.actif');
await pause(800);
console.log('après fermeture, panneau actif:', await page.evaluate(() => !!document.querySelector('[data-nova-actif]')));
await browser.close();
