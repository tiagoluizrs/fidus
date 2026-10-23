// @vitest-environment node
import { cookieKey, hostAllowed, prepareHtml } from "../electron/webguard";

describe("servidor de teste no navegador", () => {
  it("só aceita o endereço local", () => {
    for (const h of ["127.0.0.1:5174", "localhost:5174", "localhost", "[::1]:5174"]) expect(hostAllowed(h)).toBe(true);
    for (const h of ["evil.com", "127.0.0.1.evil.com", "192.168.0.5:5174", undefined, "localhost.evil.com:5174"]) expect(hostAllowed(h)).toBe(false);
  });
  it("lê só o cookie com a chave", () => {
    expect(cookieKey("a=1; fidus_key=abc-_9; b=2")).toBe("abc-_9");
    expect(cookieKey("outro=fidus_key=x")).toBeNull();
    expect(cookieKey(undefined)).toBeNull();
  });
  it("injeta a ponte antes do app e libera só a conexão ao próprio servidor", () => {
    const html = `<meta content="default-src 'none'; connect-src 'none'; script-src 'self'"><script type="module" src="/a.js"></script>`;
    const out = prepareHtml(html);
    expect(out).toContain("connect-src 'self'");
    expect(out.indexOf("/shim.js")).toBeLessThan(out.indexOf('type="module"'));
    expect(out).toContain("script-src 'self'");
  });
});
