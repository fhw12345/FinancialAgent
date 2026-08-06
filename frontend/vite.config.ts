import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { configDefaults } from "vitest/config";
import packageJson from "./package.json";

// https://vitejs.dev/config/
export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(packageJson.version),
  },
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    allowedHosts: ["host.docker.internal"],
    port: 3000,
    strictPort: true,
    // Docker on Windows: bind-mounted file changes don't fire inotify events,
    // so Vite's default fs watcher misses HMR triggers and you have to
    // restart the container after every edit. Polling at 1s catches changes
    // without inotify; cost is a few % CPU for the watcher process.
    watch: {
      usePolling: true,
      interval: 1000,
      ignored: ["**/playwright-report/**", "**/test-results/**"],
    },
  },
  preview: {
    host: "0.0.0.0",
    port: 3000,
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    exclude: [
      ...configDefaults.exclude,
      "e2e/**",
      "playwright-report/**",
      "test-results/**",
    ],
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      exclude: [
        "node_modules/",
        "src/test/",
        "**/*.config.*",
        "**/*.d.ts",
        "**/types.ts",
      ],
    },
  },
});
