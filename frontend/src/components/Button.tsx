const VARIANTS = {
  primary: "bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-60",
  secondary:
    "border border-slate-300 bg-white text-slate-800 hover:bg-slate-50 disabled:opacity-60",
  danger: "bg-red-600 text-white hover:bg-red-700 disabled:opacity-60",
  ghost: "text-slate-700 hover:bg-slate-100 disabled:opacity-60",
} as const;

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof VARIANTS;
  block?: boolean;
};

export function Button({
  variant = "primary",
  block,
  className = "",
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center rounded-lg px-4 py-2.5 text-sm font-semibold transition-colors ${
        VARIANTS[variant]
      } ${block ? "w-full" : ""} ${className}`}
      {...props}
    />
  );
}
