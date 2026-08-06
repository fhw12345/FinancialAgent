/// <reference types="vite/client" />

declare const __APP_VERSION__: string;

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_WS_URL?: string;
  readonly VITE_AUTH_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// Node.js types for timers
declare namespace NodeJS {
  interface Timeout {}
  interface Timer {}
}
