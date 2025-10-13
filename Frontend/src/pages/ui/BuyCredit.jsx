// BuyCredits.jsx - Complete Integration
import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import toast, { Toaster } from "react-hot-toast";
import { useNavigate } from "react-router-dom";

const creditOptions = [
  { credits: 2000, price: 5 },
  { credits: 5000, price: 10 },
  { credits: 10000, price: 18 },
  { credits: 25000, price: 40, popular: true },
  { credits: 50000, price: 70 },
  { credits: 100000, price: 120 },
];

export default function BuyCredits() {
  const navigate = useNavigate();
  const [selected, setSelected] = useState(creditOptions[3]); // Default to most popular
  const [showModal, setShowModal] = useState(false);
  const [currentCredits, setCurrentCredits] = useState(null);
  const [loading, setLoading] = useState(false);

  // -------------------- Monthly Subscription --------------------
  const [creditsPerDay, setCreditsPerDay] = useState(20);
  const baseRate = 0.05; // $0.05 per credit
  const monthlyCredits = creditsPerDay * 30;
  const monthlyCost = (monthlyCredits * baseRate).toFixed(2);

  const discount = creditsPerDay >= 500 ? 20 : creditsPerDay >= 200 ? 10 : 0;
  const finalCost = (monthlyCost - (monthlyCost * discount) / 100).toFixed(2);

  // -------------------- Instant Credits (Lifetime) --------------------
  const [instantCredits, setInstantCredits] = useState(25000);
  const instantBaseRate = 0.0012;
  const instantCost = (instantCredits * instantBaseRate).toFixed(2);

  const instantDiscount =
    instantCredits >= 100000 ? 15 : instantCredits >= 50000 ? 8 : 1.13;
  const finalInstantCost = (
    instantCost -
    (instantCost * instantDiscount) / 100
  ).toFixed(2);

  // ======================= Fetch Current Credits =======================
  useEffect(() => {
    const fetchCredits = async () => {
      try {
        const token = localStorage.getItem("token");
        
        if (!token) {
          console.log("❌ No token found, redirecting to login");
          navigate("/login");
          return;
        }

        const response = await fetch("http://localhost:8000/user/credits", {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        if (!response.ok) {
          if (response.status === 401) {
            console.log("❌ Unauthorized, clearing token");
            localStorage.removeItem("token");
            navigate("/login");
            return;
          }
          throw new Error("Failed to fetch credits");
        }

        const data = await response.json();
        console.log("✅ Credits fetched:", data);
        setCurrentCredits(data.credits);
      } catch (err) {
        console.error("❌ Error fetching credits:", err);
        toast.error("Failed to load credit balance");
      }
    };

    fetchCredits();
  }, [navigate]);

  // ======================= Handle Instant Credit Purchase =======================
  const handleBuy = async () => {
    setLoading(true);
    console.log("\n📦 Starting credit purchase...");
    console.log("Selected package:", selected);

    try {
      const token = localStorage.getItem("token");

      if (!token) {
        throw new Error("Not authenticated");
      }

      console.log("🔑 Using token:", token.substring(0, 20) + "...");

      const requestBody = {
        credits: selected.credits,
        price: selected.price,
        user_id: 1,
        plan: "instant",
      };

      console.log("📤 Sending request:", requestBody);

      const response = await fetch("http://localhost:8000/api/credits/buy", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(requestBody),
      });

      console.log("📥 Response status:", response.status);

      if (!response.ok) {
        const errorData = await response.json();
        console.error("❌ Error response:", errorData);
        throw new Error(errorData.detail || "Purchase failed");
      }

      const data = await response.json();
      console.log("✅ Success response:", data);

      // Update local state
      setCurrentCredits(data.new_balance);

      // Show success toast
      toast.success(
        `🎉 Order #${data.order_id} confirmed!\n` +
        `Purchased ${data.credits_purchased.toLocaleString()} credits\n` +
        `New Balance: ${data.new_balance.toLocaleString()}`,
        { duration: 5000 }
      );

      // Close modal
      setShowModal(false);

      // Redirect after delay
      setTimeout(() => {
        navigate("/dashboard");
      }, 2000);

    } catch (err) {
      console.error("❌ Purchase error:", err);
      toast.error(err.message || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  // ======================= Handle Monthly Subscription =======================
  const handleSubscribe = async () => {
    setLoading(true);
    console.log("\n📅 Starting subscription...");

    try {
      const token = localStorage.getItem("token");

      if (!token) {
        throw new Error("Not authenticated");
      }

      const requestBody = {
        credits_per_day: creditsPerDay,
        monthly_cost: parseFloat(finalCost),
        discount: discount,
      };

      console.log("📤 Subscription request:", requestBody);

      const response = await fetch("http://localhost:8000/api/credits/subscribe", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Subscription failed");
      }

      const data = await response.json();
      console.log("✅ Subscription success:", data);

      // Update credits
      setCurrentCredits(data.new_balance);

      toast.success(
        `✅ Subscription activated!\n` +
        `${data.daily_credits} credits/day\n` +
        `Monthly: $${data.monthly_cost}`,
        { duration: 5000 }
      );

      setTimeout(() => {
        navigate("/dashboard");
      }, 2000);

    } catch (err) {
      console.error("❌ Subscription error:", err);
      toast.error(err.message || "Subscription failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  // ======================= Handle Instant Slider Purchase =======================
  const handleInstantPurchase = async () => {
    setLoading(true);
    console.log("\n💰 Instant credit purchase...");

    try {
      const token = localStorage.getItem("token");

      if (!token) {
        throw new Error("Not authenticated");
      }

      const requestBody = {
        credits: instantCredits,
        price: parseFloat(finalInstantCost),
        user_id: 1,
        plan: "instant",
      };

      console.log("📤 Request:", requestBody);

      const response = await fetch("http://localhost:8000/api/credits/buy", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Purchase failed");
      }

      const data = await response.json();
      console.log("✅ Success:", data);

      setCurrentCredits(data.new_balance);

      toast.success(
        `🎉 ${instantCredits.toLocaleString()} instant credits purchased!\n` +
        `New Balance: ${data.new_balance.toLocaleString()}`,
        { duration: 5000 }
      );

      setTimeout(() => {
        navigate("/dashboard");
      }, 2000);

    } catch (err) {
      console.error("❌ Error:", err);
      toast.error(err.message || "Purchase failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gradient-to-br from-gray-50 via-indigo-50 to-white px-6 relative overflow-hidden">
      <Toaster position="top-right" />

      {/* Decorative spotlight */}
      <div className="absolute w-[600px] h-[600px] bg-indigo-300 rounded-full blur-3xl opacity-20 -z-10 top-40 left-1/2 transform -translate-x-1/2"></div>

      {/* Navigation & Balance */}
      <div className="absolute top-6 w-full px-6 flex justify-between items-center max-w-7xl mx-auto">
        <button
          onClick={() => navigate("/dashboard")}
          className="px-4 py-2 bg-white text-gray-700 rounded-lg shadow hover:bg-gray-50 transition"
        >
          ← Back to Dashboard
        </button>

        {/* Current Balance Display */}
        {currentCredits !== null && (
          <div className="bg-white rounded-xl shadow-lg px-6 py-3 border-2 border-indigo-500">
            <p className="text-sm text-gray-600">Current Balance</p>
            <p className="text-2xl font-bold text-indigo-600">
              {currentCredits.toLocaleString()} Credits
            </p>
          </div>
        )}
      </div>

      {/* Header */}
      <div className="text-center max-w-2xl mb-12 mt-24">
        <motion.h1
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="text-4xl font-extrabold text-gray-900"
        >
          Buy Credits
        </motion.h1>
        <p className="mt-3 text-gray-600 text-lg">
          Choose the{" "}
          <span className="font-medium text-gray-800">perfect plan</span> for
          your email validation needs. Credits are{" "}
          <span className="text-indigo-600 font-semibold">
            instantly activated
          </span>{" "}
          after purchase.
        </p>
      </div>

      {/* Credit Options Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 max-w-4xl">
        {creditOptions.map((opt) => (
          <motion.div
            key={opt.credits}
            whileHover={{ scale: 1.03 }}
            onClick={() => setSelected(opt)}
            className={`relative cursor-pointer border rounded-2xl p-6 shadow-sm transition ${
              selected.credits === opt.credits
                ? "border-indigo-600 shadow-md bg-indigo-50"
                : "border-gray-200 bg-white hover:border-indigo-400"
            }`}
          >
            {opt.popular && (
              <span className="absolute -top-3 left-4 bg-indigo-600 text-white text-xs font-semibold px-3 py-1 rounded-full shadow-md">
                Most Popular
              </span>
            )}
            <h3 className="text-xl font-semibold text-gray-900">
              {opt.credits.toLocaleString()} Credits
            </h3>
            <p className="mt-2 text-indigo-600 font-bold text-2xl">
              ${opt.price}
            </p>
            <p className="mt-1 text-sm text-gray-500">One-time purchase</p>
          </motion.div>
        ))}
      </div>

      {/* Checkout CTA */}
      <button
        onClick={() => setShowModal(true)}
        disabled={loading}
        className="mt-10 px-8 py-3 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 transition shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {loading ? "Processing..." : "Proceed to Checkout"}
      </button>

      <p className="text-base font-medium text-gray-600 text-center mt-6">
        🔒 Secure checkout • Instant activation • No hidden fees
      </p>

      {/* Monthly + Instant Section */}
      <div className="grid md:grid-cols-2 gap-8 mt-12 max-w-6xl w-full">
        {/* Monthly Subscription */}
        <div className="bg-white shadow-md rounded-lg p-6 text-center">
          <h2 className="text-xl font-semibold mb-4 underline">
            Monthly Subscription
          </h2>
          <p className="text-4xl font-bold text-blue-600">
            {creditsPerDay}{" "}
            <span className="text-lg font-medium">credits / day</span>
          </p>
          <p className="text-gray-600 mb-4">
            You can use up to {monthlyCredits.toLocaleString()} credits per
            month
          </p>

          <input
            type="range"
            min="20"
            max="1000"
            step="10"
            value={creditsPerDay}
            onChange={(e) => setCreditsPerDay(Number(e.target.value))}
            className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer mb-4"
          />

          <p className="text-3xl font-bold text-gray-900">${finalCost}</p>
          <p className="text-gray-600">Monthly Total – You save {discount}%</p>

          <button
            onClick={handleSubscribe}
            disabled={loading}
            className="mt-4 bg-blue-600 text-white px-6 py-2 rounded-lg shadow hover:bg-blue-700 transition disabled:opacity-50"
          >
            {loading ? "Processing..." : "Subscribe Now"}
          </button>

          <div className="flex justify-center mt-4 space-x-3">
            <img
              src="https://img.icons8.com/color/48/visa.png"
              alt="Visa"
              className="w-10"
            />
            <img
              src="https://img.icons8.com/color/48/mastercard.png"
              alt="Mastercard"
              className="w-10"
            />
            <img
              src="https://img.icons8.com/color/48/paypal.png"
              alt="Paypal"
              className="w-10"
            />
          </div>
        </div>

        {/* Instant Credits (Lifetime) */}
        <div className="bg-white shadow-md rounded-lg p-6 text-center">
          <h2 className="text-lg font-semibold underline mb-4">
            Instant Credits (Lifetime)
          </h2>
          <p className="text-4xl font-bold text-blue-600">
            {instantCredits.toLocaleString()}
          </p>
          <p className="text-gray-600 mb-4">Instant credits never expire</p>

          <input
            type="range"
            min="25000"
            max="200000"
            step="5000"
            value={instantCredits}
            onChange={(e) => setInstantCredits(Number(e.target.value))}
            className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer mb-4"
          />

          <p className="text-3xl font-bold text-gray-900">
            ${finalInstantCost}
          </p>
          <p className="text-gray-600">
            Onetime Payment – You save {instantDiscount.toFixed(1)}%
          </p>

          <div className="flex justify-center mt-6 space-x-3">
            <button
              onClick={handleInstantPurchase}
              disabled={loading}
              className="bg-gray-900 text-white px-4 py-2 rounded-lg shadow hover:bg-gray-800 transition disabled:opacity-50"
            >
              {loading ? "Processing..." : "Regular Payment"}
            </button>
            <button
              disabled
              className="bg-gray-100 px-4 py-2 rounded-lg shadow opacity-50 cursor-not-allowed"
            >
              Crypto Payment (Soon)
            </button>
          </div>

          <div className="flex justify-center mt-4 space-x-3">
            <img
              src="https://img.icons8.com/color/48/visa.png"
              alt="Visa"
              className="w-10"
            />
            <img
              src="https://img.icons8.com/color/48/mastercard.png"
              alt="Mastercard"
              className="w-10"
            />
            <img
              src="https://img.icons8.com/color/48/paypal.png"
              alt="Paypal"
              className="w-10"
            />
            <img
              src="https://img.icons8.com/color/48/bitcoin.png"
              alt="Bitcoin"
              className="w-10 opacity-30"
            />
            <img
              src="https://img.icons8.com/color/48/ethereum.png"
              alt="Ethereum"
              className="w-10 opacity-30"
            />
          </div>

          <div className="flex justify-center items-center mt-4 space-x-2">
            <input type="checkbox" className="w-4 h-4" />
            <label className="text-gray-600 text-sm">
              Enable Automatic Monthly Top-Up and Save 10% from Next Month
            </label>
          </div>
        </div>
      </div>

      {/* Modal */}
      <AnimatePresence>
        {showModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 flex items-center justify-center bg-black/50 z-50"
            onClick={() => !loading && setShowModal(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              transition={{ duration: 0.3 }}
              className="bg-white rounded-2xl shadow-xl p-8 w-full max-w-sm border border-gray-200"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 className="text-xl font-semibold text-gray-900 mb-4">
                Confirm Purchase
              </h2>
              <p className="text-gray-700 mb-4">
                You are about to buy{" "}
                <span className="font-medium text-gray-900">
                  {selected.credits.toLocaleString()} credits
                </span>{" "}
                for{" "}
                <span className="font-semibold text-indigo-600">
                  ${selected.price}
                </span>
                .
              </p>

              {/* Balance Preview */}
              <div className="bg-gray-50 rounded-lg p-4 mb-4">
                <div className="flex justify-between text-sm mb-2">
                  <span className="text-gray-600">Current Balance:</span>
                  <span className="font-semibold">
                    {currentCredits?.toLocaleString() || 0}
                  </span>
                </div>
                <div className="flex justify-between text-sm mb-2">
                  <span className="text-gray-600">New Credits:</span>
                  <span className="font-semibold text-green-600">
                    +{selected.credits.toLocaleString()}
                  </span>
                </div>
                <div className="border-t pt-2 flex justify-between text-sm">
                  <span className="text-gray-600">New Balance:</span>
                  <span className="font-bold text-indigo-600">
                    {((currentCredits || 0) + selected.credits).toLocaleString()}
                  </span>
                </div>
              </div>

              <hr className="my-4" />
              <div className="flex justify-end space-x-3">
                <button
                  onClick={() => setShowModal(false)}
                  disabled={loading}
                  className="px-5 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleBuy}
                  disabled={loading}
                  className="px-5 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? "Processing..." : "Confirm Payment"}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}