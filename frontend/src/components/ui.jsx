import { Info, ShieldAlert, ShieldCheck, TriangleAlert } from "lucide-react";

export const RISK_META = {
  none: { label: "In expected range", chip: "bg-emerald-50 text-emerald-700", dot: "bg-emerald-500", icon: ShieldCheck },
  medium: { label: "Elevated glucose predicted", chip: "bg-amber-50 text-amber-700", dot: "bg-amber-500", icon: TriangleAlert },
  high: { label: "Threshold violation predicted", chip: "bg-orange-50 text-orange-700", dot: "bg-orange-500", icon: TriangleAlert },
  critical: { label: "Severe threshold violation predicted", chip: "bg-rose-50 text-rose-700", dot: "bg-rose-500", icon: ShieldAlert },
};

export function RiskBadge({ level, size = "md" }) {
  if (level === null || level === undefined || level === "") {
    return (
      <span
        title="Risk assessment not available"
        className={`chip bg-slate-100/80 text-slate-600 ${size === "lg" ? "px-3 py-1 text-[12px]" : ""}`}
      >
        N/A
      </span>
    );
  }
  const text = String(level);
  const meta = RISK_META[text] || RISK_META.none;
  const Icon = meta.icon;
  return (
    <span
      title={meta.label}
      className={`chip ${meta.chip} ${size === "lg" ? "px-3 py-1 text-[12px]" : ""}`}
    >
      <Icon className="h-3.5 w-3.5" />
      {text.toUpperCase()}
    </span>
  );
}

export function Metric({ label, value, unit, hint, tone = "default", icon: Icon }) {
  const toneClass =
    tone === "teal" ? "text-teal-600" : tone === "indigo" ? "text-indigo-600" : "text-slate-900";
  return (
    <div className="min-w-0">
      <div className="flex items-center gap-1.5">
        {Icon && <Icon className="h-3.5 w-3.5 text-slate-500" />}
        <span className="metric-label">{label}</span>
      </div>
      <div className={`mt-1.5 flex items-baseline gap-1.5 ${toneClass}`}>
        <span className="metric-value mono-num truncate">{value ?? "—"}</span>
        {unit && <span className="text-[13px] text-slate-500">{unit}</span>}
      </div>
      {hint && <div className="mt-0.5 truncate text-[11px] text-slate-500">{hint}</div>}
    </div>
  );
}

export function StatCard({ label, value, sub, icon: Icon, accent = "from-teal-400/20 to-cyan-400/10" }) {
  return (
    <div className="card card-pad flex items-start gap-4">
      {Icon && (
        <div className={`mt-0.5 flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br ${accent} text-teal-600`}>
          <Icon className="h-5 w-5" />
        </div>
      )}
      <div className="min-w-0">
        <div className="metric-label">{label}</div>
        <div className="mt-1 truncate text-[26px] font-semibold text-slate-900">{value ?? "n/a"}</div>
        {sub && <div className="truncate text-[11px] text-slate-500">{sub}</div>}
      </div>
    </div>
  );
}

