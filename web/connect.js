// Page « Connexion » : adresses du PC sur le réseau local et QR code (généré par le serveur).
const qr = document.getElementById("qr");
const list = document.getElementById("urls");

function showQr(url) {
  qr.src = `api/qr.svg?url=${encodeURIComponent(url)}`;
  qr.title = url;
  for (const li of list.querySelectorAll("li")) li.classList.toggle("selected", li.dataset.url === url);
}

fetch("api/info")
  .then((r) => r.json())
  .then((info) => {
    document.getElementById("info").textContent =
      `Version ${info.version} · source : ${info.source} · port ${info.port}`;
    // Page ouverte depuis un autre appareil : l'adresse courante fonctionne déjà, on la propose en premier.
    const local = ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
    const urls = [...new Set([...(local ? [] : [location.origin]), ...info.lan_urls])];
    list.innerHTML = "";
    if (!urls.length) {
      list.innerHTML =
        "<li>Aucune adresse réseau local détectée (PC hors réseau, ou serveur lancé avec <code>--host 127.0.0.1</code>).</li>";
      qr.hidden = true;
      return;
    }
    for (const url of urls) {
      const li = document.createElement("li");
      li.dataset.url = url;
      const a = document.createElement("a");
      a.href = url;
      a.textContent = url;
      li.appendChild(a);
      // Plusieurs adresses (Wi-Fi + Ethernet…) : un clic choisit celle du QR code.
      li.addEventListener("click", (e) => {
        if (urls.length > 1) {
          e.preventDefault();
          showQr(url);
        }
      });
      list.appendChild(li);
    }
    showQr(urls[0]);
  })
  .catch(() => {
    list.innerHTML = "<li>Serveur injoignable.</li>";
  });
