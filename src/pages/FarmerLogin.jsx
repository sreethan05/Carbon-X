import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Phone, ArrowRight, RefreshCw, Loader2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { sendLoginOtp, loginUser, demoLogin, getSystemHealth } from '../services/api';

export default function FarmerLogin() {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [phone, setPhone] = useState('');
  const [showOtp, setShowOtp] = useState(false);
  const [otpDigits, setOtpDigits] = useState(['', '', '', '', '', '']);
  const [countdown, setCountdown] = useState(60);
  const [canResend, setCanResend] = useState(false);
  const [error, setError] = useState('');
  const [isVerifying, setIsVerifying] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [isDevOtp, setIsDevOtp] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getSystemHealth()
      .then((h) => {
        if (!cancelled && h && h.database && h.database.ready === false) {
          setDbOffline(true);
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const inputRefs = useRef([]);

  useEffect(() => {
    if (!showOtp || canResend) return;
    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          setCanResend(true);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [showOtp, canResend]);

  useEffect(() => {
    if (showOtp) {
      inputRefs.current[0]?.focus();
    }
  }, [showOtp]);

  const handleSendOtpSubmit = async (e) => {
    e.preventDefault();
    if (isVerifying) return;
    const cleanPhone = phone.trim().replace(/\D/g, '');
    const INDIAN_PHONE_REGEX = /^[6-9]\d{9}$/;
    if (!INDIAN_PHONE_REGEX.test(cleanPhone)) {
      setError('Please enter a valid 10-digit Indian mobile number (starts with 6, 7, 8, or 9)');
      return;
    }
    setError('');
    setIsVerifying(true);
    setIsDevOtp(false);
    try {
      const res = await sendLoginOtp(cleanPhone);
      if (res?.success) {
        setShowOtp(true);
        setCountdown(60);
        setCanResend(false);
        if (res.dev_otp) {
          setOtpDigits(res.dev_otp.split(''));
          setIsDevOtp(true);
        }
      } else {
        const msg = res?.detail || res?.message || 'Failed to send OTP. Please retry.';
        setError(msg);
        if (typeof msg === 'string' && /database is not configured/i.test(msg)) setDbOffline(true);
      }
    } catch {
      setError('Could not reach the server. Please check your connection and retry.');
    } finally {
      setIsVerifying(false);
    }
  };

  // Demo-mode entry: lets the whole farmer loop be explored while the
  // database is unconfigured (login needs the DB to check the profile).
  const [dbOffline, setDbOffline] = useState(false);
  const [isStartingDemo, setIsStartingDemo] = useState(false);
  const handleDemoLogin = async () => {
    setError('');
    setIsStartingDemo(true);
    try {
      const res = await demoLogin();
      if (res && res.success && res.token) {
        await login(res.token, res.user);
        navigate('/farmer/dashboard');
      } else {
        setError((res && res.message) || 'Demo mode is unavailable right now.');
      }
    } catch {
      setError('Demo mode needs the backend running (it is refused when a real database is configured).');
    } finally {
      setIsStartingDemo(false);
    }
  };

  const handleDigitChange = (index, value) => {
    const cleanVal = value.replace(/\D/g, '');
    if (!cleanVal) {
      const newDigits = [...otpDigits];
      newDigits[index] = '';
      setOtpDigits(newDigits);
      return;
    }

    const newDigits = [...otpDigits];
    newDigits[index] = cleanVal.slice(-1);
    setOtpDigits(newDigits);

    // Auto advance to next input
    if (cleanVal && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index, e) => {
    if (e.key === 'Backspace') {
      if (!otpDigits[index] && index > 0) {
        inputRefs.current[index - 1]?.focus();
      }
    } else if (e.key === 'ArrowLeft' && index > 0) {
      e.preventDefault();
      inputRefs.current[index - 1]?.focus();
    } else if (e.key === 'ArrowRight' && index < 5) {
      e.preventDefault();
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handlePaste = (e) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData('text').trim().replace(/\D/g, '');
    if (!pasted) return;
    const newDigits = [...otpDigits];
    for (let i = 0; i < 6; i++) {
      newDigits[i] = pasted[i] || '';
    }
    setOtpDigits(newDigits);
    const nextIndex = Math.min(pasted.length, 5);
    inputRefs.current[nextIndex]?.focus();
  };

  const handleResendOtp = async () => {
    if (!canResend || isResending || isVerifying) return;
    setError('');
    const cleanPhone = phone.trim().replace(/\D/g, '');
    const INDIAN_PHONE_REGEX = /^[6-9]\d{9}$/;
    if (!INDIAN_PHONE_REGEX.test(cleanPhone)) {
      setError('Please enter a valid 10-digit Indian mobile number');
      return;
    }
    setIsResending(true);
    try {
      const res = await sendLoginOtp(cleanPhone);
      if (res?.success) {
        setCountdown(60);
        setCanResend(false);
        if (res.dev_otp) {
          setOtpDigits(res.dev_otp.split(''));
          setIsDevOtp(true);
        }
      } else {
        setError(res?.message || 'Could not resend OTP. Please retry.');
      }
    } catch {
      setError('Could not resend OTP. Please retry.');
    } finally {
      setIsResending(false);
    }
  };

  const handleVerifyOtpSubmit = async (e) => {
    e.preventDefault();
    if (isVerifying) return;
    const cleanPhone = phone.trim().replace(/\D/g, '');
    const fullOtp = otpDigits.join('');
    if (fullOtp.length !== 6 || !/^\d{6}$/.test(fullOtp)) {
      setError('Please enter complete 6-digit OTP');
      return;
    }

    setIsVerifying(true);
    setError('');
    try {
      const res = await loginUser(cleanPhone, fullOtp);
      if (res?.success && res?.token) {
        await login(res.token, res.user);
        navigate('/farmer/dashboard');
        return;
      }
      setError(res?.message || 'Invalid OTP. Please try again.');
    } catch (err) {
      console.warn('Backend login unavailable', err);
      setError('Could not reach the server. Please check your connection and retry.');
    } finally {
      setIsVerifying(false);
    }
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

          {dbOffline && (
            <button
              type="button"
              onClick={handleDemoLogin}
              disabled={isStartingDemo}
              className="w-full py-2.5 bg-slate-100 hover:bg-slate-200 border border-slate-300 text-slate-800 rounded-xl text-xs font-bold transition-all"
            >
              {isStartingDemo ? 'Starting demo session…' : 'Explore in Demo Mode (sample farmer, no OTP)'}
            </button>
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
                    type="tel"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    autoComplete="tel"
                    required
                    maxLength={10}
                    placeholder="9876543210"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value.replace(/\D/g, ''))}
                    className="w-full px-3 py-2.5 bg-transparent text-xs font-bold text-carbon-900 focus:outline-none"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={isVerifying || phone.length !== 10}
                className="w-full py-3 bg-primary hover:bg-primary-hover disabled:opacity-50 text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2"
              >
                {isVerifying && <Loader2 className="w-4 h-4 animate-spin" />}
                <span>{isVerifying ? 'Sending OTP…' : 'Send 6-Digit OTP'}</span>
                {!isVerifying && <ArrowRight className="w-4 h-4" />}
              </button>
            </form>
          ) : (
            <form onSubmit={handleVerifyOtpSubmit} className="space-y-4">
              <div className="flex items-center justify-between text-xs text-agriText-muted bg-surface-sage/30 px-3 py-2 rounded-xl border border-forest-100">
                <span>Code sent to <strong className="text-carbon-900">+91 {phone}</strong></span>
                <button
                  type="button"
                  onClick={() => {
                    setShowOtp(false);
                    setOtpDigits(['', '', '', '', '', '']);
                    setError('');
                  }}
                  className="text-primary font-bold hover:underline"
                >
                  Change
                </button>
              </div>

              {isDevOtp && (
                <p className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 p-2 rounded-xl text-center">
                  Dev mode (CARBONX_ALLOW_DEV_OTP): simulated OTP auto-filled below.
                </p>
              )}

              <div>
                <label className="block text-xs font-bold text-carbon-800 mb-1.5 text-center">
                  Enter 6-Digit Verification Code
                </label>
                <div
                  className="flex justify-between gap-1.5 max-w-xs mx-auto"
                  onPaste={handlePaste}
                >
                  {otpDigits.map((digit, idx) => (
                    <input
                      key={idx}
                      ref={(el) => (inputRefs.current[idx] = el)}
                      type="text"
                      inputMode="numeric"
                      pattern="[0-9]*"
                      autoComplete={idx === 0 ? "one-time-code" : "off"}
                      aria-label={`OTP Digit ${idx + 1} of 6`}
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
                  disabled={!canResend || isResending || isVerifying}
                  className={`px-3 py-1 rounded-lg text-xs font-bold transition-all flex items-center gap-1 ${
                    canResend && !isResending && !isVerifying
                      ? 'bg-primary text-white hover:bg-primary-hover shadow-xs'
                      : 'bg-warm-cream text-agriText-subtle cursor-not-allowed'
                  }`}
                >
                  {isResending ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
                  <span>{isResending ? 'Resending...' : 'Resend OTP'}</span>
                </button>
              </div>

              <button
                type="submit"
                disabled={isVerifying || otpDigits.join('').length !== 6}
                className="w-full py-3 bg-primary hover:bg-primary-hover text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {isVerifying && <Loader2 className="w-4 h-4 animate-spin" />}
                <span>{isVerifying ? 'Verifying...' : 'Verify & Continue'}</span>
                {!isVerifying && <ArrowRight className="w-4 h-4" />}
              </button>
            </form>
          )}

          <div className="text-center pt-2 border-t border-forest-100">
            <p className="text-xs text-agriText-muted">
              Don't have a farm registered?{' '}
              <button
                type="button"
                onClick={() => navigate('/farmer/register')}
                className="text-primary font-bold hover:underline"
              >
                Register as Farmer
              </button>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
