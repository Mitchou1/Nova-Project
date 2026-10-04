// Ferme la fenêtre du globe à la demande du bouton ✕ (tactile.js).
// window.close() n'est pas fiable dans une fenêtre --app ouverte par la ligne
// de commande ; l'API windows de l'extension, si.
chrome.runtime.onMessage.addListener((message, sender) => {
  if (message === 'nova-fermer' && sender.tab) {
    chrome.windows.remove(sender.tab.windowId);
  }
});
