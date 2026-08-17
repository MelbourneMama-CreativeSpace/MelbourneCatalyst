/**
 * How long a request waits for the backend before giving up. Without this,
 * a hung backend (reachable at the TCP level but never actually answering —
 * exactly what a crashed `uvicorn --reload` worker looks like: the parent
 * process keeps the socket open, so connections still establish, but no
 * response ever comes) relies entirely on the platform's own default
 * timeout, which can be several *minutes*. A person watching a blank
 * screen for 10 minutes before any error appears is a worse failure than
 * a fast, clear one.
 */
export const API_TIMEOUT_MS = 15_000;

/** File uploads (media assets up to `MEDIA_UPLOAD_MAX_BYTES`, 20MB by
 * default) legitimately take longer than a normal JSON request on a slow
 * connection — a flat 15s budget would misreport a genuinely-in-progress
 * upload as a hung backend. */
export const API_UPLOAD_TIMEOUT_MS = 60_000;

/** `confirm-action` is the one endpoint where a chat write tool's real
 * work actually runs synchronously — for most tools (approve/reject/
 * schedule) that's a fast DB write, but `upload_youtube_video` alone does
 * three sequential real network calls (fetch the attached video from
 * storage, a presigned upload to Composio, Composio's own real YouTube
 * upload call), easily past 15s for a real video. The plain API_TIMEOUT_MS
 * budget here doesn't mean "the backend is dead" the way it does
 * elsewhere — it previously misreported a still-working upload as an
 * unreachable backend, which is worse than just waiting. */
export const API_CONFIRM_ACTION_TIMEOUT_MS = 300_000;

/** Idle-gap budget for `sendMessageStream`'s SSE connection — how long it
 * waits between chunks (including the initial response) before deciding
 * the connection is dead, not how long the whole turn is allowed to take.
 * A real turn can run several tool calls before the first token streams
 * (e.g. `create_content_item` makes its own full nested Claude call), so
 * a *fixed* deadline on the entire request — what this used to be —
 * aborts an actively-working turn under ordinary latency variance: it
 * really happened, live, as a genuine `BodyStreamBuffer was aborted`
 * mid-stream, with the backend's own log showing the exact same request
 * cancelled server-side. Resetting this on every chunk means an
 * abandoned-but-still-connected stream still gets caught, without
 * penalizing a turn that's simply doing real, visible work. */
export const API_STREAM_IDLE_TIMEOUT_MS = 90_000;

/**
 * A typed API failure, carrying enough structure (HTTP status, the
 * backend's own `detail` text) that callers can explain *what actually
 * happened* instead of dumping a raw exception message like "fetch failed"
 * or "TypeError: NetworkError when attempting to fetch resource." at
 * whoever's looking at the screen.
 *
 * `status: null` specifically means the request never reached the server
 * at all (connection refused, DNS failure, CORS, or timed out waiting) —
 * distinct from the server responding with an error status, which is a
 * different failure mode with a different fix.
 */
export class ApiError extends Error {
  readonly status: number | null;
  readonly detail: string | null;

  constructor(message: string, status: number | null, detail: string | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/**
 * Builds an `ApiError` from a non-ok `Response`. The backend's FastAPI
 * `HTTPException`s always send `{"detail": "..."}` — when the body parses
 * that way, `detail` is that clean, already-human-written string (e.g.
 * "Opportunity generation failed (check ANTHROPIC_API_KEY / Claude API
 * availability)."); otherwise it falls back to the raw response text so
 * nothing is silently dropped.
 */
export async function apiErrorFromResponse(response: Response): Promise<ApiError> {
  const text = await response.text();
  let detail: string | null = text || null;
  try {
    const parsed = JSON.parse(text);
    if (parsed && typeof parsed.detail === "string") detail = parsed.detail;
  } catch {
    // Not JSON (e.g. an HTML error page from a proxy in front of the
    // backend) — keep the raw text as the detail.
  }
  return new ApiError(`API error ${response.status}`, response.status, detail);
}

function isTimeoutFailure(cause: unknown): boolean {
  // `AbortSignal.timeout()` rejects fetch() with a DOMException named
  // "TimeoutError" (not "AbortError" — that name is reserved for an
  // explicit caller-triggered abort, which this app doesn't do).
  return (
    (typeof DOMException !== "undefined" &&
      cause instanceof DOMException &&
      cause.name === "TimeoutError") ||
    (cause instanceof Error && cause.name === "TimeoutError")
  );
}

/** Wraps whatever `fetch()` itself throws (connection refused, DNS
 * failure, CORS, or the `API_TIMEOUT_MS` deadline above) — these never
 * reach `apiErrorFromResponse` above because there's no `Response` at
 * all. `detail` here is kept internal-only (console logging, not shown to
 * a person) — see `describeError` below for the sentence a person actually
 * sees. */
export function apiErrorFromNetworkFailure(cause: unknown): ApiError {
  if (isTimeoutFailure(cause)) {
    return new ApiError(
      "Backend request timed out",
      null,
      `No response within ${API_TIMEOUT_MS / 1000}s`,
    );
  }
  return new ApiError(
    "Could not reach the backend",
    null,
    cause instanceof Error ? cause.message : String(cause),
  );
}

/**
 * One line a person can actually read, for any error a page might throw —
 * whether it's the `ApiError` shape above or something unrelated (a
 * rendering bug, an unexpected exception). Deliberately never includes an
 * env var name, file path, stack trace, or any other implementation
 * detail — this is the one place all of that gets converted into plain
 * language before it reaches the screen. The technical `error`/`.detail`
 * is still logged to the console (see callers of this function) for
 * anyone who needs to actually debug it.
 */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === null) {
      return "We're having trouble connecting right now. Please check your internet connection and try again.";
    }
    if (error.status === 401) {
      return "Your session has expired. Please sign in again.";
    }
    if (error.status === 403) {
      return "You don't have access to this yet.";
    }
    if (error.status === 404) {
      return "We couldn't find what you were looking for.";
    }
    if (error.status === 409 || error.status === 503) {
      return "This isn't available yet — please try again in a little while.";
    }
    if (error.status === 502) {
      return "One of our connected services isn't responding right now. Please try again shortly.";
    }
    if (error.status >= 500) {
      return "Something went wrong on our end. Please try again.";
    }
    if (error.status === 400 || error.status === 422) {
      return "That request couldn't be completed — please check what you entered and try again.";
    }
    return "Something went wrong with that request. Please try again.";
  }

  if (error instanceof Error) {
    return "Something unexpected happened. Please try again.";
  }

  return "Something unexpected happened. Please try again.";
}
