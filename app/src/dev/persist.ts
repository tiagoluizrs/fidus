// A prévia no navegador guarda o estado do núcleo de mentira no localStorage, para o refresh não desfazer o que você mexeu.
// `?reset=1` no endereço começa do zero.
const KEY = "fidus-dev-state-v1";

interface FakeCore {
  api: { command: (name: string, args?: Record<string, unknown>) => Promise<any> };
  profiles: Record<string, any>;
  effective: Record<string, any>;
  memory: any[];
  services: () => any[];
  setServices: (s: any[]) => void;
  piper: Record<string, any>;
  cloud: Record<string, any>;
}

export function persistFake(core: FakeCore): void {
  try {
    if (new URLSearchParams(location.search).get("reset") === "1") localStorage.removeItem(KEY);
    const blob = JSON.parse(localStorage.getItem(KEY) ?? "null");
    if (blob) {
      Object.assign(core.effective, blob.effective);
      for (const k of Object.keys(blob.profiles ?? {})) if (core.profiles[k]) Object.assign(core.profiles[k], blob.profiles[k]);
      core.memory.splice(0, core.memory.length, ...(blob.memory ?? []));
      if (blob.services) core.setServices(blob.services);
      Object.assign(core.piper, blob.piper);
      Object.assign(core.cloud, blob.cloud);
    }
  } catch { /* sem localStorage ou conteúdo antigo: começa limpo */ }

  const original = core.api.command;
  core.api.command = async (name, args) => {
    const reply = await original(name, args);
    try {
      localStorage.setItem(KEY, JSON.stringify({ effective: core.effective, profiles: core.profiles, memory: core.memory, services: core.services(), piper: core.piper, cloud: core.cloud }));
    } catch { /* cheio ou bloqueado: a prévia continua, só não lembra */ }
    return reply;
  };
}
