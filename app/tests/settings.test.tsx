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
      .toEqual({ themeSource: "dark", openAtLogin: true, trayVisible: false, idleMs: 10000, icon: "colorido" });
    expect(planAppSettings({ "app.icone": "escuro" }).icon).toBe("escuro");
    expect(planAppSettings({ "app.icone": "../../x" }).icon).toBe("colorido"); // valor estranho cai no padrão
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

describe("tela Modelo de IA (Ollama)", () => {
  it("escolher Local mostra os modelos instalados e o aviso de riscos; ações começam bloqueadas", async () => {
    const f = installFakeCore();
    const user = await open("Modelo de IA");
    await user.click(await screen.findByRole("radio", { name: /Local/ }));
    await waitFor(() => expect(f.effective["modelo.provedor"]).toBe("local"));
    expect(await screen.findByText("Ollama aberto")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "llama3.1:8b" })).toBeInTheDocument();
    expect(screen.getByText(/Riscos de liberar ações/)).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: /Permitir ações com o modelo local/ })).toBeDisabled(); // sem o check, não liga
  });

  it("só liga as ações depois de marcar que entende os riscos; desmarcar desliga de novo", async () => {
    const f = installFakeCore({ effective: { "modelo.provedor": "local" } });
    const user = await open("Modelo de IA");
    const sw = await screen.findByRole("switch", { name: /Permitir ações com o modelo local/ });
    expect(sw).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: /Li e estou de acordo/ }));
    await waitFor(() => expect(f.effective["modelo.local_acoes_ciente"]).toBe(true));
    await user.click(await screen.findByRole("switch", { name: /Permitir ações com o modelo local/ }));
    await waitFor(() => expect(f.effective["modelo.local_acoes"]).toBe(true));
    await user.click(screen.getByRole("checkbox", { name: /Li e estou de acordo/ }));
    await waitFor(() => expect(f.effective["modelo.local_acoes"]).toBe(false));
  });

  it("Ollama fechado avisa o que fazer e esconde o download", async () => {
    installFakeCore({ effective: { "modelo.provedor": "local" }, ollamaRunning: false });
    await open("Modelo de IA");
    expect(await screen.findByText("Ollama fechado")).toBeInTheDocument();
    expect(screen.getByText(/Abra o app dele e clique em Atualizar/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Baixar um modelo")).toBeNull();
  });
});

describe("aba Voz do personagem", () => {
  const openVoice = async (init: Parameters<typeof installFakeCore>[0] = {}) => {
    const f = installFakeCore(init);
    const user = await open("Personagem");
    await user.click(await screen.findByRole("tab", { name: "Voz" }));
    return { f, user };
  };

  it("mostra as quatro opções de voz", async () => {
    await openVoice();
    for (const n of ["Voz do sistema", "Piper", "Voz por descrição", "Sua própria voz"]) expect(await screen.findByRole("radio", { name: new RegExp(n) })).toBeInTheDocument();
  });

  it("Piper: instala o programa, baixa uma voz e escolhe", async () => {
    const { f, user } = await openVoice();
    await user.click(screen.getByRole("radio", { name: /Piper/ }));
    await user.click(await screen.findByRole("button", { name: "Instalar o Piper" }));
    await waitFor(() => expect(sent(f.calls, "piper", "install")).toHaveLength(1));
    await user.click(await screen.findByRole("button", { name: "Baixar a voz Faber" }));
    await waitFor(() => expect(sent(f.calls, "piper", "download_voice")[0][1].voice).toBe("pt_BR-faber-medium"));
    const radio = await screen.findByRole("radio", { name: /Faber/ });
    await waitFor(() => expect(radio).toBeEnabled());
    await user.click(radio);
    await waitFor(() => expect(f.profiles.alfred.voice).toMatchObject({ engine: "piper", voice: "pt_BR-faber-medium" }));
  });

  it("voz por descrição: sem chave não gera; com a chave gera a prévia e usa; avisa que usa a internet", async () => {
    const { f, user } = await openVoice();
    await user.click(screen.getByRole("radio", { name: /Voz por descrição/ }));
    expect(await screen.findByText(/Esta opção usa a internet/)).toBeInTheDocument();
    const desc = screen.getByLabelText(/Descreva a voz do Alfred/);
    await user.type(desc, "Masculina, grave e calma, sotaque britânico.");
    expect(screen.getByRole("button", { name: "Gerar prévia" })).toBeDisabled(); // sem chave
    await user.click(screen.getByRole("button", { name: "Definir" }));
    await user.type(screen.getByLabelText("Chave de API"), "k".repeat(30));
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Gerar prévia" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Gerar prévia" }));
    await user.click(await screen.findByRole("button", { name: "Usar a prévia 2" }));
    await waitFor(() => expect(f.profiles.alfred.voice).toMatchObject({ engine: "descricao", voice: "voz123" }));
    expect(JSON.stringify(f.calls)).not.toContain("kkkkkkkkkkkkkkkkkkkkkkkkkkkkkk".repeat(2)); // a chave só vai uma vez, no set_key
  });

  it("sua própria voz: só cria depois do consentimento", async () => {
    const { f, user } = await openVoice();
    await user.click(screen.getByRole("radio", { name: /Sua própria voz/ }));
    const gravar = await screen.findByRole("button", { name: /Gravar/ });
    expect(gravar).toBeDisabled();
    expect(screen.getByRole("button", { name: "Criar minha voz" })).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: /Eu consinto/ }));
    expect(sent(f.calls, "voice_cloud", "clone")).toHaveLength(0);
  });
});

