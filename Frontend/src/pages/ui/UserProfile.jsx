import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast, ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import { API_BASE_URL } from '../../config/api';
import { FaUser, FaCog, FaEye, FaEyeSlash } from 'react-icons/fa';

const UserProfile = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [credits, setCredits] = useState(null);
  
  // Form state
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    currentPassword: '',
    newPassword: ''
  });

  // Load current user data and credits
  useEffect(() => {
    const username = localStorage.getItem('username');
    const email = localStorage.getItem('email');
    
    setFormData(prev => ({
      ...prev,
      name: username || '',
      email: email || ''
    }));

    // Fetch credits from API
    const token = localStorage.getItem('token');
    if (token) {
      axios.get(`${API_BASE_URL}/user/credits`, {
        headers: {
          Authorization: `Bearer ${token}`
        }
      }).then((res) => {
        setCredits(res.data.credits);
      }).catch(err => {
        console.error('Failed to fetch credits:', err);
      });
    }
  }, []);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const token = localStorage.getItem('token');
      
      // Prepare update data (only send fields that have values)
      const updateData = {};
      
      if (formData.name && formData.name !== localStorage.getItem('username')) {
        updateData.name = formData.name;
      }
      
      if (formData.email && formData.email !== localStorage.getItem('email')) {
        updateData.email = formData.email;
      }
      
      if (formData.newPassword) {
        if (!formData.currentPassword) {
          toast.error('Please enter your current password to change it');
          setLoading(false);
          return;
        }
        updateData.current_password = formData.currentPassword;
        updateData.new_password = formData.newPassword;
      }

      // Check if there's anything to update
      if (Object.keys(updateData).length === 0) {
        toast.info('No changes to save');
        setLoading(false);
        return;
      }

      const response = await axios.put(
        `${API_BASE_URL}/user/profile`,
        updateData,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );

      // Update localStorage with new data
      if (response.data.user.name) {
        localStorage.setItem('username', response.data.user.name);
      }
      if (response.data.user.email) {
        localStorage.setItem('email', response.data.user.email);
      }

      toast.success('Profile updated successfully!');
      
      // Clear password fields
      setFormData(prev => ({
        ...prev,
        currentPassword: '',
        newPassword: ''
      }));

      // Trigger navbar re-render by navigating
      setTimeout(() => {
        window.location.reload();
      }, 1500);

    } catch (error) {
      console.error('Profile update error:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to update profile';
      toast.error(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-blue-50 py-12 px-4">
      <ToastContainer position="top-right" autoClose={3000} />
      
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <button
            onClick={() => navigate('/dashboard')}
            className="text-blue-600 hover:text-blue-800 mb-4 flex items-center gap-2"
          >
            ← Back to Dashboard
          </button>
          <h1 className="text-4xl font-bold text-gray-900">Account Settings</h1>
          <p className="text-gray-600 mt-2">Manage your profile and account preferences</p>
        </div>

        <div className="grid lg:grid-cols-4 gap-6">
          {/* Sidebar - Profile Info */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-2xl shadow-lg p-6 border border-gray-200 sticky top-6">
              {/* Profile Avatar */}
              <div className="flex flex-col items-center">
                <div className="w-24 h-24 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center mb-4">
                  <span className="text-white text-3xl font-bold">
                    {formData.name ? formData.name.charAt(0).toUpperCase() : 'U'}
                  </span>
                </div>
                
                <h3 className="text-xl font-bold text-gray-900 text-center">
                  {formData.name || 'User'}
                </h3>
                <p className="text-sm text-gray-500 text-center mt-1">
                  {formData.email || 'email@example.com'}
                </p>
              </div>

              {/* Profile Stats */}
              <div className="mt-6 pt-6 border-t border-gray-200 space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">Role</span>
                  <span className="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-xs font-semibold">
                    {JSON.parse(localStorage.getItem('user') || '{}').role || 'User'}
                  </span>
                </div>
                
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">Credits</span>
                  <span className="px-3 py-1 bg-green-100 text-green-800 rounded-full text-xs font-semibold">
                    {credits !== null ? credits : '...'}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">Status</span>
                  <span className="px-3 py-1 bg-green-100 text-green-800 rounded-full text-xs font-semibold">
                    Active
                  </span>
                </div>
              </div>

              {/* Quick Actions */}
              <div className="mt-6 pt-6 border-t border-gray-200">
                <button
                  onClick={() => navigate('/dashboard')}
                  className="w-full px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg transition duration-300 text-sm font-medium"
                >
                  View Dashboard
                </button>
              </div>
            </div>
          </div>

          {/* Main Content - Settings Form */}
          <div className="lg:col-span-3">
            <form onSubmit={handleSubmit} className="space-y-6">
              {/* User Details Section */}
              <div className="bg-white rounded-2xl shadow-lg p-8 border border-gray-200">
                <div className="flex items-center gap-3 mb-6">
                  <FaUser className="text-blue-600 text-2xl" />
                  <h2 className="text-2xl font-bold text-gray-900">User Details</h2>
                </div>

                <div className="grid md:grid-cols-2 gap-6">
                  {/* Full Name */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Full Name
                    </label>
                    <input
                      type="text"
                      name="name"
                      value={formData.name}
                      onChange={handleChange}
                      placeholder="Enter your name"
                      className="w-full px-4 py-3 rounded-xl border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500 transition"
                    />
                  </div>

                  {/* Email Address */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Email Address
                    </label>
                    <input
                      type="email"
                      name="email"
                      value={formData.email}
                      onChange={handleChange}
                      placeholder="Enter your email"
                      className="w-full px-4 py-3 rounded-xl border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500 transition"
                    />
                  </div>
                </div>

                {/* Change Password Section */}
                <div className="mt-8 pt-8 border-t border-gray-200">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4">Change Password</h3>
                  
                  <div className="grid md:grid-cols-2 gap-6">
                    {/* Current Password */}
                    <div className="relative">
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Current Password
                      </label>
                      <input
                        type={showCurrentPassword ? 'text' : 'password'}
                        name="currentPassword"
                        value={formData.currentPassword}
                        onChange={handleChange}
                        placeholder="Enter current password"
                        className="w-full px-4 py-3 pr-12 rounded-xl border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500 transition"
                      />
                      <button
                        type="button"
                        onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                        className="absolute right-4 top-11 text-gray-500 hover:text-blue-600"
                      >
                        {showCurrentPassword ? <FaEyeSlash /> : <FaEye />}
                      </button>
                    </div>

                    {/* New Password */}
                    <div className="relative">
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        New Password
                      </label>
                      <input
                        type={showNewPassword ? 'text' : 'password'}
                        name="newPassword"
                        value={formData.newPassword}
                        onChange={handleChange}
                        placeholder="Enter new password"
                        className="w-full px-4 py-3 pr-12 rounded-xl border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500 transition"
                      />
                      <button
                        type="button"
                        onClick={() => setShowNewPassword(!showNewPassword)}
                        className="absolute right-4 top-11 text-gray-500 hover:text-blue-600"
                      >
                        {showNewPassword ? <FaEyeSlash /> : <FaEye />}
                      </button>
                    </div>
                  </div>
                  
                  <p className="text-sm text-gray-500 mt-2">
                    Password must be at least 8 characters with uppercase, number, and special character
                  </p>
                </div>
              </div>

              {/* Account Preferences Section */}
              <div className="bg-white rounded-2xl shadow-lg p-8 border border-gray-200">
                <div className="flex items-center gap-3 mb-6">
                  <FaCog className="text-purple-600 text-2xl" />
                  <h2 className="text-2xl font-bold text-gray-900">Account Preferences</h2>
                </div>

                <div className="space-y-4">
                  <label className="flex items-center gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      className="w-5 h-5 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                    />
                    <span className="text-gray-700">Receive Email Notifications</span>
                  </label>

                  <label className="flex items-center gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      className="w-5 h-5 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                    />
                    <span className="text-gray-700">Enable Dark Mode</span>
                  </label>

                  <label className="flex items-center gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      className="w-5 h-5 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                    />
                    <span className="text-gray-700">Two-Factor Authentication</span>
                  </label>
                </div>
              </div>

              {/* Save Button */}
              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={loading}
                  className="px-8 py-3 bg-blue-600 text-white font-semibold rounded-xl shadow-lg hover:bg-blue-700 transition duration-300 hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
};

export default UserProfile;
