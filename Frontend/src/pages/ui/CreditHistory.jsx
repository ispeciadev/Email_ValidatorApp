import { useState, useEffect } from "react";
import { FaEnvelope } from "react-icons/fa";
import { useCredits } from "./CreditsContext";
export default function CreditsHistory() {
  const [searchEmail, setSearchEmail] = useState("");
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  
  // 🔹 Replace with actual logged-in user_id
  const userId = 1;

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        setLoading(true);
        const res = await fetch(`http://localhost:8000/api/credits/history/${userId}`);
        if (!res.ok) throw new Error("Failed to fetch history");
        const data = await res.json();
        setHistory(data);
      } catch (err) {
        console.error("Error fetching history:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchHistory();
  }, [userId]);

  return (
    <div className="min-h-screen bg-gray-50 px-6 py-8">
      {/* Top Search Bar */}
      <div className="flex items-center space-x-2 mb-6">
        <div className="flex items-center w-full max-w-md border border-gray-300 rounded-lg overflow-hidden shadow-sm">
          <span className="px-3 text-gray-500">
            <FaEnvelope />
          </span>
          <input
            type="text"
            placeholder="Enter an email address"
            value={searchEmail}
            onChange={(e) => setSearchEmail(e.target.value)}
            className="w-full px-2 py-2 outline-none text-gray-700"
          />
        </div>
        <button className="px-5 py-2 bg-gray-900 text-white font-medium rounded-lg shadow hover:bg-gray-800 transition">
          Verify
        </button>
      </div>

      {/* Header + Stats */}
      <div className="flex justify-between items-start mb-6">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">
            Credits History
          </h2>
          <p className="text-gray-600 text-sm">
            Find our how your credits are charged or refunded.
          </p>
        </div>
        <div className="text-right text-sm text-gray-700 space-y-1">
          <p>
            Total Single Verifications:{" "}
            <span className="font-semibold">{history.length}</span>
          </p>
          <p>
            Total API Verifications:{" "}
            <span className="font-semibold">0</span>
          </p>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-lg shadow-md overflow-hidden">
        <table className="w-full text-left border-collapse">
          <thead className="bg-gray-100 text-sm text-gray-600">
            <tr>
              <th className="px-4 py-3">DATE CREATED</th>
              <th className="px-4 py-3">REASON</th>
              <th className="px-4 py-3">CREDITS CHANGE (DAILY)</th>
              <th className="px-4 py-3">CREDITS CHANGE (INSTANT)</th>
              <th className="px-4 py-3">BALANCE AFTER (DAILY)</th>
              <th className="px-4 py-3">BALANCE AFTER (INSTANT)</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan="6" className="text-center py-10 text-gray-500">
                  Loading...
                </td>
              </tr>
            ) : history.length === 0 ? (
              <tr>
                <td colSpan="6" className="text-center py-10 text-gray-500">
                  No records found.
                </td>
              </tr>
            ) : (
              history.map((h) => (
                <tr key={h.id} className="border-t text-sm">
                  <td className="px-4 py-3">
                    {new Date(h.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3">{h.reason}</td>
                  <td className="px-4 py-3">{h.credits_change_daily}</td>
                  <td className="px-4 py-3">{h.credits_change_instant}</td>
                  <td className="px-4 py-3">{h.balance_after_daily}</td>
                  <td className="px-4 py-3">{h.balance_after_instant}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      <div className="flex justify-between items-center mt-4 text-sm text-gray-600">
        <p>
          Showing {history.length > 0 ? 1 : 0} to {history.length} of {history.length} entries
        </p>
        <div className="flex space-x-1">
          <button className="px-3 py-1 border border-gray-300 rounded-l-md hover:bg-gray-100 transition">
            Previous
          </button>
          <button className="px-3 py-1 border border-gray-300 rounded-r-md hover:bg-gray-100 transition">
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

