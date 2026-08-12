/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Public origin of the FastAPI backend (no trailing slash). Empty = same-origin / Vite proxy. */
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
