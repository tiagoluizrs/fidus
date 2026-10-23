import { LAYERS, LAYER_ALPHA, clamp01, effectiveLevel, ringLayers, ringStops, smoothLevel } from "../src/ring/ringMath";

const radius = (p: { x: number; y: number }) => Math.hypot(p.x, p.y);
const meanRadius = (pts: { x: number; y: number }[]) => pts.reduce((a, p) => a + radius(p), 0) / pts.length;
const spread = (pts: { x: number; y: number }[]) => Math.max(...pts.map(radius)) - Math.min(...pts.map(radius));

describe("geometria do anel", () => {
  it("tem 4 camadas fechadas, dentro do canvas e com opacidades decrescentes", () => {
    const layers = ringLayers(1.2, 0.5, "listening");
    expect(layers).toHaveLength(LAYERS);
    for (const pts of layers) {
      expect(pts.length).toBeGreaterThan(60);
      for (const p of pts) expect(radius(p)).toBeLessThan(1);
    }
    expect(LAYER_ALPHA).toEqual([1, 0.76, 0.52, 0.4]);
  });

  it("é determinística: mesmo tempo, nível e estado dão os mesmos pontos", () => {
    expect(ringLayers(3.3, 0.4, "speaking")).toEqual(ringLayers(3.3, 0.4, "speaking"));
    expect(ringLayers(3.3, 0.4, "speaking")).not.toEqual(ringLayers(3.4, 0.4, "speaking"));
  });

  it("deforma mais quanto maior o nível de áudio", () => {
    const calm = spread(ringLayers(2, 0, "listening")[0]);
    const loud = spread(ringLayers(2, 1, "listening")[0]);
    expect(loud).toBeGreaterThan(calm * 3);
  });

  it("camadas internas ficam mais perto do centro", () => {
    const l = ringLayers(0.5, 0.3, "listening");
    expect(meanRadius(l[0])).toBeGreaterThan(meanRadius(l[3]));
  });

  it("silenciado quase não se mexe e movimento reduzido atenua", () => {
    expect(spread(ringLayers(2, 1, "muted")[0])).toBeLessThan(spread(ringLayers(2, 1, "listening")[0]) / 3);
    expect(spread(ringLayers(2, 1, "listening", true)[0])).toBeLessThan(spread(ringLayers(2, 1, "listening", false)[0]));
  });

  it("pensando gira a onda em vez de depender do microfone", () => {
    const a = ringLayers(1, 0, "thinking");
    const b = ringLayers(2, 0, "thinking");
    expect(a).not.toEqual(b);
    expect(effectiveLevel("thinking", 0.9, 0)).toBeCloseTo(0.22, 1); // ignora o nível do microfone
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
