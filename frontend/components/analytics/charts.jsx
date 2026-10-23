"use client";

import { Bar, BarChart, CartesianGrid, LabelList, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

// Categorical slots in fixed order (validated for colour-vision separation with the dataviz palette checker).
export const SERIES_COLORS = ["#0f9d8e", "#3c78d8", "#eb6834"];
const AXIS = "#6b7380";
const GRID = "#e6e4dd";
const INK = "#232830";

const tickStyle = { fontSize: 12, fill: AXIS };

function ChartTooltip({ active, payload, label, valueFormatter }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded border border-mute-line bg-white px-3 py-2 text-xs shadow-sm">
      <p className="mb-1 font-medium text-ink">{label}</p>
      {payload.map((p) => (
        <p key={p.dataKey} className="flex items-center gap-2 text-ink-soft">
          <span className="h-2 w-2 rounded-sm" style={{ background: p.color || p.fill }} aria-hidden="true" />
          {p.name}: <span className="font-mono text-ink">{valueFormatter ? valueFormatter(p.value) : p.value}</span>
        </p>
      ))}
    </div>
  );
}

/**
 * Single-series horizontal bars with direct value labels, e.g. documents per category.
 * `data`: [{ name, value }].
 */
export function HorizontalBars({ data, seriesName = "Value", color = SERIES_COLORS[0], valueFormatter, height }) {
  const h = height ?? Math.max(160, data.length * 32 + 24);
  return (
    <div style={{ height: h }} role="img" aria-label={`${seriesName} bar chart with ${data.length} bars. A table view follows.`}>
      <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: h }}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 40, bottom: 4, left: 8 }} barCategoryGap={6}>
          <CartesianGrid horizontal={false} stroke={GRID} />
          <XAxis type="number" tick={tickStyle} axisLine={false} tickLine={false} allowDecimals={false} />
          <YAxis type="category" dataKey="name" tick={{ ...tickStyle, fill: INK }} axisLine={false} tickLine={false} width={130} />
          <Tooltip cursor={{ fill: "#f0eee8" }} content={<ChartTooltip valueFormatter={valueFormatter} />} />
          <Bar dataKey="value" name={seriesName} fill={color} radius={[0, 4, 4, 0]} maxBarSize={18} isAnimationActive={false}>
            <LabelList dataKey="value" position="right" formatter={valueFormatter} style={{ fontSize: 11, fill: INK }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/**
 * Vertical bars, one or more series. `series`: [{ key, name }] drawn with the fixed categorical order.
 * A legend is always shown for two or more series.
 */
export function VerticalBars({ data, series, height = 260, valueFormatter, domain, labelValues = false, xAngle = 0 }) {
  const multi = series.length > 1;
  return (
    <div style={{ height }} role="img" aria-label={`Bar chart of ${series.map((s) => s.name).join(", ")} across ${data.length} categories. A table view follows.`}>
      <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height }}>
        <BarChart data={data} margin={{ top: 16, right: 8, bottom: xAngle ? 36 : 4, left: xAngle ? 40 : 0 }} barCategoryGap="20%">
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis
            dataKey="name"
            tick={tickStyle}
            axisLine={{ stroke: GRID }}
            tickLine={false}
            interval={0}
            angle={xAngle}
            textAnchor={xAngle ? "end" : "middle"}
            height={xAngle ? 56 : 30}
          />
          <YAxis tick={tickStyle} axisLine={false} tickLine={false} domain={domain} tickFormatter={valueFormatter} width={40} allowDecimals={Boolean(domain)} />
          <Tooltip cursor={{ fill: "#f0eee8" }} content={<ChartTooltip valueFormatter={valueFormatter} />} />
          {multi && <Legend itemSorter={null} verticalAlign="top" align="left" iconType="square" iconSize={10} wrapperStyle={{ fontSize: 12, color: INK, paddingBottom: 8 }} />}
          {series.map((s, i) => (
            <Bar
              key={s.key}
              dataKey={s.key}
              name={s.name}
              fill={SERIES_COLORS[i % SERIES_COLORS.length]}
              radius={[4, 4, 0, 0]}
              maxBarSize={multi ? 14 : 28}
              stroke="#ffffff"
              strokeWidth={multi ? 1 : 0}
              isAnimationActive={false}
            >
              {labelValues && <LabelList dataKey={s.key} position="top" formatter={valueFormatter} style={{ fontSize: 11, fill: INK }} />}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
