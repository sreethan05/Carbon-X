import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Phone, ArrowRight, ShieldCheck, RefreshCw, CheckCircle2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { sendLoginOtp, loginUser } from '../services/api';

export default function FarmerLogin() {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [phone, setPhone] = useState('9876543210');
  const [showOtp, setShowOtp] = useState(false);
  const [otpDigits, setOtpDigits] = useState(['', '', '', '', '', '']);
  const [countdown, setCountdown] = useState(60);
  const [canResend, setCanResend] = useState(false);
  const [error, setError] = useState('');
  const [isVerifying, setIsVerifying] = useState(false);

  const inputRefs = useRef([]);

  useEffect(() => {
    let timer;
    if (showOtp && countdown > 0) {
      timer = setInterval(() => {
        setCountdown((prev) => prev - 1);
      }, 1000);
    } else if (countdown === 0) {
      setCanResend(true);
    }
    return () => clearInterval(timer);
  }, [showOtp, countdown]);

  const handleSendOtpSubmit = async (e) => {
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
        if (res.dev_otp) {
          setOtpDigits(res.dev_otp.split(''));
        }
      } else {
        setError(res.message || 'Failed to send OTP. Please retry.');
      }
    } catch {
      if (import.meta.env.DEV) {
        // Demo mode: continue the flow when no backend is running
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

  const handleDigitChange = (index, value) => {
    if (!/^\d*$/.test(value)) return;

    const newDigits = [...otpDigits];
    newDigits[index] = value.slice(-1);
    setOtpDigits(newDigits);

    // Auto advance to next input
    if (value && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index, e) => {
    if (e.key === 'Backspace' && !otpDigits[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
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

  const handleVerifyOtpSubmit = async (e) => {
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
        await login(res.token, res.user);
        navigate('/farmer/dashboard');
        return;
      }
      setError(res.message || 'Invalid OTP. Please try again.');
      setIsVerifying(false);
      return;
    } catch (err) {
      console.warn('Backend login unavailable', err);
    }

    if (!import.meta.env.DEV) {
      setError('Could not reach the server. Please check your connection and retry.');
      setIsVerifying(false);
      return;
    }

    // Demo mode fallback (dev builds only): backend unreachable
    const userData = {
      name: 'K. Ramesh',
      phone: cleanPhone,
      district: 'Yadadri Bhuvanagiri',
      village: 'Pochampally',
      role: 'farmer',
    };

    await login('cx_token_' + Date.now(), userData);
    navigate('/farmer/dashboard');
  };

  return (
    <div className="min-h-screen bg-surface font-inter text-agriText-main py-10 px-4 flex items-center justify-center">
      <div className="max-w-md w-full space-y-6">

        {/* Auth Card */}
        <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-6 space-y-5">
          <div className="text-center space-y-1">
            <div className="w-12 h-12 bg-surface-sage border border-forest-200 rounded-2xl flex items-center justify-center text-primary mx-auto mb-2 shadow-xs">
              <Phone className="w-6 h-6" />
            </div>
            <div className="flex items-center justify-center gap-1.5">
              <span className="text-[10px] font-bold text-primary uppercase tracking-wider bg-surface-sage border border-forest-200 px-2.5 py-0.5 rounded-full">
                Phone OTP Verification
              </span>
              <span className="text-[10px] font-semibold text-agriText-subtle bg-warm-cream px-2 py-0.5 rounded">
                Simulated
              </span>
            </div>
            <h1 className="text-2xl font-extrabold text-carbon-900 font-manrope">Sign In to CarbonX</h1>
            <p className="text-xs text-agriText-muted">Enter your mobile number to receive a 6-digit OTP.</p>
          </div>

          {error && (
            <p className="text-xs font-bold text-red-700 bg-red-50 border border-red-200 p-2.5 rounded-xl text-center">
              {error}
            </p>
          )}

          {!showOtp ? (
            <form onSubmit={handleSendOtpSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-carbon-800 mb-1">Mobile Number (+91)</label>
                <div className="flex bg-surface-sage/40 border border-forest-200 rounded-xl overflow-hidden focus-within:ring-2 focus-within:ring-primary/30">
                  <span className="bg-surface-sage text-carbon-800 px-3 py-2.5 text-xs font-bold border-r border-forest-200 flex items-center">
                    +91
                  </span>
                  <input
                    type="text"
                    required
                    maxLength={10}
                    placeholder="9876543210"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    className="w-full px-3 py-2.5 bg-transparent text-xs font-bold text-carbon-900 focus:outline-none"
                  />
                </div>
              </div>

              <button
                type="submit"
                className="w-full py-3 bg-primary hover:bg-primary-hover text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2"
              >
                <span>Send 6-Digit OTP</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </form>
          ) : (
            <form onSubmit={handleVerifyOtpSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-carbon-800 mb-1.5 text-center">
                  Enter 6-Digit Verification Code
                </label>
                <div className="flex justify-between gap-1.5 max-w-xs mx-auto">
                  {otpDigits.map((digit, idx) => (
                    <input
                      key={idx}
                      ref={(el) => (inputRefs.current[idx] = el)}
                      type="text"
                      maxLength={1}
                      value={digit}
                      onChange={(e) => handleDigitChange(idx, e.target.value)}
                      onKeyDown={(e) => handleKeyDown(idx, e)}
                      className="w-10 h-12 text-center text-lg font-mono font-bold bg-surface-sage/50 border border-forest-200 rounded-xl text-carbon-900 focus:outline-none focus:ring-2 focus:ring-primary/40"
                    />
                  ))}
                </div>
              </div>

              {/* 60s Countdown & Resend Button */}
              <div className="flex justify-between items-center bg-surface-sage/50 border border-forest-200 rounded-xl p-2.5 text-xs text-agriText-muted">
                <span>
                  {canResend ? (
                    <span className="text-carbon-800 font-semibold">Didn't receive code?</span>
                  ) : (
                    <span>
                      Resend code in <strong className="font-mono text-primary font-bold">{countdown}s</strong>
                    </span>
                  )}
                </span>
                <button
                  type="button"
                  onClick={handleResendOtp}
                  disabled={!canResend}
                  className={`px-3 py-1 rounded-lg text-xs font-bold transition-all flex items-center gap-1 ${
                    canResend
                      ? 'bg-primary text-white hover:bg-primary-hover shadow-xs'
                      : 'bg-warm-cream text-agriText-subtle cursor-not-allowed'
                  }`}
                >
                  <RefreshCw className="w-3 h-3" />
                  <span>Resend OTP</span>
                </button>
              </div>

              <button
                type="submit"
                disabled={isVerifying}
                className="w-full py-3 bg-primary hover:bg-primary-hover text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50"
              >
                <span>{isVerifying ? 'Verifying...' : 'Verify & Continue'}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </form>
          )}

          <div className="text-center pt-2 border-t border-forest-100">
            <p className="text-xs text-agriText-muted">
              Don't have a farm registered?{' '}
              <button
                type="button"
                onClick={() => navigate('/farmer/land-verification')}
                className="text-primary font-bold hover:underline"
              >
                Start Verification
              </button>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