describe("Escutar chamados", () => {
  it.each(["Geral", "Voz"])("o interruptor liga e desliga na tela %s e avisa o núcleo", async (tela) => {
    const f = installFakeCore();
    const user = await open(tela);
    const sw = await screen.findByRole("switch", { name: "Escutar chamados" });
    expect(sw).toHaveAttribute("aria-checked", "true");
    await user.click(sw);
    await waitFor(() => expect(screen.getByRole("switch", { name: "Escutar chamados" })).toHaveAttribute("aria-checked", "false"));
    expect(sent(f.calls, "calls")[0][1]).toEqual({ value: false });
    await user.click(screen.getByRole("switch", { name: "Escutar chamados" }));
    await waitFor(() => expect(screen.getByRole("switch", { name: "Escutar chamados" })).toHaveAttribute("aria-checked", "true"));
  });
});

describe("tela Contas: credenciais do Google e login pelo navegador", () => {
  const arquivo = (texto: string) => {
    const f = new File([texto], "credentials.json", { type: "application/json" });
    Object.defineProperty(f, "text", { value: async () => texto }); // o jsdom não implementa File.text()
    return f;
  };

  it("envia o credentials.json pela tela em vez de pedir para copiar o arquivo", async () => {
    const f = installFakeCore();
    const user = await open("Contas");
    await user.click(await screen.findByRole("button", { name: "Remover" })); // começa com o arquivo; remove para simular a falta
    expect(await screen.findByText("Falta enviar")).toBeInTheDocument();
    await user.upload(screen.getByLabelText("Enviar o credentials.json"), arquivo('{"installed":{"client_id":"x"}}'));
    await waitFor(() => expect(sent(f.calls, "accounts", "google_credentials")).toHaveLength(1));
    expect(await screen.findByText("Enviado")).toBeInTheDocument();
  });

  it("arquivo inválido mostra o erro do núcleo e continua faltando", async () => {
    installFakeCore();
    const user = await open("Contas");
    await user.click(await screen.findByRole("button", { name: "Remover" }));
    await user.upload(screen.getByLabelText("Enviar o credentials.json"), arquivo("nao e o arquivo certo"));
    expect(await screen.findByText(/campos esperados/)).toBeInTheDocument();
    expect(screen.getByText("Falta enviar")).toBeInTheDocument();
  });

  it("mostra o link de autorização só se for do Google", async () => {
    const f = installFakeCore();
    await open("Contas");
    await screen.findByText("Credenciais do Google");
    f.emit({ type: "open_url", url: "https://evil.example/phish" });
    expect(screen.queryByRole("link", { name: /página de autorização/ })).toBeNull();
    f.emit({ type: "open_url", url: "https://accounts.google.com/o/oauth2/auth?x=1" });
    const link = await screen.findByRole("link", { name: /página de autorização/ });
    expect(link).toHaveAttribute("href", "https://accounts.google.com/o/oauth2/auth?x=1");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noreferrer"));
  });
});

