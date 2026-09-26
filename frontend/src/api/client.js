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

export const api = {
    get: (path) => request(path, { method: "GET" }),
    post: (path, body) =>
        request(path, {
            method: "POST",
            body: body instanceof FormData ? body : JSON.stringify(body),
        }),
    patch: (path, body) => request(path, { method: "PATCH", body: JSON.stringify(body) }),
    delete: (path) => request(path, { method: "DELETE" }),
};

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
    return api.get("/api/auth/me");
}

export function logout() {
    clearToken();
}