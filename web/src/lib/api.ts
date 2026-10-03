export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * A non-2xx response from the API.
 *
 * `status` is what makes recovery decidable: a `401` means the session is gone
 * and the user must sign in again, a `403` means the wrong role, and a `404` on
 * an application means it is not theirs. Without the code, every call site would
 * have to parse the message to work out which of those happened.
 */
export class ApiError extends Error {
  readonly status: number;
  /** Field-keyed messages, present only on a 422. */
  fieldErrors: Record<string, string>;

  constructor(status: number, message: string, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
  }

  /** The token is missing, rejected, or expired. */
  get isUnauthenticated() {
    return this.status === 401;
  }

  /** Authenticated, but this role is not allowed. */
  get isForbidden() {
    return this.status === 403;
  }

  /**
   * The resource does not exist *for this caller*. The API deliberately returns
   * 404 rather than 403 for another tenant's application, so this must be
   * handled as "missing" and never as "you are not allowed".
   */
  get isNotFound() {
    return this.status === 404;
  }

  /** Payload the server rejected. Field-level messages come from `detail`. */
  get isValidation() {
    return this.status === 422;
  }

  /** The status itself is wrong for the operation, e.g. editing a submitted application. */
  get isConflict() {
    return this.status === 409;
  }

  /** The request never reached the server. */
  get isNetwork() {
    return this.status === 0;
  }
}

/**
 * Turn a failed response into a message plus, for a 422, per-field messages.
 *
 * Both come out of a single `response.json()` call on purpose: a Response body
 * can only be consumed once, so parsing the message and then re-reading the body
 * for field errors would silently yield empty errors on every validation
 * failure.
 */
async function parseFailure(response: Response): Promise<{
  message: string;
  fieldErrors: Record<string, string>;
}> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    const items = Array.isArray(detail) ? detail : [];

    const fieldErrors: Record<string, string> = {};
    for (const item of items) {
      const field = Array.isArray(item?.loc) ? item.loc[item.loc.length - 1] : null;
      // A model-level validator reports `loc: ["body"]`, which has no field to
      // attach to; it belongs on the form as a whole rather than on an input.
      const key = typeof field === "string" ? field : "_form";
      if (!fieldErrors[key]) fieldErrors[key] = item?.msg ?? "Invalid value";
    }

    let message: string;
    if (typeof detail === "string") {
      message = detail;
    } else if (items.length > 0) {
      message = items.map((item: { msg?: string }) => item?.msg).filter(Boolean).join("; ");
    } else {
      message = response.statusText || `Request failed with status ${response.status}`;
    }

    return { message, fieldErrors };
  } catch {
    // Body was not JSON, or was empty.
    return {
      message: response.statusText || `Request failed with status ${response.status}`,
      fieldErrors: {},
    };
  }
}

async function request<T>(
  path: string,
  init: RequestInit & { token?: string } = {},
): Promise<T> {
  const { token, headers, ...rest } = init;

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...rest,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
    });
  } catch {
    // fetch only rejects for transport-level problems: the server is down, DNS
    // failed, or CORS blocked the response. Those are worth distinguishing from
    // a 500, because no amount of retrying the request will fix them.
    throw new ApiError(
      0,
      "Cannot reach the PermitFlow API. Check that it is running.",
    );
  }

  if (!response.ok) {
    const { message, fieldErrors } = await parseFailure(response);
    throw new ApiError(response.status, message, fieldErrors);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const api = {
  get<T>(path: string, options?: { token?: string; signal?: AbortSignal }) {
    return request<T>(path, { method: "GET", signal: options?.signal, token: options?.token });
  },
  post<T>(path: string, body: unknown, options?: { token?: string; signal?: AbortSignal }) {
    return request<T>(path, {
      method: "POST",
      body: JSON.stringify(body),
      token: options?.token,
      signal: options?.signal,
    });
  },
  /**
   * `PUT /applications/{id}` replaces the editable fields wholesale, which is
   * why the application paths never use `patch` — that server has no
   * sparse-update route for them.
   *
   * `patch` itself exists for the admin agency API, whose `PATCH
   * /admin/agencies/{id}` takes a single field and is genuinely partial.
   */
  put<T>(path: string, body: unknown, options?: { token?: string; signal?: AbortSignal }) {
    return request<T>(path, {
      method: "PUT",
      body: JSON.stringify(body),
      token: options?.token,
      signal: options?.signal,
    });
  },
  patch<T>(path: string, body: unknown, options?: { token?: string; signal?: AbortSignal }) {
    return request<T>(path, {
      method: "PATCH",
      body: JSON.stringify(body),
      token: options?.token,
      signal: options?.signal,
    });
  },
  /** Resolves `undefined` on the server's 204 — a successful delete has no body. */
  delete<T>(path: string, options?: { token?: string; signal?: AbortSignal }) {
    return request<T>(path, { method: "DELETE", signal: options?.signal, token: options?.token });
  },
};

export type HealthResponse = { status: string };