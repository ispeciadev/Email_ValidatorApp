// API Base URL - uses environment variable for production, localhost for development
export const API_BASE_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8001";

export default API_BASE_URL;
