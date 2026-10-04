import React from 'react';
import { cn } from '../cn';
import { colors, radius, shadows, transitions, componentDefaults } from '../tokens';

const BASE = `
  bg-white border border-[${colors.semantic.border.light}] rounded-[${radius.xl}]
  shadow-[${shadows.card}] transition-all duration-[${transitions.normal}]
  hover:shadow-[${shadows.premium}] hover:border-[${colors.semantic.border.medium}]
`.trim();

const VARIANTS = {
  default: BASE,
  elevated: `${BASE} shadow-[${shadows.premium}] border-[${colors.semantic.border.medium}]`,
  outlined: `bg-transparent border-2 border-[${colors.semantic.border.medium}] shadow-none hover:border-[${colors.brand[300]}]`,
  filled: `bg-[${colors.semantic.bg.tertiary}] border-none shadow-none hover:bg-[${colors.brand[100]}]`,
  ghost: `bg-transparent border-none shadow-none hover:bg-[${colors.semantic.bg.tertiary}]`,
};

const PADDINGS = {
  none: '',
  sm: `p-[${componentDefaults.card.padding.sm}]`,
  md: `p-[${componentDefaults.card.padding.md}]`,
  lg: `p-[${componentDefaults.card.padding.lg}]`,
};

export const Card = React.forwardRef(function Card({
  children,
  variant = 'default',
  padding = 'md',
  className,
  hover = true,
  onClick,
  ...props
}, ref) {
  const Component = onClick ? 'button' : 'div';
  
  return (
    <Component
      ref={ref}
      className={cn(
        VARIANTS[variant],
        PADDINGS[padding],
        hover && onClick && 'cursor-pointer',
        onClick && 'focus:outline-none focus-visible:ring-2 focus-visible:ring-[${colors.brand[500]}] focus-visible:ring-offset-2',
        className
      )}
      onClick={onClick}
      {...props}
    >
      {children}
    </Component>
  );
});

Card.displayName = 'Card';

export const CardHeader = ({ children, className, ...props }) => (
  <div className={cn('mb-4', className)} {...props}>{children}</div>
);

export const CardTitle = ({ children, className, ...props }) => (
  <h3 className={cn('text-lg font-semibold text-[${colors.semantic.text.primary}]', className)} {...props}>
    {children}
  </h3>
);

export const CardDescription = ({ children, className, ...props }) => (
  <p className={cn('text-sm text-[${colors.semantic.text.muted}] mt-1', className)} {...props}>
    {children}
  </p>
);

export const CardContent = ({ children, className, ...props }) => (
  <div className={cn('', className)} {...props}>{children}</div>
);

export const CardFooter = ({ children, className, ...props }) => (
  <div className={cn('mt-4 pt-4 border-t border-[${colors.semantic.border.light}] flex items-center gap-2', className)} {...props}>
    {children}
  </div>
);