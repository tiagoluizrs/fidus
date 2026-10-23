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
    openMicSettings: function () { alert("Para mudar a permissão do microfone, clique no cadeado ao lado do endereço do navegador > Configurações do site > Microfone."); return Promise.resolve(); },
    micStatus: function () {
      if (!navigator.permissions || !navigator.permissions.query) return Promise.resolve("unknown");
      return navigator.permissions.query({ name: "microphone" }).then(function (p) { return p.state === "prompt" ? "not-determined" : p.state; }).catch(function () { return "unknown"; });
    },
    restartCore: function () { alert("Reinicie com: docker compose restart web"); return Promise.resolve(); },
    copyText: function (t) { return navigator.clipboard.writeText(t); },
  };

  // Só no anel: caixa de texto, microfone do navegador (segure para falar) e resposta em voz
  if (/ring\.html$/.test(location.pathname)) {
    var MAX_S = 20, RATE = 16000;
    var rec = null;
    var speakOn = true;
    try { speakOn = localStorage.getItem("fidus-falar") !== "0"; } catch (e) {}
    function emit(e) { listeners.forEach(function (cb) { cb(e); }); }
    function b64(int16) {
      var bytes = new Uint8Array(int16.buffer), out = "", step = 0x8000;
      for (var i = 0; i < bytes.length; i += step) out += String.fromCharCode.apply(null, bytes.subarray(i, i + step));
      return btoa(out);
    }
    async function startRec() {
      if (rec) return;
      var stream;
      try { stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } }); }
      catch (e) { alert("Não consegui usar o microfone: " + (e && e.message ? e.message : e) + "\nPermita o microfone para este endereço no navegador."); return; }
      var Ctx = window.AudioContext || window.webkitAudioContext;
      var ctx = new Ctx({ sampleRate: RATE });
      var src = ctx.createMediaStreamSource(stream);
      var proc = ctx.createScriptProcessor(4096, 1, 1);
      var r = { stream: stream, ctx: ctx, src: src, proc: proc, chunks: [], total: 0 };
      proc.onaudioprocess = function (ev) {
        var d = ev.inputBuffer.getChannelData(0), sum = 0;
        r.chunks.push(new Float32Array(d)); r.total += d.length;
        for (var i = 0; i < d.length; i++) sum += d[i] * d[i];
        var lvl = Math.min(1, Math.sqrt(sum / d.length) * 6);
        emit({ type: "level", values: [lvl, lvl * 0.85, lvl * 0.7] });
        if (r.total >= MAX_S * ctx.sampleRate) stopRec();
      };
      src.connect(proc); proc.connect(ctx.destination); // o ScriptProcessor só roda ligado à saída; não copiamos a entrada, então não há eco
      rec = r;
      if (window.speechSynthesis) window.speechSynthesis.cancel();
      emit({ type: "state", state: "listening", mic: "recording" });
      setBtn(true);
    }
    function stopRec() {
      if (!rec) return;
      var r = rec; rec = null; setBtn(false);
      r.proc.disconnect(); r.src.disconnect(); r.stream.getTracks().forEach(function (t) { t.stop(); });
      var rate = r.ctx.sampleRate; r.ctx.close();
      var all = new Float32Array(r.total), off = 0;
      r.chunks.forEach(function (c) { all.set(c, off); off += c.length; });
      if (all.length < 0.4 * rate) { emit({ type: "state", state: "idle", mic: "off" }); return; }
      var pcm = new Int16Array(all.length);
      for (var i = 0; i < all.length; i++) { var v = Math.max(-1, Math.min(1, all[i])); pcm[i] = v < 0 ? v * 0x8000 : v * 0x7fff; }
      emit({ type: "state", state: "thinking", mic: "paused" });
      post("ask_audio", { pcm: b64(pcm) }).then(function (reply) {
        if (!reply.ok) { emit({ type: "error", message: reply.error }); emit({ type: "state", state: "idle", mic: "off" }); }
      });
    }
    var btnMic;
    function setBtn(on) {
      if (!btnMic) return;
      btnMic.setAttribute("aria-pressed", on ? "true" : "false");
      btnMic.textContent = on ? "● Gravando… solte para enviar" : "🎤 Segure para falar";
      btnMic.style.background = on ? "#ffd9d9" : "#fff";
    }

    // resposta em voz (só neste modo de teste): usa a voz do navegador
    var said = "";
    listeners.add(function (e) {
      if (e.type === "caption" && e.role === "user") { said = ""; if (window.speechSynthesis) window.speechSynthesis.cancel(); }
      if (e.type === "caption" && e.role === "assistant") {
        if (!e.final) said += e.text;
        else if (said.trim() && speakOn && window.speechSynthesis) {
          var u = new SpeechSynthesisUtterance(said.trim()); u.lang = "pt-BR";
          var v = speechSynthesis.getVoices().filter(function (x) { return /^pt/i.test(x.lang); })[0]; if (v) u.voice = v;
          speechSynthesis.speak(u);
        }
      }
    });

    addEventListener("DOMContentLoaded", function () {
      var box = document.createElement("form");
      box.style.cssText = "position:fixed;left:50%;bottom:14px;transform:translateX(-50%);z-index:99;display:flex;gap:8px;flex-wrap:wrap;justify-content:center;width:min(760px,94vw);font:14px system-ui";
      var btn = "padding:10px 14px;border-radius:12px;border:1px solid #888;background:#fff;color:#111;cursor:pointer";
      box.innerHTML = '<button type="button" id="fidus-mic" aria-pressed="false" style="' + btn + '">🎤 Segure para falar</button>' +
        '<input id="fidus-ask" autocomplete="off" placeholder="…ou digite um pedido" style="flex:1;min-width:200px;padding:10px 14px;border-radius:12px;border:1px solid #888;background:#fff;color:#111">' +
        '<button style="' + btn + '">Enviar</button>' +
        '<label style="display:flex;align-items:center;gap:6px;color:#fff;background:#0008;padding:8px 10px;border-radius:12px"><input type="checkbox" id="fidus-falar"' + (speakOn ? " checked" : "") + '> Falar a resposta</label>' +
        '<button type="button" id="fidus-theme" style="' + btn + '" title="Alternar claro/escuro">◐</button>';
      document.body.append(box);
      btnMic = document.getElementById("fidus-mic");
      var down = function (ev) { ev.preventDefault(); void startRec(); }, up = function () { stopRec(); };
      btnMic.addEventListener("mousedown", down); addEventListener("mouseup", up);
      btnMic.addEventListener("touchstart", down, { passive: false }); addEventListener("touchend", up);
      // barra de espaço também segura para falar (quando não está digitando)
      addEventListener("keydown", function (ev) { if (ev.code === "Space" && !ev.repeat && document.activeElement && document.activeElement.tagName !== "INPUT") { ev.preventDefault(); void startRec(); } });
      addEventListener("keyup", function (ev) { if (ev.code === "Space") stopRec(); });
      document.getElementById("fidus-falar").onchange = function (ev) {
        speakOn = ev.target.checked;
        try { localStorage.setItem("fidus-falar", speakOn ? "1" : "0"); } catch (e) {}
        if (!speakOn && window.speechSynthesis) speechSynthesis.cancel();
      };
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
