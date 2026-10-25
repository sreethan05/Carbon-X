import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  PhoneCall, HelpCircle, ChevronDown, ChevronUp, Send, MessageSquare, User,
  ChevronLeft, Shield, Mail, Clock, CheckCircle2, AlertTriangle, FileText, Lock,
  Ticket
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { createSupportTicket, getMySupportTickets } from '../services/api';

const FAQS = [
  {
    q: 'How often does the satellite scan my farm?',
    a: 'Sentinel-2 revisits every ~5 days. A monitoring cycle on the same cadence compares your farm\'s stored NDVI against the latest satellite reading and flags a drop of 0.15 or more for FPO field review — it is triggered on the natural satellite orbital cycle rather than an artificial fixed schedule.',
  },
  {
    q: 'How is credit revenue split between farmers, FPOs, and CarbonX?',
    a: 'By immutable platform invariant, a 70% gross floor is code-enforced directly to the smallholder farmer using integer-paise math. The FPO cooperative receives a 5% verification fee when field attestation is proven. CarbonX retains 25% (or 30% if no FPO is linked) for continuous satellite MRV, cloud infrastructure, and compliance.',
  },
  {
    q: 'Does CarbonX use an Ethereum/Polygon blockchain for every transaction?',
    a: 'Our live operational ledger is a plot-specific, tamper-evident SHA-256 cryptographic hash chain stored in PostgreSQL (ISSUE → SALE → SPLIT → RETIRE). You can cryptographically verify that records have not been altered with zero gas fees. Public Polygon ERC-1155 token settlement is scheduled in our Phase 2 roadmap for international trading desks.',
  },
  {
    q: 'When do I get my UPI payout?',
    a: 'When a buyer purchases credits, funds are held in escrow and the exact split is written to each farm\'s hash chain. UPI settlement rails and bank clearing are simulated in this pilot phase — payouts are recorded immutably on the cryptographic ledger rather than cleared via commercial banking gateways.',
  },
  {
    q: 'What if my trees or crops are damaged by a storm?',
    a: 'Report it to your FPO coordinator. The 5-day monitoring cycle automatically detects sudden canopy loss (NDVI drop ≥ 0.15) and temporarily flags credits at-risk to prevent invalid corporate claims until a field inspection clears the plot.',
  },
  {
    q: 'How is my personal and land data protected?',
    a: 'In strict alignment with India\'s DPDP Act 2023, CarbonX stores only the last 4 digits of your Aadhaar (aadhaar_last4) for checksum validation. Full Aadhaar numbers are never persisted. Farm documents are fingerprinted with SHA-256 for tamper detection, and personal identity is never disclosed to corporate buyers.',
  },
  {
    q: 'How are biodiversity credits estimated?',
    a: 'Biodiversity scores are calibrated against real GBIF species richness records across India\'s agricultural biomes. An automated quality gate refuses unverified models, and credits are capped with an explicit 10–30% uncertainty deduction based on evidence quality.',
  },
];

const TRUTH_DISCLOSURES = [
  {
    title: 'Deterministic MRV (No Black Box)',
    desc: 'Carbon sequestration is calculated via VM0042-aligned 5-step formulas combining crop-calibrated biomass factors and IPCC soil constants, with explicit 10–30% uncertainty deductions. No unverified neural net claims.',
    icon: FileText,
  },
  {
    title: 'Tamper-Evident SHA-256 Hash Chain',
    desc: 'All credit issuances, escrow buys, and permanent retirements write to a plot-level cryptographic hash chain (recomputable in python via scripts/tamper_demo.py). On-chain Polygon tokenization is staged on the Phase 2 roadmap.',
    icon: Shield,
  },
  {
    title: 'Enforced 70% Smallholder Revenue Floor',
    desc: 'The 70% farmer share is a tested code invariant executed in integer paise. FPO cooperatives earn 5% only with proven attestation. Payout splits are visible on-screen for every transaction.',
    icon: CheckCircle2,
  },
  {
    title: '5-Day Sentinel-2 Monitoring Revisit',
    desc: 'Automated satellite monitoring runs on the natural Sentinel-2 ~5-day orbital cadence. A drop of 0.15 or more in stored NDVI flags credits at-risk and routes the parcel to the FPO ground-truth queue.',
    icon: Clock,
  },
  {
    title: 'Pilot Settlement Rails & Cadastral Parcels',
    desc: 'Land registry boundary validation is evaluated against 30 curated Telangana survey parcels (Dharani/Bhu-Naksha). UPI banking rails operate with simulated escrow in current pilot deployments.',
    icon: AlertTriangle,
  },
  {
    title: 'DPDP Act 2023: Aadhaar Last-4 Retention',
    desc: 'Only the last 4 digits of Aadhaar are saved in the database. FPO-assisted onboarding allows community attestation without document retention, minimizing PII exposure.',
    icon: Lock,
  },
];

