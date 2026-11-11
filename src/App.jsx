import React, { Suspense, lazy } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import { LanguageProvider } from './context/LanguageContext';
import { AuthProvider, useAuth } from './context/AuthContext';

const LandingPage = lazy(() => import('./pages/LandingPage'));
const RoleSelection = lazy(() => import('./pages/RoleSelection'));
const FarmerRegister = lazy(() => import('./pages/FarmerRegister'));
const FarmerLogin = lazy(() => import('./pages/FarmerLogin'));
const WelcomeTutorial = lazy(() => import('./pages/WelcomeTutorial'));
const FarmMapRegistration = lazy(() => import('./pages/FarmMapRegistration'));
const FarmDetailsForm = lazy(() => import('./pages/FarmDetailsForm'));
const SatellitePreview = lazy(() => import('./pages/SatellitePreview'));
const SuccessScreen = lazy(() => import('./pages/SuccessScreen'));
const FarmOwnershipVerification = lazy(() => import('./pages/FarmOwnershipVerification'));
const VerificationSuccess = lazy(() => import('./pages/VerificationSuccess'));
const FarmerDashboard = lazy(() => import('./pages/FarmerDashboard'));
const DetailedFarmAnalytics = lazy(() => import('./pages/DetailedFarmAnalytics'));
const CarbonWallet = lazy(() => import('./pages/CarbonWallet'));
const FPODashboard = lazy(() => import('./pages/FPODashboard'));
const FPOLogin = lazy(() => import('./pages/FPOLogin'));
const AdminDashboard = lazy(() => import('./pages/AdminDashboard'));
const CorporateWelcome = lazy(() => import('./pages/CorporateWelcome'));
const CorporateLogin = lazy(() => import('./pages/CorporateLogin'));
const CorporateDashboard = lazy(() => import('./pages/CorporateDashboard'));
const Marketplace = lazy(() => import('./pages/Marketplace'));
const CreateListing = lazy(() => import('./pages/CreateListing'));
const CorporateCreditAnalysis = lazy(() => import('./pages/CorporateCreditAnalysis'));
const CertificateRetirementPage = lazy(() => import('./pages/CertificateRetirementPage'));
const SupportCenter = lazy(() => import('./pages/SupportCenter'));
const VerifyPage = lazy(() => import('./pages/VerifyPage'));
const TrustCenter = lazy(() => import('./pages/TrustCenter'));

const RouteFallback = () => (
  <div className="min-h-[50vh] grid place-items-center text-sm text-slate-600" role="status">
    Loading CarbonX…
  </div>
);

function ProtectedRoute({ children, roles }) {
  const { isAuthenticated, role, loading } = useAuth();
  if (loading) return <div className="min-h-screen grid place-items-center text-sm text-slate-600">Restoring your secure session…</div>;
  if (!isAuthenticated) return <Navigate to="/farmer/login" replace />;
  if (roles && !roles.includes(role)) return <Navigate to="/dashboard" replace />;
  return children;
}

function DashboardRouter() {
  const { role } = useAuth();
  switch (role) {
    case 'buyer':
      return <CorporateDashboard />;
    case 'fpo':
    case 'verifier':
      return <FPODashboard />;
    case 'admin':
      return <AdminDashboard />;
    default:
      return <FarmerDashboard />;
  }
}

