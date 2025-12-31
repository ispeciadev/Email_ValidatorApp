import { useState, useEffect } from "react";
import { FaEnvelope, FaSpinner } from "react-icons/fa";
import { API_BASE_URL } from "../../config/api";

export default function CreditsHistory() {
  const [searchEmail, setSearchEmail] = useState("");
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage] = useState(10);

  // Fetch credit history
  useEffect(() => {
    const fetchHistory = async () => {
      try {
        setLoading(true);
        const token = localStorage.getItem("token");

        if (!token) {
          console.error("No token found");
          return;
        }

        const res = await fetch(`${API_BASE_URL}/api/credits/my-history`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        if (!res.ok) {
          throw new Error("Failed to fetch history");
        }

        const data = await res.json();
        console.log("✅ History data:", data); // Debug log
        setHistory(data || []);
      } catch (err) {
        console.error("❌ Error fetching history:", err);
        setHistory([]);
      } finally {
        setLoading(false);
      }
    };

    fetchHistory();
  }, []);

  // Calculate statistics with safety checks
  const totalVerifications = history.filter((h) =>
    h?.reason?.includes("Verification")
  ).length;

  const totalPurchases = history.filter((h) =>
    h?.reason?.includes("Purchase")
  ).length;

  const totalCreditsSpent = history
    .filter((h) => (h?.credits_change_instant || 0) < 0)
    .reduce((sum, h) => sum + Math.abs(h?.credits_change_instant || 0), 0);

  const totalCreditsPurchased = history
    .filter((h) => (h?.credits_change_instant || 0) > 0)
    .reduce((sum, h) => sum + (h?.credits_change_instant || 0), 0);

  // Filter history based on search
  const filteredHistory = history.filter((h) =>
    (h?.reason || "").toLowerCase().includes(searchEmail.toLowerCase())
  );

  // Pagination
  const indexOfLastItem = currentPage * itemsPerPage;
  const indexOfFirstItem = indexOfLastItem - itemsPerPage;
  const currentItems = filteredHistory.slice(indexOfFirstItem, indexOfLastItem);
  const totalPages = Math.ceil(filteredHistory.length / itemsPerPage);

  const handlePrevPage = () => {
    setCurrentPage((prev) => Math.max(prev - 1, 1));
  };

  const handleNextPage = () => {
    setCurrentPage((prev) => Math.min(prev + 1, totalPages));
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-blue-50 px-6 py-8">
      {/* Top Search Bar */}
      <div className="flex items-center space-x-2 mb-6">
        <div className="flex items-center w-full max-w-md border border-gray-300 rounded-lg overflow-hidden shadow-sm bg-white">
          <span className="px-3 text-gray-500">
            <FaEnvelope />
          </span>
          <input
            type="text"
            placeholder="Search transactions..."
            value={searchEmail}
            onChange={(e) => setSearchEmail(e.target.value)}
            className="w-full px-2 py-2 outline-none text-gray-700"
          />
        </div>
      </div>

      {/* Header + Stats */}
      <div className="mb-6">
        <h2 className="text-3xl font-bold text-gray-900 mb-2">
          Credits History
        </h2>
        <p className="text-gray-600 text-sm mb-6">
          Track all your credit purchases and usage transactions
        </p>

        {/* Statistics Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-white rounded-lg shadow-md p-4 border-l-4 border-blue-500">
            <p className="text-gray-600 text-sm">Total Transactions</p>
            <p className="text-2xl font-bold text-blue-600">
              {history.length}
            </p>
          </div>

          <div className="bg-white rounded-lg shadow-md p-4 border-l-4 border-green-500">
            <p className="text-gray-600 text-sm">Credits Purchased</p>
            <p className="text-2xl font-bold text-green-600">
              +{totalCreditsPurchased.toLocaleString()}
            </p>
          </div>

          <div className="bg-white rounded-lg shadow-md p-4 border-l-4 border-orange-500">
            <p className="text-gray-600 text-sm">Credits Spent</p>
            <p className="text-2xl font-bold text-orange-600">
              -{totalCreditsSpent.toLocaleString()}
            </p>
          </div>

          <div className="bg-white rounded-lg shadow-md p-4 border-l-4 border-purple-500">
            <p className="text-gray-600 text-sm">Total Verifications</p>
            <p className="text-2xl font-bold text-purple-600">
              {totalVerifications}
            </p>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-lg shadow-md overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead className="bg-gradient-to-r from-blue-500 to-blue-600 text-white">
              <tr>
                <th className="px-4 py-3 font-semibold">Date & Time</th>
                <th className="px-4 py-3 font-semibold">Transaction</th>
                <th className="px-4 py-3 font-semibold text-center">
                  Change (Instant)
                </th>
                <th className="px-4 py-3 font-semibold text-center">
                  Balance After
                </th>
                <th className="px-4 py-3 font-semibold text-center">Type</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan="5" className="text-center py-10">
                    <div className="flex items-center justify-center space-x-2">
                      <FaSpinner className="animate-spin text-blue-500" />
                      <span className="text-gray-500">Loading history...</span>
                    </div>
                  </td>
                </tr>
              ) : currentItems.length === 0 ? (
                <tr>
                  <td colSpan="5" className="text-center py-10">
                    <div className="text-gray-400">
                      <p className="text-lg font-semibold mb-2">
                        No transactions found
                      </p>
                      <p className="text-sm">
                        {searchEmail
                          ? "Try a different search term"
                          : "Your credit history will appear here"}
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                currentItems.map((h, index) => {
                  // ✅ Safe access with default values
                  const creditsChange = h?.credits_change_instant || 0;
                  const balanceAfter = h?.balance_after_instant || 0;
                  const reason = h?.reason || "Unknown Transaction";
                  const createdAt = h?.created_at || new Date().toISOString();
                  
                  const isCredit = creditsChange > 0;
                  const isDebit = creditsChange < 0;
                  const isPurchase = reason.includes("Purchase");
                  const isVerification = reason.includes("Verification");

                  return (
                    <tr
                      key={h?.id || index}
                      className={`border-t hover:bg-gray-50 transition ${
                        index % 2 === 0 ? "bg-white" : "bg-gray-50"
                      }`}
                    >
                      <td className="px-4 py-3 text-sm text-gray-700">
                        {new Date(createdAt).toLocaleString("en-US", {
                          month: "short",
                          day: "numeric",
                          year: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-start">
                          <span
                            className={`text-2xl mr-2 ${
                              isPurchase
                                ? "text-green-500"
                                : isVerification
                                ? "text-blue-500"
                                : "text-gray-500"
                            }`}
                          >
                            {isPurchase ? "💳" : isVerification ? "✉️" : "📋"}
                          </span>
                          <div>
                            <p className="font-medium text-gray-900">
                              {reason}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span
                          className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-semibold ${
                            isCredit
                              ? "bg-green-100 text-green-700"
                              : isDebit
                              ? "bg-red-100 text-red-700"
                              : "bg-gray-100 text-gray-700"
                          }`}
                        >
                          {isCredit && "+"}
                          {creditsChange}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className="font-semibold text-blue-600">
                          {balanceAfter.toLocaleString()}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span
                          className={`inline-block px-3 py-1 rounded-full text-xs font-medium ${
                            isPurchase
                              ? "bg-green-100 text-green-700"
                              : "bg-blue-100 text-blue-700"
                          }`}
                        >
                          {isPurchase ? "Purchase" : "Usage"}
                        </span>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination Footer */}
      <div className="flex justify-between items-center mt-6 text-sm text-gray-600">
        <p>
          Showing {indexOfFirstItem + 1} to{" "}
          {Math.min(indexOfLastItem, filteredHistory.length)} of{" "}
          {filteredHistory.length} entries
        </p>
        <div className="flex space-x-2">
          <button
            onClick={handlePrevPage}
            disabled={currentPage === 1}
            className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-100 transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Previous
          </button>
          <span className="px-4 py-2 bg-blue-600 text-white rounded-lg">
            {currentPage} / {totalPages || 1}
          </span>
          <button
            onClick={handleNextPage}
            disabled={currentPage === totalPages || totalPages === 0}
            className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-100 transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}