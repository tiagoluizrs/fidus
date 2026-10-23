import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  base: "./", // as páginas abrem por file://, sem servidor
  build: {
    outDir: "dist/renderer",
    emptyOutDir: true,
    rollupOptions: { input: { ring: "ring.html", settings: "settings.html" } },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    testTimeout: 30000,
  },
});
