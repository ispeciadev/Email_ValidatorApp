// Pricing.jsx
import { useState } from "react";

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

const Pricingg = () => {
  const [credits, setCredits] = useState("2000");
  const [billingCycle, setBillingCycle] = useState("monthly");
  const [customPrices, setCustomPrices] = useState(["25,000", "10,000", "100"]);

  // Convert credits to number for price calculation
  const parseCredits = (value) => {
    if (value.endsWith("K")) return parseInt(value) * 1000;
    if (value.endsWith("M")) return parseInt(value) * 1000000;
    if (value.includes("+")) return parseInt(value) * 1000000; // for 5M+
    return parseInt(value);
  };

  const pricePerCredit = 0.01;
  const price = (parseCredits(credits) * pricePerCredit).toFixed(2);

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
          {/* Input and Buttons */}
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

          {/* Price Box */}
          <div className="flex flex-col items-center justify-center border-t pt-6 md:border-t-0 md:border-l md:pl-6">
            <span className="text-blue-600 font-semibold mb-2 text-center">
              Subscribe & <br /> Save 15%
            </span>
            <h3 className="text-4xl font-bold mb-1">${price}</h3>
            <p className="text-gray-500 mb-4 text-sm">
              ${pricePerCredit.toFixed(2)}/credit
            </p>
            <button className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700">
              Get Started
            </button>
          </div>
        </div>
      </div>

      {/* SECTION 2: Subscription Plans */}
      <div>
        {/* Heading */}
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
              <div className="border-2 border-blue-600 bg-blue-50 rounded-2xl p-6 shadow-lg hover:shadow-xl transition relative">
                <h3 className="text-xl font-semibold mb-2 text-center">
                  Freemium
                </h3>
                <p className="text-center text-gray-600 mb-4">
                  Test our product with no risk
                </p>
                <p className="text-4xl font-bold text-center mb-6">
                  $0<span className="text-lg">/mo</span>
                </p>
                <button className="w-full py-3 bg-gray-200 text-gray-800 font-semibold rounded-xl hover:bg-gray-300 transition">
                  Try for free
                </button>
                <ul className="mt-6 space-y-2 text-center">
                  <li>500</li>
                  <li>200</li>
                  <li>100</li>
                  <li>50</li>
                  <li>10</li>
                </ul>
              </div>

              {/* ZeroBounce ONE */}
              <div className="border-2 border-blue-600 bg-blue-50 rounded-2xl p-6 shadow-lg hover:shadow-xl transition relative">
                <span className="absolute -top-4 left-1/2 -translate-x-1/2 bg-yellow-400 text-sm font-semibold px-3 py-1 rounded-full">
                  BEST VALUE
                </span>
                <br></br>
                <p className="text-center text-gray-600 mb-4">
                  All products for the price of ONE
                </p>
                <p className="text-4xl font-bold text-center mb-6">
                  {billingCycle === "monthly" ? "$99" : "$79"}
                  <span className="text-lg">/mo</span>
                </p>
                <button className="w-full py-3 bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition">
                  Get Started
                </button>
                <ul className="mt-6 space-y-2 text-center">
                  <li>25,000</li>
                  <li>20,000</li>
                  <li>10,000</li>
                  <li>5000</li>
                  <li>1000</li>
                </ul>
              </div>

              {/* ZeroBounce ONE Custom */}
              <div className="border-2 border-blue-600 bg-blue-50 rounded-2xl p-6 shadow-lg hover:shadow-xl transition relative">
                <span className="absolute -top-4 left-1/2 -translate-x-1/2 bg-yellow-400 text-sm font-semibold px-6 py-1 rounded-full min-w-[220px] text-center">
                  MORE CUSTOMIZATION
                </span><br></br>

                <p className="text-center text-gray-600 mb-4">
                  Tailored to fit your needs
                </p><br></br>
                <p className="text-4xl font-bold text-center mb-6">
                  {billingCycle === "monthly" ? "$274" : "$219"}
                  <span className="text-lg">/mo</span>
                </p>
                <button className="w-full py-3 bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition">
                  Get Started
                </button>

                {/* Editable Prices */}
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
                          className="px-2 py-1 md-red-500 text-white rounded-lg hover:bg-red-600 transition"
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
    </div>
  );
};

export default Pricingg;
