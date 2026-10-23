import { useEffect, useRef } from "react";
import type { MutableRefObject } from "react";
import type { UiState } from "../shared/protocol";
import type { Theme } from "../shared/theme";
import { effectiveLevel, ringStops, smoothLevel } from "./ringMath";
import { BUCKETS, BUCKET_ALPHA, STEPS, adaptStride, depthBucket, lighten, orbPoints } from "./orbMath";

interface Props {
  state: UiState;
  colors: string[];
  theme: Theme;
  /** Nível do microfone (0 a 1), atualizado ~37x por segundo fora do React para não re-renderizar. */
  levelRef: MutableRefObject<number>;
  reducedMotion: boolean;
}

/** Esfera de linhas que reage à voz. Escuro: linhas somadas, com brilho nos polos. Claro: linhas saturadas, sem brilho. */
export function RingCanvas({ state, colors, theme, levelRef, reducedMotion }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const live = useRef({ state, colors, theme, reducedMotion });
  live.current = { state, colors, theme, reducedMotion };

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    let raf = 0;
    let last = performance.now();
    let level = 0;
    const t0 = last;
    // qualidade adaptativa: começa no máximo (ou no que a URL pedir, ?q=2) e baixa sozinha se o computador não aguentar
    const forced = Number(new URLSearchParams(location.search).get("q"));
    let stride = [1, 2, 4].includes(forced) ? forced : 1;
    let avgMs = 12;
    let since = 0;

    const frame = (now: number) => {
      const { state, colors, theme, reducedMotion } = live.current;
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const t = (now - t0) / 1000;
      const dpr = window.devicePixelRatio || 1;
      const size = canvas.clientWidth;
      if (canvas.width !== Math.round(size * dpr)) {
        canvas.width = canvas.height = Math.round(size * dpr);
      }
      level = smoothLevel(level, effectiveLevel(state, levelRef.current, t), dt);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, size, size);
      const started = performance.now();
      draw(ctx, size, orbPoints(t, level, state, reducedMotion, stride), ringStops(colors, theme, state), theme, level, state);
      avgMs = avgMs * 0.9 + (performance.now() - started) * 0.1;
      since += dt;
      if (since > 1.5 && !forced) {
        stride = adaptStride(stride, avgMs);
        since = 0;
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [levelRef]);

  return <canvas ref={ref} className="ring-canvas" role="img" aria-label="Esfera de linhas reagindo à voz" />;
}

function draw(ctx: CanvasRenderingContext2D, size: number, pts: Float32Array, stops: string[], theme: Theme, level: number, state: UiState) {
  const c = size / 2;
  const dark = theme === "dark";
  const top = stops[0];
  const bottom = stops[stops.length - 1];
  const mid = stops.length > 2 ? stops[Math.floor(stops.length / 2)] : lighten(top, 0.5);
  const grad = ctx.createLinearGradient(0, c * 0.24, 0, c * 1.76);
  grad.addColorStop(0, top);
  grad.addColorStop(0.5, dark && state !== "muted" ? lighten(mid, 0.6) : mid); // o meio é claro, como na referência
  grad.addColorStop(1, bottom);

  // um caminho por faixa de profundidade: poucas chamadas de traço, mesmo com milhares de segmentos
  const paths = Array.from({ length: BUCKETS }, () => new Path2D());
  const lines = pts.length / (STEPS * 3);
  for (let m = 0; m < lines; m++) {
    for (let s = 0; s < STEPS - 1; s++) {
      const a = (m * STEPS + s) * 3;
      const b = a + 3;
      const z = (pts[a + 2] + pts[b + 2]) / 2;
      const p = paths[depthBucket(z)];
      p.moveTo(c + pts[a] * c, c + pts[a + 1] * c);
      p.lineTo(c + pts[b] * c, c + pts[b + 1] * c);
    }
  }

  ctx.lineCap = "round";
  ctx.strokeStyle = grad;
  if (dark) ctx.globalCompositeOperation = "lighter"; // linhas se somam: o centro e os polos acendem
  const boost = state === "muted" ? 0.5 : 1 + level * 0.6;
  for (let b = 0; b < BUCKETS; b++) {
    const alpha = BUCKET_ALPHA[b] * (dark ? 1 : 1.5) * boost;
    if (dark && b >= 2) {
      ctx.globalAlpha = Math.min(1, alpha * 0.28); // halo: o mesmo traço mais grosso e fraco
      ctx.lineWidth = 3.4;
      ctx.stroke(paths[b]);
    }
    ctx.globalAlpha = Math.min(1, alpha);
    ctx.lineWidth = dark ? 0.8 : 1.0;
    ctx.stroke(paths[b]);
  }

  if (dark && state !== "muted") {
    // brilho nos polos (laranja em cima, azul embaixo), mais forte com a voz
    for (const [y, color] of [[0.34, top], [1.66, bottom]] as const) {
      const r = c * (0.22 + level * 0.1); // o brilho nunca encosta na borda do canvas (sem corte reto)
      const g = ctx.createRadialGradient(c, c * y, 0, c, c * y, r);
      g.addColorStop(0, lighten(color, 0.55));
      g.addColorStop(1, "rgba(0,0,0,0)");
      ctx.globalAlpha = 0.45 + level * 0.4;
      ctx.fillStyle = g;
      ctx.fillRect(c - r, c * y - r, r * 2, r * 2);
    }
  }
  ctx.globalAlpha = 1;
  ctx.globalCompositeOperation = "source-over";
}
