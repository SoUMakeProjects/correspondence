import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export function apiProxy(mode: string) {
  // Only APP_ settings are read here. Azure credentials never become browser variables.
  const root = fileURLToPath(new URL("..", import.meta.url));
  const env = loadEnv(mode, root, "APP_");
  const target = `http://${env.APP_HOST || "127.0.0.1"}:${env.APP_PORT || "8000"}`;
  return { "/api": target, "/docs": target, "/openapi.json": target };
}

export function developmentCache(mode: string, app: "desk" | "mailbox") {
  const root = fileURLToPath(new URL("..", import.meta.url));
  const env = loadEnv(mode, root, "APP_");
  // Separate each app and test backend: concurrent Vite servers must not replace
  // one another's optimized modules while a page is loading its PDF renderer.
  const port = /^\d+$/.test(env.APP_PORT ?? "") ? env.APP_PORT : "8000";
  return fileURLToPath(
    new URL(`./node_modules/.vite-${app}-${port}`, import.meta.url),
  );
}

export default defineConfig(({ mode }) => {
  return {
    plugins: [react()],
    cacheDir: developmentCache(mode, "desk"),
    server: {
      port: 5173,
      strictPort: true,
      proxy: apiProxy(mode),
    },
  };
});
