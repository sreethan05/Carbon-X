import React from 'react';
import VerificationBadge, { BADGE_DEFINITIONS } from './VerificationBadge';

export const BADGE_CONFIG = BADGE_DEFINITIONS;

export default function BadgePill(props) {
  return <VerificationBadge {...props} />;
}
