// Nível de áudio e cores do anel. Funções puras (sem Canvas).
import type { UiState } from "../shared/protocol";

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
