import axios from "axios";

// Use environment variable for API URL, fallback to localhost for development
const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8001";

export default axios.create({
  baseURL: API_URL,
  withCredentials: true,
});
