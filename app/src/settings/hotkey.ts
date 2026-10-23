// Captura de atalho: transforma uma tecla pressionada no formato do núcleo ("ctrl+alt+space").
const MODIFIERS = new Set(["Control", "Alt", "Shift", "Meta"]);

export function comboFromEvent(e: Pick<KeyboardEvent, "key" | "code" | "ctrlKey" | "altKey" | "shiftKey" | "metaKey">): string | null {
  if (MODIFIERS.has(e.key)) return null; // só modificadores: ainda não é um atalho
  const main = keyName(e.code, e.key);
  if (!main) return null;
  const parts: string[] = [];
  if (e.ctrlKey) parts.push("ctrl");
  if (e.altKey) parts.push("alt");
  if (e.shiftKey) parts.push("shift");
  if (e.metaKey) parts.push("cmd");
  const isFn = /^f\d{1,2}$/.test(main);
  if (!parts.length && !isFn) return null; // tecla solta de digitação não serve (só F1 a F24 podem ir sozinhas)
  return [...parts, main].join("+");
}

function keyName(code: string, key: string): string | null {
  if (code === "Space") return "space";
  if (/^Key[A-Z]$/.test(code)) return code.slice(3).toLowerCase();
  if (/^Digit\d$/.test(code)) return code.slice(5);
  if (/^F\d{1,2}$/.test(code)) return code.toLowerCase();
  const named: Record<string, string> = { Enter: "enter", Tab: "tab", Backspace: "backspace" };
  return named[key] ?? null;
}

const LABEL: Record<string, string> = { ctrl: "Ctrl", alt: "Alt", shift: "Shift", cmd: "Win", space: "Espaço", enter: "Enter", tab: "Tab", backspace: "Backspace" };
export const humanize = (combo: string): string => combo.split("+").map((k) => LABEL[k] ?? k.toUpperCase()).join(" + ");
