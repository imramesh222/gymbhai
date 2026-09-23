const VARIANTS = {
  primary:
    "bg-brand-600 text-white shadow-brand hover:bg-brand-700 active:translate-y-px disabled:bg-brand-300 disabled:shadow-none",
  secondary:
    "bg-white text-slate-800 ring-1 ring-hairline shadow-card hover:bg-slate-50 active:translate-y-px disabled:opacity-60",
  subtle: "bg-brand-50 text-brand-700 hover:bg-brand-100 disabled:opacity-60",
  danger:
    "bg-red-600 text-white shadow-[0_6px_16px_-8px_rgba(220,38,38,0.6)] hover:bg-red-700 active:translate-y-px disabled:opacity-60",
  ghost: "text-slate-600 hover:bg-slate-100 hover:text-slate-900 disabled:opacity-60",
} as const;

const SIZES = {
  sm: "gap-1.5 rounded-lg px-3 py-1.5 text-xs",
  md: "gap-2 rounded-xl px-4 py-2.5 text-sm",
  lg: "gap-2 rounded-xl px-5 py-3 text-base",
} as const;

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof VARIANTS;
  size?: keyof typeof SIZES;
  block?: boolean;
};

export function Button({
  variant = "primary",
  size = "md",
  block,
  className = "",
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center font-semibold whitespace-nowrap transition-[background-color,box-shadow,transform] duration-150 disabled:cursor-not-allowed disabled:active:translate-y-0 ${
        SIZES[size]
      } ${VARIANTS[variant]} ${block ? "w-full" : ""} ${className}`}
      {...props}
    />
  );
}
