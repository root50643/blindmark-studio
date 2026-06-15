import createClient from "openapi-fetch";
import type { paths } from "./schema";

const baseUrl = window.__APP_CONFIG__?.API_BASE_URL ?? "http://localhost:8000";
const typedClient = createClient<paths>({ baseUrl });

export interface ProblemDetail {
  title: string;
  detail: string;
  code: string;
  request_id?: string;
}

export interface ExtractionResult {
  kind: "text" | "image";
  text?: string;
  image_data_url?: string;
  width?: number;
  height?: number;
}

export interface PreviewResult {
  image_data_url: string;
  width: number;
  height: number;
  resized: boolean;
  capacity_bits: number;
  used_bits: number;
}

export interface AuditRecord {
  id: string;
  request_id: string;
  operation: string;
  created_at: string;
  completed_at?: string;
  client_ip: string;
  direct_ip?: string;
  forwarded_chain?: string[];
  user_agent?: string;
  status: string;
  http_status?: number;
  error_code?: string;
  duration_ms?: number;
  input_files?: Record<string, unknown>[];
  parameters?: Record<string, unknown>;
  result?: Record<string, unknown>;
}

export interface Artifact {
  id: string;
  role: string;
  original_name: string;
  mime: string;
  size: number;
  sha256: string;
  created_at: string;
}

export class ApiError extends Error {
  problem: ProblemDetail;

  constructor(problem: ProblemDetail) {
    super(problem.detail || problem.title);
    this.problem = problem;
  }
}

async function parseError(response: Response): Promise<never> {
  let problem: ProblemDetail;
  try {
    problem = (await response.json()) as ProblemDetail;
  } catch {
    problem = {
      title: "連線失敗",
      detail: `API 回傳 HTTP ${response.status}`,
      code: "http_error",
    };
  }
  throw new ApiError(problem);
}

async function request(
  path: string,
  init: RequestInit = {},
  token?: string,
): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("X-Frontend-Version", __APP_VERSION__);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(`${baseUrl}${path}`, { ...init, headers });
  if (!response.ok) {
    return parseError(response);
  }
  return response;
}

export const api = {
  async capabilities() {
    const { data, error } = await typedClient.GET("/api/v1/capabilities");
    if (error || !data) {
      throw new Error("無法載入 API 功能資訊");
    }
    return data;
  },

  async preview(form: FormData): Promise<PreviewResult> {
    const response = await request("/api/v1/watermark-previews", {
      method: "POST",
      body: form,
    });
    return (await response.json()) as PreviewResult;
  },

  async embed(form: FormData): Promise<Blob> {
    return (
      await request("/api/v1/watermarked-images", {
        method: "POST",
        body: form,
      })
    ).blob();
  },

  async extract(form: FormData, legacy = false): Promise<ExtractionResult> {
    const path = legacy
      ? "/api/v1/legacy-watermark-extractions"
      : "/api/v1/watermark-extractions";
    const response = await request(path, { method: "POST", body: form });
    return (await response.json()) as ExtractionResult;
  },

  async login(username: string, password: string) {
    const { data, error, response } = await typedClient.POST("/api/v1/admin/auth/login", {
      body: { username, password },
    });
    if (error || !data) {
      await parseError(response);
    }
    return data!;
  },

  async records(token: string, query = "") {
    const params = new URLSearchParams({ limit: "100", offset: "0" });
    if (query) params.set("query", query);
    const response = await request(`/api/v1/admin/audit-records?${params}`, {}, token);
    return (await response.json()) as { items: AuditRecord[]; total: number };
  },

  async record(token: string, id: string): Promise<AuditRecord> {
    const response = await request(`/api/v1/admin/audit-records/${id}`, {}, token);
    return (await response.json()) as AuditRecord;
  },

  async artifacts(token: string, id: string): Promise<Artifact[]> {
    const response = await request(
      `/api/v1/admin/audit-records/${id}/artifacts`,
      {},
      token,
    );
    return (await response.json()) as Artifact[];
  },

  async revealPassphrase(token: string, id: string): Promise<string> {
    const response = await request(
      `/api/v1/admin/audit-records/${id}/passphrase-reveal`,
      { method: "POST" },
      token,
    );
    return ((await response.json()) as { passphrase: string }).passphrase;
  },

  async downloadArtifact(token: string, artifact: Artifact): Promise<void> {
    const response = await request(
      `/api/v1/admin/artifacts/${artifact.id}/content`,
      {},
      token,
    );
    downloadBlob(await response.blob(), artifact.original_name);
  },

  async deleteRecord(token: string, id: string, reason: string): Promise<void> {
    await request(
      `/api/v1/admin/audit-records/${id}`,
      {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason }),
      },
      token,
    );
  },
};

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
