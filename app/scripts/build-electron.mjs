// Empacota o processo principal e o preload (esbuild). O renderer é construído pelo Vite.
import { build } from "esbuild";

const common = { bundle: true, platform: "node", target: "node20", format: "cjs", sourcemap: false, external: ["electron"], logLevel: "info" };
await build({ ...common, entryPoints: ["electron/main.ts"], outfile: "dist-electron/main.js" });
await build({ ...common, entryPoints: ["electron/preload.ts"], outfile: "dist-electron/preload.js" });
await build({ ...common, entryPoints: ["electron/webhost.ts"], outfile: "dist-electron/webhost.js" }); // só para o teste no navegador (Docker)
