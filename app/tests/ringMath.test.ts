import { clamp01, effectiveLevel, ringStops, smoothLevel } from "../src/ring/ringMath";
import { BUCKETS, BUCKET_ALPHA, MERIDIANS, adaptStride, ORB_RADIUS, STEPS, depthBucket, lighten, orbPoints, spinSpeed } from "../src/ring/orbMath";

const xy = (p: Float32Array) => Array.from({ length: p.length / 3 }, (_, i) => Math.hypot(p[i * 3], p[i * 3 + 1]));
// deformação = variação do raio em 3D (a sombra x/y de uma esfera já varia naturalmente)
const spread = (p: Float32Array) => {
  const r = Array.from({ length: p.length / 3 }, (_, i) => Math.hypot(p[i * 3], p[i * 3 + 1], p[i * 3 + 2] * ORB_RADIUS));
  return Math.max(...r) - Math.min(...r);
};

describe("esfera de linhas", () => {
  it("tem meridianos x passos pontos, todos dentro do canvas, com profundidade em [-1, 1]", () => {
    const p = orbPoints(1.2, 0.5, "listening");
    expect(p).toHaveLength(MERIDIANS * STEPS * 3);
    for (const r of xy(p)) expect(r).toBeLessThan(1);
    for (let i = 2; i < p.length; i += 3) expect(Math.abs(p[i])).toBeLessThanOrEqual(1.3);
    expect(Number.isFinite(p.reduce((a, b) => a + b, 0))).toBe(true);
  });

  it("é determinística e muda com o tempo", () => {
    expect(orbPoints(3.3, 0.4, "speaking")).toEqual(orbPoints(3.3, 0.4, "speaking"));
    expect(orbPoints(3.3, 0.4, "speaking")).not.toEqual(orbPoints(3.4, 0.4, "speaking"));
  });

  it("deforma mais quanto maior o nível de áudio", () => {
    expect(spread(orbPoints(2, 1, "listening"))).toBeGreaterThan(spread(orbPoints(2, 0, "listening")) * 1.4);
  });

  it("cabe na esfera quando calmo e o norte fica em cima", () => {
    const p = orbPoints(0.5, 0, "idle");
    expect(Math.max(...xy(p))).toBeLessThan(ORB_RADIUS * 1.12);
    const ys = Array.from({ length: STEPS }, (_, s) => p[s * 3 + 1]); // primeiro meridiano, do polo sul ao norte
    expect(ys[0]).toBeGreaterThan(ys[STEPS - 1]); // y cresce para baixo (como no Canvas): o norte fica em cima
  });

  it("silenciado quase não se mexe e movimento reduzido atenua", () => {
    expect(spread(orbPoints(2, 1, "muted"))).toBeLessThan(spread(orbPoints(2, 1, "listening")));
    expect(spread(orbPoints(2, 1, "listening", true))).toBeLessThan(spread(orbPoints(2, 1, "listening", false)));
    expect(spinSpeed("muted", false)).toBeLessThan(spinSpeed("idle", false));
    expect(spinSpeed("thinking", false)).toBeGreaterThan(spinSpeed("listening", false));
    expect(spinSpeed("thinking", true)).toBeLessThan(spinSpeed("thinking", false));
  });

  it("pensando gira a esfera sem depender do microfone", () => {
    expect(orbPoints(1, 0, "thinking")).not.toEqual(orbPoints(2, 0, "thinking"));
    expect(effectiveLevel("thinking", 0.9, 0)).toBeCloseTo(0.22, 1);
  });

  it("faixas de profundidade: a frente é mais forte que o fundo", () => {
    expect(depthBucket(-1)).toBe(0);
    expect(depthBucket(1)).toBe(BUCKETS - 1);
    expect(depthBucket(5)).toBe(BUCKETS - 1);
    expect(BUCKET_ALPHA).toHaveLength(BUCKETS);
    expect([...BUCKET_ALPHA].sort((a, b) => a - b)).toEqual(BUCKET_ALPHA);
  });

  it("qualidade adaptativa: menos meridianos deixam o desenho mais leve, e o ajuste é gradual", () => {
    expect(orbPoints(1, 0.3, "listening", false, 2)).toHaveLength((MERIDIANS / 2) * STEPS * 3);
    expect(orbPoints(1, 0.3, "listening", false, 4)).toHaveLength((MERIDIANS / 4) * STEPS * 3);
    expect(adaptStride(1, 40)).toBe(2); // quadro lento: baixa a qualidade
    expect(adaptStride(2, 40)).toBe(4);
    expect(adaptStride(4, 90)).toBe(4); // já no mínimo
    expect(adaptStride(4, 3)).toBe(2); // sobrou folga: sobe de volta
    expect(adaptStride(2, 12)).toBe(2); // no meio: não mexe (sem piscar)
    expect(adaptStride(1, 3)).toBe(1);
  });

  it("clareia uma cor sem estragar a que não entende", () => {
    expect(lighten("#000000", 0.5)).toBe("#808080");
    expect(lighten("#FF0000", 1)).toBe("#ffffff");
    expect(lighten("rgb(1,2,3)", 0.5)).toBe("rgb(1,2,3)");
  });
});

describe("nível efetivo", () => {
  it("ouvindo segue o microfone; falando usa um envelope; silenciado é zero", () => {
    expect(effectiveLevel("listening", 0.7, 5)).toBe(0.7);
    expect(effectiveLevel("listening", 7, 5)).toBe(1);
    expect(effectiveLevel("muted", 1, 5)).toBe(0);
    const speaking = Array.from({ length: 50 }, (_, i) => effectiveLevel("speaking", 0, i / 10));
    expect(Math.max(...speaking)).toBeGreaterThan(Math.min(...speaking) + 0.2);
    expect(speaking.every((v) => v >= 0 && v <= 1)).toBe(true);
    expect(effectiveLevel("idle", 1, 3)).toBeLessThan(0.1); // parado: só respira
  });

  it("suaviza: sobe rápido e desce devagar", () => {
    const up = smoothLevel(0, 1, 0.033);
    const down = 1 - smoothLevel(1, 0, 0.033);
    expect(up).toBeGreaterThan(down * 2);
    expect(clamp01(-1)).toBe(0);
    expect(clamp01(2)).toBe(1);
  });

  it("cores do anel: do personagem, padrão se faltar e cinza quando silenciado", () => {
    expect(ringStops(["#1", "#2", "#3"], "dark", "listening")).toEqual(["#1", "#2", "#3"]);
    expect(ringStops([], "dark", "idle")).toHaveLength(3);
    expect(new Set(ringStops(["#1", "#2", "#3"], "light", "muted")).size).toBe(1);
  });
});
