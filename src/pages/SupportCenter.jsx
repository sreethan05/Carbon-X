import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { PhoneCall, HelpCircle, ChevronDown, ChevronUp, Send, MessageSquare, User, ChevronLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const FAQS = [
  { q: 'How often does the satellite scan my farm?', a: 'Sentinel-2 scans every 5 days. CarbonX updates your NDVI index every Thursday at 06:00 AM IST.' },
  { q: 'When do I get my UPI payout?', a: 'As soon as a buyer purchases your carbon credits, funds are locked in escrow and cleared to your bank account via UPI in under 3 minutes.' },
  { q: 'What if my trees are damaged by a storm?', a: 'Report it to your local coordinator. Our satellite detects canopy loss and logs it under micro-insurance to protect your baseline credit score.' },
  { q: 'Is my data safe?', a: 'Yes. All documents are encrypted with 256-bit encryption. We are DPI compliant and never share your Aadhaar or bank details.' },
];

const QUICK_REPLIES = [
  'How do I map my farm?',
  'When is the next satellite scan?',
  'How are carbon credits calculated?',
  'What is NDVI?',
];

export default function SupportCenter() {
  const navigate = useNavigate();
  const [openFaq, setOpenFaq] = useState(0);
  const [messages, setMessages] = useState([{ role: 'bot', text: 'Hello! I am CarbonX Support. How can I help you today?' }]);
  const [input, setInput] = useState('');
  const chatEnd = useRef(null);

  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const send = (text) => {
    if (!text.trim()) return;
    setMessages(m => [...m, { role: 'user', text }]);
    setInput('');
    setTimeout(() => {
      const reply = text.toLowerCase().includes('map') ? 'You can map your farm by clicking "Map New Farm" on your dashboard. Draw the boundary on the satellite map and our system will calculate the area automatically.'
        : text.toLowerCase().includes('scan') ? 'The next Sentinel-2 scan is scheduled every 5 days. You will see updated NDVI values on your analytics page.'
        : text.toLowerCase().includes('credit') ? 'Carbon credits are calculated from your farm NDVI, area, and crop type. The formula uses IPCC guidelines for soil organic carbon.'
        : text.toLowerCase().includes('ndvi') ? 'NDVI (Normalized Difference Vegetation Index) measures vegetation health using satellite imagery. Values range from -1 to 1, with higher values indicating healthier crops.'
        : 'I can help with farm mapping, satellite scans, carbon credits, UPI payouts, and KYC verification. What would you like to know?';
      setMessages(m => [...m, { role: 'bot', text: reply }]);
    }, 1000);
  };

  return (
    <div className="pb-24 px-4 pt-6 max-w-4xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => navigate('/dashboard')} className="p-2 rounded-xl bg-white border border-forest-100 text-carbon-600 hover:text-forest-800">
          <ChevronLeft className="w-5 h-5" />
        </button>
        <h1 className="text-lg font-bold text-carbon-900">Support Center</h1>
      </div>

      {/* FAQ */}
      <div className="bg-white rounded-2xl border border-forest-100 shadow-sm mb-6">
        <h2 className="text-xs font-bold text-carbon-700 uppercase tracking-wider p-4 border-b border-forest-50">Frequently Asked Questions</h2>
        {FAQS.map((faq, i) => (
          <div key={i} className="border-b border-forest-50 last:border-0">
            <button onClick={() => setOpenFaq(openFaq === i ? -1 : i)}
              className="w-full flex justify-between items-center p-4 text-left hover:bg-forest-50/30 transition-colors">
              <span className="text-xs font-bold text-carbon-800">{faq.q}</span>
              {openFaq === i ? <ChevronUp size={16} className="text-carbon-400" /> : <ChevronDown size={16} className="text-carbon-400" />}
            </button>
            {openFaq === i && <p className="px-4 pb-4 text-xs text-carbon-500 leading-relaxed">{faq.a}</p>}
          </div>
        ))}
      </div>

      {/* Helpline */}
      <div className="bg-forest-50 border border-forest-100 rounded-2xl p-4 mb-6 flex items-center gap-3">
        <div className="p-2.5 bg-forest-100 text-forest-700 rounded-xl"><PhoneCall className="w-5 h-5" /></div>
        <div className="flex-1">
          <p className="text-xs font-bold text-carbon-800">Farmer Helpline</p>
          <p className="text-[11px] text-carbon-500">1800-420-2026 (Toll-Free, 9 AM - 9 PM IST)</p>
        </div>
      </div>

      {/* Chatbot */}
      <div className="bg-white rounded-2xl border border-forest-100 shadow-sm overflow-hidden">
        <div className="bg-forest-800 text-white p-4 flex items-center gap-2">
          <MessageSquare size={18} />
          <span className="text-xs font-bold">CarbonX Assistant</span>
        </div>
        <div className="p-4 space-y-3 max-h-80 overflow-y-auto">
          {messages.map((m, i) => (
            <div key={i} className={`flex gap-2 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${m.role === 'user' ? 'bg-forest-100 text-forest-700' : 'bg-forest-800 text-white'}`}>
                {m.role === 'user' ? <User size={16} /> : <HelpCircle size={16} />}
              </div>
              <div className={`rounded-2xl px-3 py-2 text-xs max-w-[75%] ${m.role === 'user' ? 'bg-forest-800 text-white' : 'bg-forest-50 text-carbon-800'}`}>
                {m.text}
              </div>
            </div>
          ))}
          <div ref={chatEnd} />
        </div>

        {/* Quick replies */}
        {messages.length <= 2 && (
          <div className="px-4 pb-3 flex flex-wrap gap-2">
            {QUICK_REPLIES.map(q => (
              <button key={q} onClick={() => send(q)} className="text-[10px] font-bold bg-forest-50 text-forest-700 px-3 py-1.5 rounded-xl hover:bg-forest-100 transition-colors">{q}</button>
            ))}
          </div>
        )}

        {/* Input */}
        <form onSubmit={e => { e.preventDefault(); send(input); }} className="p-4 border-t border-forest-50 flex gap-2">
          <input type="text" value={input} onChange={e => setInput(e.target.value)} placeholder="Type your question..."
            className="flex-1 p-2.5 bg-forest-50 border border-forest-100 rounded-xl text-xs focus:outline-none focus:border-forest-600 focus:bg-white" />
          <button type="submit" className="p-2.5 bg-forest-800 text-white rounded-xl hover:bg-forest-900 transition-colors">
            <Send size={16} />
          </button>
        </form>
      </div>
    </div>
  );
}
