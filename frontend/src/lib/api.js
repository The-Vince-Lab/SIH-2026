import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

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
