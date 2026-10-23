import { initialModel, micLabel, modelLabel, reduce, STATE_LABEL } from "../src/shared/model";
import type { CoreEvent, Snapshot } from "../src/shared/protocol";

const snapshot: Snapshot = {
  status: "ready", message: "", state: "idle", mic: "passive",
  character: { id: "alfred", name: "Alfred", call: "ei Alfred", ring: { dark: ["#FF6A3D", "#FF5C9E", "#3D8BFF"], light: ["#F2541F", "#E8307F", "#1F6BF2"] } },
  default_character: "alfred",
  characters: [],
  model: { provider: "claude", name: "claude-sonnet-5-5", where: "Nuvem" },
  calls: { enabled: true, until: null }, muted: false,
};
const run = (events: CoreEvent[], m = initialModel) => events.reduce(reduce, m);

describe("modelo da interface", () => {
  it("o ready carrega o snapshot", () => {
    const m = run([{ type: "ready", protocol: 1, snapshot }]);
    expect(m.status).toBe("ready");
    expect(modelLabel(m.character, m.model)).toBe("Alfred · Claude · Nuvem");
  });

  it("legenda do assistente chega em pedaços e fecha; nova fala do usuário começa uma troca nova", () => {
    let m = run([
      { type: "caption", role: "user", text: "O que tenho hoje?", final: true },
      { type: "caption", role: "assistant", text: "Bom dia. ", final: false },
      { type: "caption", role: "assistant", text: "Duas reuniões.", final: false },
    ]);
    expect(m.user.text).toBe("O que tenho hoje?");
    expect(m.assistant).toEqual({ text: "Bom dia. Duas reuniões.", final: false });
    m = run([{ type: "caption", role: "assistant", text: "", final: true }], m);
    expect(m.assistant).toEqual({ text: "Bom dia. Duas reuniões.", final: true }); // fechar sem texto mantém o que chegou
    m = run([{ type: "caption", role: "assistant", text: "Outra resposta", final: false }], m);
    expect(m.assistant.text).toBe("Outra resposta"); // depois de fechada, a próxima começa do zero
    m = run([{ type: "caption", role: "user", text: "Valeu", final: true }], m);
    expect(m.assistant.text).toBe("");
  });

  it("estado, microfone, personagem e chamados", () => {
    const m = run([
      { type: "state", state: "listening", mic: "recording" },
      { type: "character", id: "donna", name: "Donna", call: "ei Donna", ring: { dark: ["#1", "#2", "#3"], light: [] } },
      { type: "calls", enabled: false, until: 123 },
      { type: "model", provider: "local", name: "x", where: "Local" },
    ]);
    expect(m.state).toBe("listening");
    expect(m.character?.name).toBe("Donna");
    expect(m.calls).toEqual({ enabled: false, until: 123 });
    expect(modelLabel(m.character, m.model)).toBe("Donna · Local · Local");
  });

  it("confirmação pendente: aparece e some só com o id certo", () => {
    let m = run([{ type: "confirm", id: "a", text: "Abrir o regedit?" }]);
    expect(m.confirm).toEqual({ id: "a", text: "Abrir o regedit?" });
    m = run([{ type: "confirm_done", id: "outra" }], m);
    expect(m.confirm).not.toBeNull();
    m = run([{ type: "confirm_done", id: "a" }], m);
    expect(m.confirm).toBeNull();
  });

  it("nível de áudio não mexe no modelo (vai por fora do React)", () => {
    expect(run([{ type: "level", values: [0.1, 0.2, 0.3] }])).toBe(initialModel);
  });

  it("rótulos em português", () => {
    expect(micLabel("passive")).toEqual({ text: "Microfone ativo", tone: "ok" });
    expect(micLabel("muted")).toEqual({ text: "Microfone silenciado", tone: "off" });
    expect(STATE_LABEL.listening).toBe("Ouvindo…");
    expect(STATE_LABEL.thinking).toBe("Pensando…");
    expect(STATE_LABEL.speaking).toBe("Falando…");
  });
});
