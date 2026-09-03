import axios from "axios";

const RAW_BASE = process.env.REACT_APP_BACKEND_URL;
if (!RAW_BASE) {
  // Fail loudly in the console instead of silently calling "undefined/api/...".
  // eslint-disable-next-line no-console
  console.error(
    "[SkillTrace] REACT_APP_BACKEND_URL is not set. API calls will fail. " +
      "Set it in the frontend environment (e.g. Vercel project env var) and rebuild."
  );
}
// Normalize: drop any trailing slash so we never produce a double slash before /api.
const BASE = (RAW_BASE || "").replace(/\/+$/, "");
const API = `${BASE}/api`;

const api = axios.create({ baseURL: API });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("skilltrace_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error?.response?.status === 401 && !window.location.pathname.startsWith("/login")) {
      localStorage.removeItem("skilltrace_token");
      localStorage.removeItem("skilltrace_user");
      window.location.assign("/login");
    }
    return Promise.reject(error);
  }
);

export { api, API };
