import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RingApp } from "../src/ring/RingApp";
import type { CoreEvent, FidusApi, Snapshot } from "../src/shared/protocol";

const snapshot: Snapshot = {
  status: "ready", message: "", state: "idle", mic: "passive",
  character: { id: "donna", name: "Donna", call: "ei Donna", ring: { dark: ["#E5484D", "#FF5C9E", "#B38CFF"], light: ["#C93A3F", "#E8307F", "#8F5CF0"] } },
  default_character: "alfred", characters: [],
  model: { provider: "claude", name: "claude-sonnet-5-5", where: "Nuvem" }, calls: { enabled: true, until: null }, muted: false,
};

let emit: (e: CoreEvent) => void;
let themeCb: (t: "light" | "dark") => void;
const api = {
  command: vi.fn(async () => ({ type: "reply" as const, id: "1", ok: true })),
  closeWindow: vi.fn(),
  getSnapshot: vi.fn(async () => snapshot as Snapshot | null),
  getTheme: vi.fn(async () => "dark" as "light" | "dark"),
} satisfies Partial<FidusApi>;

beforeEach(() => {
  vi.clearAllMocks();
  // o canvas do jsdom não desenha: o anel é testado em ringMath.test.ts
  HTMLCanvasElement.prototype.getContext = (() => null) as never;
  window.fidus = {
    ...api,
    onEvent: (cb) => {
      emit = cb;
      return () => {};
    },
    onThemeChange: (cb) => {
      themeCb = cb;
      return () => {};
    },
  } as FidusApi;
});

const mount = async () => {
  render(<RingApp />);
  await screen.findByText(/Donna · Claude · Nuvem/);
};
const send = (e: CoreEvent) => act(() => emit(e));

describe("tela do anel", () => {
  it("mostra marca, microfone ativo, personagem · modelo · nuvem e a dica do Esc", async () => {
    await mount();
    expect(screen.getByText("Fidus")).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Microfone ativo" })).toBeInTheDocument();
    expect(screen.getByText("Donna · Claude · Nuvem")).toBeInTheDocument();
    expect(screen.getByText("para fechar")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Anel de luz reagindo à voz" })).toBeInTheDocument();
  });

  it("rótulo do estado e legendas acompanham os eventos", async () => {
    await mount();
    await send({ type: "state", state: "listening", mic: "recording" });
    expect(screen.getByText("Ouvindo…")).toBeInTheDocument();
    await send({ type: "caption", role: "user", text: "O que tenho na agenda hoje?", final: true });
    await send({ type: "state", state: "thinking", mic: "paused" });
    expect(screen.getByText("Pensando…")).toBeInTheDocument();
    await send({ type: "caption", role: "assistant", text: "Bom dia. ", final: false });
    await send({ type: "caption", role: "assistant", text: "Duas reuniões.", final: false });
    await send({ type: "state", state: "speaking", mic: "paused" });
    expect(screen.getByText("Falando…")).toBeInTheDocument();
    expect(screen.getByText("O que tenho na agenda hoje?")).toHaveClass("user");
    expect(screen.getByText("Bom dia. Duas reuniões.")).toHaveClass("assistant");
  });

  it("microfone silenciado vira aviso e muda a cor do indicador", async () => {
    await mount();
    await send({ type: "state", state: "muted", mic: "muted" });
    expect(screen.getAllByText("Microfone silenciado").length).toBeGreaterThan(0);
    expect(screen.getByRole("status", { name: "Microfone silenciado" }).querySelector(".dot")).toHaveClass("off");
  });

  it("troca o nome do personagem quando outro é chamado", async () => {
    await mount();
    await send({ type: "character", id: "jarbis", name: "Jarbis", call: "ei Jarbis", ring: { dark: ["#2CC8E8", "#3D8BFF", "#B38CFF"], light: [] } });
    expect(screen.getByText("Jarbis · Claude · Nuvem")).toBeInTheDocument();
  });

  it("Esc fecha a janela", async () => {
    await mount();
    await userEvent.keyboard("{Escape}");
    expect(api.closeWindow).toHaveBeenCalledOnce();
  });

  it("tema: aplica as variáveis de cor e acompanha o Windows ao vivo", async () => {
    await mount();
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.documentElement.style.getPropertyValue("--bg")).toBe("#000000");
    act(() => themeCb("light"));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(document.documentElement.style.getPropertyValue("--bg")).toBe("#FFFFFF");
    expect(document.documentElement.style.getPropertyValue("--text")).toBe("#0A0A0B");
  });

  describe("confirmação pendente", () => {
    it("aparece como diálogo acessível e os botões respondem ao núcleo", async () => {
      await mount();
      await send({ type: "confirm", id: "c1", text: "Fidus quer executar abrir_app (escrita): nome='regedit'." });
      const dlg = screen.getByRole("alertdialog", { name: "Confirmar ação" });
      expect(dlg).toHaveTextContent("abrir_app");
      expect(screen.getByRole("button", { name: /Não/ })).toHaveFocus(); // o foco começa no lado seguro
      await userEvent.click(screen.getByRole("button", { name: /Sim/ }));
      expect(api.command).toHaveBeenCalledWith("confirm_reply", { id: "c1", answer: true });
      await send({ type: "confirm_done", id: "c1" });
      expect(screen.queryByRole("alertdialog")).toBeNull();
    });

    it("teclas S e N também respondem, e o N recusa", async () => {
      await mount();
      await send({ type: "confirm", id: "c2", text: "Apagar?" });
      await userEvent.keyboard("n");
      expect(api.command).toHaveBeenCalledWith("confirm_reply", { id: "c2", answer: false });
      await userEvent.keyboard("s");
      expect(api.command).toHaveBeenLastCalledWith("confirm_reply", { id: "c2", answer: true });
    });

    it("sem confirmação pendente, S e N não mandam nada", async () => {
      await mount();
      await userEvent.keyboard("sn");
      expect(api.command).not.toHaveBeenCalled();
    });
  });
});
