// Regras do servidor de teste no navegador (separadas para poderem ser testadas sem subir o núcleo).
/** Só aceita o endereço que o próprio dono digitou (barra "DNS rebinding": páginas de fora falando com o seu núcleo). */
export function hostAllowed(host: string | undefined): boolean {
  return /^(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$/.test(host ?? "");
}

/** Injeta a ponte `window.fidus` e libera só a conexão com este mesmo servidor (o CSP do app instalado bloqueia tudo). */
export function prepareHtml(html: string): string {
  return html
    .replace("connect-src 'none'", "connect-src 'self'")
    .replace('<script type="module"', '<script src="/shim.js"></script>\n    <script type="module"');
}

export function cookieKey(header: string | undefined): string | null {
  const m = /(?:^|;\s*)fidus_key=([\w-]+)/.exec(header ?? "");
  return m ? m[1] : null;
}