export function Panel({ title, subtitle, action, children, className = "", bodyClass = "card-pad", dense = false }) {
  return (
    <section className={`card fade-in-up ${className}`}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b border-slate-200/80 px-5 py-4">
          <div className="min-w-0">
            <h2 className="card-title">{title}</h2>
            {subtitle && <p className="mt-0.5 text-[11px] text-slate-500">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className={dense ? "" : bodyClass}>{children}</div>
    </section>
  );
}

export function PageHeader({ title, subtitle, actions, breadcrumb, meta }) {
  return (
    <header className="page-header mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-3 fade-in">
      <div className="min-w-0">
        {breadcrumb && <div className="eyebrow mb-2">{breadcrumb}</div>}
        <h1 className="page-title">{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
        {meta && <div className="mt-3 flex flex-wrap items-center gap-2">{meta}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function EmptyState({ icon: Icon, title, description, action, tone = "default" }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      {Icon && (
        <div
          className={`mb-3 flex h-12 w-12 items-center justify-center rounded-full ${
            tone === "warning"
              ? "bg-amber-50 text-amber-600"
              : "bg-gradient-to-br from-teal-400/20 to-indigo-400/10 text-teal-600"
          }`}
        >
          <Icon className="h-6 w-6" />
        </div>
      )}
      <h3 className="text-[15px] font-semibold text-slate-900">{title}</h3>
      {description && (
        <p className="mt-1.5 max-w-md text-[13px] leading-relaxed text-slate-500">{description}</p>
      )}
      {action && <div className="mt-4 flex flex-wrap items-center justify-center gap-2">{action}</div>}
    </div>
  );
}

export function ModelUnavailable({ message, onRetry }) {
  return (
    <EmptyState
      tone="warning"
      icon={TriangleAlert}
      title="Forecasting model unavailable"
      description={
        message ||
        "No trained model artifact was found on the server, so predictions and risk flags cannot be produced."
      }
      action={
        <>
          <code className="rounded-full bg-slate-100/80 px-3 py-1 text-[12px] text-slate-700">
            python -m backend.scripts.train_model
          </code>
          {onRetry && (
            <button type="button" className="btn-secondary" onClick={onRetry}>
              Retry
            </button>
          )}
        </>
      }
    />
  );
}

export function SyntheticTag() {
  return (
    <span
      className="chip bg-slate-100/80 text-slate-600"
      title="All data is generated for demonstration (not real clinical data)"
    >
      Synthetic data
    </span>
  );
}

export function DataTag({ label }) {
  const isSynthetic = !label || label === "synthetic";
  if (isSynthetic) return <SyntheticTag />;
  return (
    <span
      className="chip bg-slate-100/80 text-slate-600"
      title="Entered through this app for demonstration - not a real clinical record"
    >
      Demo entry
    </span>
  );
}

export function DisclaimerBanner({ text }) {
  const msg = text || "Synthetic data · research prototype, not clinically validated.";
  return (
    <div className="border-b border-slate-200/70 bg-white/60 px-4 py-1.5 backdrop-blur md:px-6 lg:px-8">
      <div className="flex items-center justify-center gap-1.5 text-center text-[11px] text-slate-500">
        <Info className="h-3.5 w-3.5 shrink-0" />
        <span>{msg}</span>
      </div>
    </div>
  );
}

export function ErrorBanner({ message, onRetry }) {
  if (!message) return null;
  return (
    <div className="flex items-start justify-between gap-3 rounded-2xl border border-rose-200/80 bg-rose-50/80 px-4 py-2.5 text-[13px] text-rose-700 shadow-[0_20px_60px_-40px_rgba(244,63,94,0.9)]">
      <span>{message}</span>
      {onRetry && (
        <button type="button" onClick={onRetry} className="shrink-0 font-medium underline underline-offset-2">
          Retry
        </button>
      )}
    </div>
  );
}

export function Spinner({ label = "Loading…" }) {
  return (
    <div className="flex items-center justify-center py-12 text-slate-500">
      <div className="relative h-6 w-6">
        <div className="absolute inset-0 rounded-full border-2 border-slate-200" />
        <div className="absolute inset-0 animate-spin rounded-full border-2 border-teal-500 border-t-transparent" />
      </div>
      <span className="ml-3 text-[13px]">{label}</span>
    </div>
  );
}

export function ValueRow({ label, value, mono = false }) {
  return (
    <div className="flex items-center justify-between border-b border-dashed border-slate-200/80 py-1.5 text-[13px] last:border-0">
      <span className="text-slate-500">{label}</span>
      <span className={`font-medium text-slate-900 ${mono ? "mono-num" : ""}`}>{value ?? "n/a"}</span>
    </div>
  );
}

export function fmtTime(iso) {
  if (!iso) return "n/a";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function fmtDuration(minutes) {
  if (minutes === undefined || minutes === null) return "n/a";
  return minutes < 60 ? `${minutes} min` : `${Math.round((minutes / 60) * 10) / 10} h`;
}
