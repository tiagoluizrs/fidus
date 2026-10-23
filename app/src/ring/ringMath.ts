// Geometria do anel. Funções puras (sem Canvas): o mesmo tempo, nível e estado sempre dão os mesmos pontos.
import type { UiState } from "../shared/protocol";

export interface Point {
  x: number;
  y: number;
}
export const LAYERS = 4;
export const LAYER_ALPHA = [1, 0.76, 0.52, 0.4]; // do anel externo ao mais interno (como no design)
const POINTS = 96;
const BASE_RADIUS = 0.8; // fração do raio útil (1 = metade do canvas)

/** Nível "efetivo" por estado. Falando não tem nível de microfone, então usa um envelope sintético. */
export function effectiveLevel(state: UiState, micLevel: number, t: number): number {
  switch (state) {
    case "listening":
      return clamp01(micLevel);
    case "speaking":
      return clamp01(0.38 + 0.28 * Math.sin(t * 5.1) + 0.2 * Math.sin(t * 9.7 + 1.3));
    case "thinking":
      return 0.22 + 0.06 * Math.sin(t * 2.4);
    case "muted":
      return 0;
    default:
      return 0.04 + 0.03 * Math.sin(t * 1.1); // respiração lenta
  }
}

export function clamp01(v: number): number {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

/** Camadas do anel (4 contornos ondulados) para o instante `t` (segundos). Coordenadas em [-1, 1]. */
export function ringLayers(t: number, level: number, state: UiState, reducedMotion = false): Point[][] {
  const speed = reducedMotion ? 0.25 : 1;
  const amp = (reducedMotion ? 0.4 : 1) * (state === "muted" ? 0.2 : 1);
  const spin = state === "thinking" ? t * 0.9 * speed : 0; // pensando: a onda gira em volta do anel
  const layers: Point[][] = [];
  for (let l = 0; l < LAYERS; l++) {
    const pts: Point[] = [];
    const wobble = (0.012 + level * 0.075 * (1 + l * 0.45)) * amp;
    for (let i = 0; i < POINTS; i++) {
      const a = (i / POINTS) * Math.PI * 2;
      const n =
        Math.sin(3 * a + t * 1.3 * speed + l * 1.7 + spin) * 0.55 +
        Math.sin(5 * a - t * 1.9 * speed + l * 0.9 + spin) * 0.3 +
        Math.sin(8 * a + t * 2.6 * speed + l * 2.3) * 0.15;
      const r = BASE_RADIUS - l * 0.04 + n * wobble + (state === "idle" ? 0.006 * Math.sin(t * 1.1 + l) : 0);
      pts.push({ x: Math.cos(a) * r, y: Math.sin(a) * r });
    }
    layers.push(pts);
  }
  return layers;
}

/** Suavização do nível do microfone: sobe rápido e desce devagar (parece voz, não ruído). */
export function smoothLevel(prev: number, next: number, dt: number): number {
  const rate = next > prev ? 18 : 5;
  return prev + (next - prev) * (1 - Math.exp(-rate * dt));
}

/** Cores do gradiente do anel. O muted fica cinza (sem destaque). */
export function ringStops(colors: string[], theme: "light" | "dark", state: UiState): string[] {
  if (state === "muted") return theme === "dark" ? ["#8E8E96", "#8E8E96", "#8E8E96"] : ["#6B6B73", "#6B6B73", "#6B6B73"];
  return colors.length >= 2 ? colors : ["#FF6A3D", "#FF5C9E", "#3D8BFF"];
}
