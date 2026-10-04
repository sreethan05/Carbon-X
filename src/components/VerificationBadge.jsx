import React from 'react';
import { ShieldCheck, FileCheck, FileText, Users, AlertTriangle } from 'lucide-react';

export const BADGE_DEFINITIONS = {
  REGISTRY: {
    label: 'REGISTRY',
    tier: 'Tier 1A',
    price: 'INR 340 / credit',
    priceNum: 340,
    textClass: 'text-[#065F46]',
    bgClass: 'bg-[#ECFDF5]',
    borderClass: 'border-[#A7F3D0]',
    Icon: ShieldCheck,
    description: 'Tier 1A: Exact Govt Cadastral Registry Polygon match',
  },
  REGISTRY_DOC: {
    label: 'REGISTRY_DOC',
    tier: 'Tier 1B',
    price: 'INR 320 / credit',
    priceNum: 320,
    textClass: 'text-[#166534]',
    bgClass: 'bg-[#F0FDF4]',
    borderClass: 'border-[#BBF7D0]',
    Icon: FileCheck,
    description: 'Tier 1B: Pahani Record match with verified survey bounds',
  },
  DOCUMENT: {
    label: 'DOCUMENT',
    tier: 'Tier 2',
    price: 'INR 310 / credit',
    priceNum: 310,
    textClass: 'text-[#075985]',
    bgClass: 'bg-[#F0F9FF]',
    borderClass: 'border-[#BAE6FD]',
    Icon: FileText,
    description: 'Tier 2: Extracted RoR 1B document with OCR validation',
  },
  FPO: {
    label: 'FPO',
    tier: 'Tier 3',
    price: 'INR 300 / credit',
    priceNum: 300,
    textClass: 'text-[#92400E]',
    bgClass: 'bg-[#FFFBEB]',
    borderClass: 'border-[#FDE68A]',
    Icon: Users,
    description: 'Tier 3: Attested by recognized Farmer Producer Org',
  },
  PENDING: {
    label: 'PENDING',
    tier: 'Blocked',
    price: 'Blocked',
    priceNum: 0,
    textClass: 'text-[#9F1239]',
    bgClass: 'bg-[#FFF1F2]',
    borderClass: 'border-[#FECDD3]',
    Icon: AlertTriangle,
    description: 'Blocked: Overlap conflict or pending FPO attestation',
  },
};

export default function VerificationBadge({ badge, showPrice = true, showTier = false, size = 'md', className = '' }) {
  const normalizedKey = (badge || 'PENDING').toUpperCase().replace(/[-\s]/g, '_');
  const config = BADGE_DEFINITIONS[normalizedKey] || BADGE_DEFINITIONS.PENDING;
  const { label, tier, price, textClass, bgClass, borderClass, Icon } = config;

  const sizeClasses = size === 'sm'
    ? 'px-2 py-0.5 text-xs gap-1'
    : size === 'lg'
    ? 'px-3 py-1.5 text-xs font-bold gap-1.5'
    : 'px-2.5 py-1 text-xs font-semibold gap-1.5';

  const iconSizes = size === 'sm' ? 'w-3 h-3' : size === 'lg' ? 'w-4 h-4' : 'w-3.5 h-3.5';

  return (
    <span className={`inline-flex items-center rounded-full border ${bgClass} ${borderClass} ${textClass} ${sizeClasses} ${className} transition-all`}>
      <Icon className={iconSizes} />
      <span>{label}</span>
      {showTier && <span className="opacity-80 text-[10px]">({tier})</span>}
      {showPrice && (
        <span className="opacity-75 font-normal border-l border-current/30 pl-1.5 ml-0.5">
          {price}
        </span>
      )}
    </span>
  );
}

export { VerificationBadge };
