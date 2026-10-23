// Faz o papel do preload do Electron no navegador: window.fidus conversa com o servidor de teste (webhost) por HTTP.
(function () {
  var listeners = new Set();
  var themeCbs = new Set();
  function systemTheme() { return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"; }
  var theme = new URLSearchParams(location.search).get("theme") || systemTheme();
  function post(name, args) {
    return fetch("/api/command", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: name, args: args || {} }) }).then(function (r) { return r.json(); });
  }
  var es = new EventSource("/api/events");
  es.onmessage = function (m) { var e = JSON.parse(m.data); listeners.forEach(function (cb) { cb(e); }); };
  // Se a conexão caiu e voltou, eventos podem ter se perdido: entrega o estado atual como um novo "ready" para as telas relerem tudo.
  var opened = false;
  es.onopen = function () {
    if (opened) fetch("/api/snapshot").then(function (r) { return r.json(); }).then(function (snap) { if (snap) listeners.forEach(function (cb) { cb({ type: "ready", protocol: 1, snapshot: snap }); }); });
    opened = true;
  };
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () { theme = systemTheme(); themeCbs.forEach(function (cb) { cb(theme); }); });
  window.__fidusSetTheme = function (t) { theme = t; themeCbs.forEach(function (cb) { cb(t); }); };
  window.fidus = {
    command: post,
    getSnapshot: function () { return fetch("/api/snapshot").then(function (r) { return r.json(); }); },
    getTheme: function () { return Promise.resolve(theme); },
    onThemeChange: function (cb) { themeCbs.add(cb); return function () { themeCbs.delete(cb); }; },
    onEvent: function (cb) { listeners.add(cb); return function () { listeners.delete(cb); }; },
    onNavigate: function (cb) { function on() { cb(location.hash.slice(1)); } addEventListener("hashchange", on); return function () { removeEventListener("hashchange", on); }; },
    closeWindow: function () {},
    pickFolder: function () { return Promise.resolve(prompt("Caminho da pasta (dentro do container, ex.: /work/docs):")); },
    pickSavePath: function (name) { return Promise.resolve("/data/exports/" + name); },
    saveTextFile: function (name, text) {
      var a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
      a.download = name; a.click(); URL.revokeObjectURL(a.href);
      return Promise.resolve(true);
    },
    openPath: function (p) { alert("No container: " + p); return Promise.resolve(true); },
    openMicSettings: function () { alert("No navegador não há microfone do Fidus; no Windows isso abre os ajustes do sistema."); return Promise.resolve(); },
    micStatus: function () { return Promise.resolve("granted"); },
    restartCore: function () { alert("Reinicie com: docker compose restart web"); return Promise.resolve(); },
    copyText: function (t) { return navigator.clipboard.writeText(t); },
  };

  // Só no anel: caixa de texto para pedir por texto (no Windows seria a voz) e atalho claro/escuro
  if (/ring\.html$/.test(location.pathname)) {
    addEventListener("DOMContentLoaded", function () {
      var box = document.createElement("form");
      box.style.cssText = "position:fixed;left:50%;bottom:14px;transform:translateX(-50%);z-index:99;display:flex;gap:8px;width:min(640px,92vw);font:14px system-ui";
      box.innerHTML = '<input id="fidus-ask" autocomplete="off" placeholder="Digite um pedido (no Windows seria falando)…" style="flex:1;padding:10px 14px;border-radius:12px;border:1px solid #888;background:#fff;color:#111"><button style="padding:10px 14px;border-radius:12px;border:1px solid #888;background:#fff;color:#111;cursor:pointer">Enviar</button><button type="button" id="fidus-theme" style="padding:10px 12px;border-radius:12px;border:1px solid #888;background:#fff;color:#111;cursor:pointer" title="Alternar claro/escuro">◐</button>';
      document.body.append(box);
      box.onsubmit = function (e) {
        e.preventDefault();
        var i = document.getElementById("fidus-ask");
        var text = i.value.trim(); if (!text) return;
        post("ask", { text: text }).then(function (r) { if (!r.ok) alert(r.error); }); i.value = "";
      };
      document.getElementById("fidus-theme").onclick = function () { window.__fidusSetTheme(theme === "dark" ? "light" : "dark"); };
    });
  }
})();
