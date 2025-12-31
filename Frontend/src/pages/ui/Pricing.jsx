import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { API_BASE_URL } from "../../config/api";

const creditOptions = [
  "2K",
  "5K",
  "10K",
  "25K",
  "50K",
  "100K",
  "250K",
  "500K",
  "1M",
  "2M",
  "5M",
  "5M+",
];

const Pricing = () => {
  const navigate = useNavigate();
  const [credits, setCredits] = useState("2K");
  const [billingCycle, setBillingCycle] = useState("monthly");
  const [customPrices, setCustomPrices] = useState(["25,000", "10,000", "100"]);
  const [showModal, setShowModal] = useState(false);
  const [loading, setLoading] = useState(false);
  const [currentCredits, setCurrentCredits] = useState(null);
  const [selectedPlan, setSelectedPlan] = useState(null);

  // Parse credits to number
  const parseCredits = (value) => {
    if (value.endsWith("K")) return parseInt(value) * 1000;
    if (value.endsWith("M")) return parseInt(value) * 1000000;
    if (value.includes("+")) return parseInt(value) * 1000000;
    return parseInt(value);
  };

  const pricePerCredit = 0.01;
  const creditAmount = parseCredits(credits);
  const price = (creditAmount * pricePerCredit).toFixed(2);

  // Fetch current credits
  useEffect(() => {
    const fetchCredits = async () => {
      try {
        const token = localStorage.getItem("token");
        if (!token) return;

        const response = await fetch(`${API_BASE_URL}/user/credits`, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (response.ok) {
          const data = await response.json();
          setCurrentCredits(data.credits);
        }
      } catch (err) {
        console.error("Failed to fetch credits:", err);
      }
    };

    fetchCredits();
  }, []);

  // Handle Pay-As-You-Go purchase
  const handlePayAsYouGo = () => {
    setSelectedPlan({
      type: "payasyougo",
      credits: creditAmount,
      price: parseFloat(price),
      name: `${credits} Credits`,
    });
    setShowModal(true);
  };

  // Handle subscription plan purchase
  const handleSubscriptionPlan = (planType) => {
    let planCredits, planPrice, planName;

    if (planType === "freemium") {
      planCredits = 500;
      planPrice = 0;
      planName = "Freemium Plan";
    } else if (planType === "one") {
      planCredits = 25000;
      planPrice = billingCycle === "monthly" ? 99 : 79;
      planName = "ZeroBounce ONE";
    } else if (planType === "custom") {
      planCredits = customPrices.reduce((sum, val) => sum + (parseInt(val.replace(/,/g, "")) || 0), 0);
      planPrice = billingCycle === "monthly" ? 274 : 219;
      planName = "ZeroBounce ONE Custom";
    }

    setSelectedPlan({
      type: "subscription",
      credits: planCredits,
      price: planPrice,
      name: planName,
      billing: billingCycle,
    });
    setShowModal(true);
  };

  // Handle purchase confirmation
  const handleConfirmPurchase = async () => {
    if (!selectedPlan) return;
    setLoading(true);

    try {
      const token = localStorage.getItem("token");
      if (!token) {
        throw new Error("Not authenticated. Please login.");
      }

      const requestBody = {
        credits: selectedPlan.credits,
        price: selectedPlan.price,
        user_id: 1,
        plan: selectedPlan.type === "subscription" ? "monthly" : "instant",
        package_name: selectedPlan.name,
      };

      const response = await fetch(`${API_BASE_URL}/api/credits/buy`, {
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
      setCurrentCredits(data.new_balance);

      // Show success message
      alert(`✅ Purchase successful!\nOrder ID: ${data.order_id}\nCredits: ${data.credits_purchased.toLocaleString()}\nNew Balance: ${data.new_balance.toLocaleString()}`);

      setShowModal(false);
    } catch (err) {
      alert(`❌ Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleCustomChange = (index, value) => {
    const updated = [...customPrices];
    updated[index] = value;
    setCustomPrices(updated);
  };

  const handleAddCustom = () => setCustomPrices([...customPrices, ""]);

  const handleRemoveCustom = (index) =>
    setCustomPrices(customPrices.filter((_, i) => i !== index));

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-20">
      {/* Back to Dashboard Button */}
      <button
        onClick={() => navigate('/dashboard')}
        className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors shadow-md"
      >
        <svg 
          xmlns="http://www.w3.org/2000/svg" 
          className="h-5 w-5" 
          viewBox="0 0 20 20" 
          fill="currentColor"
        >
          <path 
            fillRule="evenodd" 
            d="M9.707 16.707a1 1 0 01-1.414 0l-6-6a1 1 0 010-1.414l6-6a1 1 0 011.414 1.414L5.414 9H17a1 1 0 110 2H5.414l4.293 4.293a1 1 0 010 1.414z" 
            clipRule="evenodd" 
          />
        </svg>
        Back to Dashboard
      </button>

      {/* Current Balance Display */}
      {currentCredits !== null && (
        <div className="fixed top-6 right-6 bg-white rounded-xl shadow-lg px-6 py-3 border-2 border-blue-500 z-50">
          <p className="text-sm text-gray-600">Current Balance</p>
          <p className="text-2xl font-bold text-blue-600">
            {currentCredits.toLocaleString()} Credits
          </p>
        </div>
      )}

      {/* SECTION 1: Pay-As-You-Go */}
      <div>
        <h1 className="text-4xl font-bold mb-2">
          <span className="text-blue-600">Simple pricing</span> for everyone
        </h1>
        <p className="text-gray-600 mb-6">
          Get credits any time with Pay-As-You-Go or subscribe and save for
          ongoing email validation.
        </p>

        {/* Pricing Card */}
        <div className="border rounded-lg shadow p-6 flex flex-col md:flex-row justify-between items-center gap-6">
          <div className="flex-1">
            <h2 className="text-blue-600 font-semibold mb-2">
              Pay-as-You-Go Credits
            </h2>
            <input
              type="text"
              value={credits}
              onChange={(e) => setCredits(e.target.value)}
              className="border border-blue-400 rounded px-3 py-2 w-full mb-4"
            />
            <p className="text-gray-500 mb-4">
              Our minimum purchase size is 2,000 credits
            </p>

            <div className="grid grid-cols-4 gap-2">
              {creditOptions.map((option) => (
                <button
                  key={option}
                  className={`border rounded px-2 py-1 text-blue-600 hover:bg-blue-100 ${
                    credits === option ? "bg-blue-100 font-semibold" : ""
                  }`}
                  onClick={() => setCredits(option)}
                >
                  {option} Credits
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col items-center justify-center border-t pt-6 md:border-t-0 md:border-l md:pl-6">
            <span className="text-blue-600 font-semibold mb-2 text-center">
              Subscribe & <br /> Save 15%
            </span>
            <h3 className="text-4xl font-bold mb-1">${price}</h3>
            <p className="text-gray-500 mb-4 text-sm">
              ${pricePerCredit.toFixed(2)}/credit
            </p>
            <button
              onClick={handlePayAsYouGo}
              className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700"
            >
              Get Started
            </button>
          </div>
        </div>
      </div>

      {/* SECTION 2: Subscription Plans */}
      <div>
        <h2 className="text-4xl font-bold text-center mb-12">
          Increase your{" "}
          <span className="text-blue-600">email deliverability</span> with our
          advanced tools
        </h2>

        <div className="grid md:grid-cols-4 gap-10 items-start">
          {/* Sidebar */}
          <div className="md:col-span-1 space-y-6">
            <div className="bg-blue-50 text-blue-700 border border-blue-200 px-4 py-2 rounded-lg w-fit rotate-[-6deg]">
              <span className="font-semibold">
                Subscribe &<br /> Save 15%
              </span>
            </div>

            <ul className="space-y-4 text-gray-700">
              <li className="flex items-center gap-2">
                <span className="text-blue-600">🏷️</span> Save 15% on
                Pay-As-You-Go and Autopay
              </li>
              <li className="flex items-center gap-2">
                <span className="text-blue-600">📧</span> Email Validation /
                Email Scoring
              </li>
              <li className="flex items-center gap-2">
                <span className="text-blue-600">🔍</span> Email Finder / Domain
                Searches
              </li>
              <li className="flex items-center gap-2">
                <span className="text-blue-600">📬</span> Inbox Placement Tests
              </li>
            </ul>
          </div>

          {/* Pricing Plans */}
          <div className="md:col-span-3 space-y-8">
            {/* Billing Toggle */}
            <div className="flex justify-center bg-gray-100 p-1 rounded-full w-fit mx-auto">
              <button
                onClick={() => setBillingCycle("monthly")}
                className={`px-6 py-2 rounded-full font-medium ${
                  billingCycle === "monthly"
                    ? "bg-blue-600 text-white"
                    : "text-gray-700"
                }`}
              >
                Monthly
              </button>
              <button
                onClick={() => setBillingCycle("annually")}
                className={`px-6 py-2 rounded-full font-medium ${
                  billingCycle === "annually"
                    ? "bg-blue-600 text-white"
                    : "text-gray-700"
                }`}
              >
                Annually (Save 20%)
              </button>
            </div>

            {/* Cards */}
            <div className="grid md:grid-cols-3 gap-8">
              {/* Freemium */}
              <div className="border-2 border-blue-600 bg-blue-50 rounded-2xl p-6 shadow-lg hover:shadow-xl transition">
                <h3 className="text-xl font-semibold mb-2 text-center">
                  Freemium
                </h3>
                <p className="text-center text-gray-600 mb-4">
                  Test our product with no risk
                </p>
                <p className="text-4xl font-bold text-center mb-6">
                  $0<span className="text-lg">/mo</span>
                </p>
                <button
                  onClick={() => handleSubscriptionPlan("freemium")}
                  className="w-full py-3 bg-gray-200 text-gray-800 font-semibold rounded-xl hover:bg-gray-300 transition"
                >
                  Try for free
                </button>
                <ul className="mt-6 space-y-2 text-center">
                  <li>500 credits</li>
                  <li>200 emails</li>
                  <li>100 searches</li>
                  <li>50 verifications</li>
                  <li>10 tests</li>
                </ul>
              </div>

              {/* ZeroBounce ONE */}
              <div className="border-2 border-blue-600 bg-blue-50 rounded-2xl p-6 shadow-lg hover:shadow-xl transition relative">
                <span className="absolute -top-4 left-1/2 -translate-x-1/2 bg-yellow-400 text-sm font-semibold px-3 py-1 rounded-full">
                  BEST VALUE
                </span>
                <h3 className="text-xl font-semibold mb-2 text-center mt-2">
                  ZeroBounce ONE
                </h3>
                <p className="text-center text-gray-600 mb-4">
                  All products for the price of ONE
                </p>
                <p className="text-4xl font-bold text-center mb-6">
                  {billingCycle === "monthly" ? "$99" : "$79"}
                  <span className="text-lg">/mo</span>
                </p>
                <button
                  onClick={() => handleSubscriptionPlan("one")}
                  className="w-full py-3 bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition"
                >
                  Get Started
                </button>
                <ul className="mt-6 space-y-2 text-center">
                  <li>25,000 credits</li>
                  <li>20,000 emails</li>
                  <li>10,000 searches</li>
                  <li>5,000 verifications</li>
                  <li>1,000 tests</li>
                </ul>
              </div>

              {/* ZeroBounce ONE Custom */}
              <div className="border-2 border-blue-600 bg-blue-50 rounded-2xl p-6 shadow-lg hover:shadow-xl transition relative">
                <span className="absolute -top-4 left-1/2 -translate-x-1/2 bg-yellow-400 text-sm font-semibold px-6 py-1 rounded-full min-w-[220px] text-center">
                  MORE CUSTOMIZATION
                </span>
                <h3 className="text-xl font-semibold mb-2 text-center mt-2">
                  Custom Plan
                </h3>
                <p className="text-center text-gray-600 mb-4">
                  Tailored to fit your needs
                </p>
                <p className="text-4xl font-bold text-center mb-6">
                  {billingCycle === "monthly" ? "$274" : "$219"}
                  <span className="text-lg">/mo</span>
                </p>
                <button
                  onClick={() => handleSubscriptionPlan("custom")}
                  className="w-full py-3 bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition"
                >
                  Get Started
                </button>

                <div className="mt-6 space-y-2 text-center max-w-xs mx-auto">
                  <ul className="space-y-2">
                    {customPrices.map((price, idx) => (
                      <li
                        key={idx}
                        className="flex justify-center items-center gap-2"
                      >
                        <input
                          type="text"
                          value={price}
                          onChange={(e) =>
                            handleCustomChange(idx, e.target.value)
                          }
                          className="text-center border border-blue-300 rounded-lg px-2 py-1 w-28 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                        <button
                          onClick={() => handleRemoveCustom(idx)}
                          className="px-2 py-1 bg-red-500 text-white rounded-lg hover:bg-red-600 transition"
                        >
                          ✕
                        </button>
                      </li>
                    ))}
                  </ul>
                  <button
                    onClick={handleAddCustom}
                    className="mt-2 px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition"
                  >
                    + Add Price
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Purchase Confirmation Modal */}
      <AnimatePresence>
        {showModal && selectedPlan && (
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
              className="bg-white rounded-2xl shadow-xl p-8 w-full max-w-md border border-gray-200"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">
                Confirm Purchase
              </h2>
              
              <div className="bg-blue-50 rounded-lg p-4 mb-6">
                <h3 className="font-semibold text-lg mb-2">{selectedPlan.name}</h3>
                <p className="text-gray-700">
                  Credits: <span className="font-semibold">{selectedPlan.credits.toLocaleString()}</span>
                </p>
                <p className="text-gray-700">
                  Price: <span className="font-semibold text-blue-600">${selectedPlan.price}</span>
                </p>
                {selectedPlan.billing && (
                  <p className="text-gray-700">
                    Billing: <span className="font-semibold capitalize">{selectedPlan.billing}</span>
                  </p>
                )}
              </div>

              {currentCredits !== null && (
                <div className="bg-gray-50 rounded-lg p-4 mb-6">
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-gray-600">Current Balance:</span>
                    <span className="font-semibold">
                      {currentCredits.toLocaleString()}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-gray-600">New Credits:</span>
                    <span className="font-semibold text-green-600">
                      +{selectedPlan.credits.toLocaleString()}
                    </span>
                  </div>
                  <div className="border-t pt-2 flex justify-between text-sm">
                    <span className="text-gray-600">New Balance:</span>
                    <span className="font-bold text-blue-600">
                      {(currentCredits + selectedPlan.credits).toLocaleString()}
                    </span>
                  </div>
                </div>
              )}

              <div className="flex justify-end space-x-3">
                <button
                  onClick={() => setShowModal(false)}
                  disabled={loading}
                  className="px-6 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfirmPurchase}
                  disabled={loading}
                  className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
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
};

export default Pricing;