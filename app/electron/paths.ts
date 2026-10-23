import path from "node:path";
import type { CoreCommand } from "./core";

export interface ResolveOptions {
  isPackaged: boolean;
  resourcesPath: string;
  appPath: string;
  argv: string[];
  env: NodeJS.ProcessEnv;
  platform?: NodeJS.Platform;
}

/** Como iniciar o núcleo. Empacotado: o executável em resources/core. Desenvolvimento: `uv run fidus daemon`. */
export function resolveCoreCommand(o: ResolveOptions): CoreCommand {
  const simulated = o.argv.includes("--simulado") || o.env.FIDUS_SIMULATED === "1";
  const flags = ["daemon", "--stdin-watch", ...(simulated ? ["--simulado"] : [])];

  if (o.env.FIDUS_CORE_CMD) {
    const parts = JSON.parse(o.env.FIDUS_CORE_CMD) as string[];
    return { command: parts[0], args: [...parts.slice(1), ...flags], cwd: path.resolve(o.appPath, "..") };
  }
  if (o.isPackaged) {
    const exe = (o.platform ?? process.platform) === "win32" ? "fidus-core.exe" : "fidus-core";
    return { command: path.join(o.resourcesPath, "core", exe), args: flags };
  }
  return { command: "uv", args: ["run", "fidus", ...flags], cwd: path.resolve(o.appPath, "..") };
}
