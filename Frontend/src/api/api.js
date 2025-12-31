// api.js
import axios from "axios";
import { API_BASE_URL } from "../config/api";

export const getAdminStats = async () => {
  const [summary, users, rate] = await Promise.all([
    axios.get(`${API_BASE_URL}/admin/summary`),
    axios.get(`${API_BASE_URL}/admin/active-users`),
    axios.get(`${API_BASE_URL}/admin/success-rate`)
  ]);

  return {
    total: summary.data.total_validations,
    users: users.data.active_users,
    rate: rate.data.success_rate
  };
};
