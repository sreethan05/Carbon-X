import { useEffect, useState } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { Home, Compass, ShoppingCart, Wallet, Menu, Globe2, X, LogOut, Leaf, ShieldCheck, ClipboardList, BarChart3, Building2 } from 'lucide-react';
import { useLanguage } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';
import OfflineBanner from './OfflineBanner';
import InstallPrompt from './InstallPrompt';
import FarmerVoiceAssistant from '../features/voice-agent/FarmerVoiceAssistant';

const ROLE_NAV = {
  farmer: [
    { name: 'Dashboard', key: 'dashboard', path: '/farmer/dashboard', icon: Home },
    { name: 'Land Verification', key: 'landVerification', path: '/farmer/land-verification', icon: ShieldCheck },
    { name: 'Carbon Passport', key: 'carbonPassport', path: '/farm-analytics', icon: Compass },
    { name: 'Marketplace', key: 'marketplaceTitle', path: '/marketplace', icon: ShoppingCart },
    { name: 'Wallet & UPI Ledger', key: 'walletLedger', path: '/farmer/wallet', icon: Wallet },
    { name: 'Trust & Privacy', key: 'trustPrivacy', path: '/trust', icon: ShieldCheck },
    { name: 'Support', key: 'support', path: '/support', icon: ClipboardList },
  ],
  fpo: [
    { name: 'FPO Dashboard', key: 'fpoDashboard', path: '/fpo/dashboard', icon: Building2 },
    { name: 'Credit Pooling', key: 'creditPooling', path: '/fpo/credit-pooling', icon: ShieldCheck },
    { name: 'Marketplace', key: 'marketplaceTitle', path: '/marketplace', icon: ShoppingCart },
    { name: 'Trust & Privacy', key: 'trustPrivacy', path: '/trust', icon: ShieldCheck },
    { name: 'Support', key: 'support', path: '/support', icon: ClipboardList },
  ],
  buyer: [
    { name: 'ESG Dashboard', key: 'esgDashboard', path: '/corporate/dashboard', icon: Home },
    { name: 'Marketplace', key: 'marketplaceTitle', path: '/marketplace', icon: ShoppingCart },
    { name: 'Bulk Auto-Match', key: 'bulkAutoMatch', path: '/marketplace/checkout', icon: BarChart3 },
    { name: 'Certificates', key: 'certificates', path: '/corporate/dashboard#certificates', icon: ShieldCheck },
    { name: 'Trust & Privacy', key: 'trustPrivacy', path: '/trust', icon: ShieldCheck },
    { name: 'Support', key: 'support', path: '/support', icon: ClipboardList },
  ],
  verifier: [
    { name: 'FPO Audit Desk', key: 'fpoAuditDesk', path: '/fpo/dashboard', icon: Home },
    { name: 'Marketplace', key: 'marketplaceTitle', path: '/marketplace', icon: ShoppingCart },
    { name: 'Trust & Privacy', key: 'trustPrivacy', path: '/trust', icon: ShieldCheck },
    { name: 'Support', key: 'support', path: '/support', icon: ClipboardList },
  ],
  admin: [
    { name: 'Admin Dashboard', key: 'adminDashboard', path: '/admin/dashboard', icon: Home },
    { name: 'Marketplace', key: 'marketplaceTitle', path: '/marketplace', icon: ShoppingCart },
    { name: 'Trust & Privacy', key: 'trustPrivacy', path: '/trust', icon: ShieldCheck },
    { name: 'Support', key: 'support', path: '/support', icon: ClipboardList },
  ],
};

const VISITOR_NAV = [
  { name: 'Marketplace', key: 'marketplaceTitle', path: '/marketplace', icon: ShoppingCart },
  { name: 'Verify a certificate', path: '/verify', icon: ShieldCheck },
  { name: 'Trust & Privacy', key: 'trustPrivacy', path: '/trust', icon: Compass },
  { name: 'Support', key: 'support', path: '/support', icon: ClipboardList },
];

const ROLE_LABELS = { farmer: 'Farmer', fpo: 'FPO', buyer: 'Corporate buyer', verifier: 'Verifier', admin: 'Administrator' };
const SHORT_NAV_LABELS = {
  dashboard: 'Home', landVerification: 'Verify', carbonPassport: 'Passport',
  marketplaceTitle: 'Market', walletLedger: 'Wallet', esgDashboard: 'Desk',
  bulkAutoMatch: 'Bulk', trustPrivacy: 'Trust', fpoDashboard: 'Home', creditPooling: 'Pooling',
};
const STANDALONE = new Set([
  '/', '/role-selection', '/farmer/register', '/farmer-register', '/farmer/login',
  '/farmer-login', '/fpo/login', '/fpo-login', '/corporate/login', '/corporate-login',
  '/corporate/welcome', '/corporate-welcome', '/onboarding', '/welcome-tutorial',
]);

