import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import axios from "axios";
import { API_BASE_URL } from "../../config/api";

const SubscriberSubscribe = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const handleSubscribe = async (e) => {
    e.preventDefault();
    setLoading(true);
    setMessage("");

    try {
      // Replace this API with your backend subscription endpoint
      const response = await axios.post(`${API_BASE_URL}/subscriber/subscribe`, {
        email,
      });

      setMessage("Subscription successful! You can now login.");
      setTimeout(() => {
        navigate("/subscriber/login");
      }, 2000);

    } catch (error) {
      console.error(error);
      setMessage(error.response?.data?.message || "Subscription failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-r from-blue-50 to-blue-100 px-4">
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
        className="w-full max-w-md p-10 bg-white rounded-2xl shadow-2xl"
      >
        <h2 className="text-3xl font-bold mb-6 text-center text-blue-700">
          Subscribe
        </h2>

        <form onSubmit={handleSubscribe} className="space-y-6">
          <motion.div whileFocus={{ scale: 1.02 }}>
            <input
              type="email"
              placeholder="Enter your email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full p-4 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-400 focus:outline-none transition-all duration-300"
              required
            />
          </motion.div>

          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            type="submit"
            disabled={loading}
            className="w-full py-4 bg-green-600 text-white font-semibold rounded-lg shadow-md hover:bg-green-700 transition-all duration-300"
          >
            {loading ? "Subscribing..." : "Subscribe Now"}
          </motion.button>
        </form>

        {message && (
          <p className="mt-4 text-center text-blue-600 font-medium">{message}</p>
        )}
      </motion.div>
    </div>
  );
};

export default SubscriberSubscribe;
