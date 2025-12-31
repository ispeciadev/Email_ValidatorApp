import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const Navbar = () => {
  const [isCompanyOpen, setIsCompanyOpen] = useState(false);
  const [isLoginOpen, setIsLoginOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation(); // Trigger re-render on route change
  const token = localStorage.getItem("token");

  const handleLogout = () => {
    localStorage.clear(); // Clear everything for a fresh state
    navigate("/login");
  };

  const dropdownVariants = {
    hidden: { opacity: 0, y: -15 },
    visible: { opacity: 1, y: 0 },
  };

  return (
    <header className="bg-white/90 backdrop-blur-md shadow-md sticky top-0 z-50">
      <nav className="max-w-screen-xl mx-auto px-8 py-4 flex justify-between items-center text-gray-900">
        {/* Logo */}
        <Link
          to="/"
          className="text-3xl md:text-4xl font-extrabold tracking-wide hover:text-blue-600 transition duration-300"
        >
          Email Validator
        </Link>

        {/* Menu */}
        <div className="flex items-center space-x-4 text-base font-medium">
          {!token ? (
            <>
              {/* Home */}
              <Link
                to="/"
                className="px-4 py-2 rounded-lg hover:bg-blue-100 transition duration-300"
              >
                Home
              </Link>

              {/* Pricing (after Home, before Company) */}
              <Link
                to="/pricing"
                className="px-4 py-2 rounded-lg hover:bg-blue-100 transition duration-300"
              >
                Pricing
              </Link>

              {/* Company Dropdown */}
              <div
                className="relative"
                onMouseEnter={() => setIsCompanyOpen(true)}
                onMouseLeave={() => setIsCompanyOpen(false)}
              >
                <button className="px-4 py-2 rounded-lg hover:bg-blue-100 transition duration-300">
                  Company ▾
                </button>
                <AnimatePresence>
                  {isCompanyOpen && (
                    <motion.div
                      initial="hidden"
                      animate="visible"
                      exit="hidden"
                      variants={dropdownVariants}
                      className="absolute top-12 left-0 w-52 bg-white border border-gray-200 rounded-lg shadow-lg z-30"
                    >
                      {['About Us', 'Why Us', 'Contact', 'Security', 'Updates', 'Reviews'].map((item, idx) => (
                        <Link
                          key={idx}
                          to={`/${item.replace(/\s+/g, '')}`}
                          className="block px-4 py-2 hover:bg-blue-50 transition duration-200"
                        >
                          {item}
                        </Link>
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Login Dropdown */}
              <div
                className="relative"
                onMouseEnter={() => setIsLoginOpen(true)}
                onMouseLeave={() => setIsLoginOpen(false)}
              >
                <button className="px-4 py-2 rounded-lg hover:bg-blue-100 transition duration-300">
                  Login ▾
                </button>
                <AnimatePresence>
                  {isLoginOpen && (
                    <motion.div
                      initial="hidden"
                      animate="visible"
                      exit="hidden"
                      variants={dropdownVariants}
                      className="absolute top-12 left-0 w-48 bg-white border border-gray-200 rounded-lg shadow-lg z-30"
                    >
                      <Link
                        to="/login"
                        className="block px-4 py-2 hover:bg-blue-50 transition duration-200"
                      >
                        Email Verifier Dashboard
                      </Link>
                      <Link
                        to="/subscriber/login"
                        className="block px-4 py-2 hover:bg-blue-50 transition duration-200"
                      >
                        Subscriptions (PayPro)
                      </Link>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Buttons */}
              <Link
                to="/signup"
                className="px-4 py-2 text-blue-700 font-semibold border border-blue-300 hover:bg-blue-50 rounded-3xl transition duration-300 hover:scale-105"
              >
                Free Signup
              </Link>

              <Link
                to="/admin/login"
                className="px-4 py-2 text-gray-700 font-semibold border border-gray-300 hover:bg-gray-100 rounded-3xl transition duration-300 hover:scale-105"
              >
                Admin Login
              </Link>

              <Link
                to="/subscriber/subscribe"
                className="px-5 py-2 bg-green-500 text-white font-bold rounded-3xl shadow-lg hover:shadow-xl transition duration-300 hover:scale-110"
              >
                Subscribe
              </Link>
            </>
          ) : (
            <>
              {/* User Profile - Clickable */}
              <Link
                to="/profile"
                className="flex items-center gap-2 px-4 py-2 bg-blue-50 rounded-full hover:bg-blue-100 transition duration-300"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-blue-600" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clipRule="evenodd" />
                </svg>
                <span className="font-semibold text-gray-800">
                  {localStorage.getItem("username") || "User"}
                </span>
              </Link>

              {/* Logout Button */}
              <button
                onClick={handleLogout}
                className="px-5 py-2 bg-red-600 text-white font-bold rounded-3xl shadow-lg hover:shadow-xl transition duration-300 hover:scale-105 flex items-center gap-2"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M3 3a1 1 0 00-1 1v12a1 1 0 102 0V4a1 1 0 00-1-1zm10.293 1.293a1 1 0 011.414 0l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414-1.414L14.586 11H7a1 1 0 110-2h7.586l-1.293-1.293a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
                Logout
              </button>
            </>
          )}
        </div>
      </nav>
    </header>
  );
};

export default Navbar;
