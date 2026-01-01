// API Base URL - support both dual local and live paths
// Priority: Environment Variable (Live) > Local Fallback (Development)
export const API_BASE_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8001";

export default API_BASE_URL;