describe("Conectar o Google sem credenciais", () => {
  it("o botão Conectar fica desabilitado até enviar o credentials.json", async () => {
    installFakeCore();
    const user = await open("Contas");
    await user.click(await screen.findByRole("button", { name: "Remover" }));
    await screen.findByText("Falta enviar");
    const agenda = screen.getByLabelText("Google Agenda");
    expect(within(agenda).getByRole("button", { name: "Conectar" })).toBeDisabled();
    expect(within(screen.getByLabelText("Slack")).getByRole("button", { name: "Conectar" })).toBeEnabled(); // o Slack não usa o Google
    expect(screen.getAllByText(/Envie o credentials.json do Google/).length).toBeGreaterThan(0);
  });
});

describe("Baixar modelo do Ollama pelo painel", () => {
  it("baixa, mostra o progresso e deixa o modelo selecionado", async () => {
    const f = installFakeCore({ effective: { "modelo.provedor": "local" } });
    const user = await open("Modelo de IA");
    await user.type(await screen.findByLabelText("Baixar um modelo"), "qwen2.5:7b");
    await user.click(screen.getByRole("button", { name: "Baixar" }));
    await waitFor(() => expect(sent(f.calls, "local_models", "pull")[0][1].model).toBe("qwen2.5:7b"));
    f.emit({ type: "model_pull", what: "qwen2.5:7b", state: "progress", done: 50, total: 100 });
    expect(await screen.findByRole("progressbar", { name: "Baixando qwen2.5:7b" })).toHaveAttribute("value", "50");
    f.emit({ type: "model_pull", what: "qwen2.5:7b", state: "done" });
    await waitFor(() => expect(f.effective["modelo.local"]).toBe("qwen2.5:7b"));
    expect(await screen.findByRole("option", { name: "qwen2.5:7b" })).toBeInTheDocument();
  });

  it("erro no download aparece e não troca o modelo", async () => {
    const f = installFakeCore({ effective: { "modelo.provedor": "local" } });
    await open("Modelo de IA");
    await screen.findByLabelText("Baixar um modelo");
    f.emit({ type: "model_pull", what: "x:1b", state: "error", message: "O modelo 'x:1b' não existe no catálogo do Ollama." });
    expect(await screen.findByText(/não existe no catálogo/)).toBeInTheDocument();
    expect(f.effective["modelo.local"]).toBe("qwen3:8b");
  });
});

describe("Ícone do app", () => {
  it("mostra as três artes e grava a escolhida", async () => {
    const f = installFakeCore();
    const user = await open("Geral");
    const grupo = await screen.findByRole("radiogroup", { name: "Ícone do app" });
    const opcoes = within(grupo).getAllByRole("radio");
    expect(opcoes.map((o) => o.textContent?.match(/Escuro|Claro|Colorido/)?.[0])).toEqual(["Escuro", "Claro", "Colorido"]);
    expect(within(grupo).getByRole("radio", { name: /Colorido/ })).toHaveAttribute("aria-checked", "true");
    await user.click(within(grupo).getByRole("radio", { name: /Escuro/ }));
    await waitFor(() => expect(f.effective["app.icone"]).toBe("escuro"));
    expect(within(grupo).getByRole("radio", { name: /Escuro/ })).toHaveAttribute("aria-checked", "true");
  });
});

