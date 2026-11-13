import { isAxiosError } from 'axios';

/** The backend's error format: {"error": {"code", "message", "details"}}. */
export interface ApiErrorBody {
  error: { code: string; message: string; details: Record<string, unknown> };
}

export interface ParsedError {
  code: string;
  message: string;
  /** Field name -> first message, for showing under form inputs. */
  fieldErrors: Record<string, string>;
  status?: number;
}

function firstMessage(value: unknown): string | undefined {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) {
    for (const v of value) {
      const m = firstMessage(v);
      if (m) return m;
    }
  }
  if (value && typeof value === 'object') {
    for (const v of Object.values(value)) {
      const m = firstMessage(v);
      if (m) return m;
    }
  }
  return undefined;
}

export function parseApiError(err: unknown): ParsedError {
  if (isAxiosError(err)) {
    const status = err.response?.status;
    const body = err.response?.data as Partial<ApiErrorBody> | undefined;
    if (body?.error) {
      const fieldErrors: Record<string, string> = {};
      for (const [field, value] of Object.entries(body.error.details ?? {})) {
        const m = firstMessage(value);
        if (m) fieldErrors[field] = m;
      }
      return { code: body.error.code, message: body.error.message, fieldErrors, status };
    }
    if (!err.response) {
      return { code: 'network_error', message: "Can't reach the server. Check your connection.", fieldErrors: {} };
    }
    return { code: 'error', message: `Something went wrong (${status}).`, fieldErrors: {}, status };
  }
  return { code: 'error', message: 'Something went wrong.', fieldErrors: {} };
}
