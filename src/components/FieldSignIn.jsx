import { ArrowLeft, Leaf } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function FieldSignIn({ title, description, children }) {
  return (
    <main className="field-auth-layout">
      <aside className="field-auth-image">
        <Link className="field-brand" to="/" aria-label="CarbonX home"><span><Leaf size={20} /></span>CarbonX</Link>
        <div className="field-auth-image-copy"><h2>{title}</h2><p>{description}</p></div>
      </aside>
      <div className="field-auth-panel">
        <div className="max-w-md w-full space-y-4">
          <Link to="/role-selection" className="field-back"><ArrowLeft size={16} /> All workspaces</Link>
          {children}
        </div>
      </div>
    </main>
  );
}
