import React from 'react';
import { cn } from '../cn';
import { colors, radius, transitions, componentDefaults } from '../tokens';

const BASE = `
  w-full h-[${componentDefaults.input.height}]
  bg-white border border-[${colors.semantic.border.medium}]
  rounded-[${radius.lg}] px-[${componentDefaults.input.padding}]
  text-[${colors.semantic.text.primary}] placeholder-[${colors.semantic.text.muted}]
  font-medium text-sm
  transition-all duration-[${transitions.fast}]
  focus:outline-none focus:ring-2 focus:ring-[${colors.brand[500]}] focus:border-transparent
  disabled:bg-[${colors.semantic.bg.primary}] disabled:cursor-not-allowed disabled:opacity-60
  error:border-[${colors.semantic.status.error.icon}] error:focus:ring-[${colors.semantic.status.error.icon}]
`.trim();

const LABEL_BASE = `
  block text-xs font-semibold text-[${colors.semantic.text.secondary}] mb-1.5
`.trim();

const ERROR_BASE = `
  text-xs font-medium text-[${colors.semantic.status.error.text}] mt-1.5
`.trim();

const HINT_BASE = `
  text-xs text-[${colors.semantic.text.muted}] mt-1.5
`.trim();

export const Input = React.forwardRef(function Input({
  label,
  error,
  hint,
  className,
  id,
  required,
  disabled,
  leftIcon,
  rightIcon,
  ...props
}, ref) {
  const defaultId = React.useId();
  const inputId = id || defaultId;
  const errorId = error ? `${inputId}-error` : undefined;
  const hintId = hint ? `${inputId}-hint` : undefined;
  const describedBy = [errorId, hintId].filter(Boolean).join(' ') || undefined;

  return (
    <div className={cn('w-full', className)}>
      {label && (
        <label htmlFor={inputId} className={LABEL_BASE}>
          {label}
          {required && <span className="text-[${colors.semantic.status.error.icon}] ml-1" aria-hidden="true">*</span>}
        </label>
      )}
      <div className="relative">
        {leftIcon && (
          <div className="absolute left-3 top-1/2 -translate-y-1/2 text-[${colors.semantic.text.muted}] pointer-events-none" aria-hidden="true">
            {leftIcon}
          </div>
        )}
        <input
          ref={ref}
          id={inputId}
          className={cn(
            BASE,
            leftIcon && 'pl-10',
            rightIcon && 'pr-10',
            error && 'error',
            className
          )}
          disabled={disabled}
          aria-invalid={!!error}
          aria-describedby={describedBy}
          aria-required={required}
          {...props}
        />
        {rightIcon && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2 text-[${colors.semantic.text.muted}] pointer-events-none" aria-hidden="true">
            {rightIcon}
          </div>
        )}
      </div>
      {error && <p id={errorId} className={ERROR_BASE} role="alert">{error}</p>}
      {hint && !error && <p id={hintId} className={HINT_BASE}>{hint}</p>}
    </div>
  );
});

Input.displayName = 'Input';

export const Textarea = React.forwardRef(function Textarea({
  label,
  error,
  hint,
  className,
  id,
  required,
  disabled,
  rows = 3,
  ...props
}, ref) {
  const defaultId = React.useId();
  const inputId = id || defaultId;
  const errorId = error ? `${inputId}-error` : undefined;
  const hintId = hint ? `${inputId}-hint` : undefined;
  const describedBy = [errorId, hintId].filter(Boolean).join(' ') || undefined;

  return (
    <div className={cn('w-full', className)}>
      {label && (
        <label htmlFor={inputId} className={LABEL_BASE}>
          {label}
          {required && <span className="text-[${colors.semantic.status.error.icon}] ml-1" aria-hidden="true">*</span>}
        </label>
      )}
      <textarea
        ref={ref}
        id={inputId}
        rows={rows}
        className={cn(
          BASE,
          'h-auto resize-y min-h-[80px]',
          error && 'error',
        )}
        disabled={disabled}
        aria-invalid={!!error}
        aria-describedby={describedBy}
        aria-required={required}
        {...props}
      />
      {error && <p id={errorId} className={ERROR_BASE} role="alert">{error}</p>}
      {hint && !error && <p id={hintId} className={HINT_BASE}>{hint}</p>}
    </div>
  );
});

Textarea.displayName = 'Textarea';

export const Select = React.forwardRef(function Select({
  label,
  error,
  hint,
  className,
  id,
  required,
  disabled,
  options,
  placeholder,
  ...props
}, ref) {
  const defaultId = React.useId();
  const selectId = id || defaultId;
  const errorId = error ? `${selectId}-error` : undefined;
  const hintId = hint ? `${selectId}-hint` : undefined;
  const describedBy = [errorId, hintId].filter(Boolean).join(' ') || undefined;

  return (
    <div className={cn('w-full', className)}>
      {label && (
        <label htmlFor={selectId} className={LABEL_BASE}>
          {label}
          {required && <span className="text-[${colors.semantic.status.error.icon}] ml-1" aria-hidden="true">*</span>}
        </label>
      )}
      <div className="relative">
        <select
          ref={ref}
          id={selectId}
          className={cn(BASE, 'pr-10 appearance-none', error && 'error')}
          disabled={disabled}
          aria-invalid={!!error}
          aria-describedby={describedBy}
          aria-required={required}
          {...props}
        >
          {placeholder && <option value="" disabled>{placeholder}</option>}
          {options?.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-[${colors.semantic.text.muted]}" aria-hidden="true">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M6 9l6 6 6-6" />
          </svg>
        </div>
      </div>
      {error && <p id={errorId} className={ERROR_BASE} role="alert">{error}</p>}
      {hint && !error && <p id={hintId} className={HINT_BASE}>{hint}</p>}
    </div>
  );
});

Select.displayName = 'Select';

export const Checkbox = React.forwardRef(function Checkbox({
  label,
  error,
  className,
  id,
  required,
  disabled,
  ...props
}, ref) {
  const defaultId = React.useId();
  const checkboxId = id || defaultId;
  const errorId = error ? `${checkboxId}-error` : undefined;
  const describedBy = errorId ? errorId : undefined;

  return (
    <div className={cn('flex items-start gap-3', className)}>
      <input
        ref={ref}
        type="checkbox"
        id={checkboxId}
        className={cn(
          'mt-0.5 h-4 w-4',
          'rounded-[${radius.sm}] border-[${colors.semantic.border.medium}]',
          'text-[${colors.brand[500]}] focus:ring-2 focus:ring-[${colors.brand[500]}] focus:ring-offset-2',
          'checked:bg-[${colors.brand[500]}] checked:border-[${colors.brand[500]}]',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          error && 'border-[${colors.semantic.status.error.icon}]'
        )}
        disabled={disabled}
        aria-invalid={!!error}
        aria-describedby={describedBy}
        aria-required={required}
        {...props}
      />
      {label && (
        <label htmlFor={checkboxId} className="text-sm text-[${colors.semantic.text.primary}] cursor-pointer select-none">
          {label}
        </label>
      )}
      {error && <p id={errorId} className={ERROR_BASE} role="alert">{error}</p>}
    </div>
  );
});

Checkbox.displayName = 'Checkbox';