// Tokens do PROJETO.md (Identidade visual). O tema muda trocando o conjunto de variáveis.
export type Theme = "light" | "dark";

export const TOKENS: Record<Theme, Record<string, string>> = {
  light: {
    "--bg": "#FFFFFF", "--sidebar": "#F5F5F7", "--card": "#FFFFFF", "--border": "#E8E8EC", "--text": "#0A0A0B",
    "--text-2": "#6B6B73", "--link": "#1F5FE0", "--error": "#C93A3F", "--accent": "#3D7BFF", "--success": "#30A46C",
  },
  dark: {
    "--bg": "#000000", "--sidebar": "#0B0B0C", "--card": "#121214", "--border": "#232327", "--text": "#F5F5F7",
    "--text-2": "#8E8E96", "--link": "#8FB1FF", "--error": "#FF6B70", "--accent": "#3D7BFF", "--success": "#30A46C",
  },
};

export function applyTheme(theme: Theme, root: HTMLElement = document.documentElement): void {
  root.dataset.theme = theme;
  for (const [k, v] of Object.entries(TOKENS[theme])) root.style.setProperty(k, v);
}
