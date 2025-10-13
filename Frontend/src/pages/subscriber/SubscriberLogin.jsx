import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { FaEye, FaEyeSlash } from "react-icons/fa";
import axios from "axios";

const SubscriberLogin = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const togglePassword = () => setShowPassword(!showPassword);

  const handleLogin = async (e) => {
    e.preventDefault();
    setErrorMessage("");
    setLoading(true);

    try {
      const response = await axios.post("http://localhost:8000/subscriber/login", {
        email,
        password,
      });

      const { token, role } = response.data;

      if (role !== "subscriber") {
        setErrorMessage("Unauthorized: Only subscribers can login.");
        setLoading(false);
        return;
      }

      // Save token & role
      localStorage.setItem("token", token);
      localStorage.setItem("user", JSON.stringify({ email, role }));

      // Navigate to subscriber dashboard
      navigate("/subscriber/dashboard");
    } catch (err) {
      console.error(err);
      setErrorMessage(
        err.response?.data?.message || "Invalid email or password."
      );
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
          Subscriber Login
        </h2>

        <form onSubmit={handleLogin} className="space-y-6">
          {/* Email */}
          <motion.div whileFocus={{ scale: 1.02 }}>
            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full p-4 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-400 focus:outline-none transition-all duration-300"
              required
            />
          </motion.div>

          {/* Password */}
          <motion.div className="relative" whileFocus={{ scale: 1.02 }}>
            <input
              type={showPassword ? "text" : "password"}
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full p-4 pr-12 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-400 focus:outline-none transition-all duration-300"
              required
            />
            <button
              type="button"
              onClick={togglePassword}
              className="absolute right-4 top-1/2 transform -translate-y-1/2 text-gray-500 hover:text-blue-600 transition"
            >
              {showPassword ? <FaEyeSlash /> : <FaEye />}
            </button>
          </motion.div>

          {errorMessage && (
            <p className="text-red-600 text-sm text-center">{errorMessage}</p>
          )}

          {/* Submit */}
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            type="submit"
            disabled={loading}
            className="w-full py-4 bg-blue-600 text-white font-semibold rounded-lg shadow-md hover:bg-blue-700 transition-all duration-300"
          >
            {loading ? "Logging in..." : "Login"}
          </motion.button>
        </form>

        <p className="mt-6 text-center text-sm text-gray-600">
          Don't have an account?{" "}
          <a href="/subscriber/signup" className="text-blue-600 hover:underline">
            Sign up
          </a>
        </p>
      </motion.div>
    </div>
  );
};

export default SubscriberLogin;
