import { ArrowDown, ArrowRight, Building2, Globe2, Leaf, Map, ScanLine, ShieldCheck, Sprout, Users } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useLanguage } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';

const steps = [
  { title: 'Map the parcel', detail: 'Draw the field boundary and attach the land evidence needed for review.', icon: Map },
  { title: 'Review the estimate', detail: 'Satellite observations and practice evidence inform a carbon estimate with a published uncertainty range.', icon: ScanLine },
  { title: 'Follow the record', detail: 'Track purchases, settlement splits, and retirement in the ledger.', icon: ShieldCheck },
];

const roles = [
  { title: 'Farmers', detail: 'Register a field, follow its review, and see what a sale could earn.', to: '/farmer/register', label: 'Register as a farmer', icon: Sprout },
  { title: 'Farmer organizations', detail: 'Review member parcels and pool eligible credits across the cooperative.', to: '/fpo/login', label: 'Open the FPO desk', icon: Users },
  { title: 'Corporate buyers', detail: 'Compare listings, inspect the evidence, and track retirement certificates.', to: '/corporate/login', label: 'Open the buyer desk', icon: Building2 },
];

export default function LandingPage() {
  const { currentLang, changeLanguage, supportedLanguages } = useLanguage();
  const { isAuthenticated, role } = useAuth();

  return (
    <div className="field-site">
      <header className="field-site-header">
        <Link className="field-brand" to="/" aria-label="CarbonX home"><span><Leaf size={21} /></span>CarbonX</Link>
        <nav aria-label="Public navigation" className="field-site-nav">
          <a href="#how-it-works">How it works</a>
          <Link to="/marketplace">Marketplace</Link>
          <Link to="/trust">Trust center</Link>
        </nav>
        <div className="field-site-controls">
          <label className="field-language">
            <Globe2 size={16} aria-hidden="true" />
            <select aria-label="Select interface language" value={currentLang} onChange={(event) => changeLanguage(event.target.value)}>
              {supportedLanguages.map((language) => <option key={language.code} value={language.code}>{language.nativeLabel}</option>)}
            </select>
          </label>
          <Link className="field-button field-button-dark" to={isAuthenticated ? '/dashboard' : '/role-selection'}>
            {isAuthenticated ? 'Workspace' : 'Sign in'} <ArrowRight size={16} />
          </Link>
        </div>
      </header>

      <main id="main-content">
        <section className="field-hero">
          <div className="field-hero-copy">
            <p className="field-kicker"><span /> Agricultural carbon & biodiversity</p>
            <h1>Carbon starts<br className="hidden sm:block" /> in the <em>field.</em></h1>
            <p>CarbonX connects Indian smallholder farms to carbon markets through field evidence, satellite estimates, and a settlement record everyone can follow.</p>
            <div className="field-actions">
              <Link className="field-button field-button-lime" to="/farmer/register">Register a farm <ArrowRight size={17} /></Link>
              <Link className="field-button field-button-outline" to="/marketplace">Explore marketplace</Link>
            </div>
            <a className="field-scroll-link" href="#how-it-works"><ArrowDown size={17} /> From parcel to purchase</a>
          </div>
          <figure className="field-hero-photo">
            <figcaption><Map size={17} aria-hidden="true" /> Telangana farmland <span>Illustrative aerial view</span></figcaption>
          </figure>
        </section>

        <section id="how-it-works" className="field-process">
          <div className="field-section-heading">
            <p className="field-kicker"><span /> How it works</p>
            <h2>Follow the evidence.</h2>
          </div>
          <div className="field-process-grid">
            {steps.map(({ title, detail, icon: Icon }) => (
              <article key={title}><Icon size={23} aria-hidden="true" /><h3>{title}</h3><p>{detail}</p></article>
            ))}
          </div>
        </section>

        <section className="field-disclosure">
          <div><p className="field-kicker"><span /> Claims & verification</p><h2>Know what you’re buying.</h2>
            <p>Carbon volumes are proxy estimates until field validation passes. The pilot settlement ledger records a 70% farmer share floor. Pilot bank transfers are simulated.</p>
          </div>
          <div className="field-actions">
            <Link className="field-button field-button-lime" to="/trust">Read the evidence policy <ArrowRight size={17} /></Link>
            <Link className="field-button field-button-light" to="/verify">Verify a certificate</Link>
          </div>
        </section>

        <section className="field-roles">
          <div className="field-section-heading"><p className="field-kicker"><span /> Workspaces</p><h2>Choose your role.</h2></div>
          <div className="field-role-grid">
            {roles.map(({ title, detail, to, label, icon: Icon }) => (
              <article key={to}>
                <Icon size={25} aria-hidden="true" />
                <h3>{title}</h3><p>{detail}</p>
                <Link to={to === '/fpo/login' && isAuthenticated && (role === 'fpo' || role === 'verifier') ? '/fpo/dashboard' : to}>
                  {label} <ArrowRight size={17} />
                </Link>
              </article>
            ))}
          </div>
        </section>
      </main>

      <footer className="field-footer">
        <Link className="field-brand" to="/"><span><Leaf size={19} /></span>CarbonX</Link>
        <nav aria-label="Footer"><Link to="/trust">Trust & privacy</Link><Link to="/verify">Verification</Link><Link to="/support">Support</Link></nav>
      </footer>
    </div>
  );
}
