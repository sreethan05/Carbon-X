import React, { useState } from 'react';
import { ShieldCheck, AlertTriangle, Users, Layers, FileText, Check, X, Search } from 'lucide-react';
import BadgePill from '../components/BadgePill';

export default function AdminDashboard() {
  const [badgeFilter, setBadgeFilter] = useState('ALL');

  const [complianceQueue, setComplianceQueue] = useState([
    {
      id: 'ADM-001',
      farmer: 'Padma Bai',
      survey: '124/B',
      village: 'Pochampally',
      acres: 2.20,
      issue: 'ST_Intersects overlap collision detected with Survey 124/A',
      riskScore: 88,
      assignedBadge: 'PENDING',
      status: 'FLAGGED'
    },
    {
      id: 'ADM-002',
      farmer: 'K. Ramesh',
      survey: '124/A',
      village: 'Pochampally',
      acres: 2.50,
      issue: 'Zero collision. Exact Cadastral match.',
      riskScore: 4,
      assignedBadge: 'REGISTRY',
      status: 'APPROVED'
    },
    {
      id: 'ADM-003',
      farmer: 'B. Lakshmi',
      survey: '88/B',
      village: 'Mothkur',
      acres: 1.80,
      issue: 'RoR 1B document OCR verified.',
      riskScore: 12,
      assignedBadge: 'REGISTRY_DOC',
      status: 'APPROVED'
    }
  ]);

  const handleApprove = (id) => {
    setComplianceQueue(complianceQueue.map(item => item.id === id ? { ...item, status: 'APPROVED', assignedBadge: 'FPO', riskScore: 15 } : item));
  };

  const handleReject = (id) => {
    setComplianceQueue(complianceQueue.map(item => item.id === id ? { ...item, status: 'REJECTED', assignedBadge: 'PENDING', riskScore: 99 } : item));
  };

  return (
    <div className="min-h-screen bg-slate-50 font-inter text-slate-900 py-8 px-4 md:px-10">
      <div className="max-w-7xl mx-auto space-y-6">

        {/* Header */}
        <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 flex justify-between items-center">
          <div>
            <span className="text-xs font-semibold text-rose-800 uppercase tracking-wider bg-rose-50 border border-rose-200 px-2.5 py-0.5 rounded-full inline-block mb-1">
              Integrity Oversight
            </span>
            <h1 className="text-2xl font-extrabold text-slate-900 font-manrope">Platform Compliance & Audit Desk</h1>
            <p className="text-xs text-slate-500 mt-0.5">PostGIS spatial collision auditing, hash duplicate prevention & trust badge governance.</p>
          </div>
          <ShieldCheck className="w-10 h-10 text-slate-800" />
        </div>

        {/* System-wide Compliance Metrics */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-5">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Total Onboarded Farmers</p>
            <p className="text-2xl font-extrabold text-slate-900 font-manrope mt-1">1,420 Farmers</p>
            <p className="text-xs text-emerald-700 font-medium mt-1">Across 10 Telangana Mandals</p>
          </div>

          <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-5">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Active Credit Listings</p>
            <p className="text-2xl font-extrabold text-slate-900 font-manrope mt-1">85 Listings</p>
            <p className="text-xs text-emerald-700 font-medium mt-1">Volume: 14,200 MT CO2e</p>
          </div>

          <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-5">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Fraud Flags Raised</p>
            <p className="text-2xl font-extrabold text-rose-800 font-manrope mt-1">3 Overlaps</p>
            <p className="text-xs text-rose-700 font-medium mt-1">ST_Intersects spatial collision</p>
          </div>

          <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-5">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Aggregate Carbon Offsets</p>
            <p className="text-2xl font-extrabold text-emerald-800 font-manrope mt-1">285.4K Tonnes</p>
            <p className="text-xs text-emerald-700 font-medium mt-1">Verified via Sentinel-2 MRV</p>
          </div>
        </div>

        {/* Trust Engine Badge Breakdown */}
        <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 space-y-4">
          <h2 className="text-base font-bold text-slate-900">Verification Badge Governance Breakdown</h2>

          <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
            <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3 text-center">
              <BadgePill badge="REGISTRY" size="sm" />
              <p className="text-xl font-bold text-slate-900 mt-2">420 Farms</p>
              <p className="text-[10px] text-emerald-800">INR 340 / Credit</p>
            </div>

            <div className="bg-emerald-50/60 border border-emerald-200 rounded-xl p-3 text-center">
              <BadgePill badge="REGISTRY_DOC" size="sm" />
              <p className="text-xl font-bold text-slate-900 mt-2">310 Farms</p>
              <p className="text-[10px] text-emerald-800">INR 320 / Credit</p>
            </div>

            <div className="bg-sky-50 border border-sky-200 rounded-xl p-3 text-center">
              <BadgePill badge="DOCUMENT" size="sm" />
              <p className="text-xl font-bold text-slate-900 mt-2">280 Farms</p>
              <p className="text-[10px] text-sky-800">INR 310 / Credit</p>
            </div>

            <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-center">
              <BadgePill badge="FPO" size="sm" />
              <p className="text-xl font-bold text-slate-900 mt-2">390 Farms</p>
              <p className="text-[10px] text-amber-800">INR 300 / Credit</p>
            </div>

            <div className="bg-rose-50 border border-rose-200 rounded-xl p-3 text-center">
              <BadgePill badge="PENDING" size="sm" />
              <p className="text-xl font-bold text-rose-900 mt-2">20 Blocked</p>
              <p className="text-[10px] text-rose-800">Trading Blocked</p>
            </div>
          </div>
        </div>

        {/* Fraud Risk Inspector Table */}
        <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 space-y-4">
          <h2 className="text-base font-bold text-slate-900">Fraud Risk Inspector Queue</h2>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-slate-600 font-semibold uppercase tracking-wider">
                  <th className="py-3 px-4">Audit ID</th>
                  <th className="py-3 px-4">Farmer & Survey</th>
                  <th className="py-3 px-4">Village</th>
                  <th className="py-3 px-4">Acreage</th>
                  <th className="py-3 px-4">Audit Finding / Issue</th>
                  <th className="py-3 px-4">Risk Score</th>
                  <th className="py-3 px-4">Badge</th>
                  <th className="py-3 px-4">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium">
                {complianceQueue.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50 transition-colors">
                    <td className="py-3 px-4 font-mono text-slate-600">{item.id}</td>
                    <td className="py-3 px-4 font-bold text-slate-900">{item.farmer} ({item.survey})</td>
                    <td className="py-3 px-4 text-slate-700">{item.village}</td>
                    <td className="py-3 px-4 text-slate-900">{item.acres} Acres</td>
                    <td className="py-3 px-4 text-slate-700">{item.issue}</td>
                    <td className="py-3 px-4">
                      <span className={`font-mono font-bold px-2 py-0.5 rounded text-[10px] ${
                        item.riskScore > 50 ? 'bg-rose-100 text-rose-800' : 'bg-emerald-100 text-emerald-900'
                      }`}>
                        {item.riskScore} / 100
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <BadgePill badge={item.assignedBadge} size="sm" />
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleApprove(item.id)}
                          className="px-2.5 py-1 bg-emerald-700 hover:bg-emerald-600 text-white rounded text-[10px] font-bold flex items-center gap-1"
                        >
                          <Check className="w-3 h-3" />
                          <span>Approve</span>
                        </button>
                        <button
                          onClick={() => handleReject(item.id)}
                          className="px-2.5 py-1 bg-rose-800 hover:bg-rose-700 text-white rounded text-[10px] font-bold flex items-center gap-1"
                        >
                          <X className="w-3 h-3" />
                          <span>Reject</span>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </div>
  );
}
