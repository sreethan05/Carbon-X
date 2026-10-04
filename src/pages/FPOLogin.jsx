import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Building2, Phone, ArrowRight, Loader2, RefreshCw } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { sendLoginOtp, loginUser } from '../services/api';

export default function FPOLogin() {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [phone, setPhone] = useState('');
  const [showOtp, setShowOtp] = useState(false);
  const [otpDigits, setOtpDigits] = useState(['', '', '', '', '', '']);
  const [countdown, setCountdown] = useState(60);
  const [canResend, setCanResend] = useState(false);
  const [error, setError] = useState('');
  const [isVerifying, setIsVerifying] = useState(false);

  useEffect(() => {
    let timer;
    if (showOtp && countdown > 0) {
      timer = setInterval(() => setCountdown((prev) => prev - 1), 1000);
    } else if (countdown === 0) {
      setCanResend(true);
    }
    return () => clearInterval(timer);
  }, [showOtp, countdown]);

  const handleSendOtp = async (e) => {
    e.preventDefault();
    const cleanPhone = phone.trim().replace(/\s+/g, '');
    if (cleanPhone.length !== 10 || !/^\d+$/.test(cleanPhone)) {
      setError('Please enter a valid 10-digit mobile number');
      return;
    }
    setError('');
    setIsVerifying(true);
    try {
      const res = await sendLoginOtp(cleanPhone);
      if (res.success) {
        setShowOtp(true);
        setCountdown(60);
        setCanResend(false);
        if (res.dev_otp) setOtpDigits(res.dev_otp.split(''));
      } else {
        setError(res.message || 'Failed to send OTP. Please retry.');
      }
    } catch {
      if (import.meta.env.DEV) {
        setShowOtp(true);
        setCountdown(60);
        setCanResend(false);
      } else {
        setError('Could not reach the server. Please check your connection and retry.');
      }
    } finally {
      setIsVerifying(false);
    }
  };

  const handleResendOtp = async () => {
    if (!canResend) return;
    setCountdown(60);
    setCanResend(false);
    setError('');
    const cleanPhone = phone.trim().replace(/\s+/g, '');
    try {
      const res = await sendLoginOtp(cleanPhone);
      if (res.dev_otp) setOtpDigits(res.dev_otp.split(''));
      if (!res.success) setError(res.message || 'Could not resend OTP. Please retry.');
    } catch {
      setError('Could not resend OTP. Please retry.');
    }
  };

  const handleVerifyOtp = async (e) => {
    e.preventDefault();
    const cleanPhone = phone.trim().replace(/\s+/g, '');
    const fullOtp = otpDigits.join('');
    if (fullOtp.length !== 6) {
      setError('Please enter complete 6-digit OTP');
      return;
    }

    setIsVerifying(true);
    setError('');
    try {
      const res = await loginUser(cleanPhone, fullOtp);
      if (res.success && res.token) {
        const user = res.user || {};
        if (String(user.role || '').toLowerCase() !== 'fpo') {
          setError('This phone number is not registered as an FPO officer.');
          setIsVerifying(false);
          return;
        }
        await login(res.token, user);
        navigate('/fpo/dashboard');
        return;
      }
      setError(res.message || 'Invalid OTP. Please try again.');
      setIsVerifying(false);
    } catch (err) {
      console.warn('FPO login unavailable', err);
      setError('Could not reach the server. Please check your connection and retry.');
      setIsVerifying(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#F8FAF8] font-inter text-slate-900 py-10 px-4 flex items-center justify-center">
      <div className="max-w-md w-full space-y-6">

        {/* FPO Auth Card */}
        <div className="bg-white border border-slate-200 shadow-sm rounded-2xl p-6 space-y-5">
          <div className="text-center space-y-1">
            <div className="w-12 h-12 bg-emerald-50 border border-emerald-200 rounded-2xl flex items-center justify-center text-emerald-800 mx-auto mb-2 shadow-xs">
              <Building2 className="w-6 h-6" />
            </div>
            <div className="flex items-center justify-center gap-1.5">
              <span className="text-[10px] font-bold text-emerald-800 uppercase tracking-wider bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full">
                Authorized FPO / Cooperative Desk
              </span>
              <span className="text-[10px] font-semibold text-amber-800 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded">
                Cooperative
              </span>
            </div>
            <h1 className="text-2xl font-extrabold text-slate-900 font-manrope">FPO Officer Sign In</h1>
            <p className="text-xs text-slate-500">Access member roster, bulk onboarding & credit pooling desk.</p>
          </div>

          {error && (
            <p className="text-xs font-bold text-rose-700 bg-rose-50 border border-rose-200 p-2.5 rounded-xl text-center">
              {error}
            </p>
          )}

          {!showOtp ? (
            <form onSubmit={handleSendOtp} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Officer Mobile Number (+91)</label>
                <div className="flex bg-[#F8FAF8] border border-slate-200 rounded-xl overflow-hidden focus-within:ring-2 focus-within:ring-emerald-600/30">
                  <span className="bg-emerald-50 text-emerald-800 px-3 py-2.5 text-xs font-bold border-r border-slate-200 flex items-center">
                    +91
                  </span>
                  <input
                    type="text"
                    required
                    maxLength={10}
                    placeholder="10-digit registered mobile"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value.replace(/\D/g, ''))}
                    className="w-full px-3 py-2.5 bg-transparent text-xs font-bold text-slate-900 focus:outline-none"
                  />
                </div>
                <p className="text-[10px] text-slate-500 mt-1">
                  Only mobile numbers registered as FPO officers can access this desk.
                </p>
              </div>

              <button
                type="submit"
                disabled={isVerifying}
                className="w-full py-3 bg-[#1B4332] hover:bg-[#2D6A4F] disabled:opacity-60 text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2"
              >
                {isVerifying ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowRight className="w-4 h-4" />}
                <span>Send Officer 6-Digit OTP</span>
              </button>
            </form>
          ) : (
            <form onSubmit={handleVerifyOtp} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-800 mb-1.5 text-center">
                  Enter 6-Digit Officer Verification Code
                </label>
                <div className="flex justify-between gap-1.5 max-w-xs mx-auto">
                  {otpDigits.map((digit, idx) => (
                    <input
                      key={idx}
                      type="text"
                      maxLength={1}
                      value={digit}
                      onChange={(e) => {
                        const v = (e.target.value || '').replace(/\D/g, '').slice(-1);
                        const next = [...otpDigits];
                        next[idx] = v;
                        setOtpDigits(next);
                        if (v && idx < 5) e.target.parentElement.children[idx + 1]?.focus();
                      }}
                      className="w-10 h-12 text-center text-lg font-mono font-bold bg-[#F8FAF8] border border-slate-200 rounded-xl text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-600/40"
                    />
                  ))}
                </div>
              </div>

              <div className="flex justify-between items-center bg-[#F8FAF8] border border-slate-200 rounded-xl p-2.5 text-xs text-slate-600">
                <span>
                  {canResend ? (
                    <span className="text-slate-800 font-semibold">Didn't receive code?</span>
                  ) : (
                    <span>
                      Resend code in <strong className="font-mono text-emerald-800 font-bold">{countdown}s</strong>
                    </span>
                  )}
                </span>
                <button
                  type="button"
                  onClick={handleResendOtp}
                  disabled={!canResend}
                  className={`px-3 py-1 rounded-lg text-xs font-bold transition-all flex items-center gap-1 ${
                    canResend
                      ? 'bg-[#1B4332] text-white hover:bg-[#2D6A4F] shadow-xs'
                      : 'bg-slate-100 text-slate-400 cursor-not-allowed'
                  }`}
                >
                  <RefreshCw className="w-3 h-3" />
                  <span>Resend OTP</span>
                </button>
              </div>

              <button
                type="submit"
                disabled={isVerifying}
                className="w-full py-3 bg-[#1B4332] hover:bg-[#2D6A4F] text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {isVerifying ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowRight className="w-4 h-4" />}
                <span>{isVerifying ? 'Authenticating FPO Officer...' : 'Verify & Access FPO Desk'}</span>
              </button>
            </form>
          )}

          <div className="text-center pt-2 border-t border-slate-100">
            <p className="text-xs text-slate-500 flex items-center justify-center gap-1.5">
              <Phone className="w-3.5 h-3.5" />
              FPO officer accounts are provisioned by the CarbonX platform admin.
            </p>
          </div>
        </div>

      </div>
    </div>
  );
}
