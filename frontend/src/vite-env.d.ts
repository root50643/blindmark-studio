/// <reference types="vite/client" />

interface Window {
  __APP_CONFIG__?: {
    API_BASE_URL?: string;
  };
}

declare const __APP_VERSION__: string;
