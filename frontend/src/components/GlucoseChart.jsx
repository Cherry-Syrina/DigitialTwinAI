import {
  Area,
  CartesianGrid,
  Legend,
  Line,
  ComposedChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useMemo } from "react";

const fmtX = (ts) => {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return String(ts);
  return d.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
};

const fmtVal = (v) => (v === null || v === undefined ? "–" : `${v} mg/dL`);

const AXIS = { fontSize: 11, fill: "#64748b" };

export default function GlucoseChart({
  history = [],
  trajectory = [],
  thresholds,
  height = 320,
  showLegend = true,
}) {
  const data = useMemo(() => {
    const rows = [];
    for (const r of history) {
      rows.push({
        ts: r.timestamp,
        label: fmtX(r.timestamp),
        observed: r.glucose_mg_dl ?? null,
        predicted: null,
        band: null,
        source: "observed",
      });
    }
    for (const p of trajectory || []) {
      const interval = p.interval || null;
      const lower = interval?.lower_mg_dl ?? null;
      const upper = interval?.upper_mg_dl ?? null;
      rows.push({
        ts: p.timestamp,
        label: fmtX(p.timestamp),
        observed: null,
        predicted: p.predicted_glucose_mg_dl ?? null,
        band: lower !== null && upper !== null ? [lower, upper] : null,
        horizon: p.horizon_minutes,
        source: "prediction",
      });
    }
    rows.sort((a, b) => new Date(a.ts) - new Date(b.ts));
    return rows;
  }, [history, trajectory]);

  const boundary = useMemo(() => {
    let idx = -1;
    for (let i = data.length - 1; i >= 0; i -= 1) {
      if (data[i].observed !== null && data[i].observed !== undefined) {
        idx = i;
        break;
      }
    }
    return idx >= 0 ? data[idx] : null;
  }, [data]);

  const hasBand = useMemo(() => data.some((d) => d.band), [data]);
  const hasForecast = useMemo(() => data.some((d) => d.predicted !== null), [data]);

  if (data.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-[13px] text-slate-500">
        No time-series data to display.
      </div>
    );
  }

  const hyper = thresholds?.hyper_high_mg_dl;
  const hypo = thresholds?.hypo_low_mg_dl;
  const forecastStart = boundary?.ts;
  const forecastEnd = data.length ? data[data.length - 1].ts : null;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 10, right: 14, left: 2, bottom: 2 }}>
        <defs>
          <linearGradient id="gtBand" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#6366f1" stopOpacity={0.18} />
            <stop offset="100%" stopColor="#6366f1" stopOpacity={0.03} />
          </linearGradient>
        </defs>

        <CartesianGrid strokeDasharray="3 5" stroke="#e8edf4" vertical={false} />

        {hasForecast && forecastStart && forecastEnd && (
          <ReferenceArea x1={fmtX(forecastStart)} x2={fmtX(forecastEnd)} fill="#e0e7ff" fillOpacity={0.42} />
        )}

        <XAxis
          dataKey="label"
          tick={AXIS}
          tickLine={false}
          axisLine={{ stroke: "#e2e8f0" }}
          minTickGap={44}
          tickMargin={8}
        />
        <YAxis
          tick={AXIS}
          tickLine={false}
          axisLine={false}
          width={58}
          domain={["auto", "auto"]}
          unit=""
          label={{ value: "mg/dL", angle: -90, position: "insideLeft", dy: 20, fontSize: 10, fill: "#475569" }}
        />
        <Tooltip
          contentStyle={{
            borderRadius: 12,
            border: "1px solid #dbe3ec",
            boxShadow: "0 14px 34px rgba(15,23,42,0.12)",
            fontSize: 12,
            padding: "10px 12px",
          }}
          formatter={(value, name) => {
            if (Array.isArray(value)) return [`${value[0]} – ${value[1]} mg/dL`, "Uncertainty interval"];
            if (name === "predicted") return [fmtVal(value), "Forecast"];
            return [fmtVal(value), "Observed"];
          }}
          labelStyle={{ color: "#475569", fontWeight: 500 }}
        />
        {showLegend && (
          <Legend
            verticalAlign="top"
            align="right"
            height={28}
            iconType="plainline"
            iconSize={16}
            wrapperStyle={{ fontSize: 11, color: "#64748b" }}
          />
        )}

        {hasBand && (
          <Area
            dataKey="band"
            name="Uncertainty"
            stroke="none"
            fill="url(#gtBand)"
            connectNulls
            isAnimationActive={false}
          />
        )}

        <Line
          dataKey="observed"
          name="Observed"
          type="monotone"
          stroke="#101b35"
          strokeWidth={2}
          connectNulls
          dot={false}
          activeDot={{ r: 4, strokeWidth: 0 }}
          isAnimationActive={false}
        />
        <Line
          dataKey="predicted"
          name="Forecast"
          type="monotone"
          stroke="#4f46e5"
          strokeWidth={2.6}
          strokeDasharray="6 4"
          connectNulls
          dot={{ r: 3, fill: "#4f46e5", strokeWidth: 0 }}
          activeDot={{ r: 5, strokeWidth: 0 }}
          isAnimationActive={false}
        />

        {hyper !== undefined && hyper !== null && (
          <ReferenceLine
            y={hyper}
            stroke="#f59e0b"
            strokeDasharray="4 4"
            label={{ value: `high ${hyper}`, position: "insideTopRight", fontSize: 10, fill: "#b45309" }}
          />
        )}
        {hypo !== undefined && hypo !== null && (
          <ReferenceLine
            y={hypo}
            stroke="#dc2626"
            strokeDasharray="4 4"
            label={{ value: `low ${hypo}`, position: "insideBottomRight", fontSize: 10, fill: "#b91c1c" }}
          />
        )}
        {boundary && (
          <ReferenceLine
            x={fmtX(boundary.ts)}
            stroke="#cbd5e1"
            strokeDasharray="3 3"
            label={{ value: "now", position: "top", fontSize: 10, fill: "#64748b" }}
          />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}
