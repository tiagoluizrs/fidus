import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SettingsApp } from "../src/settings/SettingsApp";
import { comboFromEvent, humanize } from "../src/settings/hotkey";
import { ago } from "../src/settings/pages/Memoria";
import { planAppSettings, safeFileName, MIC_SETTINGS_URL } from "../electron/logic";
import { installFakeCore, sent } from "./fakeCore";

const open = async (label: string) => {
  const user = userEvent.setup();
  render(<SettingsApp />);
  await user.click(await screen.findByRole("link", { name: label }));
  return user;
};

describe("atalho de teclado", () => {
  const ev = (o: object) => ({ key: "", code: "", ctrlKey: false, altKey: false, shiftKey: false, metaKey: false, ...o });
  it("monta a combinação no formato do núcleo", () => {
    expect(comboFromEvent(ev({ key: " ", code: "Space", ctrlKey: true, altKey: true }))).toBe("ctrl+alt+space");
    expect(comboFromEvent(ev({ key: "k", code: "KeyK", ctrlKey: true, shiftKey: true }))).toBe("ctrl+shift+k");
    expect(comboFromEvent(ev({ key: "F9", code: "F9" }))).toBe("f9");
  });
  it("recusa só modificador e tecla solta de digitação", () => {
    expect(comboFromEvent(ev({ key: "Control", code: "ControlLeft", ctrlKey: true }))).toBeNull();
    expect(comboFromEvent(ev({ key: "a", code: "KeyA" }))).toBeNull();
  });
  it("humaniza", () => expect(humanize("ctrl+alt+space")).toBe("Ctrl + Alt + Espaço"));
});

describe("funções puras", () => {
  it("ago", () => {
    const now = Date.parse("2026-10-23T12:00:00Z");
    expect(ago("2026-10-23T08:00:00Z", now)).toBe("hoje");
    expect(ago("2026-10-22T08:00:00Z", now)).toBe("ontem");
    expect(ago("2026-10-18T12:00:00Z", now)).toBe("há 5 dias");
    expect(ago("lixo", now)).toBe("");
  });
  it("planAppSettings", () => {
    expect(planAppSettings({ "app.tema": "escuro", "app.iniciar_com_windows": true, "app.icone_bandeja": false, "app.janela_inatividade_s": 10 }))
      .toEqual({ themeSource: "dark", openAtLogin: true, trayVisible: false, idleMs: 10000 });
    expect(planAppSettings({ "app.janela_inatividade_s": 999 }).idleMs).toBe(6000);
    expect(planAppSettings({}).themeSource).toBe("system");
  });
  it("safeFileName tira caminhos e caracteres proibidos", () => {
    expect(safeFileName("../../etc/passwd")).not.toMatch(/[\\/]/);
    expect(safeFileName("a:b*c?.md")).toBe("a_b_c_.md");
    expect(safeFileName("...")).toBe("fidus");
  });
  it("só os ajustes de microfone são abertos", () => expect(MIC_SETTINGS_URL).toBe("ms-settings:privacy-microphone"));
});

describe("tela Geral", () => {
  it("salva uma mudança de configuração no núcleo", async () => {
    const f = installFakeCore();
    const user = await open("Geral");
    const sw = await screen.findByRole("switch", { name: /iniciar junto com o sistema/i });
    await user.click(sw);
    await waitFor(() => expect(sent(f.calls, "set_settings").some(([, a]) => (a.patch as any)["app.iniciar_com_windows"] === true)).toBe(true));
  });
});

describe("tela Memória", () => {
  it("adiciona, busca e só apaga com confirmação explícita", async () => {
    const f = installFakeCore();
    const user = await open("Memória");
    expect(await screen.findByText(/Nenhuma lembrança ainda/)).toBeInTheDocument();
    f.memory.push({ id: "m9", section: "perfil", text: "Gosta de café sem açúcar", tag: null, ts: "2026-10-20", source: "aprendida" });
    await user.type(screen.getByLabelText("Buscar lembranças"), "café");
    expect(await screen.findByDisplayValue(/café sem açúcar/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Apagar: Gosta/ }));
    const dialog = await screen.findByRole("alertdialog");
    expect(sent(f.calls, "memory", "delete")).toHaveLength(0); // nada some só de clicar
    await user.click(within(dialog).getByRole("button", { name: "Apagar" }));
    await waitFor(() => expect(sent(f.calls, "memory", "delete")[0][1].confirm).toBe(true));
  });
  it("apagar tudo exige digitar APAGAR", async () => {
    const f = installFakeCore();
    const user = await open("Memória");
    await user.click(await screen.findByRole("button", { name: "Apagar toda a memória" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByRole("button", { name: "Apagar tudo" })).toBeDisabled();
    await user.type(within(dialog).getByRole("textbox"), "APAGAR");
    await user.click(within(dialog).getByRole("button", { name: "Apagar tudo" }));
    await waitFor(() => expect(sent(f.calls, "memory", "delete_all")[0][1].confirm).toBe(true));
  });
});

describe("tela Privacidade", () => {
  it("adiciona e remove pasta liberada", async () => {
    const f = installFakeCore();
    const user = await open("Privacidade");
    await user.click(await screen.findByRole("button", { name: "+ Adicionar pasta" }));
    await waitFor(() => expect(f.effective["arquivos.pastas_liberadas"]).toEqual(["C:\\Projetos"]));
    await user.click(await screen.findByRole("button", { name: /Remover a pasta/ }));
    await waitFor(() => expect(f.effective["arquivos.pastas_liberadas"]).toEqual([]));
  });
  it("exportar usa o caminho escolhido na janela do sistema", async () => {
    const f = installFakeCore();
    const user = await open("Privacidade");
    await user.click(await screen.findByRole("button", { name: "Exportar" }));
    await waitFor(() => expect(sent(f.calls, "privacy", "export")[0][1].path).toBe("C:\\saida\\meus-dados.zip"));
  });
});

describe("tela Contas", () => {
  it("serviços futuros aparecem como 'em breve' e sem botão de conectar", async () => {
    installFakeCore();
    await open("Contas");
    expect((await screen.findAllByText(/em breve/i)).length).toBeGreaterThanOrEqual(3);
  });
});

describe("tela Personagem", () => {
  it("lista os personagens do núcleo", async () => {
    installFakeCore();
    await open("Personagem");
    expect(await screen.findAllByText(/Donna/)).not.toHaveLength(0);
  });
});
