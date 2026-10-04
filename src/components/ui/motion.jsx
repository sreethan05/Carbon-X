import { useEffect, useRef, useState } from "react";
import { motion, useInView, useMotionValue, useSpring } from "framer-motion";

/** Scroll-triggered fade+rise wrapper. Wrap any block. */
export function FadeIn({ children, delay = 0, y = 18, className = "", ...props }) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.6, delay, ease: [0.2, 0.7, 0.3, 1] }}
      {...props}
    >
      {children}
    </motion.div>
  );
}

/** Animated number that counts up when scrolled into view. */
export function CountUp({ value, decimals = 0, suffix = "", prefix = "", className = "", duration = 1.4 }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const mv = useMotionValue(0);
  const spring = useSpring(mv, { duration: duration * 1000, bounce: 0 });
  const [display, setDisplay] = useState((0).toFixed(decimals));

  useEffect(() => { if (inView) mv.set(value); }, [inView, value, mv]);
  useEffect(() => spring.on("change", (v) => setDisplay(v.toFixed(decimals))), [spring, decimals]);

  return (
    <span ref={ref} className={className}>
      {prefix}{display}{suffix}
    </span>
  );
}

/** Radial progress ring (C3-style) — value 0-100. */
export function ProgressRing({ value = 0, size = 72, stroke = 8, color = "#10B981", track = "rgba(255,255,255,.08)", label, dark = true }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true });
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  return (
    <div ref={ref} className="flex flex-col items-center">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={track} strokeWidth={stroke} />
        <motion.circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
          strokeLinecap="round" strokeDasharray={circ}
          initial={{ strokeDashoffset: circ }}
          animate={{ strokeDashoffset: inView ? circ * (1 - value / 100) : circ }}
          transition={{ duration: 1.2, ease: [0.2, 0.7, 0.3, 1] }}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        {label && (
          <text x="50%" y="54%" textAnchor="middle" dominantBaseline="middle"
            fill={dark ? "#fff" : "#0F172A"} fontSize={size / 4.2} fontWeight="800"
            fontFamily="Manrope, sans-serif">
            {label}
          </text>
        )}
      </svg>
    </div>
  );
}

/** Stagger container + item for lists/grids. */
export const staggerContainer = {
  hidden: {},
  show: { transition: { staggerChildren: 0.07 } },
};
export const staggerItem = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.2, 0.7, 0.3, 1] } },
};