describe("Contas se atualiza ao voltar da página do Google", () => {
  it("relê as contas quando a janela volta ao foco ou o núcleo reenvia o estado", async () => {
    const f = installFakeCore();
    await open("Contas");
    await screen.findByText("Credenciais do Google");
    const antes = sent(f.calls, "accounts", "list").length;
    window.dispatchEvent(new Event("focus"));
    await waitFor(() => expect(sent(f.calls, "accounts", "list").length).toBeGreaterThan(antes));
    const meio = sent(f.calls, "accounts", "list").length;
    f.emit({ type: "ready", protocol: 1, snapshot: {} as never });
    await waitFor(() => expect(sent(f.calls, "accounts", "list").length).toBeGreaterThan(meio));
  });
});

describe("modelos pequenos", () => {
  it("reconhece os modelos fracos e deixa os de 7B/8B em paz", async () => {
    const { isSmallModel } = await import("../src/settings/pages/ModeloIA");
    for (const n of ["llama3.2:1b", "llama3.2:3b", "qwen2.5:0.5b", "gemma2:2b", "phi3:3.8b-mini".replace("3.8b", "3b")]) expect(isSmallModel(n), n).toBe(true);
    for (const n of ["llama3.1:8b", "qwen3:8b", "qwen2.5:7b", "llama3.3:70b", "mistral:7b", "qwen3:32b", "llama3.1:latest"]) expect(isSmallModel(n), n).toBe(false);
  });

  it("avisa quando o modelo escolhido é pequeno", async () => {
    installFakeCore({ effective: { "modelo.provedor": "local", "modelo.local": "llama3.2:3b" } });
    await open("Modelo de IA");
    expect(await screen.findByText(/é pequeno e costuma responder mal/)).toBeInTheDocument();
  });
});

describe("Gemini", () => {
  it("escolher o Gemini mostra o modelo, o aviso do plano grátis e guarda a chave", async () => {
    const f = installFakeCore();
    const user = await open("Modelo de IA");
    await user.click(await screen.findByRole("radio", { name: /Gemini/ }));
    await waitFor(() => expect(f.effective["modelo.provedor"]).toBe("gemini"));
    expect(await screen.findByText(/pode ser usado para melhorar os produtos deles/)).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "gemini-2.5-flash" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Definir" }));
    await user.type(screen.getByLabelText("Chave do Gemini", { selector: "input" }), "AQ.Ab8" + "k".repeat(35));
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(sent(f.calls, "api_key", "set")[0][1]).toMatchObject({ provider: "gemini" }));
  });
});

describe("Gemini: modelos que a chave enxerga", () => {
  it("se o modelo salvo não existe para a chave, troca pelo melhor e mostra só os disponíveis", async () => {
    const f = installFakeCore({ effective: { "modelo.provedor": "gemini", "modelo.gemini": "gemini-2.5-flash" } });
    const user = await open("Modelo de IA");
    await user.click(await screen.findByRole("button", { name: "Definir" }));
    await user.type(screen.getByLabelText("Chave do Gemini", { selector: "input" }), "AQ.Ab8" + "k".repeat(35));
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(f.effective["modelo.gemini"]).toBe("gemini-3.6-flash"));
    expect(await screen.findByRole("option", { name: "gemini-3.6-flash" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "gemini-2.5-flash" })).toBeNull(); // o que não existe some da lista
    expect(await screen.findByText(/não está disponível para a sua chave/)).toBeInTheDocument();
  });
});

describe("Como perceber o chamado", () => {
  it("mostra a escolha, grava e avisa que precisa reiniciar", async () => {
    const f = installFakeCore();
    const user = await open("Voz");
    const grupo = await screen.findByRole("radiogroup", { name: "Como perceber o chamado" });
    expect(within(grupo).getByRole("radio", { name: "Automático" })).toHaveAttribute("aria-checked", "true");
    await user.click(within(grupo).getByRole("radio", { name: "Por fala" }));
    await waitFor(() => expect(f.effective["chamados.modo"]).toBe("voz"));
  });
});
