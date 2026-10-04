import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Building2, ArrowRight } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { corporateLogin } from '../services/api';

export default function CorporateLogin() {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [name, setName] = useState('Telangana Sustainable Agro Pvt Ltd');
  const [password, setPassword] = useState('Corporate@2026');

  const [error, setError] = useState('');
  const [isVerifying, setIsVerifying] = useState(false);

  const handleCorporateLogin = async (e) => {
    if (e) e.preventDefault();
    if (!name || !password) {
      setError('Please provide corporate name and password');
      return;
    }
    setError('');

    setIsVerifying(true);

    try {
      const data = await corporateLogin(name, password);
      if (data && data.success && data.token) {
        await login(data.token, data.user);
        setIsVerifying(false);
        navigate('/corporate/dashboard');
        return;
      }
      setError((data && data.message) || 'Login failed. Check your credentials.');
      setIsVerifying(false);
    } catch (err) {
      console.warn('Corporate login API unreachable', err);
      if (import.meta.env.DEV) {
        // Demo mode (dev builds only): proceed with a locally-forged session
        await login('cx_corp_token_' + Date.now(), { c_id: 101, name, role: 'buyer' });
        setIsVerifying(false);
        navigate('/corporate/dashboard');
        return;
      }
      setError('Authentication service unreachable. Please try again shortly.');
      setIsVerifying(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#F8FAF8] font-inter text-slate-900 py-10 px-4 flex items-center justify-center">
      <div className="max-w-md w-full space-y-6">

        {/* Corporate Auth Card */}
        <div className="bg-white border border-slate-200 shadow-sm rounded-2xl p-6 space-y-5">
          <div className="text-center space-y-1">
            <div className="w-12 h-12 bg-emerald-50 border border-emerald-200 rounded-2xl flex items-center justify-center text-emerald-800 mx-auto mb-2 shadow-xs">
              <Building2 className="w-6 h-6" />
            </div>
            <div className="flex items-center justify-center gap-1.5">
              <span className="text-[10px] font-bold text-emerald-800 uppercase tracking-wider bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full">
                Institutional Buyer Desk
              </span>
              <span className="text-[10px] font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                ESG / BRSR
              </span>
            </div>
            <h1 className="text-2xl font-extrabold text-slate-900 font-manrope">Corporate Buyer Sign In</h1>
            <p className="text-xs text-slate-500">Access enterprise credit allocation, BRSR reports & Scope 1-3 retirement.</p>
          </div>

          {error && (
            <p className="text-xs font-bold text-rose-700 bg-rose-50 border border-rose-200 p-2.5 rounded-xl text-center">
              {error}
            </p>
          )}

          <form onSubmit={handleCorporateLogin} className="space-y-4">
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Corporate Name / Identifier (`name`)</label>
              <input
                type="text"
                required
                placeholder="e.g. Telangana Sustainable Agro Pvt Ltd"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-3.5 py-2.5 bg-[#F8FAF8] border border-slate-200 rounded-xl text-xs font-semibold text-slate-900 focus:outline-none focus:border-emerald-600"
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Corporate Password (`password`)</label>
              <input
                type="password"
                required
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3.5 py-2.5 bg-[#F8FAF8] border border-slate-200 rounded-xl text-xs font-semibold text-slate-900 focus:outline-none focus:border-emerald-600"
              />
            </div>

            <button
              type="submit"
              disabled={isVerifying}
              className="w-full py-3 bg-[#1B4332] hover:bg-[#2D6A4F] text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2"
            >
              <span>{isVerifying ? 'Authenticating Corporate...' : 'Sign In to Corporate ESG Desk'}</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </form>

          <div className="text-center pt-2 border-t border-slate-100">
            <p className="text-xs text-slate-500">
              Need corporate enterprise access?{' '}
              <button
                type="button"
                onClick={() => navigate('/corporate/welcome')}
                className="text-emerald-800 font-bold hover:underline"
              >
                View Procurement Overview
              </button>
            </p>
          </div>
        </div>

      </div>
    </div>
  );
}
