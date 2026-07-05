

export interface ApiFetchError extends Error {
  status: number;
}

function makeApiFetchError(message: string, status: number): ApiFetchError {
  const err = new Error(message) as ApiFetchError;
  err.status = status;
  return err;
}

function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;

  const token = getAccessToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  try {
    response = await fetch(path, {
      ...options,
      credentials: "include",
      headers,
    });
  } catch {
    throw makeApiFetchError("Network error — could not connect to the server.", 0);
  }

  if (response.status === 401 || response.status === 403) {
    // Token missing/expired/invalid. Clear stale credentials and bounce to
    // login rather than let every caller re-implement this check.
    if (typeof window !== "undefined") {
      const isAuthed = !!localStorage.getItem("access_token");
      if (isAuthed) {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        window.location.href = "/login";
      }
    }
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      detail = body?.detail ?? detail;
    } catch {
      /* response had no JSON body */
    }
    throw makeApiFetchError(detail, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
