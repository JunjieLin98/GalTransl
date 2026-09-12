/** /api/pipeline/* 客户端(M2 补丁工作台专用)。 */

const TOKEN_KEY = 'galtrans-pipeline-token';

function backendBaseUrl(): string {
  const configured = import.meta.env.VITE_BACKEND_URL?.trim();
  return configured ? configured.replace(/\/$/, '') : 'http://127.0.0.1:12333';
}

export function savePipelineToken(token: string): void {
  try {
    sessionStorage.setItem(TOKEN_KEY, token);
  } catch {
    // ignore
  }
}

function getToken(): string {
  try {
    return sessionStorage.getItem(TOKEN_KEY) || '';
  } catch {
    return '';
  }
}

export class PipelineApiError extends Error {
  code: string;
  status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${backendBaseUrl()}${path}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
        'X-Local-Token': getToken(),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new PipelineApiError(`无法连接到后端：${backendBaseUrl()}`, 'network', 0);
  }
  const data = (await response.json().catch(() => ({}))) as T & {
    error?: string;
    detail?: string;
  };
  if (!response.ok) {
    throw new PipelineApiError(
      data.detail || data.error || `请求失败：${response.status}`,
      data.error || 'unknown',
      response.status,
    );
  }
  return data;
}

/** 启动时调用:向后端换取本地 token(DPAPI 校验链,仅 GUI Origin 可达)。 */
export async function fetchPipelineToken(): Promise<string> {
  const response = await fetch(`${backendBaseUrl()}/api/pipeline/token`);
  if (!response.ok) {
    throw new PipelineApiError('后端拒绝下发流水线 token', 'E-AUTH-UNAUTHORIZED', response.status);
  }
  const data = (await response.json()) as { token: string };
  savePipelineToken(data.token);
  return data.token;
}

export type PipelineProfile = {
  profile: string;
  capability: string;
  translator_mode: string;
};

export async function fetchPipelineProfiles(): Promise<PipelineProfile[]> {
  const data = await request<{ profiles: PipelineProfile[] }>('GET', '/api/pipeline/profiles');
  return data.profiles;
}

export async function detectEngine(
  gameDir: string,
): Promise<{ results: { profile: string; score: number; capability: string; matched: string[] }[] }> {
  return request('POST', '/api/pipeline/detect', { game_dir: gameDir });
}

export async function createPipelineProject(payload: {
  game_dir: string;
  profile: string;
  project_dir: string;
}): Promise<{ project_dir: string; profile: string }> {
  return request('POST', '/api/pipeline/projects', payload);
}

export type RunPayload = {
  project_dir: string;
  from_step?: string;
  only?: string;
  api_key?: string;
  endpoint?: string;
  model?: string;
};

export async function startPipelineRun(payload: RunPayload): Promise<{ job_id: string }> {
  return request('POST', '/api/pipeline/run', payload);
}

export async function cancelPipelineRun(jobId: string): Promise<void> {
  await request('POST', '/api/pipeline/cancel', { job_id: jobId });
}

export type PipelineStatus = {
  project_dir: string;
  game_dir: string;
  profile: string;
  schema_version: number;
  steps: Record<string, { status: string; finished_at: string; note: string }>;
};

export async function fetchPipelineStatus(projectDir: string): Promise<PipelineStatus> {
  const encoded = encodeURIComponent(projectDir);
  return request('GET', `/api/pipeline/status?project_dir=${encoded}`);
}

export async function restorePipeline(projectDir: string): Promise<{ restored: number }> {
  return request('POST', '/api/pipeline/restore', { project_dir: projectDir });
}

export type PipelineEvent =
  | { event: 'hello'; data: Record<string, never> }
  | { event: 'job_started'; data: { job_id: string; project_dir: string } }
  | { event: 'log'; data: { job_id: string; step: string; message: string } }
  | { event: 'job_done'; data: { job_id: string; results: Record<string, number> } }
  | { event: 'job_failed'; data: { job_id: string; code: string; message: string } };

/** 订阅 SSE 进度流(一次性票据置于 query)。返回关闭函数。 */
export function subscribePipelineEvents(
  onEvent: (event: PipelineEvent) => void,
  onError: (error: string) => void,
): () => void {
  let closed = false;
  let source: EventSource | null = null;

  const connect = async () => {
    try {
      const { ticket } = await request<{ ticket: string }>('POST', '/api/pipeline/sse-ticket');
      if (closed) {
        return;
      }
      source = new EventSource(`${backendBaseUrl()}/api/pipeline/events?ticket=${encodeURIComponent(ticket)}`);
      for (const name of ['hello', 'job_started', 'log', 'job_done', 'job_failed']) {
        source.addEventListener(name, (raw) => {
          try {
            const data = JSON.parse((raw as MessageEvent).data);
            onEvent({ event: name, data } as PipelineEvent);
          } catch {
            // 忽略坏帧
          }
        });
      }
      source.onerror = () => {
        if (!closed) {
          onError('与后端的进度连接中断');
        }
      };
    } catch (error) {
      onError(error instanceof Error ? error.message : String(error));
    }
  };
  void connect();

  return () => {
    closed = true;
    source?.close();
  };
}
