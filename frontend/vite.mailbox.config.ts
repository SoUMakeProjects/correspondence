import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { apiProxy, developmentCache } from "./vite.config";

export default defineConfig(({ mode }) => ({
  root: fileURLToPath(new URL("./mailbox", import.meta.url)),
  publicDir: fileURLToPath(new URL("./public", import.meta.url)),
  plugins: [react()],
  cacheDir: developmentCache(mode, "mailbox"),
  optimizeDeps: { include: ["pdfjs-dist"] },
  server: {
    port: 5176,
    strictPort: true,
    fs: { allow: [fileURLToPath(new URL(".", import.meta.url))] },
    proxy: apiProxy(mode),
  },
  build: { outDir: "../dist-mailbox", emptyOutDir: true },
}));
