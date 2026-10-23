// Geometria da esfera de linhas do anel (funções puras, sem Canvas): mesmo tempo, nível e estado, mesmos pontos.
// Uma esfera feita de "meridianos" ondulantes (linhas de polo a polo) que giram e se deformam com a voz.
import type { UiState } from "../shared/protocol";

export const MERIDIANS = 128; // linhas em volta da esfera
export const STEPS = 64; // pontos em cada linha, do polo sul ao norte
export const ORB_RADIUS = 0.8; // fração do raio útil do canvas (1 = metade)
export const BUCKETS = 5; // faixas de profundidade (a frente é mais forte que o fundo)

const TAU = Math.PI * 2;

/** Quanto a esfera gira (rad/s) em cada estado. */
export function spinSpeed(state: UiState, reducedMotion: boolean): number {
  const base = state === "thinking" ? 0.95 : state === "speaking" ? 0.4 : state === "listening" ? 0.3 : state === "muted" ? 0.04 : 0.14;
  return reducedMotion ? base * 0.25 : base;
}

/**
 * Pontos da esfera para o instante `t` (segundos). Devolve x, y, z de cada ponto (3 números por ponto, meridiano por
 * meridiano). x e y em [-1, 1] já projetados (y positivo para baixo, como no Canvas); z em [-1, 1] (1 = de frente).
 */
export function orbPoints(t: number, level: number, state: UiState, reducedMotion = false, stride = 1): Float32Array {
  const lines = Math.ceil(MERIDIANS / stride); // `stride` > 1 usa só parte dos meridianos (qualidade menor, bem mais leve)
  const out = new Float32Array(lines * STEPS * 3);
  const amp = (reducedMotion ? 0.4 : 1) * (state === "muted" ? 0.2 : 1);
  const motion = reducedMotion ? 0.25 : 1;
  const spin = t * spinSpeed(state, reducedMotion);
  const shimmer = state === "thinking" ? 1 : 0.35; // pensando: ondas correndo de cima a baixo
  const A = (0.014 + level * 0.12) * amp;
  const tilt = 0.24 + 0.05 * Math.sin(t * 0.45 * motion); // rad; "respira" devagar
  const cosTilt = Math.cos(tilt);
  const sinTilt = Math.sin(tilt);
  let k = 0;
  for (let m = 0; m < MERIDIANS; m += stride) {
    const lon = (m / MERIDIANS) * TAU;
    for (let s = 0; s < STEPS; s++) {
      const lat = -Math.PI / 2 + ((s + 0.5) / STEPS) * Math.PI; // evita cravar exatamente nos polos
      // ondulação do contorno: lóbulos largos + detalhe fino (a borda fica "turbulenta", como a voz)
      const n =
        0.1 * Math.sin(5 * lon + 1.0 * t * motion + 3 * lat) + // lóbulos largos: poucos, para a silhueta continuar redonda
        0.12 * Math.sin(9 * lon - 1.6 * t * motion + 2 * lat) +
        0.3 * Math.sin(17 * lon + 2.3 * t * motion - 5 * lat) +
        0.3 * Math.sin(29 * lon - 3.1 * t * motion + 7 * lat);
      const band = level * 0.55 * Math.sin(9 * lat - 5.5 * t * motion * shimmer);
      const r = ORB_RADIUS * (1 + A * (n + band));
      // tremor lateral fino: faz as linhas do centro ondularem, como fios vibrando
      const wiggle = (0.003 + level * 0.012) * amp * (0.6 * Math.sin(23 * lat - 2.6 * t * motion + 4 * lon) + 0.4 * Math.sin(47 * lat + 3.3 * t * motion - 9 * lon));
      const theta = lon + spin + wiggle;
      const cl = Math.cos(lat);
      const x = r * cl * Math.sin(theta);
      const y = -r * Math.sin(lat); // norte em cima
      const z = r * cl * Math.cos(theta);
      // inclinação para a frente: vemos a esfera levemente de cima, com volume em vez de um disco chato
      out[k++] = x;
      out[k++] = y * cosTilt - z * sinTilt;
      out[k++] = (y * sinTilt + z * cosTilt) / ORB_RADIUS; // profundidade normalizada
    }
  }
  return out;
}

/**
 * Ajusta a qualidade ao computador: `ms` é quanto custou o último quadro. Devolve o novo passo de meridianos
 * (1 = todos; 2 e 4 = metade e um quarto). Só muda devagar, para não ficar piscando entre qualidades.
 */
export function adaptStride(stride: number, avgMs: number): number {
  if (avgMs > 22 && stride < 4) return stride * 2;
  if (avgMs < 7 && stride > 1) return stride / 2;
  return stride;
}

/** Faixa de profundidade (0 = fundo, BUCKETS-1 = frente) de um z em [-1, 1]. */
export function depthBucket(z: number): number {
  const b = Math.floor(((Math.max(-1, Math.min(1, z)) + 1) / 2) * BUCKETS);
  return Math.min(BUCKETS - 1, b);
}

/** Opacidade de cada faixa de profundidade, do fundo à frente. */
export const BUCKET_ALPHA = [0.05, 0.1, 0.18, 0.3, 0.46];

/** Mistura `hex` com branco (0 a 1): o meio da esfera é mais claro, como na referência. */
export function lighten(hex: string, amount: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  const mix = (c: number) => Math.round(c + (255 - c) * amount);
  return `#${[(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => mix(c).toString(16).padStart(2, "0")).join("")}`;
}
