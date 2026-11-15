/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "1" in the static GitHub Pages demo build (`vite build --mode static`). */
  readonly VITE_STATIC?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}