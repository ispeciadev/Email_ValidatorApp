// src/components/CreditsContext.jsx
import { createContext, useContext, useState, useEffect } from "react";

const CreditsContext = createContext();

export function CreditsProvider({ children }) {
  const [history, setHistory] = useState([]);

  // 🔹 Fetch history from backend when app loads
  const fetchHistory = async (userId = 1) => {
    try {
      const res = await fetch(`http://localhost:8000/api/credits/history/${userId}`);
      if (!res.ok) throw new Error("Failed to fetch history");
      const data = await res.json();
      setHistory(data);
    } catch (err) {
      console.error("Error fetching history:", err);
    }
  };

  // Load on mount
  useEffect(() => {
    fetchHistory();
  }, []);

  return (
    <CreditsContext.Provider value={{ history, setHistory, fetchHistory }}>
      {children}
    </CreditsContext.Provider>
  );
}

export function useCredits() {
  return useContext(CreditsContext);
}