function Brand({ to }) {
  return <Link className="field-brand" to={to} aria-label="CarbonX home"><span><Leaf size={20} /></span>CarbonX</Link>;
}

export default function Layout({ children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { changeLanguage, currentLang, t, supportedLanguages } = useLanguage();
  const { user, logout, role, isAuthenticated } = useAuth();
  const [menuLocation, setMenuLocation] = useState(null);
  const menuOpen = menuLocation === location.key;
  const nav = isAuthenticated ? ROLE_NAV[role] || ROLE_NAV.farmer : VISITOR_NAV;
  const name = user?.name || ROLE_LABELS[role] || 'Account';
  const initials = name.trim().split(/\s+/).slice(0, 2).map((word) => word[0]).join('').toUpperCase();
  const home = isAuthenticated ? '/dashboard' : '/';
  const closeMenu = () => setMenuLocation(null);

  useEffect(() => {
    if (!menuOpen) return undefined;
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') setMenuLocation(null);
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [menuOpen]);

  function activePath(path) {
    if (path.includes('#')) return location.pathname + location.hash === path;
    if (location.pathname === path) return path !== '/corporate/dashboard' || location.hash !== '#certificates';
    if (path === '/verify') return location.pathname.startsWith('/verify/');
    if (path === '/farm-analytics') return /^\/(farm-map|farm-details|satellite-preview|farmer\/passport\/)/.test(location.pathname);
    if (path === '/trust') return location.pathname === '/privacy';
    if (path === '/farmer/wallet') return location.pathname === '/wallet';
    if (location.pathname === '/dashboard') return isAuthenticated && nav[0]?.path === path;
    return false;
  }

  function renderNav(items, mobile = false) {
    return items.map(({ key, name, path, icon: Icon }) => {
      const label = key ? t(key, name) : name;
      const shortLabel = mobile && currentLang === 'en' ? SHORT_NAV_LABELS[key] || label : label;
      return (
        <Link key={key || path} to={path} onClick={closeMenu} aria-current={activePath(path) ? 'page' : undefined} className={mobile ? 'field-dock-link' : 'field-rail-link'}>
          <Icon size={mobile ? 19 : 17} aria-hidden="true" />
          <span>{shortLabel}</span>
        </Link>
      );
    });
  }

  function signOut() {
    closeMenu();
    logout();
    navigate('/role-selection');
  }

  if (STANDALONE.has(location.pathname)) return <div className="public-route-shell min-h-screen">{children}</div>;

  return (
    <div className="field-workspace">
      <a className="field-skip" href="#main-content">Skip to content</a>
      <header className="field-topbar">
        <div className="field-topbar-identity">
          <button type="button" className="field-menu-btn" aria-expanded={menuOpen} aria-controls="workspace-navigation" aria-label={menuOpen ? 'Close menu' : 'Open menu'} onClick={() => setMenuLocation(menuOpen ? null : location.key)}>
            {menuOpen ? <X size={21} /> : <Menu size={21} />}
          </button>
          <Brand to={home} />
          {isAuthenticated && <span className="field-role-label">{ROLE_LABELS[role] || 'Workspace'}</span>}
        </div>
        <div className="field-topbar-actions">
          <label className="field-language">
            <Globe2 size={16} aria-hidden="true" />
            <select value={currentLang} onChange={e => changeLanguage(e.target.value)} aria-label="Select interface language">
              {supportedLanguages.map((lang) => <option key={lang.code} value={lang.code}>{lang.nativeLabel}</option>)}
            </select>
          </label>
          {isAuthenticated ? (
            <button className="field-icon-button" type="button" onClick={signOut} aria-label={t('logout', 'Logout')} title={t('logout', 'Logout')}><LogOut size={18} /></button>
          ) : <NavLink to="/role-selection" className="field-button field-button-dark">{t('login', 'Login')}</NavLink>}
        </div>
      </header>
      <OfflineBanner />
      <div className="field-workspace-grid">
        {menuOpen && <button type="button" className="field-menu-backdrop" onClick={closeMenu} aria-label="Close navigation" />}
        <aside id="workspace-navigation" className={`field-rail ${menuOpen ? 'field-rail-open' : ''}`}>
          <nav aria-label="Workspace navigation">
            <p>{isAuthenticated ? 'Workspace' : 'Explore CarbonX'}</p>
            {renderNav(nav)}
          </nav>
          {isAuthenticated && (
            <div className="field-account">
              <span aria-hidden="true">{initials}</span>
              <div><strong>{name}</strong><small>{[user?.village, user?.district].filter(Boolean).join(', ') || ROLE_LABELS[role]}</small></div>
            </div>
          )}
        </aside>
        <main id="main-content" className="field-main">{children}</main>
      </div>
      {isAuthenticated && role === 'farmer' && <FarmerVoiceAssistant />}
      <nav className="field-dock" aria-label="Quick navigation">{renderNav(nav.slice(0, 5), true)}</nav>
      <InstallPrompt />
    </div>
  );
}
