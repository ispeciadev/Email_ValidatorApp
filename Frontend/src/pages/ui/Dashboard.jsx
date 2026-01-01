import { useState } from "react";
import { useEffect } from "react";
import { FaCoins } from "react-icons/fa";
import axios from "axios";
import {
  FaTachometerAlt,
  FaUser,
  FaChartBar,
  FaCreditCard,
  FaSignOutAlt,
} from "react-icons/fa";
import { useNavigate } from "react-router-dom";
import {
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  PieChart,
  Pie,
  Cell,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { API_BASE_URL } from "../../config/api";

const COLORS = ["#22c55e", "#ef4444", "#3b82f6"];

const Dashboard = () => {
  const navigate = useNavigate();

  const [selectedTab, setSelectedTab] = useState("dashboard"); // tab state
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [singleEmail, setSingleEmail] = useState("");
  const [singleResult, setSingleResult] = useState(null);
  const [singleLoading, setSingleLoading] = useState(false);
  const [singleTimeTaken, setSingleTimeTaken] = useState(null);
  const [bulkTimeTaken, setBulkTimeTaken] = useState(null);
  const [weeklyStats, setWeeklyStats] = useState([]);
  const [credits, setCredits] = useState(null);
  const [selectedBulkTask, setSelectedBulkTask] = useState(null); // For viewing bulk task details
  const [bulkTaskEmails, setBulkTaskEmails] = useState([]); // Individual emails from bulk task
  const [selectedEmailDetail, setSelectedEmailDetail] = useState(null); // For showing individual email modal
  const [validationTasks, setValidationTasks] = useState([]); // Bulk validation history
  const userId = 1;
  const handleFileChange = (e) => setSelectedFiles(e.target.files);

  const [stats, setStats] = useState({
    total: 0,
    valid: 0,
    invalid: 0,
    disposable: 0,
  });

  const pieData = [
    { name: "Valid", value: stats.valid },
    { name: "Invalid", value: stats.invalid },
    { name: "Disposable", value: stats.disposable },
  ];
  const rotateDaysToEndOnToday = () => {
    const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    const todayIndex = new Date().getDay(); // 0 (Sun) - 6 (Sat)
    const map = [6, 0, 1, 2, 3, 4, 5]; // To match "Mon" = 0, "Sun" = 6
    const adjustedIndex = map[todayIndex];

    return [
      ...days.slice(0, adjustedIndex + 1),
      ...days.slice(adjustedIndex + 1),
    ];
  };

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) return;

    // Rotate days so the chart ends on today (e.g., Tue if today is Tuesday)
    const getRotatedDays = () => {
      const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
      const today = new Date().toLocaleDateString("en-US", {
        weekday: "short",
      });
      const todayIndex = days.indexOf(today);
      if (todayIndex === -1) return days;
      return [...days.slice(todayIndex + 1), ...days.slice(0, todayIndex + 1)];
    };

    // Fetch total stats (valid/invalid/etc)
    const fetchUserRecords = async () => {
      try {
        const res = await axios.get(`${API_BASE_URL}/user/all-emails`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        const data = res.data;

        const statCounts = {
          total: data.length,
          valid: data.filter((r) => r.status?.toLowerCase() === "valid").length,
          invalid: data.filter((r) => r.status?.toLowerCase() === "invalid")
            .length,
          disposable: data.filter(
            (r) => r.status?.toLowerCase() === "disposable"
          ).length,
        };

        setStats(statCounts);
      } catch (err) {
        console.error(
          "Failed to fetch records:",
          err.response?.data || err.message
        );
      }
    };

    // Fetch weekly validation stats per user
    const fetchWeeklyStats = async () => {
      try {
        const res = await fetch(
          `${API_BASE_URL}/api/validation-stats/weekly`,
          {
            headers: {
              Authorization: `Bearer ${token}`,
            },
          }
        );
        const data = await res.json();

        // Default values
        const defaultStats = {
          Mon: 0,
          Tue: 0,
          Wed: 0,
          Thu: 0,
          Fri: 0,
          Sat: 0,
          Sun: 0,
        };

        // Populate values from API
        data.forEach((item) => {
          if (item.day in defaultStats) {
            defaultStats[item.day] = item.emails;
          }
        });

        // Format with rotated day order
        const rotatedDays = getRotatedDays();
        const formatted = rotatedDays.map((day) => ({
          day,
          emails: defaultStats[day],
        }));

        setWeeklyStats(formatted);
      } catch (err) {
        console.error("Error fetching weekly stats:", err);
      }
    };

    const fetchValidationTasks = async () => {
      try {
        const res = await axios.get(`${API_BASE_URL}/user/validation-tasks`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
        setValidationTasks(res.data);
      } catch (err) {
        console.error("Error fetching validation tasks:", err);
      }
    };

    fetchUserRecords();
    fetchWeeklyStats();
    fetchValidationTasks();
  }, []);

  const handleUpload = async () => {
    if (selectedFiles.length === 0) {
      alert("Please select at least one CSV file.");
      return;
    }

    const formData = new FormData();
    for (let i = 0; i < selectedFiles.length; i++) {
      formData.append("files", selectedFiles[i]);
    }

    try {
      setLoading(true);
      setBulkTimeTaken(null);
      const token = localStorage.getItem("token");
      const startTime = performance.now();
      const response = await axios.post(
        `${API_BASE_URL}/validate-emails/`,
        formData,
        {
          headers: {
            "Content-Type": "multipart/form-data",
            Authorization: `Bearer ${token}`,
          },
        }
      );
      const endTime = performance.now(); // ⏱ end timer
      const seconds = ((endTime - startTime) / 1000).toFixed(2);

      setResults(response.data.results);
      setBulkTimeTaken(seconds);

      // Refresh validation tasks list
      try {
        const tasksRes = await axios.get(`${API_BASE_URL}/user/validation-tasks`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        setValidationTasks(tasksRes.data);
      } catch (err) {
        console.error("Error refreshing tasks:", err);
      }
    } catch (err) {
      console.error(err);
      alert("Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  const handleSingleValidation = async (e) => {
    e.preventDefault();
    setSingleLoading(true);
    try {
      const formData = new FormData();
      formData.append("email", singleEmail);
      const token = localStorage.getItem("token");

      const res = await axios.post(
        `${API_BASE_URL}/validate-single-email/`,
        formData,
        {
          headers: {
            "Content-Type": "multipart/form-data",
            Authorization: `Bearer ${token}`,
          },
        }
      );

      setSingleResult(res.data);
      setSingleTimeTaken(res.data.time_taken);
    } catch (err) {
      console.error(err);
      alert("Something went wrong.");
      setSingleResult(null);
    } finally {
      setSingleLoading(false);
    }
  };
  // Fetch credits on mount
  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) return;

    axios.get(`${API_BASE_URL}/user/credits`, {
      headers: {
        Authorization: `Bearer ${token}`
      }
    }).then((res) => {
      setCredits(res.data.credits);
    }).catch(err => {
      console.error("Failed to fetch credits:", err);
    });
  }, []);

  const handleBuyCredits = async (amount) => {
    const res = await axios.post(`/api/users/${userId}/buy-credits`, { amount });
    setCredits(res.data); // 🔄 update frontend immediately
  };

  const handleUseCredits = async (count, prefer = "auto") => {
    const res = await axios.post(`/api/users/${userId}/use-credits`, { count, prefer });
    setCredits(res.data); // 🔄 update frontend immediately
  };

  return (
    <div className="flex min-h-screen bg-gray-100">


      {/* Sidebar */}
      <aside className="w-64 bg-[#0f172a] text-white p-6 space-y-6">
        <h1 className="text-2xl font-bold mb-8">Email Validator</h1>
        <nav className="space-y-4">
          <button
            className={`flex items-center gap-3 px-3 py-2 rounded-lg w-full text-left transition ${selectedTab === "dashboard" ? "bg-blue-600" : "hover:bg-blue-900"
              }`}
            onClick={() => setSelectedTab("dashboard")}
          >
            <FaTachometerAlt /> Dashboard
          </button>
          <button
            className={`flex items-center gap-3 px-3 py-2 rounded-lg w-full text-left transition hover:bg-blue-900`}
            onClick={() => navigate("/profile")}
          >
            <FaUser /> Profile
          </button>
          <button
            className={`flex items-center gap-3 px-3 py-2 rounded-lg w-full text-left transition ${selectedTab === "analyze" ? "bg-blue-600" : "hover:bg-blue-900"
              }`}
            onClick={() => setSelectedTab("analyze")}
          >
            <FaChartBar /> Analyze Page
          </button>
          <button
            className={`flex items-center gap-3 px-3 py-2 rounded-lg w-full text-left transition ${selectedTab === "pricing" ? "bg-blue-600" : "hover:bg-blue-900"
              }`}
            onClick={() => navigate("/pricingg")}
          >
            <FaChartBar /> Pricing
          </button>
          <button
            className={`flex items-center gap-3 px-3 py-2 rounded-lg w-full text-left transition ${selectedTab === "subscription"
              ? "bg-blue-600"
              : "hover:bg-blue-900"
              }`}
            onClick={() => setSelectedTab("subscription")}
          >
            <FaCreditCard /> Subscription
          </button>
          <button
            className={`flex items-center gap-3 px-3 py-2 rounded-lg w-full text-left transition ${selectedTab === "buycredit"
              ? "bg-blue-600"
              : "hover:bg-blue-900"
              }`}
            onClick={() => navigate("/buy-credit")}
          >

            <FaCoins /> Buy Credits
          </button>
          <button
            className={`flex items-center gap-3 px-3 py-2 rounded-lg w-full text-left transition ${selectedTab === "buycredit"
              ? "bg-blue-600"
              : "hover:bg-blue-900"
              }`}
            onClick={() => navigate("/credit-history")}
          >

            <FaCoins /> Credit History
          </button>
          <div className="mt-auto space-y-3 border-t border-gray-700 pt-4">
            <div className="flex justify-between items-center">
              <span>Credits</span>
              <span className="bg-blue-600 px-2 py-1 rounded text-sm font-bold">
                {credits !== null ? credits : "…"}
              </span>
            </div>

            <div className="flex justify-between items-center">
              <span>Remaining Credits</span>
              <span className="px-3 py-1 rounded-full bg-blue-100 text-blue-600 font-bold">
                {credits !== null ? credits : "…"}
              </span>
            </div>
          </div>
        </nav>
      </aside>

      {/* Main content area */}
      <main className="flex-1 overflow-y-auto">
        {selectedTab === "dashboard" && (

          <div className="p-6 space-y-8">
            <div className="flex justify-between items-center mb-6">
              <div className="flex items-center gap-3 text-lg font-semibold text-gray-800">
                Credits:
                <span className="px-3 py-1 rounded-full bg-blue-100 text-blue-600 font-bold">
                  {credits !== null ? credits : "…"}
                </span>
              </div>

              <button
                onClick={() => navigate("/pricing")}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg shadow hover:bg-blue-700 transition"
              >
                Buy Credits
              </button>
            </div>
            <h2 className="text-3xl font-bold text-center">
              Welcome to the Dashboard!
            </h2>
            {/* Stats cards  */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
              <div className="bg-white shadow-lg rounded-xl p-6 text-center">
                <p className="text-gray-500">Total Emails</p>
                <p className="text-2xl font-bold">{stats.total}</p>
              </div>
              <div className="bg-green-100 shadow-lg rounded-xl p-6 text-center">
                <p className="text-gray-500">Valid Emails</p>
                <p className="text-2xl font-bold">{stats.valid}</p>
              </div>
              <div className="bg-red-100 shadow-lg rounded-xl p-6 text-center">
                <p className="text-gray-500">Invalid Emails</p>
                <p className="text-2xl font-bold">{stats.invalid}</p>
              </div>
              <div className="bg-yellow-100 shadow-lg rounded-xl p-6 text-center">
                <p className="text-gray-500">Disposable</p>
                <p className="text-2xl font-bold">{stats.disposable}</p>
              </div>
            </div>
            {/* Line Chart */}
            <div className="bg-white shadow-lg rounded-xl p-6">
              <h3 className="text-xl font-semibold mb-4">
                Emails Validated This Week
              </h3>

              {weeklyStats.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart width={600} height={300} data={weeklyStats}>
                    <CartesianGrid stroke="#ccc" />
                    <XAxis dataKey="day" />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="emails" stroke="#8884d8" />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="text-gray-500 text-center">
                  Loading chart data...
                </div>
              )}
            </div>
            {/* Pie Chart */}
            <div className="bg-white shadow-lg rounded-xl p-6">
              <h3 className="text-xl font-semibold mb-4">
                Validation Type Breakdown
              </h3>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, percent }) =>
                      `${name} ${(percent * 100).toFixed(0)}%`
                    }
                    outerRadius={100}
                    fill="#8884d8"
                    dataKey="value"
                  >
                    {pieData.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={COLORS[index % COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
        {/* analyze Tab */}

        {selectedTab === "analyze" && (
          <div className="text-gray-800">
            {/* Hero Section */}
            <section className="bg-gradient-to-r from-[#1e293b] to-[#0f172a] text-white py-20 px-6 text-center">
              <h1 className="text-5xl font-extrabold mb-4 animate-fade-in">
                Validate Emails with Precision
              </h1>
              <p className="text-lg md:text-xl mb-10 text-slate-300 animate-fade-in delay-100">
                Upload your CSV files and clean your email lists instantly.
                Protect your sender reputation.
              </p>
              <form
                onSubmit={handleSingleValidation}
                className="flex flex-col md:flex-row items-center justify-center gap-4 max-w-2xl mx-auto animate-fade-in delay-200"
              >
                <input
                  type="email"
                  placeholder="Your email"
                  value={singleEmail}
                  onChange={(e) => setSingleEmail(e.target.value)}
                  required
                  className="px-5 py-3 w-full md:w-auto flex-1 rounded-lg bg-white/10 text-white placeholder:text-gray-300 border border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-500 transition"
                />
                <button
                  type="submit"
                  disabled={singleLoading}
                  className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-lg shadow-md hover:shadow-blue-400 transition duration-200 active:scale-95"
                >
                  {singleLoading ? "Checking..." : "Try Now"}
                </button>
              </form>
              {singleResult && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 animate-fade-in p-4">
                  <div className="bg-white rounded-2xl max-w-4xl w-full shadow-2xl">
                    {/* Header with Status Icon and Close Button */}
                    <div className="relative text-center py-6 border-b border-gray-200">
                      <button
                        onClick={() => setSingleResult(null)}
                        className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 transition-colors"
                        aria-label="Close modal"
                      >
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>

                      <div className={`inline-flex items-center justify-center w-20 h-20 rounded-full mb-3 ${
                        singleResult.status === 'valid' ? 'bg-green-100' : 
                        singleResult.status === 'risky' ? 'bg-yellow-100' : 'bg-red-100'
                      }`}>
                        {singleResult.status === 'valid' ? (
                          <svg className="w-10 h-10 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                        ) : singleResult.status === 'risky' ? (
                          <svg className="w-10 h-10 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                          </svg>
                        ) : (
                          <svg className="w-10 h-10 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        )}
                      </div>
                      <h2 className={`text-3xl font-bold uppercase tracking-wide ${
                        singleResult.status === 'valid' ? 'text-green-600' : 
                        singleResult.status === 'risky' ? 'text-yellow-600' : 'text-red-600'
                      }`}>
                        {singleResult.status || 'VALIDATION RESULT'}
                      </h2>
                    </div>

                    {/* Validation Details - 2 Column Layout */}
                    <div className="p-6">
                      <div className="grid grid-cols-2 gap-x-8 gap-y-1.5 text-sm text-gray-700">
                        <div className="flex justify-between py-2 border-b border-gray-100">
                          <span className="font-semibold text-gray-600">email:</span>
                          <span className="text-blue-600 font-medium">{singleResult.email}</span>
                        </div>

                        <div className="flex justify-between py-2 border-b border-gray-100">
                          <span className="font-semibold text-gray-600">status:</span>
                          <span className={`font-medium italic ${
                            singleResult.status === 'valid' ? 'text-green-600' :
                            singleResult.status === 'risky' ? 'text-yellow-600' : 'text-red-600'
                          }`}>{singleResult.status || 'risky'}</span>
                        </div>

                        <div className="flex justify-between py-2 border-b border-gray-100">
                          <span className="font-semibold text-gray-600">is_safe_to_send:</span>
                          <span className={singleResult.is_valid ? "text-green-600 italic" : "text-red-600 italic"}>
                            {singleResult.is_valid ? 'true' : 'false'}
                          </span>
                        </div>

                        <div className="flex justify-between py-2 border-b border-gray-100">
                          <span className="font-semibold text-gray-600">is_valid_syntax:</span>
                          <span className={singleResult.syntax_valid ? "text-green-600 italic" : "text-red-600 italic"}>
                            {singleResult.syntax_valid ? 'true' : 'false'}
                          </span>
                        </div>

                        <div className="flex justify-between py-2 border-b border-gray-100">
                          <span className="font-semibold text-gray-600">is_disposable:</span>
                          <span className={singleResult.is_disposable ? "text-red-600 italic" : "text-green-600 italic"}>
                            {singleResult.is_disposable ? 'true' : 'false'}
                          </span>
                        </div>

                        <div className="flex justify-between py-2 border-b border-gray-100">
                          <span className="font-semibold text-gray-600">is_role_account:</span>
                          <span className={singleResult.is_role_account ? "text-yellow-600 italic" : "text-green-600 italic"}>
                            {singleResult.is_role_account ? 'true' : 'false'}
                          </span>
                        </div>

                        <div className="flex justify-between py-2 border-b border-gray-100">
                          <span className="font-semibold text-gray-600">mx_accepts_mail:</span>
                          <span className={singleResult.mx_valid ? "text-green-600 italic" : "text-red-600 italic"}>
                            {singleResult.mx_valid ? 'true' : 'false'}
                          </span>
                        </div>

                        <div className="flex justify-between py-2 border-b border-gray-100">
                          <span className="font-semibold text-gray-600">mx_records:</span>
                          <span className="text-gray-600 italic text-sm truncate max-w-md">
                            {singleResult.mx_records || 'MX record found'}
                          </span>
                        </div>

                        <div className="flex justify-between py-2 border-b border-gray-100">
                          <span className="font-semibold text-gray-600">can_connect_smtp:</span>
                          <span className={singleResult.smtp === 'Valid' ? "text-green-600 italic" : "text-gray-500 italic"}>
                            {singleResult.smtp === 'Valid' ? 'true' : 'false'}
                          </span>
                        </div>

                        <div className="flex justify-between py-2 border-b border-gray-100">
                          <span className="font-semibold text-gray-600">has_inbox_full:</span>
                          <span className={singleResult.status === 'inbox_full' ? "text-red-600 italic" : "text-green-600 italic"}>
                            {singleResult.status === 'inbox_full' ? 'true' : 'false'}
                          </span>
                        </div>

                        <div className="flex justify-between py-2 border-b border-gray-100">
                          <span className="font-semibold text-gray-600">is_catch_all:</span>
                          <span className={singleResult.is_catch_all ? "text-yellow-600 italic" : "text-green-600 italic"}>
                            {singleResult.is_catch_all ? 'true' : 'false'}
                          </span>
                        </div>

                        <div className="flex justify-between py-2 border-b border-gray-100">
                          <span className="font-semibold text-gray-600">is_deliverable:</span>
                          <span className={singleResult.is_valid ? "text-green-600 italic" : "text-red-600 italic"}>
                            {singleResult.is_valid ? 'true' : 'false'}
                          </span>
                        </div>

                        <div className="flex justify-between py-2 border-b border-gray-100">
                          <span className="font-semibold text-gray-600">is_disabled:</span>
                          <span className="text-green-600 italic">false</span>
                        </div>

                        <div className="flex justify-between py-2 border-b border-gray-100">
                          <span className="font-semibold text-gray-600">is_free_email:</span>
                          <span className="text-green-600 italic">true</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Removed OK button per requirements */}
                </div>
              )}
              {singleTimeTaken !== null && (
                <div className="mt-6 flex justify-center">
                  <div className="relative px-6 py-3 bg-gradient-to-r from-green-100 to-green-200 border border-green-400 rounded-xl shadow-lg transform transition duration-300 hover:scale-105">
                    <div className="flex items-center space-x-2 text-green-800 text-sm font-medium animate-fade-in">
                      <span className="text-xl">⏱️</span>
                      <span>
                        Validation completed in{" "}
                        <span className="font-bold text-green-700">
                          {singleTimeTaken}
                        </span>{" "}
                        seconds
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </section>

            {/* Bulk Upload Section */}
            <section className="py-20 px-6 bg-[#f9fbfd]">
              <h2 className="text-4xl font-extrabold text-center mb-12 text-gray-900 tracking-tight animate-fade-in">
                📤 Bulk Email Validation
              </h2>
              <div className="w-full p-4 border rounded-xl bg-white shadow-sm">
                <label className="block text-lg font-semibold mb-2 text-gray-800">
                  Upload CSV File(s)
                </label>

                <input
                  type="file"
                  multiple
                  accept=".csv"
                  onChange={handleFileChange}
                  className="block w-full px-4 py-2 text-gray-800 border border-blue-400 rounded-lg cursor-pointer bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-300"
                />

                {selectedFiles.length > 0 && (
                  <div className="flex flex-wrap gap-2 mt-4">
                    {Array.from(selectedFiles).map((file, index) => (
                      <div
                        key={index}
                        className="bg-blue-100 text-blue-800 text-sm font-medium px-3 py-1 rounded-full border border-blue-300"
                      >
                        {file.name}
                      </div>
                    ))}
                  </div>
                )}

                <button
                  onClick={handleUpload}
                  className="mt-6 w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 rounded-lg flex items-center justify-center gap-2 transition"
                >
                  🚀 Validate Emails
                </button>
                {loading && (
                  <p className="text-center mt-6 text-indigo-600 font-medium text-md animate-pulse">
                    Validating files... Hang tight!
                  </p>
                )}
                {bulkTimeTaken !== null && (
                  <div className="mt-6 flex justify-center">
                    <div className="relative px-6 py-3 bg-gradient-to-r from-green-100 to-green-200 border border-green-400 rounded-xl shadow-lg transform transition duration-300 hover:scale-105">
                      <div className="flex items-center space-x-2 text-green-800 text-sm font-medium animate-fade-in">
                        <span className="text-xl">⏱️</span>
                        <span>
                          Validation completed in{" "}
                          <span className="font-bold text-green-700">
                            {bulkTimeTaken}
                          </span>{" "}
                          seconds
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </section>

            {/* Results Section */}
            {results.length > 0 && (
              <section className="py-20 px-6 bg-white">
                <h2 className="text-3xl font-bold text-center mb-12 animate-fade-in">
                  Validation Results
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-10 max-w-6xl mx-auto">
                  {results.map((file, idx) => {
                    // Enhanced data with all categories - SHOW ALL EVEN IF 0
                    const detailedData = [
                      { name: "Safe (Valid)", value: file.safe || 0, color: "#22c55e" },
                      { name: "Role (Valid)", value: file.role || 0, color: "#84cc16" },
                      { name: "Catch All", value: file.catch_all || 0, color: "#eab308" },
                      { name: "Disposable", value: file.disposable || 0, color: "#f59e0b" },
                      { name: "Inbox Full", value: file.inbox_full || 0, color: "#fb923c" },
                      { name: "Spam Trap", value: file.spam_trap || 0, color: "#f97316" },
                      { name: "Disabled", value: file.disabled || 0, color: "#ef4444" },
                      { name: "Invalid", value: file.invalid || 0, color: "#dc2626" },
                      { name: "Unknown", value: file.unknown || 0, color: "#9ca3af" },
                    ]; // Show all categories, even with 0 values

                    return (
                      <div
                        key={idx}
                        className="bg-white rounded-xl shadow-lg p-6 border border-slate-200 hover:shadow-xl transition animate-fade-in delay-300"
                      >
                        <h3 className="text-xl font-semibold mb-1 text-indigo-700">
                          {file.file}
                        </h3>
                        <p className="text-sm text-gray-500 mb-4">
                          Total Emails: {file.total}
                        </p>

                        {/* Donut Chart with Legend */}
                        <div className="flex items-center justify-center gap-6">
                          <ResponsiveContainer width="60%" height={300}>
                            <PieChart>
                              <Pie
                                data={detailedData}
                                dataKey="value"
                                nameKey="name"
                                cx="50%"
                                cy="50%"
                                innerRadius={60}
                                outerRadius={100}
                              >
                                {detailedData.map((entry, index) => (
                                  <Cell key={`cell-${index}`} fill={entry.color} />
                                ))}
                              </Pie>
                              <Tooltip />
                              <text
                                x="50%"
                                y="50%"
                                textAnchor="middle"
                                dominantBaseline="middle"
                                className="text-2xl font-bold fill-gray-700"
                              >
                                total
                              </text>
                              <text
                                x="50%"
                                y="58%"
                                textAnchor="middle"
                                dominantBaseline="middle"
                                className="text-3xl font-bold fill-gray-800"
                              >
                                {file.total}
                              </text>
                            </PieChart>
                          </ResponsiveContainer>

                          {/* Legend */}
                          <div className="flex flex-col gap-2 text-sm">
                            {detailedData.map((item, index) => (
                              <div key={index} className="flex items-center gap-2">
                                <div
                                  className="w-4 h-4 rounded"
                                  style={{ backgroundColor: item.color }}
                                ></div>
                                <span className="text-gray-700">
                                  {item.name}: <span className="font-semibold">{item.value}</span>
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>

                        <div className="mt-6 space-y-2 text-sm">
                          <a
                            href={`${API_BASE_URL}${file.validated_download}`}
                            className="text-blue-600 hover:text-blue-800 underline block font-medium"
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            📥 Download All Emails
                          </a>
                          <a
                            href={`${API_BASE_URL}/download-valid/${file.validated_download.split('/').pop()}`}
                            className="text-green-600 hover:text-green-800 underline block font-medium"
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            ✅ Download Valid Only
                          </a>
                          <a
                            href={`${API_BASE_URL}/download-invalid/${file.validated_download.split('/').pop()}`}
                            className="text-red-600 hover:text-red-800 underline block font-medium"
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            ❌ Download Invalid Only
                          </a>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            )}

            {/* Validation History Table */}
            <section className="py-10 px-6 bg-gray-50">
              <h2 className="text-3xl font-bold text-center mb-8 text-gray-900">
                Validation History
              </h2>

              {validationTasks.length === 0 ? (
                <p className="text-center text-gray-500">No validation history yet. Upload a CSV file to get started!</p>
              ) : (
                <div className="overflow-x-auto bg-white rounded-lg shadow">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-100 border-b">
                      <tr>
                        <th className="px-6 py-3 text-left font-semibold text-gray-700">TASK ID</th>
                        <th className="px-6 py-3 text-left font-semibold text-gray-700">DATE STARTED</th>
                        <th className="px-6 py-3 text-left font-semibold text-gray-700">TASK NAME</th>
                        <th className="px-6 py-3 text-left font-semibold text-gray-700">STATUS</th>
                        <th className="px-6 py-3 text-left font-semibold text-gray-700">TOTAL EMAILS</th>
                        <th className="px-6 py-3 text-left font-semibold text-gray-700">CURRENT PROGRESS</th>
                        <th className="px-6 py-3 text-left font-semibold text-gray-700">ACTION</th>
                      </tr>
                    </thead>
                    <tbody>
                      {validationTasks.map((task) => (
                        <tr key={task.id} className="border-b hover:bg-gray-50">
                          <td className="px-6 py-4 text-gray-900">{task.task_id.substring(0, 7)}</td>
                          <td className="px-6 py-4 text-gray-600">
                            {new Date(task.created_at).toLocaleString('en-US', {
                              hour: '2-digit',
                              minute: '2-digit',
                              day: '2-digit',
                              month: '2-digit',
                              year: 'numeric'
                            })}
                          </td>
                          <td className="px-6 py-4 text-gray-900">{task.filename}</td>
                          <td className="px-6 py-4">
                            <span className="px-3 py-1 rounded-full text-xs font-semibold bg-green-100 text-green-700">
                              {task.status}
                            </span>
                          </td>
                          <td className="px-6 py-4 text-gray-900 text-center">{task.total_emails}</td>
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-2">
                              <div className="flex-1 bg-gray-200 rounded-full h-2">
                                <div
                                  className="bg-blue-600 h-2 rounded-full"
                                  style={{ width: `${task.progress}%` }}
                                ></div>
                              </div>
                              <span className="text-blue-600 font-semibold">{task.progress}%</span>
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex gap-2">
                              <button
                                onClick={() => setSelectedBulkTask(task)}
                                className="text-blue-600 hover:text-blue-800 font-medium"
                              >
                                Details
                              </button>
                              <span className="text-gray-300">/</span>
                              <a
                                href={`${API_BASE_URL}${task.download_url}`}
                                className="text-blue-600 hover:text-blue-800 font-medium"
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                Download
                              </a>
                              <span className="text-gray-300">/</span>
                              <button
                                onClick={async () => {
                                  if (window.confirm('Are you sure you want to delete this task?')) {
                                    try {
                                      const token = localStorage.getItem("token");
                                      await axios.delete(`${API_BASE_URL}/user/validation-task/${task.task_id}`, {
                                        headers: { Authorization: `Bearer ${token}` }
                                      });
                                      setValidationTasks(validationTasks.filter(t => t.id !== task.id));
                                    } catch (err) {
                                      console.error("Error deleting task:", err);
                                      alert("Failed to delete task");
                                    }
                                  }
                                }}
                                className="text-red-600 hover:text-red-800 font-medium"
                              >
                                Delete
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            {/* Details Modal for Bulk Task */}
            {selectedBulkTask && (
              <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                <div className="bg-white rounded-2xl max-w-4xl w-full shadow-2xl">
                  <div className="p-6 border-b border-gray-200 flex justify-between items-center">
                    <h2 className="text-2xl font-bold text-gray-800">Task Details - {selectedBulkTask.filename}</h2>
                    <button
                      onClick={() => setSelectedBulkTask(null)}
                      className="text-gray-500 hover:text-gray-700 text-2xl font-bold"
                    >
                      ×
                    </button>
                  </div>

                  <div className="p-6">
                    <div className="flex items-center justify-center gap-6">
                      <ResponsiveContainer width="60%" height={300}>
                        <PieChart>
                          <Pie
                            data={[
                              { name: "Safe (Valid)", value: selectedBulkTask.safe || 0, color: "#22c55e" },
                              { name: "Role-based", value: selectedBulkTask.role || 0, color: "#84cc16" },
                              { name: "Catch All", value: selectedBulkTask.catch_all || 0, color: "#eab308" },
                              { name: "Disposable", value: selectedBulkTask.disposable || 0, color: "#f59e0b" },
                              { name: "Inbox Full", value: selectedBulkTask.inbox_full || 0, color: "#fb923c" },
                              { name: "Disabled", value: selectedBulkTask.disabled || 0, color: "#ef4444" },
                              { name: "Invalid", value: selectedBulkTask.invalid || 0, color: "#dc2626" },
                              { name: "Risky", value: selectedBulkTask.unknown || 0, color: "#f97316" },
                            ]}
                            dataKey="value"
                            nameKey="name"
                            cx="50%"
                            cy="50%"
                            innerRadius={60}
                            outerRadius={100}
                          >
                            {[
                              { name: "Safe (Valid)", value: selectedBulkTask.safe || 0, color: "#22c55e" },
                              { name: "Role-based", value: selectedBulkTask.role || 0, color: "#84cc16" },
                              { name: "Catch All", value: selectedBulkTask.catch_all || 0, color: "#eab308" },
                              { name: "Disposable", value: selectedBulkTask.disposable || 0, color: "#f59e0b" },
                              { name: "Inbox Full", value: selectedBulkTask.inbox_full || 0, color: "#fb923c" },
                              { name: "Disabled", value: selectedBulkTask.disabled || 0, color: "#ef4444" },
                              { name: "Invalid", value: selectedBulkTask.invalid || 0, color: "#dc2626" },
                              { name: "Risky", value: selectedBulkTask.unknown || 0, color: "#f97316" },
                            ].map((entry, index) => (
                              <Cell key={`cell-${index}`} fill={entry.color} />
                            ))}
                          </Pie>
                          <Tooltip />
                          <text
                            x="50%"
                            y="50%"
                            textAnchor="middle"
                            dominantBaseline="middle"
                            className="text-2xl font-bold fill-gray-700"
                          >
                            total
                          </text>
                          <text
                            x="50%"
                            y="58%"
                            textAnchor="middle"
                            dominantBaseline="middle"
                            className="text-3xl font-bold fill-gray-800"
                          >
                            {selectedBulkTask.total_emails}
                          </text>
                        </PieChart>
                      </ResponsiveContainer>

                      <div className="flex flex-col gap-2 text-sm">
                        {[
                          { name: "Safe (Valid)", value: selectedBulkTask.safe || 0, color: "#22c55e" },
                          { name: "Role-based", value: selectedBulkTask.role || 0, color: "#84cc16" },
                          { name: "Catch All", value: selectedBulkTask.catch_all || 0, color: "#eab308" },
                          { name: "Disposable", value: selectedBulkTask.disposable || 0, color: "#f59e0b" },
                          { name: "Inbox Full", value: selectedBulkTask.inbox_full || 0, color: "#fb923c" },
                          { name: "Disabled", value: selectedBulkTask.disabled || 0, color: "#ef4444" },
                          { name: "Invalid", value: selectedBulkTask.invalid || 0, color: "#dc2626" },
                          { name: "Risky", value: selectedBulkTask.unknown || 0, color: "#f97316" },
                        ].map((item, index) => (
                          <div key={index} className="flex items-center gap-2">
                            <div
                              className="w-4 h-4 rounded"
                              style={{ backgroundColor: item.color }}
                            ></div>
                            <span className="text-gray-700">
                              {item.name}: <span className="font-semibold">{item.value}</span>
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Download Section */}
                  <div className="p-6 border-t border-gray-200 bg-gray-50">
                    <h3 className="text-lg font-semibold text-gray-800 mb-4">📥 Download Options</h3>
                    <div className="flex flex-wrap gap-3 justify-center">
                      <a
                        href={`${API_BASE_URL}${selectedBulkTask.download_url}`}
                        className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg shadow transition duration-200"
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        📥 Download All Emails
                      </a>
                      <a
                        href={`${API_BASE_URL}/download-valid/${selectedBulkTask.download_url.split('/').pop()}`}
                        className="px-6 py-2.5 bg-green-600 hover:bg-green-700 text-white font-medium rounded-lg shadow transition duration-200"
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        ✅ Download Valid Only
                      </a>
                      <a
                        href={`${API_BASE_URL}/download-invalid/${selectedBulkTask.download_url.split('/').pop()}`}
                        className="px-6 py-2.5 bg-red-600 hover:bg-red-700 text-white font-medium rounded-lg shadow transition duration-200"
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        ❌ Download Invalid Only
                      </a>
                    </div>
                  </div>

                  <div className="p-4 text-center border-t border-gray-200">
                    <button
                      onClick={() => setSelectedBulkTask(null)}
                      className="px-8 py-2.5 bg-gray-600 hover:bg-gray-700 text-white font-semibold rounded-lg shadow-md transition duration-200"
                    >
                      Close
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )
        }

        {/* Other Tabs Placeholder */}
        {
          selectedTab === "dashboard" && (
            <div className="p-10 text-2xl font-semibold text-center">
              📊 More things will be added soon......
            </div>
          )
        }

        {
          selectedTab === "profile" && (
            <div className="p-8 max-w-4xl mx-auto space-y-12">
              {/* Section 1: User Details */}
              <section className="bg-white rounded-xl shadow-lg p-8">
                <h2 className="text-2xl font-bold text-gray-800 mb-6">
                  👤 User Details
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      Full Name
                    </label>
                    <input
                      type="text"
                      placeholder="Enter your name"
                      className="mt-2 w-full rounded-lg border border-gray-300 px-4 py-3 focus:ring-2 focus:ring-blue-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      Email Address
                    </label>
                    <input
                      type="email"
                      placeholder="Enter your email"
                      className="mt-2 w-full rounded-lg border border-gray-300 px-4 py-3 focus:ring-2 focus:ring-blue-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      Change Password
                    </label>
                    <input
                      type="password"
                      placeholder="New password"
                      className="mt-2 w-full rounded-lg border border-gray-300 px-4 py-3 focus:ring-2 focus:ring-blue-500 focus:outline-none"
                    />
                  </div>
                </div>
              </section>

              {/* Section 2: Account Preferences */}
              <section className="bg-white rounded-xl shadow-lg p-8">
                <h2 className="text-2xl font-bold text-gray-800 mb-6">
                  ⚙️ Account Preferences
                </h2>
                <div className="space-y-4">
                  <label className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      className="h-5 w-5 text-blue-600 rounded border-gray-300"
                    />
                    <span className="text-gray-700">
                      Receive Email Notifications
                    </span>
                  </label>
                  <label className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      className="h-5 w-5 text-blue-600 rounded border-gray-300"
                    />
                    <span className="text-gray-700">Enable Dark Mode</span>
                  </label>
                  <label className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      className="h-5 w-5 text-blue-600 rounded border-gray-300"
                    />
                    <span className="text-gray-700">
                      Two-Factor Authentication
                    </span>
                  </label>
                </div>
                <div className="mt-6 text-right">
                  <button
                    type="button"
                    className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-lg shadow transition"
                  >
                    Save Changes
                  </button>
                </div>
              </section>

              {/* Section 3: Account Controls */}
              <section className="bg-white rounded-xl shadow-lg p-8">
                <h2 className="text-2xl font-bold text-gray-800 mb-6">
                  🚨 Account Controls
                </h2>
                <p className="text-gray-600 mb-6">
                  Manage your account status. You can deactivate your account
                  temporarily or delete it permanently.
                </p>
                <div className="flex flex-col sm:flex-row gap-4">
                  <button
                    type="button"
                    className="flex-1 py-3 bg-yellow-100 text-yellow-700 border border-yellow-300 hover:bg-yellow-200 font-semibold rounded-lg shadow-sm transition"
                  >
                    Deactivate Account
                  </button>
                  <button
                    type="button"
                    className="flex-1 py-3 bg-red-100 text-red-700 border border-red-300 hover:bg-red-200 font-semibold rounded-lg shadow-sm transition"
                  >
                    Delete Account
                  </button>
                </div>
              </section>
            </div>
          )
        }
        {
          selectedTab === "subscription" && (


            <div className="p-6 space-y-8">
              <h2 className="text-3xl font-bold text-center mb-8">
                Upgrade Your Plan
              </h2>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-5xl mx-auto">
                {/* Free Plan */}
                <div className="bg-white rounded-xl shadow-lg p-6 border border-gray-200 text-center">
                  <h3 className="text-2xl font-semibold mb-4">Free Plan</h3>
                  <p className="text-gray-600 mb-6">
                    Limited to 50 emails/month & 1 file upload
                  </p>
                  <p className="text-lg font-bold mb-4">Free</p>
                  <button
                    disabled
                    className="px-6 py-3 bg-gray-400 text-white font-semibold rounded-lg cursor-not-allowed"
                  >
                    Current Plan
                  </button>
                </div>

                {/* Pro Plan */}
                <div className="bg-white rounded-xl shadow-lg p-6 border border-gray-200 text-center">
                  <h3 className="text-2xl font-semibold mb-4">Pro Plan</h3>
                  <p className="text-gray-600 mb-6">
                    Unlimited validations & uploads
                  </p>
                  <p className="text-lg font-bold mb-4">$19.99 / month</p>
                  <button
                    onClick={() => alert("Payment Integration Coming Soon!")}
                    className="px-6 py-3 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition"
                  >
                    Subscribe Now
                  </button>
                </div>
              </div>
            </div>
          )
        }
      </main >
    </div >
  );
};

export default Dashboard;
