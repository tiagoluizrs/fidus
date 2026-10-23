import { useEffect, useRef } from "react";
import type { MutableRefObject } from "react";
import type { UiState } from "../shared/protocol";
import type { Theme } from "../shared/theme";
import { LAYER_ALPHA, effectiveLevel, ringLayers, ringStops, smoothLevel } from "./ringMath";

interface Props {
  state: UiState;
  colors: string[];
  theme: Theme;
  /** Nível do microfone (0 a 1), atualizado ~37x por segundo fora do React para não re-renderizar. */
  levelRef: MutableRefObject<number>;
  reducedMotion: boolean;
}

/** Desenha o anel em Canvas. Escuro: fundo preto com brilho. Claro: linhas mais saturadas, sem brilho. */
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
      draw(ctx, size, ringLayers(t, level, state, reducedMotion), ringStops(colors, theme, state), theme, level);
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [levelRef]);

  return <canvas ref={ref} className="ring-canvas" role="img" aria-label="Anel de luz reagindo à voz" />;
}

function draw(ctx: CanvasRenderingContext2D, size: number, layers: ReturnType<typeof ringLayers>, stops: string[], theme: Theme, level: number) {
  const c = size / 2;
  const grad = ctx.createLinearGradient(0, c - c * 0.85, 0, c + c * 0.85);
  stops.forEach((color, i) => grad.addColorStop(stops.length === 1 ? 0 : i / (stops.length - 1), color));
  ctx.lineJoin = "round";
  layers.forEach((pts, l) => {
    const path = () => {
      ctx.beginPath();
      pts.forEach((p, i) => (i ? ctx.lineTo(c + p.x * c, c + p.y * c) : ctx.moveTo(c + p.x * c, c + p.y * c)));
      ctx.closePath();
    };
    ctx.globalAlpha = LAYER_ALPHA[l];
    ctx.strokeStyle = grad;
    if (theme === "dark") {
      // brilho: um traço borrado por baixo e o traço fino por cima
      ctx.shadowColor = stops[Math.floor(stops.length / 2)];
      ctx.shadowBlur = 14 + level * 26;
      ctx.lineWidth = l === 0 ? 3 : 2;
      path();
      ctx.stroke();
      ctx.shadowBlur = 0;
      ctx.lineWidth = 1.2;
      path();
      ctx.stroke();
    } else {
      ctx.shadowBlur = 0; // claro: sem brilho, linhas um pouco mais grossas e saturadas
      ctx.lineWidth = l === 0 ? 2.4 : 1.6;
      path();
      ctx.stroke();
    }
  });
  ctx.globalAlpha = 1;
}
