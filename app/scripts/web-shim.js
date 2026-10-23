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

  // Só no anel: microfone sempre ligado (como no app instalado), caixa de texto e resposta em voz
  if (/ring\.html$/.test(location.pathname)) {
    var MAX_S = 19, RATE = 16000, BLOCK = 2048;
    var micOn = true, speakOn = true;
    try { micOn = localStorage.getItem("fidus-mic") !== "0"; speakOn = localStorage.getItem("fidus-falar") !== "0"; } catch (e) {}
    var amb = null;      // captura em andamento: { stream, ctx, src, proc }
    var seg = null;      // fala em andamento: { chunks, total, quiet, wake }
    var pre = [];        // últimos blocos, para não cortar o começo da frase
    var loud = 0, floor = 0.01, ptt = false, assistBusy = false, muted = false;
    var btnMic, hint;

    function emit(e) { listeners.forEach(function (cb) { cb(e); }); }
    function b64(int16) {
      var bytes = new Uint8Array(int16.buffer), out = "", step = 0x8000;
      for (var i = 0; i < bytes.length; i += step) out += String.fromCharCode.apply(null, bytes.subarray(i, i + step));
      return btoa(out);
    }
    function resample(f32, from) {
      if (from === RATE) return f32;
      var ratio = from / RATE, n = Math.floor(f32.length / ratio), out = new Float32Array(n);
      for (var i = 0; i < n; i++) { var p = i * ratio, a = Math.floor(p), b = Math.min(a + 1, f32.length - 1); out[i] = f32[a] + (f32[b] - f32[a]) * (p - a); }
      return out;
    }
    function label() {
      if (!btnMic) return;
      btnMic.setAttribute("aria-pressed", micOn ? "true" : "false");
      btnMic.textContent = micOn ? "🎙 Microfone ligado" : "🔇 Microfone desligado";
      if (hint) hint.textContent = micOn ? "Diga “ei Alfred…”, “ei Donna…” ou “ei Jarbis…”. Ou segure a barra de espaço para falar direto." : "Ligue o microfone para chamar pelo nome, ou segure a barra de espaço para falar.";
    }

    // o que o ring está fazendo: enquanto o assistente pensa/fala, o microfone não capta (evita ouvir a própria voz)
    listeners.add(function (e) {
      if (e.type === "state") { assistBusy = e.state === "thinking" || e.state === "speaking"; muted = e.state === "muted"; }
    });

    async function startMic() {
      if (amb) return true;
      var stream;
      try { stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } }); }
      catch (e) { alert("Não consegui usar o microfone: " + (e && e.message ? e.message : e) + "\nPermita o microfone para este endereço no navegador (cadeado ao lado do endereço)."); return false; }
      var Ctx = window.AudioContext || window.webkitAudioContext;
      var ctx = new Ctx({ sampleRate: RATE });
      if (ctx.state === "suspended") ctx.resume();
      var src = ctx.createMediaStreamSource(stream);
      var proc = ctx.createScriptProcessor(BLOCK, 1, 1);
      proc.onaudioprocess = onBlock;
      src.connect(proc); proc.connect(ctx.destination); // o ScriptProcessor só roda ligado à saída; a entrada não é copiada, então não há eco
      amb = { stream: stream, ctx: ctx, src: src, proc: proc };
      return true;
    }
    function stopMic() {
      if (!amb) return;
      var a = amb; amb = null; seg = null; pre = []; loud = 0;
      a.proc.disconnect(); a.src.disconnect(); a.stream.getTracks().forEach(function (t) { t.stop(); }); a.ctx.close();
    }
    function idleState() { emit({ type: "state", state: "idle", mic: micOn ? "passive" : "off" }); }

    function onBlock(ev) {
      var d = new Float32Array(ev.inputBuffer.getChannelData(0)), sum = 0;
      for (var i = 0; i < d.length; i++) sum += d[i] * d[i];
      var rms = Math.sqrt(sum / d.length);
      var busy = assistBusy || muted || audioPlaying || playQueue.length > 0 || (window.speechSynthesis && speechSynthesis.speaking);
      if (!seg) {
        if (busy && !ptt) { pre = []; loud = 0; return; }
        pre.push(d); if (pre.length > 3) pre.shift();
        floor = Math.min(0.03, Math.max(0.004, floor * 0.95 + rms * 0.05)); // ruído de fundo
        var thr = Math.max(0.02, floor * 3.5);
        loud = rms > thr ? loud + 1 : 0;
        if (loud >= 2 || ptt) {
          seg = { chunks: pre.slice(), total: pre.reduce(function (n, c) { return n + c.length; }, 0), quiet: 0, wake: !ptt, thr: thr };
          if (window.speechSynthesis) speechSynthesis.cancel();
          emit({ type: "state", state: "listening", mic: "recording" });
        }
      } else {
        seg.chunks.push(d); seg.total += d.length;
        var lvl = Math.min(1, rms * 6);
        emit({ type: "level", values: [lvl, lvl * 0.85, lvl * 0.7] });
        if (!ptt) {
          seg.quiet = rms < seg.thr * 0.7 ? seg.quiet + 1 : 0;
          if (seg.quiet >= 7 || seg.total >= MAX_S * amb.ctx.sampleRate) finish();
        }
      }
    }
    function finish() {
      if (!seg) return;
      var s = seg; seg = null; loud = 0; pre = [];
      var rate = amb ? amb.ctx.sampleRate : RATE;
      var speechSeconds = (s.total - s.quiet * BLOCK) / rate;
      var all = new Float32Array(s.total), off = 0;
      s.chunks.forEach(function (c) { all.set(c, off); off += c.length; });
      all = resample(all, rate);
      if (speechSeconds < 0.5) { idleState(); if (!micOn) stopMic(); return; } // ruído curto: descarta
      var pcm = new Int16Array(all.length);
      for (var i = 0; i < all.length; i++) { var v = Math.max(-1, Math.min(1, all[i])); pcm[i] = v < 0 ? v * 0x8000 : v * 0x7fff; }
      if (!s.wake) emit({ type: "state", state: "thinking", mic: "paused" });
      else idleState(); // microfone aberto: só vira "pensando" se o núcleo reconhecer o chamado
      post("ask_audio", { pcm: b64(pcm), wake: s.wake }).then(function (reply) {
        if (!reply.ok) { emit({ type: "error", message: reply.error }); idleState(); }
      });
      if (!micOn) stopMic();
    }

    async function setMic(on) {
      micOn = on;
      try { localStorage.setItem("fidus-mic", on ? "1" : "0"); } catch (e) {}
      if (on) { if (!(await startMic())) micOn = false; } else stopMic();
      post("browser_mic", { on: micOn });
      label();
    }

    // voz gerada pelo NÚCLEO (Piper ou voz da nuvem): chega como áudio, frase a frase, e toca em ordem
    var serverVoice = false, playQueue = [], audioPlaying = false, curAudio = null, wasPlaying = false;
    function stopAudio() {
      playQueue = [];
      if (curAudio) { try { curAudio.pause(); } catch (e) {} curAudio = null; }
      audioPlaying = false;
    }
    function playNext() {
      if (audioPlaying) return;
      var item = playQueue.shift();
      if (!item) { if (wasPlaying) { wasPlaying = false; idleState(); } return; }
      audioPlaying = true; wasPlaying = true;
      emit({ type: "state", state: "speaking", mic: "paused" });
      var bytes = Uint8Array.from(atob(item.wav), function (c) { return c.charCodeAt(0); });
      var url = URL.createObjectURL(new Blob([bytes], { type: "audio/wav" }));
      var a = new Audio(url); curAudio = a;
      var done = function () { URL.revokeObjectURL(url); if (curAudio === a) { curAudio = null; audioPlaying = false; playNext(); } };
      a.onended = done; a.onerror = done;
      a.play().catch(done);
    }
    listeners.add(function (e) {
      if (e.type === "voice_mode") serverVoice = e.mode === "server";
      if (e.type === "speak_audio" && speakOn) { playQueue.push(e); playNext(); }
      if (e.type === "caption" && e.role === "user") stopAudio();
    });

    // resposta em voz pela voz do navegador (quando o personagem usa a voz do sistema, que só existe no Windows)
    var said = "";
    listeners.add(function (e) {
      if (e.type === "caption" && e.role === "user") { said = ""; if (window.speechSynthesis) window.speechSynthesis.cancel(); }
      if (e.type === "caption" && e.role === "assistant") {
        if (!e.final) said += e.text;
        else if (said.trim() && speakOn && !serverVoice && window.speechSynthesis) {
          var u = new SpeechSynthesisUtterance(said.trim()); u.lang = "pt-BR";
          var v = speechSynthesis.getVoices().filter(function (x) { return /^pt/i.test(x.lang); })[0]; if (v) u.voice = v;
          speechSynthesis.speak(u);
        }
      }
    });

    addEventListener("DOMContentLoaded", function () {
      var style = document.createElement("style");
      style.textContent =
        "#root{height:calc(100% - 118px)!important}" +
        "#fidus-dock{position:fixed;left:0;right:0;bottom:0;height:118px;box-sizing:border-box;padding:10px 16px;background:var(--bg);border-top:1px solid var(--border);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;z-index:50;font:14px system-ui,sans-serif;color:var(--text)}" +
        "#fidus-form{display:flex;gap:8px;flex-wrap:wrap;justify-content:center;width:min(840px,100%)}" +
        "#fidus-dock button,#fidus-dock input[type=text]{padding:9px 14px;border-radius:12px;border:1px solid var(--border);background:var(--card);color:var(--text);font:inherit;cursor:pointer}" +
        "#fidus-dock #fidus-ask{flex:1;min-width:200px;cursor:text}" +
        "#fidus-dock label{display:flex;align-items:center;gap:6px;color:var(--text-2);padding:0 6px}" +
        "#fidus-dock button[aria-pressed=true]{border-color:var(--success);background:color-mix(in srgb,var(--success) 16%,var(--card))}" +
        "#fidus-dock button:focus-visible,#fidus-dock input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}" +
        "#fidus-hint{color:var(--text-2);font-size:12.5px;text-align:center}";
      document.head.append(style);
      var box = document.createElement("div");
      box.id = "fidus-dock";
      box.innerHTML = '<form id="fidus-form">' +
        '<button type="button" id="fidus-mic" aria-pressed="false"></button>' +
        '<input id="fidus-ask" type="text" autocomplete="off" placeholder="…ou digite um pedido" aria-label="Digite um pedido">' +
        '<button type="submit">Enviar</button>' +
        '<label><input type="checkbox" id="fidus-falar"' + (speakOn ? " checked" : "") + '> Falar a resposta</label>' +
        '<button type="button" id="fidus-theme" title="Alternar claro/escuro" aria-label="Alternar claro/escuro">◐</button>' +
        '</form><div id="fidus-hint"></div>';
      document.body.append(box);
      btnMic = document.getElementById("fidus-mic"); hint = document.getElementById("fidus-hint"); label();
      btnMic.onclick = function () { void setMic(!micOn); };
      // o navegador só libera o áudio depois de um clique ou tecla: no primeiro gesto, religa o que estiver suspenso
      var wake = function () { if (amb && amb.ctx.state === "suspended") amb.ctx.resume(); };
      addEventListener("pointerdown", wake); addEventListener("keydown", wake);
      // segurar a barra de espaço = falar direto (sem chamar o nome), com o microfone ligado ou não
      addEventListener("keydown", async function (ev) {
        if (ev.code !== "Space" || ev.repeat || (document.activeElement && document.activeElement.tagName === "INPUT")) return;
        ev.preventDefault(); ptt = true;
        if (!(await startMic())) ptt = false;
      });
      addEventListener("keyup", function (ev) { if (ev.code === "Space" && ptt) { ptt = false; finish(); } });
      document.getElementById("fidus-falar").onchange = function (ev) {
        speakOn = ev.target.checked;
        try { localStorage.setItem("fidus-falar", speakOn ? "1" : "0"); } catch (e) {}
        if (!speakOn) { if (window.speechSynthesis) speechSynthesis.cancel(); stopAudio(); }
      };
      document.getElementById("fidus-form").onsubmit = function (e) {
        e.preventDefault();
        var i = document.getElementById("fidus-ask");
        var text = i.value.trim(); if (!text) return;
        post("ask", { text: text }).then(function (r) { if (!r.ok) alert(r.error); }); i.value = "";
      };
      document.getElementById("fidus-theme").onclick = function () { window.__fidusSetTheme(theme === "dark" ? "light" : "dark"); };
      if (micOn) void setMic(true); // microfone ligado por padrão, como no app instalado
    });
  }
})();
