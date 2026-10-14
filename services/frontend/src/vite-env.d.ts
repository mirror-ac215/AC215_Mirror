/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** where the api gateway lives */
  readonly VITE_API_BASE_URL?: string;
  /** "true" = use fake responses (no gateway needed), "false" = call the real gateway */
  readonly VITE_USE_MOCK_API?: string;
}
