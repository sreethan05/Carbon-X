import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Mic, Volume2, Phone, ShieldCheck, ArrowRight, Lock } from 'lucide-react';
import { useLanguage } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';
import { sendOtp, verifyRegistrationOtp, registerUser } from '../services/api';

export default function FarmerRegister() {
  const navigate = useNavigate();
  const { currentLang } = useLanguage();
  const { login } = useAuth();

  // Voice Assistance Simulation
  const [isListening, setIsListening] = useState(false);
  const [speechText] = useState('');

  // Form State
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [idType, setIdType] = useState('Govt Aadhaar ID');
  const [rawIdNumber, setRawIdNumber] = useState('');
  const [maskedId, setMaskedId] = useState('');
  const [district, setDistrict] = useState('Yadadri Bhuvanagiri');
  const [mandal, setMandal] = useState('Pochampally');
  const [village, setVillage] = useState('Pochampally');

  // OTP Verification State
  const [showOtpModal, setShowOtpModal] = useState(false);
  const [otp, setOtp] = useState('');
  const [otpTimer, setOtpTimer] = useState(600); // 10 minutes timer
  const [timerActive, setTimerActive] = useState(false);
  const [otpError, setOtpError] = useState('');
  const [, setIsRegistering] = useState(false);

  useEffect(() => {
    let interval = null;
    if (timerActive && otpTimer > 0) {
      interval = setInterval(() => setOtpTimer((prev) => prev - 1), 1000);
    } else if (otpTimer === 0) {
      setTimerActive(false);
    }
    return () => clearInterval(interval);
  }, [timerActive, otpTimer]);

  const handleMicClick = () => {
    setIsListening(true);
    setTimeout(() => {
      setName('K. Ramesh');
      setPhone('9876543210');
      setRawIdNumber('200000000009');
      setMaskedId('XXXXXXXX0009');
      setDistrict('Yadadri Bhuvanagiri');
      setMandal('Pochampally');
      setVillage('Pochampally');
      setIsListening(false);
    }, 2000);
  };

  const handleIdChange = (e) => {
    const val = e.target.value;
    setRawIdNumber(val);
    if (val.length === 12) {
      const last4 = val.slice(-4);
      setMaskedId(`XXXX-XXXX-[${last4} Redacted]`);
    } else {
      setMaskedId(val);
    }
  };

  const handleSubmitForm = async (e) => {
    e.preventDefault();
    const cleanPhone = phone.trim().replace(/\s+/g, '');
    if (!name || cleanPhone.length < 10) return;

    setOtpError('');
    setOtp('');

    try {
      const res = await sendOtp(cleanPhone);
      setShowOtpModal(true);
      if (res.success) {
        setTimerActive(true);
        setOtpTimer(600);
      } else {
        setOtpError(res.message || 'Failed to dispatch SMS to your phone.');
      }
    } catch (err) {
      console.warn('Backend OTP send offline', err);
      setShowOtpModal(true);
      setOtpError('Failed to send SMS to your phone. Please check connectivity.');
    }
  };

  const handleVerifyOtpSubmit = async (e) => {
    e.preventDefault();
    const cleanPhone = phone.trim().replace(/\s+/g, '');
    if (otp.length !== 6) {
      setOtpError('Invalid 6-digit OTP code');
      return;
    }

    setIsRegistering(true);
    setOtpError('');

    let verificationToken = null;
    try {
      const verifyRes = await verifyRegistrationOtp(cleanPhone, otp);
      if (!verifyRes || !verifyRes.success) {
        setOtpError((verifyRes && verifyRes.message) || 'Invalid or expired OTP');
        return;
      }
      verificationToken = verifyRes.verification_token;
    } catch {
      // Backend unreachable; registration attempt below reports the outcome
    }

    // Step 2: Register user
    const regPayload = {
      phone: cleanPhone,
      otp,
      otp_verification_token: verificationToken,
      name: name || 'K. Ramesh',
      aadhaar: rawIdNumber,
      state: 'Telangana',
      district: district || 'Yadadri Bhuvanagiri',
      village: village || 'Pochampally',
      upi: `${cleanPhone}@upi`,
      role: 'farmer',
      preferred_language: currentLang || 'en',
    };

    try {
      const regRes = await registerUser(regPayload);
      if (regRes.success && regRes.token) {
        await login(regRes.token, regRes.user);
        setShowOtpModal(false);
        navigate('/farmer/land-verification');
        return;
      }
      setOtpError(regRes.message || 'Registration failed. Please try again.');
      return;
    } catch (err) {
      console.warn('Backend registration unavailable', err);
      if (!import.meta.env.DEV) {
        setOtpError('Could not reach the registration service. Please check your connection and retry.');
        return;
      }
    } finally {
      setIsRegistering(false);
    }

    // Demo mode fallback (dev builds only): backend unreachable
    const userData = {
      name: name || 'K. Ramesh',
      phone: cleanPhone,
      district,
      mandal,
      village,
      role: 'farmer',
      aadhaar_last4: rawIdNumber.slice(-4) || '3210'
    };

    await login('cx_token_' + Date.now(), userData);
    setShowOtpModal(false);
    navigate('/farmer/land-verification');
  };

  const formatTimer = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };

  return (
    <div className="min-h-screen bg-[#F8FAF8] font-inter text-slate-900 py-8 px-4 md:px-10">
      <div className="max-w-2xl mx-auto space-y-6">

        {/* Header Title */}
        <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 flex justify-between items-center">
          <div>
            <span className="text-xs font-semibold text-emerald-800 uppercase tracking-wider bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full inline-block mb-1">
              Farmer Onboarding Portal
            </span>
            <h1 className="text-2xl font-extrabold text-slate-900 font-manrope">Voice & OTP Farmer Registration</h1>
            <p className="text-xs text-slate-500 mt-0.5">Automated identity onboarding for Telangana carbon credit enrollment.</p>
          </div>
          <ShieldCheck className="w-10 h-10 text-emerald-700" />
        </div>

        {/* Voice Assistance Bar */}
        <div className="bg-[#0C2A18] text-white border border-emerald-900 shadow-sm rounded-xl p-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <button
              onClick={handleMicClick}
              type="button"
              className={`w-12 h-12 rounded-xl flex items-center justify-center transition-all ${
                isListening ? 'bg-rose-600 animate-pulse text-white' : 'bg-[#15803D] hover:bg-[#10B981] text-white'
              }`}
            >
              <Mic className="w-6 h-6" />
            </button>
            <div>
              <div className="flex items-center gap-2">
                <Volume2 className="w-4 h-4 text-emerald-400" />
                <span className="text-xs font-bold text-emerald-300 uppercase tracking-wider">
                  {currentLang === 'te' ? 'వాయిస్ సహాయం (Telugu / Eng)' : 'Voice-First Input Guidance'}
                </span>
              </div>
              <p className="text-xs text-slate-300 mt-0.5">
                {speechText || (currentLang === 'te' ? 'మైక్ క్లిక్ చేసి మాట్లాడండి' : 'Click mic to speak your name, village & details')}
              </p>
            </div>
          </div>
        </div>

        {/* Onboarding Form */}
        <form onSubmit={handleSubmitForm} className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Legal Full Name</label>
              <input
                type="text"
                required
                placeholder="e.g. K. Ramesh"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-3 py-2.5 bg-[#F8FAF8] border border-slate-200 rounded-lg text-xs text-slate-900 focus:outline-none focus:border-emerald-600"
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Mobile Number (+91)</label>
              <input
                type="text"
                required
                placeholder="e.g. 9876543210"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="w-full px-3 py-2.5 bg-[#F8FAF8] border border-slate-200 rounded-lg text-xs text-slate-900 focus:outline-none focus:border-emerald-600"
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Identification Proof Type</label>
              <select
                value={idType}
                onChange={(e) => setIdType(e.target.value)}
                className="w-full px-3 py-2.5 bg-[#F8FAF8] border border-slate-200 rounded-lg text-xs text-slate-900 focus:outline-none focus:border-emerald-600"
              >
                <option value="Govt Aadhaar ID">Govt Aadhaar ID</option>
                <option value="Farmer Passbook ID">Telangana Farmer Passbook ID</option>
                <option value="Masked Government ID">Masked Government ID</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Identification Number (Masked)</label>
              <input
                type="text"
                required
                placeholder="Enter ID (e.g. 123456783210)"
                value={rawIdNumber}
                onChange={(e) => handleIdChange(e.target.value)}
                className="w-full px-3 py-2.5 bg-[#F8FAF8] border border-slate-200 rounded-lg text-xs text-slate-900 focus:outline-none focus:border-emerald-600 font-mono"
              />
              {maskedId && (
                <div className="mt-1 flex items-center gap-1 text-[10px] font-mono text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                  <Lock className="w-3 h-3 text-emerald-600" />
                  <span>Privacy Masked Output: {maskedId}</span>
                </div>
              )}
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">District</label>
              <select
                value={district}
                onChange={(e) => setDistrict(e.target.value)}
                className="w-full px-3 py-2.5 bg-[#F8FAF8] border border-slate-200 rounded-lg text-xs text-slate-900 focus:outline-none focus:border-emerald-600"
              >
                <option value="Yadadri Bhuvanagiri">Yadadri Bhuvanagiri</option>
                <option value="Warangal">Warangal</option>
                <option value="Jangaon">Jangaon</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Mandal</label>
              <input
                type="text"
                value={mandal}
                onChange={(e) => setMandal(e.target.value)}
                className="w-full px-3 py-2.5 bg-[#F8FAF8] border border-slate-200 rounded-lg text-xs text-slate-900 focus:outline-none focus:border-emerald-600"
              />
            </div>

            <div className="md:col-span-2">
              <label className="block text-xs font-bold text-slate-700 mb-1">Village Name</label>
              <input
                type="text"
                value={village}
                onChange={(e) => setVillage(e.target.value)}
                className="w-full px-3 py-2.5 bg-[#F8FAF8] border border-slate-200 rounded-lg text-xs text-slate-900 focus:outline-none focus:border-emerald-600"
              />
            </div>
          </div>

          <button
            type="submit"
            className="w-full py-3 bg-[#0C2A18] hover:bg-[#15803D] text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2 mt-4"
          >
            <span>Verify Phone & Continue</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </form>

        {/* OTP Verification Modal */}
        {showOtpModal && (
          <div className="fixed inset-0 z-50 bg-[#0C2A18]/60 backdrop-blur-xs flex items-center justify-center p-4">
            <div className="bg-white border border-slate-200 shadow-xl rounded-xl p-6 max-w-md w-full space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <div className="flex items-center gap-2">
                  <Phone className="w-5 h-5 text-emerald-700" />
                  <h3 className="text-sm font-bold text-slate-900">Phone OTP Verification</h3>
                </div>
                <span className="text-xs font-mono font-bold text-rose-700 bg-rose-50 border border-rose-200 px-2 py-0.5 rounded">
                  {formatTimer(otpTimer)}
                </span>
              </div>

              <p className="text-xs text-slate-600">
                A 6-digit authentication code has been dispatched to <span className="font-bold text-slate-900">+91 {phone}</span>.
              </p>

              {otpError && (
                <p className="text-xs text-rose-700 font-bold bg-rose-50 border border-rose-200 p-2.5 rounded-lg leading-relaxed">
                  {otpError}
                </p>
              )}

              <form onSubmit={handleVerifyOtpSubmit} className="space-y-4">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Enter 6-Digit Code</label>
                  <input
                    type="text"
                    maxLength={6}
                    required
                    placeholder="Enter 6-digit OTP"
                    value={otp}
                    onChange={(e) => setOtp(e.target.value)}
                    className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-center text-lg font-mono font-bold tracking-widest text-slate-900 focus:outline-none focus:border-emerald-600"
                  />
                </div>

                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setShowOtpModal(false)}
                    className="flex-1 py-2.5 bg-slate-100 text-slate-700 rounded-lg text-xs font-bold hover:bg-slate-200"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="flex-1 py-2.5 bg-emerald-700 text-white rounded-lg text-xs font-bold hover:bg-emerald-600 flex items-center justify-center gap-1"
                  >
                    <span>Verify & Route</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