export default function App() {
  return (
    <AuthProvider>
      <LanguageProvider>
        <Router>
          <Layout>
            <Suspense fallback={<RouteFallback />}>
            <Routes>
              {/* Public Gateway & Role Routes */}
              <Route path="/" element={<LandingPage />} />
              <Route path="/verify" element={<VerifyPage />} />
              <Route path="/verify/:certId" element={<VerifyPage />} />
              <Route path="/role-selection" element={<RoleSelection />} />

              {/* Farmer Auth & Onboarding Routes */}
              <Route path="/farmer/register" element={<FarmerRegister />} />
              <Route path="/farmer-register" element={<FarmerRegister />} />
              <Route path="/farmer/login" element={<FarmerLogin />} />
              <Route path="/farmer-login" element={<FarmerLogin />} />
              <Route path="/onboarding" element={<WelcomeTutorial />} />
              <Route path="/welcome-tutorial" element={<WelcomeTutorial />} />

              {/* FPO & Corporate Login Routes */}
              <Route path="/fpo/login" element={<FPOLogin />} />
              <Route path="/fpo-login" element={<FPOLogin />} />
              <Route path="/corporate/login" element={<CorporateLogin />} />
              <Route path="/corporate-login" element={<CorporateLogin />} />

              {/* Farmer Verification & Mapping Flow */}
              <Route path="/farmer/land-verification" element={<ProtectedRoute roles={['farmer', 'fpo', 'verifier', 'admin']}><FarmOwnershipVerification /></ProtectedRoute>} />
              <Route path="/farm-verification" element={<ProtectedRoute roles={['farmer', 'fpo', 'verifier', 'admin']}><FarmOwnershipVerification /></ProtectedRoute>} />
              <Route path="/farm-map" element={<ProtectedRoute roles={['farmer', 'fpo', 'verifier', 'admin']}><FarmMapRegistration /></ProtectedRoute>} />
              <Route path="/farm-details" element={<ProtectedRoute roles={['farmer', 'fpo', 'verifier', 'admin']}><FarmDetailsForm /></ProtectedRoute>} />
              <Route path="/satellite-preview" element={<ProtectedRoute roles={['farmer', 'fpo', 'verifier', 'admin']}><SatellitePreview /></ProtectedRoute>} />
              <Route path="/verification-success" element={<ProtectedRoute roles={['farmer', 'fpo', 'verifier', 'admin']}><VerificationSuccess /></ProtectedRoute>} />
              <Route path="/submission-success" element={<ProtectedRoute roles={['farmer', 'fpo', 'verifier', 'admin']}><SuccessScreen /></ProtectedRoute>} />

              {/* Farmer Dashboard & Analytics & Wallet */}
              <Route path="/farmer/dashboard" element={<ProtectedRoute><FarmerDashboard /></ProtectedRoute>} />
              <Route path="/dashboard" element={<ProtectedRoute><DashboardRouter /></ProtectedRoute>} />
              <Route path="/farmer/passport/:farmId" element={<ProtectedRoute><DetailedFarmAnalytics /></ProtectedRoute>} />
              <Route path="/farm-analytics" element={<ProtectedRoute><DetailedFarmAnalytics /></ProtectedRoute>} />
              <Route path="/farmer/wallet" element={<ProtectedRoute><CarbonWallet /></ProtectedRoute>} />
              <Route path="/wallet" element={<ProtectedRoute><CarbonWallet /></ProtectedRoute>} />

              {/* FPO Command Center & Pooling */}
              <Route path="/fpo/dashboard" element={<ProtectedRoute roles={['fpo', 'verifier']}><FPODashboard /></ProtectedRoute>} />
              <Route path="/fpo/credit-pooling" element={<ProtectedRoute roles={['fpo', 'verifier']}><FPODashboard /></ProtectedRoute>} />

              {/* Admin Oversight */}
              <Route path="/admin/dashboard" element={<ProtectedRoute roles={['admin']}><AdminDashboard /></ProtectedRoute>} />

              {/* Corporate Buyer Portal & Marketplace */}
              <Route path="/corporate/welcome" element={<CorporateWelcome />} />
              <Route path="/corporate-welcome" element={<CorporateWelcome />} />
              <Route path="/corporate/dashboard" element={<ProtectedRoute roles={['buyer']}><CorporateDashboard /></ProtectedRoute>} />
              <Route path="/marketplace" element={<Marketplace />} />
              <Route path="/create-listing" element={<ProtectedRoute><CreateListing /></ProtectedRoute>} />
              <Route path="/marketplace/checkout" element={<ProtectedRoute roles={['buyer']}><CorporateCreditAnalysis /></ProtectedRoute>} />
              <Route path="/credit-analysis/:id" element={<ProtectedRoute roles={['buyer']}><CorporateCreditAnalysis /></ProtectedRoute>} />
              <Route path="/buyer/certificates/:certId" element={<ProtectedRoute roles={['buyer']}><CertificateRetirementPage /></ProtectedRoute>} />

              {/* Support & trust */}
              <Route path="/support" element={<SupportCenter />} />
              <Route path="/trust" element={<TrustCenter />} />
              <Route path="/privacy" element={<TrustCenter />} />

              {/* Catch-all */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
            </Suspense>
          </Layout>
        </Router>
      </LanguageProvider>
    </AuthProvider>
  );
}
