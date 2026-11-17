import { Link } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Building2, Globe, Leaf, Users } from 'lucide-react';
import { useLanguage } from '../context/LanguageContext';

export default function RoleSelection() {
  const { t } = useLanguage();
  const roles = [
    { route: '/farmer/login', title: t('farmerLandOwner', 'Farmer & Land Owner'), icon: Users, description: 'Enroll land, check farm estimates, and track settlements.' },
    { route: '/fpo/login', title: t('fpoOfficer', 'FPO / Cooperative Officer'), icon: Building2, description: 'Onboard members and review parcels that need verification.' },
    { route: '/corporate/login', title: t('corporateBuyer', 'Corporate Buyer & ESG Officer'), icon: Globe, description: 'Compare listings and manage your retirement records.' },
  ];

  return (
    <main className="field-site field-workspace-select">
      <header className="field-site-header">
        <Link className="field-brand" to="/" aria-label="CarbonX home"><span><Leaf size={20} /></span>CarbonX</Link>
        <Link className="field-back" to="/"><ArrowLeft size={16} /> {t('backToGateway', 'Back to Gateway')}</Link>
      </header>
      <div className="field-section-heading">
        <h1>{t('selectEcosystemRole', 'Choose your workspace')}</h1>
      </div>
      <div className="field-role-grid">
        {roles.map(({ route, title, icon: Icon, description }) => (
          <article key={route}>
            <Icon size={24} aria-hidden="true" />
            <h2>{title}</h2>
            <p>{description}</p>
            <Link to={route} aria-label={`${title} sign in`}>Sign in <ArrowRight size={16} /></Link>
            {route === '/farmer/login' && <Link className="field-register-link" to="/farmer/register">Create a farmer account <ArrowRight size={16} /></Link>}
          </article>
        ))}
      </div>
    </main>
  );
}
