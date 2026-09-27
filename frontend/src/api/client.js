const BASE_URL = import.meta.env.VITE_API_BASE_URL;

function getToken() {
    return sessionStorage.getItem("token");
}

export function setToken(token) {
    sessionStorage.setItem("token", token);
}

export function clearToken() {
    sessionStorage.removeItem("token");
}

async function request(path, options = {}) {
    const token = getToken();
    // FormData bodies get their multipart Content-Type (with boundary) from the browser
    const isJson = options.body && !(options.body instanceof FormData);

    const headers = {
        ...(isJson ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
    };

    const response = await fetch(`${BASE_URL}${path}`, {
        ...options,
        headers,
    });

    if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw { status: response.status, detail: errorBody.detail };
    }

    if (response.status === 204) return null;
    return response.json();
}

// Identical GETs already in flight share one request. Used for loads that run
// on mount, which React StrictMode runs twice in development.
const inflightGets = new Map();

// One-shot handoff: a page that has just fetched what the next page loads on
// mount (e.g. the trainee search, which checks the trainee exists before
// opening the profile) hands the response over instead of it being fetched
// twice. Used at most once, only within a few seconds, and kept in memory
// only, so a reload or a later visit always fetches fresh data.
const HANDOFF_MS = 10000;
const handoffs = new Map();

function handOff(path, data) {
    handoffs.set(path, { data, at: Date.now() });
}

function takeHandOff(path) {
    const entry = handoffs.get(path);
    handoffs.delete(path);
    return entry && Date.now() - entry.at < HANDOFF_MS ? entry : null;
}

function getShared(path) {
    if (!inflightGets.has(path)) {
        const handed = takeHandOff(path);
        const promise = (handed ? Promise.resolve(handed.data) : request(path, { method: "GET" })).finally(
            () => {
                inflightGets.delete(path);
            }
        );
        inflightGets.set(path, promise);
    }
    return inflightGets.get(path);
}

export const api = {
    get: (path) => request(path, { method: "GET" }),
    getShared,
    handOff,
    post: (path, body) =>
        request(path, {
            method: "POST",
            body: body instanceof FormData ? body : JSON.stringify(body),
        }),
    patch: (path, body) => request(path, { method: "PATCH", body: JSON.stringify(body) }),
    delete: (path) => request(path, { method: "DELETE" }),
};

/**
 * A message for an error from request()/login(): the backend's own detail
 * when it sent one (a 422's field errors joined into one line), a connection
 * message when the server could not be reached at all (fetch threw, so there
 * is no status), else `fallback`.
 */
export function errorMessage(err, fallback) {
    if (typeof err?.detail === "string" && err.detail) return err.detail;
    if (Array.isArray(err?.detail) && err.detail.length) {
        return err.detail
            .map((e) => {
                const field = e.loc?.slice(1).join(".");
                const msg = (e.msg || "").replace(/^Value error, /, "");
                return field ? `${field}: ${msg}` : msg;
            })
            .join(", ");
    }
    if (err?.status === undefined) {
        return "Could not reach the server. Check your connection and try again.";
    }
    return fallback;
}

export async function login(username, password) {
    const body = new URLSearchParams();
    body.append("grant_type", "password");
    body.append("username", username);
    body.append("password", password);

    const response = await fetch(`${BASE_URL}/api/auth/token`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
    });

    if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw { status: response.status, detail: errorBody.detail };
    }

    const data = await response.json();
    setToken(data.access_token);
    return data;
}

export async function getMe() {
    return api.getShared("/api/auth/me");
}

export function logout() {
    clearToken();
}