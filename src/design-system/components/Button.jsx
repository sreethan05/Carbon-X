import React from 'react';
import { cn } from '../cn';
import { colors, radius, transitions, componentDefaults } from '../tokens';

const VARIANTS = {
  primary: `bg-[${colors.brand[500]}] text-white hover:bg-[${colors.brand[600]}] active:bg-[${colors.brand[700]}] focus:ring-[${colors.brand[500]}]`,
  secondary: `bg-white text-[${colors.semantic.text.primary}] border border-[${colors.semantic.border.medium}] hover:bg-[${colors.semantic.bg.tertiary}] active:bg-[${colors.brand[100]}] focus:ring-[${colors.brand[500]}]`,
  ghost: `text-[${colors.semantic.text.primary}] hover:bg-[${colors.semantic.bg.tertiary}] active:bg-[${colors.brand[100]}] focus:ring-[${colors.brand[500]}]`,
  danger: `bg-[${colors.semantic.status.error.icon}] text-white hover:bg-[${colors.semantic.status.error.icon}]/90 active:bg-[${colors.semantic.status.error.icon}] focus:ring-[${colors.semantic.status.error.icon}]`,
  outline: `border-2 border-[${colors.brand[500]}] text-[${colors.brand[500]}] hover:bg-[${colors.brand[50]}] active:bg-[${colors.brand[100]}] focus:ring-[${colors.brand[500]}]`,
  success: `bg-[${colors.semantic.status.success.icon}] text-white hover:bg-[${colors.semantic.status.success.icon}]/90 active:bg-[${colors.semantic.status.success.icon}] focus:ring-[${colors.semantic.status.success.icon}]`,
};

const SIZES = {
  sm: `h-[${componentDefaults.button.height.sm}] px-[${componentDefaults.button.padding.sm}] text-xs gap-1.5`,
  md: `h-[${componentDefaults.button.height.md}] px-[${componentDefaults.button.padding.md}] text-sm gap-2`,
  lg: `h-[${componentDefaults.button.height.lg}] px-[${componentDefaults.button.padding.lg}] text-base gap-2.5`,
};

const BASE = `
  inline-flex items-center justify-center font-semibold
  rounded-[${radius.lg}] transition-all duration-[${transitions.fast}]
  focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2
  disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none
  select-none
`.trim();

export const Button = React.forwardRef(function Button({
  children,
  variant = 'primary',
  size = 'md',
  className,
  leftIcon,
  rightIcon,
  fullWidth = false,
  loading = false,
  type = 'button',
  ...props
}, ref) {
  const isLoading = loading && !props.disabled;
  
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        BASE,
        VARIANTS[variant],
        SIZES[size],
        fullWidth && 'w-full',
        className
      )}
      disabled={props.disabled || isLoading}
      aria-busy={isLoading}
      {...props}
    >
      {isLoading ? (
        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" fill="none" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
      ) : leftIcon ? (
        <span aria-hidden="true">{leftIcon}</span>
      ) : null}
      {children}
      {!isLoading && rightIcon && <span aria-hidden="true">{rightIcon}</span>}
    </button>
  );
});

Button.displayName = 'Button';

// Convenience exports
export const PrimaryButton = ({ children, ...props }) => <Button variant="primary" {...props}>{children}</Button>;
export const SecondaryButton = ({ children, ...props }) => <Button variant="secondary" {...props}>{children}</Button>;
export const GhostButton = ({ children, ...props }) => <Button variant="ghost" {...props}>{children}</Button>;
export const DangerButton = ({ children, ...props }) => <Button variant="danger" {...props}>{children}</Button>;
export const OutlineButton = ({ children, ...props }) => <Button variant="outline" {...props}>{children}</Button>;
export const SuccessButton = ({ children, ...props }) => <Button variant="success" {...props}>{children}</Button>;