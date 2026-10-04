/**
 * Classnames utility — clsx + tailwind-merge in 30 lines
 * Usage: cn('base-classes', { 'conditional-class': condition }, 'more-classes')
 */
export function cn(...inputs) {
  const classes = [];
  
  for (const input of inputs) {
    if (!input) continue;
    
    if (typeof input === 'string') {
      classes.push(input);
    } else if (Array.isArray(input)) {
      classes.push(cn(...input));
    } else if (typeof input === 'object') {
      for (const [key, value] of Object.entries(input)) {
        if (value) classes.push(key);
      }
    }
  }
  
  // Simple tailwind-merge: deduplicate conflicting utilities
  // Keeps the LAST occurrence of any utility class
  const seen = new Map();
  const result = [];
  
  for (const cls of classes.join(' ').split(/\s+/)) {
    if (!cls) continue;
    // Match tailwind utility pattern: prefix-value (e.g., bg-red-500, px-4, hover:bg-blue-600)
    const match = cls.match(/^([a-z-]+:)?([a-z]+)(?:-([\w-]+))?$/);
    if (match) {
      const [, variant, property] = match;
      const key = `${variant || ''}${property}`;
      seen.set(key, cls);
    } else {
      // Non-tailwind class (custom CSS, etc.) — keep all
      result.push(cls);
    }
  }
  
  // Append deduplicated tailwind classes
  for (const cls of seen.values()) {
    result.push(cls);
  }
  
  return result.join(' ');
}