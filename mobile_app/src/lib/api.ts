import { Platform } from 'react-native';

type ApiEnvelope<T> = {
  data: T;
  meta: { requestId: string };
};

type ProblemDetails = {
  title?: string;
  detail?: string;
  requestId?: string;
};

const platformDefault = Platform.select({
  android: 'http://10.0.2.2:8001',
  ios: 'http://127.0.0.1:8001',
  default: 'http://127.0.0.1:8001',
});

export const API_BASE_URL = (process.env.EXPO_PUBLIC_API_URL || platformDefault || '').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly requestId?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set('Accept', 'application/json');
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  if (options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  let result: Response;
  try {
    result = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  } catch {
    throw new ApiError(`Cannot reach the banking API at ${API_BASE_URL}. Check the API server and network address.`, 0);
  }

  const payload = (await result.json().catch(() => ({}))) as ApiEnvelope<T> | ProblemDetails;
  if (!result.ok) {
    const problem = payload as ProblemDetails;
    throw new ApiError(problem.detail || problem.title || `Request failed (${result.status}).`, result.status, problem.requestId);
  }
  return (payload as ApiEnvelope<T>).data;
}

export function jsonBody(value: unknown): Pick<RequestInit, 'body'> {
  return { body: JSON.stringify(value) };
}

