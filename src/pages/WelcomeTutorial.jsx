import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Compass, Leaf, Wallet, ArrowRight, ArrowLeft, CheckCircle2, RotateCcw } from 'lucide-react';
import { useLanguage } from '../context/LanguageContext';

export default function WelcomeTutorial() {
  const navigate = useNavigate();
  const { t } = useLanguage();

  const [slideIndex, setSlideIndex] = useState(() => {
    try {
      const savedStep = parseInt(localStorage.getItem('carbonx_tutorial_step') || '0', 10);
      return Number.isInteger(savedStep) && savedStep >= 0 && savedStep < 3 ? savedStep : 0;
    } catch {
      return 0;
    }
  });

  const [hasCompletedBefore] = useState(() => {
    try {
      return localStorage.getItem('carbonx_tutorial_completed') === 'true';
    } catch {
      return false;
    }
  });

  // Keep saved step in sync with slide index
  useEffect(() => {
    try {
      localStorage.setItem('carbonx_tutorial_step', slideIndex.toString());
    } catch { /* ignore */ }
  }, [slideIndex]);

  const steps = [
    {
      step: 1,
      title: t('tutorialTitle') || 'Satellite Soil Verification',
      desc: t('tutorialDesc') || 'NASA and ISRO multi-spectral satellite imagery scans your soil organic carbon density without requiring manual soil collection.',
      icon: Compass,
      bgColor: 'bg-emerald-50 text-emerald-800 border-emerald-200'
    },
    {
      step: 2,
      title: t('tutorialTitle3') || 'Real-time NDVI Monitoring',
      desc: t('tutorialDesc3') || 'Access high-resolution vegetation health charts, temperature indices, and biodiversity alerts right on your phone.',
      icon: Leaf,
      bgColor: 'bg-sky-50 text-sky-800 border-sky-200'
    },
    {
      step: 3,
      title: t('tutorialTitle2') || 'UPI Wallet Settlements',
      desc: t('tutorialDesc2') || 'Once carbon credits are verified and minted, funds are wired directly into your bank account via instant UPI.',
      icon: Wallet,
      bgColor: 'bg-amber-50 text-amber-800 border-amber-200'
    }
  ];

  const currentStep = steps[slideIndex];
  const Icon = currentStep.icon;

  // Arrow key navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'ArrowRight') {
        setSlideIndex((prev) => Math.min(prev + 1, steps.length - 1));
      } else if (e.key === 'ArrowLeft') {
        setSlideIndex((prev) => Math.max(prev - 1, 0));
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [steps.length]);

  const markCompleteAndNavigate = (target = '/farmer/dashboard') => {
    try {
      localStorage.setItem('carbonx_tutorial_completed', 'true');
      localStorage.removeItem('carbonx_tutorial_step');
    } catch { /* ignore */ }
    navigate(target);
  };

  const handleNext = () => {
    if (slideIndex < steps.length - 1) {
      setSlideIndex(slideIndex + 1);
    } else {
      markCompleteAndNavigate('/farmer/dashboard');
    }
  };

  const handlePrev = () => {
    if (slideIndex > 0) {
      setSlideIndex(slideIndex - 1);
    } else {
      markCompleteAndNavigate('/farmer/dashboard');
    }
  };

  const handleReset = () => {
    setSlideIndex(0);
    try {
      localStorage.setItem('carbonx_tutorial_step', '0');
    } catch { /* ignore */ }
  };

  return (
    <div className="min-h-screen bg-[#F8FAF8] font-inter text-slate-900 py-10 px-4 flex flex-col items-center justify-center">
      <div className="max-w-md w-full space-y-6" role="region" aria-label="Welcome Onboarding Walkthrough">

        {/* Top Progress & Skip Controls */}
        <div className="flex justify-between items-center">
          <button
            onClick={handlePrev}
            aria-label={slideIndex > 0 ? "Previous step" : "Exit to dashboard"}
            className="p-2 hover:bg-slate-200 rounded-lg text-slate-700 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>

          {/* Interactive Progress Dot Indicators */}
          <div className="flex gap-2" role="tablist" aria-label="Tutorial step progress">
            {steps.map((s, idx) => (
              <button
                key={idx}
                type="button"
                role="tab"
                aria-selected={idx === slideIndex}
                aria-label={`Step ${idx + 1}: ${s.title}`}
                onClick={() => setSlideIndex(idx)}
                className={`h-2.5 rounded-full transition-all focus:outline-none focus:ring-2 focus:ring-emerald-600 ${
                  idx === slideIndex ? 'w-7 bg-[#0C2A18]' : 'w-2.5 bg-slate-300 hover:bg-slate-400'
                }`}
              />
            ))}
          </div>

          <div className="flex items-center gap-2">
            {hasCompletedBefore && (
              <button
                onClick={handleReset}
                title={t('restartTutorial', 'Restart walkthrough')}
                aria-label={t('restartTutorial', 'Restart walkthrough')}
                className="p-1.5 text-slate-400 hover:text-slate-700 transition-colors rounded-lg"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>
            )}
            <button
              onClick={() => markCompleteAndNavigate('/farmer/dashboard')}
              className="text-xs font-bold text-slate-500 hover:text-slate-900 transition-colors"
            >
              {t('skip', 'Skip')}
            </button>
          </div>
        </div>

        {/* Walkthrough Slide Card */}
        <div className="bg-white border border-slate-200 shadow-sm rounded-2xl p-8 text-center space-y-5 transition-all">
          <div className={`w-16 h-16 rounded-2xl flex items-center justify-center mx-auto border shadow-xs ${currentStep.bgColor}`}>
            <Icon className="w-8 h-8" />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-center gap-1.5">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                {t('step', 'Step')} {currentStep.step} {t('of', 'of')} 3
              </span>
              {hasCompletedBefore && (
                <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-1.5 py-0.2 rounded flex items-center gap-0.5">
                  <CheckCircle2 className="w-2.5 h-2.5" />
                  {t('completed', 'Completed')}
                </span>
              )}
            </div>
            <h2 className="text-xl font-extrabold text-slate-900 font-manrope">{currentStep.title}</h2>
            <p className="text-xs text-slate-600 leading-relaxed max-w-sm mx-auto">{currentStep.desc}</p>
          </div>

          <div className="pt-2 text-[11px] text-slate-400">
            {t('tutorialNavHint', 'Use left/right arrow keys or buttons to navigate')}
          </div>
        </div>

        {/* Next / Proceed Button */}
        <button
          onClick={handleNext}
          className="w-full py-3.5 bg-[#0C2A18] hover:bg-[#15803D] text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2"
        >
          <span>
            {slideIndex < steps.length - 1
              ? t('nextStep', t('continue', 'Next Step'))
              : t('proceedToFarm', t('getStarted', 'Proceed to My Farm'))}
          </span>
          <ArrowRight className="w-4 h-4" />
        </button>

      </div>
    </div>
  );
}
