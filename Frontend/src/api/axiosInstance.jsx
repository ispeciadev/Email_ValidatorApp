import axios from "axios";

// API URL configuration for dual environment support (Local & Live)
const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8001";

export default axios.create({
  baseURL: API_URL,
  withCredentials: true,
});