const QUICK_REPLIES = [
  'How do I map my farm?',
  'How is revenue split (70% floor)?',
  'Does CarbonX use blockchain?',
  'When is the next satellite scan?',
  'How are carbon credits calculated?',
  'What is NDVI?',
];

const SUPPORT_CATEGORIES = [
  { value: 'boundary', label: 'Farm boundary is wrong / cannot be corrected' },
  { value: 'ownership', label: 'Land ownership match is wrong' },
  { value: 'estimate', label: 'Dispute the carbon estimate' },
  { value: 'payout', label: 'Payout amount or status issue' },
  { value: 'privacy', label: 'Privacy / data request' },
  { value: 'other', label: 'Something else' },
];

const TICKET_STATUS_STYLES = {
  Open: 'bg-sky-50 text-sky-800 border-sky-200',
  'In Review': 'bg-amber-50 text-amber-900 border-amber-200',
  Resolved: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  Rejected: 'bg-rose-50 text-rose-800 border-rose-200',
};

export default function SupportCenter() {
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();
  const [openFaq, setOpenFaq] = useState(0);
  const [messages, setMessages] = useState([
    { role: 'bot', text: 'Hello! I am CarbonX Support. How can I assist you with farm verification, satellite monitoring, or credit transparent settlement?' }
  ]);
  const [input, setInput] = useState('');
  const chatEnd = useRef(null);

  // Tracked support requests (Open → In Review → Resolved/Rejected).
  const [tickets, setTickets] = useState([]);
  const [ticketForm, setTicketForm] = useState({ category: 'boundary', title: '', detail: '', farm_id: '' });
  const [ticketBusy, setTicketBusy] = useState(false);
  const [ticketError, setTicketError] = useState('');
  const [ticketInfo, setTicketInfo] = useState('');

  const loadTickets = useCallback(async () => {
    if (!isAuthenticated) {
      setTickets([]);
      return;
    }
    const res = await getMySupportTickets(50);
    if (res?.success) setTickets(res.tickets || []);
  }, [isAuthenticated]);

  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);
  useEffect(() => { loadTickets(); }, [loadTickets]);

  const submitTicket = async (e) => {
    e.preventDefault();
    setTicketBusy(true);
    setTicketError('');
    setTicketInfo('');
    const res = await createSupportTicket({
      category: ticketForm.category,
      title: ticketForm.title.trim(),
      detail: ticketForm.detail.trim(),
      farm_id: ticketForm.farm_id.trim() || undefined,
    });
    setTicketBusy(false);
    if (res?.success) {
      setTicketInfo(res.storage === 'live_db'
        ? `Request ${res.ticket?.id?.slice(0, 8) || ''}… filed — staff will respond within the published SLA.`
        : `Request filed in labelled demo storage (DB not configured) — status tracking works within this device session.`);
      setTicketForm({ category: ticketForm.category, title: '', detail: '', farm_id: '' });
      loadTickets();
    } else {
      setTicketError(res?.message || 'The request could not be filed. Please retry.');
    }
  };

  const send = (text) => {
    if (!text.trim()) return;
    setMessages(m => [...m, { role: 'user', text }]);
    setInput('');
    setTimeout(() => {
      const lower = text.toLowerCase();
      const reply = lower.includes('map') ? 'You can map your farm by clicking "Map New Farm" on your dashboard. Draw the boundary on the satellite map and our system will calculate the area automatically.'
        : (lower.includes('split') || lower.includes('70') || lower.includes('payout') || lower.includes('floor')) ? 'Revenue split is code-enforced: Smallholder farmers receive a minimum 70% floor of gross credit value directly. FPOs receive 5% for field attestation, and CarbonX retains 25% (or 30% if unlinked) for satellite MRV and operations.'
        : (lower.includes('blockchain') || lower.includes('crypto') || lower.includes('polygon') || lower.includes('hash')) ? 'CarbonX uses a tamper-evident SHA-256 cryptographic hash chain stored in PostgreSQL for zero-gas, instant auditability. Polygon mainnet token minting is staged in Phase 2 of our roadmap.'
        : (lower.includes('scan') || lower.includes('satellite') || lower.includes('revisit')) ? 'Sentinel-2 orbits revisit your plot every ~5 days. Our automated monitoring checks whether stored NDVI has dropped by ≥ 0.15, flagging any stress for FPO coordinator review.'
        : lower.includes('credit') ? 'Carbon credits are estimated using a deterministic VM0042-aligned engine: crop-calibrated biomass + IPCC soil sequestration constants, minus a 10–30% uncertainty deduction based on evidence quality.'
        : lower.includes('ndvi') ? 'NDVI (Normalized Difference Vegetation Index) measures photosynthetic plant health using Sentinel-2 red and near-infrared bands, on a scale from -1.0 to +1.0.'
        : (lower.includes('privacy') || lower.includes('aadhaar') || lower.includes('data')) ? 'We follow DPDP Act 2023 principles: only aadhaar_last4 is stored, documents are SHA-256 hashed for tamper-proofing, and buyer certificates never disclose farmer PII.'
        : 'I can assist with farm mapping, 5-day satellite monitoring, credit calculations, revenue split guarantees, and truth-in-advertising statements. What would you like to know?';
      setMessages(m => [...m, { role: 'bot', text: reply }]);
    }, 1000);
  };

  return (
    <div className="pb-24 px-4 pt-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <button aria-label="Back to dashboard" onClick={() => navigate('/dashboard')} className="p-2 rounded-xl bg-white border border-forest-100 text-carbon-600 hover:text-forest-800">
          <ChevronLeft className="w-5 h-5" />
        </button>
        <div>
          <h1 className="text-xl font-bold text-carbon-900 font-manrope">Support & Transparency Center</h1>
          <p className="text-xs text-agriText-muted">Knowledge base, pilot disclosures, verified contact channels, and AI assistant.</p>
        </div>
      </div>

      {/* Truth-in-Advertising & Pilot Disclosures */}
      <div className="bg-white rounded-2xl border border-forest-100 shadow-sm p-6 space-y-4">
        <div className="flex items-center gap-2">
          <Shield className="w-5 h-5 text-primary" />
          <h2 className="text-sm font-bold text-carbon-900 font-manrope uppercase tracking-wider">
            Truth-in-Advertising & Pilot Integrity Disclosures
          </h2>
        </div>
        <p className="text-xs text-agriText-muted leading-relaxed">
          CarbonX operates under strict scientific honesty and verifiable claims. The statements below reflect the exact system architecture, code invariants, and pilot scope:
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 pt-2">
          {TRUTH_DISCLOSURES.map((item, idx) => {
            const Icon = item.icon;
            return (
              <div key={idx} className="bg-surface-sage/30 border border-forest-200/80 rounded-xl p-4 space-y-2">
                <div className="flex items-center gap-2 text-primary">
                  <Icon className="w-4 h-4 shrink-0" />
                  <h3 className="text-xs font-bold text-carbon-900">{item.title}</h3>
                </div>
                <p className="text-[11px] text-agriText-muted leading-relaxed">{item.desc}</p>
              </div>
            );
          })}
        </div>
      </div>

      {/* FAQ Accordion */}
      <div className="bg-white rounded-2xl border border-forest-100 shadow-sm overflow-hidden">
        <h2 className="text-xs font-bold text-carbon-700 uppercase tracking-wider p-4 border-b border-forest-50 bg-[#F8FAF8]">
          Frequently Asked Questions
        </h2>
        {FAQS.map((faq, i) => (
          <div key={i} className="border-b border-forest-50 last:border-0">
            <button
              onClick={() => setOpenFaq(openFaq === i ? -1 : i)}
              className="w-full flex justify-between items-center p-4 text-left hover:bg-forest-50/30 transition-colors"
            >
              <span className="text-xs font-bold text-carbon-800">{faq.q}</span>
              {openFaq === i ? <ChevronUp size={16} className="text-carbon-400 shrink-0 ml-2" /> : <ChevronDown size={16} className="text-carbon-400 shrink-0 ml-2" />}
            </button>
            {openFaq === i && <p className="px-4 pb-4 text-xs text-carbon-600 leading-relaxed bg-[#FAFCFA]">{faq.a}</p>}
          </div>
        ))}
      </div>

      {/* Tracked requests — farmers can file and follow resolution */}
      <div className="bg-white rounded-2xl border border-forest-100 shadow-sm p-6 space-y-4">
        <div className="flex items-center gap-2">
          <Ticket className="w-5 h-5 text-primary" />
          <h2 className="text-sm font-bold text-carbon-900 font-manrope uppercase tracking-wider">
            My Requests
          </h2>
          <span className="text-[10px] font-bold text-carbon-500">
            {tickets.length ? `${tickets.length} tracked request${tickets.length === 1 ? '' : 's'}` : ''}
          </span>
        </div>
        <p className="text-xs text-agriText-muted">
          Report a wrong boundary, an ownership mismatch, a disputed estimate, a payout issue or a privacy
          request. Requests are tracked to a written resolution — payouts are corrected via refund/ledger
          events, never by editing history, and no money moves from this form.
        </p>

        {isAuthenticated ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <form onSubmit={submitTicket} className="rounded-xl border border-forest-100 bg-surface-sage/30 p-4 space-y-3">
              <select
                value={ticketForm.category}
                onChange={(e) => setTicketForm(f => ({ ...f, category: e.target.value }))}
                aria-label="Request category"
                className="w-full rounded-xl border border-forest-200 bg-white px-3 py-2 text-xs font-semibold text-carbon-800"
              >
                {SUPPORT_CATEGORIES.map(c => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </select>
              <input
                value={ticketForm.title}
                onChange={(e) => setTicketForm(f => ({ ...f, title: e.target.value }))}
                maxLength={140}
                aria-label="Short title"
                required
                placeholder="Short title (e.g. Boundary misses the south canal)"
                className="w-full rounded-xl border border-forest-200 bg-white px-3 py-2 text-xs"
              />
              <textarea
                value={ticketForm.detail}
                onChange={(e) => setTicketForm(f => ({ ...f, detail: e.target.value }))}
                maxLength={4000}
                rows={3}
                aria-label="Request details"
                required
                placeholder="Describe what is wrong, what should change, and when it started."
                className="w-full rounded-xl border border-forest-200 bg-white px-3 py-2 text-xs"
              />
              <input
                value={ticketForm.farm_id}
                onChange={(e) => setTicketForm(f => ({ ...f, farm_id: e.target.value }))}
                maxLength={120}
                aria-label="Farm or parcel reference"
                placeholder="Farm / parcel reference (optional)"
                className="w-full rounded-xl border border-forest-200 bg-white px-3 py-2 text-xs"
              />
              {ticketError && <p className="text-[11px] font-semibold text-rose-700">{ticketError}</p>}
              {ticketInfo && <p className="text-[11px] font-semibold text-emerald-800">{ticketInfo}</p>}
              <button
                type="submit"
                disabled={ticketBusy}
                className="w-full py-2.5 rounded-xl bg-[#0C2A18] hover:bg-[#15803D] text-white text-xs font-bold disabled:opacity-60"
              >
                {ticketBusy ? 'Filing…' : 'File request'}
              </button>
            </form>

            <div className="space-y-2">
              {tickets.length === 0 ? (
                <div className="rounded-xl border border-forest-100 bg-surface-sage/30 p-4 text-xs text-carbon-600">
                  No requests yet. Filed requests appear here with their status and the staff resolution.
                </div>
              ) : (
                <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                  {tickets.map(t => (
                    <div key={t.id} className="rounded-xl border border-forest-100 p-3 space-y-1">
                      <div className="flex items-center gap-2">
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${TICKET_STATUS_STYLES[t.status] || 'bg-slate-50 text-slate-700 border-slate-200'}`}>
                          {t.status}
                        </span>
                        <span className="text-[10px] font-bold uppercase tracking-wide text-carbon-500">
                          {t.category}
                        </span>
                        <span className="ml-auto text-[10px] font-mono text-carbon-400">
                          {String(t.id || '').slice(0, 8)}
                        </span>
                      </div>
                      <p className="text-xs font-bold text-carbon-900">{t.title}</p>
                      <p className="text-[11px] text-carbon-700 leading-snug">{t.detail}</p>
                      {t.resolution && (
                        <p className="text-[11px] text-emerald-900 bg-emerald-50 border border-emerald-100 rounded-lg px-2 py-1">
                          <strong>Resolution:</strong> {t.resolution}
                        </p>
                      )}
                      {t.staff_notes && !t.resolution && (
                        <p className="text-[11px] text-carbon-600">
                          <strong>Staff note:</strong> {t.staff_notes}
                        </p>
                      )}
                      <p className="text-[10px] text-carbon-400">
                        Filed {String(t.created_at || '').slice(0, 10)}{t.updated_at && t.updated_at !== t.created_at ? ` · updated ${String(t.updated_at).slice(0, 10)}` : ''}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ) : (
          <button
            onClick={() => navigate('/farmer/login')}
            className="px-4 py-2 rounded-xl bg-[#0C2A18] text-white text-xs font-bold hover:bg-[#15803D]"
          >
            Sign in to file a request
          </button>
        )}
      </div>

      {/* Support & Helpdesk Contact Details */}
      <div className="bg-white rounded-2xl border border-forest-100 shadow-sm p-6 space-y-4">
        <h2 className="text-xs font-bold text-carbon-700 uppercase tracking-wider">
          Pilot Helpdesk & Contact Channels
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <div className="bg-forest-50/60 border border-forest-100 rounded-xl p-4 flex items-start gap-3">
            <div className="p-2.5 bg-forest-100 text-forest-700 rounded-xl shrink-0">
              <PhoneCall className="w-4 h-4" />
            </div>
            <div>
              <p className="text-xs font-bold text-carbon-800">FPO Field Coordinator</p>
              <p className="text-[11px] text-carbon-600 mt-0.5">Reach your assigned cooperative officer for ground assistance.</p>
              <p className="text-[11px] font-mono font-bold text-primary mt-1">+91 90000 00001</p>
            </div>
          </div>

          <div className="bg-forest-50/60 border border-forest-100 rounded-xl p-4 flex items-start gap-3">
            <div className="p-2.5 bg-forest-100 text-forest-700 rounded-xl shrink-0">
              <Mail className="w-4 h-4" />
            </div>
            <div>
              <p className="text-xs font-bold text-carbon-800">Support & Grievances</p>
              <p className="text-[11px] text-carbon-600 mt-0.5">Prompt technical and ledger verification resolution.</p>
              <p className="text-[11px] font-mono font-bold text-primary mt-1">support@carbonx.agri</p>
            </div>
          </div>

          <div className="bg-forest-50/60 border border-forest-100 rounded-xl p-4 flex items-start gap-3 sm:col-span-2 lg:col-span-1">
            <div className="p-2.5 bg-forest-100 text-forest-700 rounded-xl shrink-0">
              <Clock className="w-4 h-4" />
            </div>
            <div>
              <p className="text-xs font-bold text-carbon-800">Operational Hours</p>
              <p className="text-[11px] text-carbon-600 mt-0.5">Monday through Saturday</p>
              <p className="text-[11px] font-semibold text-carbon-800 mt-1">9:00 AM – 6:00 PM IST</p>
            </div>
          </div>
        </div>
      </div>

      {/* Chatbot */}
      <div className="bg-white rounded-2xl border border-forest-100 shadow-sm overflow-hidden">
        <div className="bg-[#0C2A18] text-white p-4 flex items-center gap-2">
          <MessageSquare size={18} />
          <span className="text-xs font-bold font-manrope">CarbonX Transparency & Support Assistant</span>
        </div>
        <div className="p-4 space-y-3 max-h-80 overflow-y-auto">
          {messages.map((m, i) => (
            <div key={i} className={`flex gap-2 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${m.role === 'user' ? 'bg-forest-100 text-forest-700' : 'bg-forest-800 text-white'}`}>
                {m.role === 'user' ? <User size={16} /> : <HelpCircle size={16} />}
              </div>
              <div className={`rounded-2xl px-3.5 py-2.5 text-xs max-w-[80%] leading-relaxed ${m.role === 'user' ? 'bg-[#0C2A18] text-white' : 'bg-surface-sage/50 text-carbon-900 border border-forest-100'}`}>
                {m.text}
              </div>
            </div>
          ))}
          <div ref={chatEnd} />
        </div>

        {/* Quick replies */}
        <div className="px-4 pb-3 flex flex-wrap gap-2 border-t border-forest-50 pt-3">
          {QUICK_REPLIES.map(q => (
            <button
              key={q}
              onClick={() => send(q)}
              className="text-[10px] font-bold bg-surface-sage text-primary px-3 py-1.5 rounded-xl hover:bg-forest-100 transition-colors border border-forest-200"
            >
              {q}
            </button>
          ))}
        </div>

        {/* Input */}
        <form onSubmit={e => { e.preventDefault(); send(input); }} className="p-4 border-t border-forest-50 flex gap-2">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            aria-label="Ask the assistant"
            placeholder="Ask about farm mapping, credit calculations, 70% split floor, or hash ledger..."
            className="flex-1 min-w-0 p-2.5 bg-forest-50/50 border border-forest-100 rounded-xl text-xs focus:outline-none focus:border-forest-600 focus:bg-white text-carbon-900"
          />
          <button
            type="submit"
            aria-label="Send question"
            className="p-2.5 bg-[#0C2A18] hover:bg-[#15803D] text-white rounded-xl transition-colors shadow-xs"
          >
            <Send size={16} />
          </button>
        </form>
      </div>
    </div>
  );
}
