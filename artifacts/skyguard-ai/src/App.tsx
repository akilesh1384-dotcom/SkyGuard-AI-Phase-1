import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Check,
  ChevronDown,
  CircleHelp,
  Cloud,
  CloudDrizzle,
  Gauge,
  Pause,
  Play,
  Radio,
  RefreshCw,
  RotateCcw,
  Server,
  Settings2,
  ShieldCheck,
  Signal,
  Square,
  Thermometer,
  TimerReset,
  TriangleAlert,
  Wifi,
  WifiOff,
} from 'lucide-react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Route, Switch, Router as WouterRouter, useLocation } from 'wouter';
import {
  getGetLatestReadingQueryKey,
  getGetReadingHistoryQueryKey,
  getGetSimulatorStatusQueryKey,
  getHealthCheckQueryKey,
  SimulatorMode,
  useGetLatestReading,
  useGetReadingHistory,
  useGetSimulatorStatus,
  useHealthCheck,
  useResetSimulator,
  useSetSimulatorMode,
  useStartSimulator,
  useStopSimulator,
  type SensorReading,
  type SimulatorStatus,
} from '@workspace/api-client-react';
import { ErrorBoundary } from '@/components/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import NotFound from '@/pages/not-found';
import '@/index.css';

const queryClient = new QueryClient();
const HISTORY_PARAMS = { limit: 120 };
const MODE_OPTIONS = [
  SimulatorMode.NORMAL,
  SimulatorMode.TEMPERATURE_SPIKE,
  SimulatorMode.TEMPERATURE_DROP,
  SimulatorMode.HUMIDITY_SPIKE,
  SimulatorMode.PRESSURE_ANOMALY,
  SimulatorMode.FROZEN_SENSOR,
  SimulatorMode.GRADUAL_DRIFT,
  SimulatorMode.MISSING_DATA,
  SimulatorMode.MULTIVARIATE_INCONSISTENCY,
] as const;

type ConnectionState = 'connecting' | 'live' | 'offline';

const modeNames: Record<string, string> = {
  NORMAL: 'Normal baseline',
  TEMPERATURE_SPIKE: 'Temperature spike',
  TEMPERATURE_DROP: 'Temperature drop',
  HUMIDITY_SPIKE: 'Humidity spike',
  PRESSURE_ANOMALY: 'Pressure anomaly',
  FROZEN_SENSOR: 'Frozen sensor',
  GRADUAL_DRIFT: 'Gradual drift',
  MISSING_DATA: 'Missing data',
  MULTIVARIATE_INCONSISTENCY: 'Multivariate inconsistency',
};

const modeDescriptions: Record<string, string> = {
  NORMAL: 'Reference conditions for a healthy station.',
  TEMPERATURE_SPIKE: 'Fast upward movement in thermal readings.',
  TEMPERATURE_DROP: 'Fast downward movement in thermal readings.',
  HUMIDITY_SPIKE: 'Moisture rises beyond the expected envelope.',
  PRESSURE_ANOMALY: 'Barometric pressure departs from baseline.',
  FROZEN_SENSOR: 'Reading remains fixed to test stale-data detection.',
  GRADUAL_DRIFT: 'Slow, persistent movement away from baseline.',
  MISSING_DATA: 'Intentional gaps in the station stream.',
  MULTIVARIATE_INCONSISTENCY: 'Metrics move in conflicting directions.',
};

function formatTime(value?: string | null) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(value));
}

function formatDate(value?: string | null) {
  if (!value) return 'Awaiting first reading';
  return new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(value));
}

function statusTone(status?: SimulatorStatus['status']) {
  if (status === 'ERROR') return 'critical';
  if (status === 'STOPPED') return 'muted';
  if (status === 'SIMULATING') return 'amber';
  return 'healthy';
}

function StatusDot({ tone = 'healthy' }: { tone?: 'healthy' | 'amber' | 'critical' | 'muted' }) {
  const colors = {
    healthy: 'bg-[#36d8c3]',
    amber: 'bg-[#ffbe55]',
    critical: 'bg-[#ef7168]',
    muted: 'bg-[#8da4ad]',
  };
  return <span className={`inline-block h-2 w-2 rounded-full ${colors[tone]} ${tone === 'healthy' ? 'soft-pulse' : ''}`} />;
}

function MetricIcon({ type }: { type: 'temperature' | 'humidity' | 'pressure' }) {
  if (type === 'temperature') return <Thermometer className="h-4 w-4" />;
  if (type === 'humidity') return <CloudDrizzle className="h-4 w-4" />;
  return <Gauge className="h-4 w-4" />;
}

function MetricCard({
  label,
  value,
  unit,
  detail,
  type,
  accent,
}: {
  label: string;
  value?: number;
  unit: string;
  detail: string;
  type: 'temperature' | 'humidity' | 'pressure';
  accent: string;
}) {
  return (
    <section className="sg-panel rise-in relative overflow-hidden rounded-[1.15rem] p-5" data-testid={`card-metric-${type}`}>
      <div className={`absolute right-0 top-0 h-24 w-24 translate-x-7 -translate-y-7 rounded-full opacity-20 blur-2xl ${accent}`} />
      <div className="relative flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.17em] text-muted-foreground">
            <span className={`flex h-7 w-7 items-center justify-center rounded-lg ${accent} bg-opacity-15 text-foreground`}>
              <MetricIcon type={type} />
            </span>
            {label}
          </div>
          <div className="mt-5 flex items-baseline gap-1.5">
            <span className="reading-number font-display text-[2.65rem] font-semibold leading-none text-foreground" data-testid={`text-value-${type}`}>
              {value == null ? '—' : (value == null ? '—' : value.toFixed(1))}
            </span>
            <span className="font-data text-sm text-muted-foreground">{unit}</span>
          </div>
        </div>
        <span className="mt-1 h-2 w-2 rounded-full bg-primary" />
      </div>
      <div className="mt-5 flex items-center gap-2 border-t border-border/70 pt-3 text-xs text-muted-foreground">
        <Activity className="h-3.5 w-3.5 text-primary" />
        <span>{detail}</span>
      </div>
    </section>
  );
}

function DashboardChart({
  title,
  subtitle,
  data,
  dataKey,
  color,
  unit,
  domain,
}: {
  title: string;
  subtitle: string;
  data: Array<SensorReading & { shortTime: string }>;
  dataKey: 'temperature' | 'humidity' | 'pressure';
  color: string;
  unit: string;
  domain?: [number | 'auto', number | 'auto'];
}) {
  return (
    <section className="sg-panel min-w-0 rounded-[1.15rem] p-5" data-testid={`chart-${dataKey}`}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-base font-semibold tracking-tight text-foreground">{title}</h3>
          <p className="mt-1 text-[11px] uppercase tracking-[0.13em] text-muted-foreground">{subtitle}</p>
        </div>
        <div className="flex items-center gap-1.5 rounded-full bg-secondary/70 px-2 py-1 font-data text-[10px] text-muted-foreground">
          <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
          {unit}
        </div>
      </div>
      <div className="h-[172px] w-full">
        {data.length < 2 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border/80 text-center text-xs text-muted-foreground">
            <Activity className="h-4 w-4 opacity-50" />
            Waiting for two readings to draw a trend
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 4, left: -20, bottom: 0 }}>
              <CartesianGrid stroke="hsl(193 24% 78% / .45)" vertical={false} strokeDasharray="3 5" />
              <XAxis dataKey="shortTime" tick={{ fill: 'hsl(203 22% 45%)', fontSize: 9 }} axisLine={false} tickLine={false} minTickGap={30} />
              <YAxis domain={domain} tick={{ fill: 'hsl(203 22% 45%)', fontSize: 9 }} axisLine={false} tickLine={false} width={38} />
              <Tooltip
                contentStyle={{ background: 'hsl(201 45% 14%)', border: '1px solid hsl(198 32% 28%)', borderRadius: 10, color: '#eef8f6', fontSize: 11 }}
                labelStyle={{ color: '#a7c5c8', marginBottom: 4 }}
                formatter={(value: number) => [`${value == null ? '—' : (value == null ? '—' : value.toFixed(1))} ${unit}`, title]}
              />
              <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2.5} dot={false} activeDot={{ r: 4, fill: color, stroke: '#effbf7', strokeWidth: 2 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}

function DashboardSkeleton() {
  return (
    <div className="animate-pulse space-y-5" data-testid="loading-dashboard">
      <div className="h-28 rounded-[1.15rem] bg-secondary/70" />
      <div className="grid gap-4 md:grid-cols-3">
        <div className="h-40 rounded-[1.15rem] bg-secondary/70" />
        <div className="h-40 rounded-[1.15rem] bg-secondary/70" />
        <div className="h-40 rounded-[1.15rem] bg-secondary/70" />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="h-64 rounded-[1.15rem] bg-secondary/70" />
        <div className="h-64 rounded-[1.15rem] bg-secondary/70" />
        <div className="h-64 rounded-[1.15rem] bg-secondary/70" />
      </div>
    </div>
  );
}

function Sidebar({ status, connection }: { status?: SimulatorStatus; connection: ConnectionState }) {
  const activeTone = statusTone(status?.status);
  return (
    <aside className="skyguard-sidebar flex w-full flex-col px-4 py-5 text-sidebar-foreground md:sticky md:top-0 md:h-screen md:w-[238px] md:shrink-0 md:px-5" data-testid="navigation-sidebar">
      <div className="flex items-center gap-3 px-2">
        <div className="flex h-10 w-10 items-center justify-center rounded-[13px] bg-[#ffd06a] text-[#173844] shadow-[0_8px_24px_rgba(255,208,106,.2)]">
          <Cloud className="h-5 w-5" strokeWidth={2.4} />
        </div>
        <div>
          <div className="font-display text-lg font-bold leading-none tracking-tight text-[#f1fbf8]">SkyGuard</div>
          <div className="mt-1 font-data text-[9px] uppercase tracking-[0.2em] text-[#8aaeb1]">AI / field console</div>
        </div>
      </div>
      <div className="mt-10 px-2 text-[10px] font-bold uppercase tracking-[0.18em] text-[#709397]">Workspace</div>
      <nav className="mt-3 space-y-1" aria-label="Primary navigation">
        <button type="button" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })} className="flex w-full items-center gap-3 rounded-xl bg-[#2a6771] px-3 py-3 text-left text-sm font-semibold text-[#f1fbf8] shadow-inner shadow-white/5" data-testid="button-live-overview">
          <Radio className="h-4 w-4 text-[#ffd06a]" />
          Live overview
          <span className="ml-auto h-1.5 w-1.5 rounded-full bg-[#46e1c7]" />
        </button>
      </nav>
      <div className="mt-auto space-y-3">
        <div className="rounded-xl border border-[#315d65] bg-[#173b45]/70 p-3">
          <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-[0.14em] text-[#7ba1a4]">
            <span>Station link</span>
            <StatusDot tone={connection === 'live' ? 'healthy' : connection === 'connecting' ? 'amber' : 'critical'} />
          </div>
          <div className="mt-2 flex items-center gap-2 text-sm text-[#e2f2ef]">
            {connection === 'live' ? <Wifi className="h-3.5 w-3.5 text-[#45d5c1]" /> : <WifiOff className="h-3.5 w-3.5 text-[#ffbe55]" />}
            {connection === 'live' ? 'Stream connected' : connection === 'connecting' ? 'Connecting…' : 'Reconnecting'}
          </div>
          <div className="mt-2 font-data text-[10px] text-[#779da1]">WS /ws · TLS tunnel</div>
        </div>
        <div className="flex items-center gap-3 border-t border-[#315d65] px-2 pt-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[#d4edf0] font-display text-xs font-bold text-[#1b5360]">SI</div>
          <div className="min-w-0">
            <div className="truncate text-xs font-semibold text-[#e2f2ef]">SIH field team</div>
            <div className="mt-0.5 text-[10px] text-[#7ba1a4]">Prototype operator</div>
          </div>
          <Settings2 className="ml-auto h-4 w-4 text-[#7ba1a4]" />
        </div>
        <div className="flex items-center gap-2 px-2 pb-1 text-[10px] text-[#7ba1a4]">
          <StatusDot tone={activeTone} />
          <span>{status?.status === 'ERROR' ? 'Station needs attention' : 'Station nominal'}</span>
        </div>
      </div>
    </aside>
  );
}

function StatusOverview({ status, health, connection }: { status?: SimulatorStatus; health?: string; connection: ConnectionState }) {
  const tone = statusTone(status?.status);
  const statusLabel = status?.status === 'SIMULATING' ? 'Simulation running' : status?.status === 'STOPPED' ? 'Simulator stopped' : status?.status === 'ERROR' ? 'Station error' : 'System normal';
  return (
    <section className="sg-panel-dark rise-in overflow-hidden rounded-[1.15rem] p-5 text-[#e9f8f4] md:p-6" data-testid="section-status-overview">
      <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-center">
        <div className="flex items-start gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#ffd06a] text-[#173844]">
            <ShieldCheck className="h-6 w-6" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="font-display text-xl font-bold tracking-tight">Live station overview</h1>
              <span className="rounded-full border border-[#407883] bg-[#255762] px-2 py-0.5 font-data text-[9px] uppercase tracking-[0.14em] text-[#b3dfd9]">AWS-07</span>
            </div>
            <p className="mt-1 text-sm text-[#9cc2c2]">Automatic weather station · IIT field lab, New Delhi</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <div className="flex items-center gap-2 rounded-full border border-[#315d65] bg-[#173b45]/75 px-3 py-2">
            <StatusDot tone={tone} />
            <span className="font-semibold">{statusLabel}</span>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-[#315d65] bg-[#173b45]/75 px-3 py-2 text-[#a9cccb]">
            <span className={`h-1.5 w-1.5 rounded-full ${connection === 'live' ? 'bg-[#45d5c1]' : 'bg-[#ffbe55]'}`} />
            {connection === 'live' ? 'WebSocket live' : connection === 'connecting' ? 'Opening stream' : 'Stream offline'}
          </div>
        </div>
      </div>
      <div className="mt-6 grid gap-4 border-t border-[#315d65] pt-4 sm:grid-cols-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#749b9e]">Simulator mode</div>
          <div className="mt-1 flex items-center gap-2 font-display text-sm font-semibold text-[#e8f7f4]" data-testid="text-simulator-mode">
            <Activity className="h-3.5 w-3.5 text-[#ffd06a]" />
            {modeNames[status?.mode ?? 'NORMAL']}
          </div>
        </div>
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#749b9e]">Last reading</div>
          <div className="mt-1 font-data text-sm text-[#d6ece9]" data-testid="text-last-reading">{formatDate(status?.lastReadingAt)}</div>
        </div>
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#749b9e]">Service health</div>
          <div className="mt-1 flex items-center gap-2 font-data text-sm text-[#d6ece9]" data-testid="status-service-health">
            <span className={`h-1.5 w-1.5 rounded-full ${health === 'ok' ? 'bg-[#45d5c1]' : 'bg-[#ffbe55]'}`} />
            {health === 'ok' ? 'API operational' : health ?? 'Checking API'}
          </div>
        </div>
      </div>
    </section>
  );
}

function SimulatorControls({ status }: { status?: SimulatorStatus }) {
  const queryClient = useQueryClient();
  const [selectedMode, setSelectedMode] = useState<string>(status?.mode ?? SimulatorMode.NORMAL);
  const [notice, setNotice] = useState('');
  const startSimulator = useStartSimulator();
  const stopSimulator = useStopSimulator();
  const resetSimulator = useResetSimulator();
  const setSimulatorMode = useSetSimulatorMode();

  useEffect(() => {
    if (status?.mode) setSelectedMode(status.mode);
  }, [status?.mode]);

  const refreshStatus = (message: string, result?: SimulatorStatus) => {
    if (result) queryClient.setQueryData(getGetSimulatorStatusQueryKey(), result);
    queryClient.invalidateQueries({ queryKey: getGetLatestReadingQueryKey() });
    setNotice(message);
    window.setTimeout(() => setNotice(''), 3200);
  };

  return (
    <section className="sg-panel rounded-[1.15rem] p-5 md:p-6" data-testid="section-simulator-controls">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Settings2 className="h-4 w-4 text-primary" />
            <h2 className="font-display text-base font-bold">Simulator controls</h2>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">Change the synthetic stream without leaving the live view.</p>
        </div>
        <span className="rounded-full bg-secondary px-2.5 py-1 font-data text-[10px] text-muted-foreground">{status?.readingsStored ?? 0} stored</span>
      </div>
      <div className="mt-5 grid gap-3 sm:grid-cols-[1fr_auto]">
        <label className="relative block">
          <span className="mb-2 block text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Active scenario</span>
          <select
            value={selectedMode}
            onChange={(event) => {
              const nextMode = event.target.value as SimulatorMode;
              setSelectedMode(nextMode);
              setSimulatorMode.mutate({ data: { mode: nextMode } }, {
                onSuccess: (result) => refreshStatus('Scenario changed', result),
                onError: () => setNotice('Could not change scenario'),
              });
            }}
            disabled={setSimulatorMode.isPending}
            className="w-full appearance-none rounded-xl border border-input bg-background px-3 py-3 pr-10 text-sm font-semibold outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20 disabled:cursor-wait disabled:opacity-60"
            data-testid="select-simulator-mode"
          >
            {MODE_OPTIONS.map((mode) => <option key={mode} value={mode}>{modeNames[mode]}</option>)}
          </select>
          <ChevronDown className="pointer-events-none absolute bottom-3.5 right-3 h-4 w-4 text-muted-foreground" />
          <span className="mt-2 block text-[11px] text-muted-foreground">{modeDescriptions[selectedMode]}</span>
        </label>
        <div className="flex items-end gap-2 sm:justify-end">
          <button type="button" onClick={() => startSimulator.mutate(undefined, { onSuccess: (result) => refreshStatus('Simulator started', result), onError: () => setNotice('Could not start simulator') })} disabled={startSimulator.isPending || status?.status === 'SIMULATING'} className="flex h-11 items-center gap-2 rounded-xl bg-primary px-3.5 text-xs font-bold text-primary-foreground transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-45" data-testid="button-start-simulator">
            <Play className="h-3.5 w-3.5 fill-current" /> Start
          </button>
          <button type="button" onClick={() => stopSimulator.mutate(undefined, { onSuccess: (result) => refreshStatus('Simulator stopped', result), onError: () => setNotice('Could not stop simulator') })} disabled={stopSimulator.isPending || status?.status === 'STOPPED'} className="flex h-11 items-center gap-2 rounded-xl border border-input bg-background px-3.5 text-xs font-bold text-foreground transition hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-45" data-testid="button-stop-simulator">
            <Square className="h-3.5 w-3.5 fill-current" /> Stop
          </button>
          <button type="button" onClick={() => resetSimulator.mutate(undefined, { onSuccess: (result) => refreshStatus('Station reset', result), onError: () => setNotice('Could not reset station') })} disabled={resetSimulator.isPending} className="flex h-11 items-center justify-center rounded-xl border border-input bg-background px-3.5 text-xs font-bold text-foreground transition hover:bg-secondary disabled:cursor-wait disabled:opacity-45" data-testid="button-reset-simulator" aria-label="Reset simulator">
            <RotateCcw className={`h-3.5 w-3.5 ${resetSimulator.isPending ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>
      {notice && <div className="mt-4 flex items-center gap-2 rounded-lg bg-primary/10 px-3 py-2 text-xs font-semibold text-primary" role="status" data-testid="status-control-notice"><Check className="h-3.5 w-3.5" />{notice}</div>}
    </section>
  );
}

function HistoryTable({ readings, loading, error }: { readings: SensorReading[]; loading: boolean; error: boolean }) {
  const rows = [...readings].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()).slice(0, 10);
  return (
    <section className="sg-panel overflow-hidden rounded-[1.15rem]" data-testid="section-reading-history">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 px-5 py-4 md:px-6">
        <div>
          <div className="flex items-center gap-2">
            <TimerReset className="h-4 w-4 text-primary" />
            <h2 className="font-display text-base font-bold">Recent readings</h2>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">Live history · latest 10 of {readings.length || 0} available</p>
        </div>
        <div className="flex items-center gap-2 font-data text-[10px] uppercase tracking-[0.12em] text-muted-foreground"><Signal className="h-3.5 w-3.5 text-primary" /> 1 min cadence</div>
      </div>
      {loading ? (
        <div className="space-y-2 p-5" data-testid="loading-history">{Array.from({ length: 5 }).map((_, index) => <div className="h-9 animate-pulse rounded-lg bg-secondary" key={index} />)}</div>
      ) : error ? (
        <div className="flex min-h-44 flex-col items-center justify-center gap-2 p-6 text-center text-sm text-muted-foreground" data-testid="error-history"><TriangleAlert className="h-5 w-5 text-[#d97857]" />History could not be loaded. Live readings will still appear here.</div>
      ) : rows.length === 0 ? (
        <div className="flex min-h-44 flex-col items-center justify-center gap-2 p-6 text-center text-sm text-muted-foreground" data-testid="empty-history"><Pause className="h-5 w-5 opacity-50" />No readings stored yet. Start the simulator to begin the stream.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-xs">
            <thead className="bg-secondary/50 text-[10px] uppercase tracking-[0.13em] text-muted-foreground">
              <tr><th className="px-5 py-3 font-bold md:px-6">Timestamp</th><th className="px-3 py-3 font-bold">Temperature</th><th className="px-3 py-3 font-bold">Humidity</th><th className="px-3 py-3 font-bold">Pressure</th><th className="px-5 py-3 text-right font-bold md:px-6">Record</th></tr>
            </thead>
            <tbody>
              {rows.map((reading) => (
                <tr key={`${reading.id}-${reading.timestamp}`} className="border-t border-border/60 transition hover:bg-secondary/30" data-testid={`row-reading-${reading.id}`}>
                  <td className="px-5 py-3 font-data text-muted-foreground md:px-6">{formatTime(reading.timestamp)}</td>
                  <td className="px-3 py-3 font-data font-medium text-foreground">{(reading.temperature == null ? '—' : reading.temperature.toFixed(1))} °C</td>
                  <td className="px-3 py-3 font-data font-medium text-foreground">{(reading.humidity == null ? '—' : reading.humidity.toFixed(1))} %</td>
                  <td className="px-3 py-3 font-data font-medium text-foreground">{reading.pressure == null ? '—' : (reading.pressure == null ? '—' : reading.pressure.toFixed(1))} hPa</td>
                  <td className="px-5 py-3 text-right font-data text-[10px] text-muted-foreground md:px-6">#{reading.id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Home() {
  const queryClient = useQueryClient();
  const [connection, setConnection] = useState<ConnectionState>('connecting');
  const [streamReading, setStreamReading] = useState<SensorReading | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  const health = useHealthCheck({ query: { queryKey: getHealthCheckQueryKey(), refetchInterval: 30000 } });
  const latest = useGetLatestReading({ query: { queryKey: getGetLatestReadingQueryKey(), refetchInterval: 15000 } });
  const history = useGetReadingHistory(HISTORY_PARAMS, { query: { queryKey: getGetReadingHistoryQueryKey(HISTORY_PARAMS), refetchInterval: 30000 } });
  const simulator = useGetSimulatorStatus({ query: { queryKey: getGetSimulatorStatusQueryKey(), refetchInterval: 15000 } });

  useEffect(() => {
    let reconnectTimer: number | undefined;
    let disposed = false;
    const connect = () => {
      if (disposed) return;
      setConnection('connecting');
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const socket = new WebSocket(`${protocol}//${window.location.host}/ws`);
      socketRef.current = socket;
      socket.onopen = () => setConnection('live');
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as Partial<SensorReading> & { data?: Partial<SensorReading>; reading?: Partial<SensorReading> };
          const candidate = payload.data ?? payload.reading ?? payload;
          if (typeof candidate.temperature === 'number' && typeof candidate.humidity === 'number' && typeof candidate.pressure === 'number') {
            const reading: SensorReading = {
              id: candidate.id ?? Date.now(),
              timestamp: candidate.timestamp ?? new Date().toISOString(),
              temperature: candidate.temperature,
              humidity: candidate.humidity,
              pressure: candidate.pressure,
            };
            setStreamReading(reading);
            queryClient.setQueryData(getGetLatestReadingQueryKey(), reading);
            queryClient.setQueryData(getGetReadingHistoryQueryKey(HISTORY_PARAMS), (old: SensorReading[] | undefined) => [...(old ?? []), reading].slice(-120));
            queryClient.setQueryData(getGetSimulatorStatusQueryKey(), (old: SimulatorStatus | undefined) => old ? { ...old, lastReadingAt: reading.timestamp, readingsStored: Math.max(old.readingsStored, (old.readingsStored ?? 0) + 1) } : old);
          }
        } catch {
          setConnection('offline');
        }
      };
      socket.onerror = () => setConnection('offline');
      socket.onclose = () => {
        setConnection('offline');
        if (!disposed) reconnectTimer = window.setTimeout(connect, 3000);
      };
    };
    connect();
    return () => {
      disposed = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      socketRef.current?.close();
    };
  }, [queryClient]);

  const reading = streamReading ?? latest.data ?? history.data?.[history.data.length - 1];
  const readings = useMemo(() => {
    const map = new Map<number, SensorReading>();
    [...(history.data ?? []), ...(streamReading ? [streamReading] : [])].forEach((item) => map.set(item.id, item));
    return [...map.values()].sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
  }, [history.data, streamReading]);
  const chartData = useMemo(() => readings.map((item) => ({ ...item, shortTime: formatTime(item.timestamp).slice(0, 5) })), [readings]);
  const hasQueryError = health.isError || latest.isError || history.isError || simulator.isError;

  if (health.isLoading && latest.isLoading && history.isLoading && simulator.isLoading) {
    return <div className="skyguard-shell min-h-[100dvh] md:flex"><Sidebar connection={connection} /><main className="min-w-0 flex-1 p-4 md:p-8"><DashboardSkeleton /></main></div>;
  }

  return (
    <div className="skyguard-shell min-h-[100dvh] md:flex">
      <Sidebar status={simulator.data} connection={connection} />
      <main className="skyguard-grid min-w-0 flex-1 p-4 md:p-8">
        <div className="mx-auto max-w-[1480px] space-y-5">
          <header className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <div className="mb-2 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.18em] text-primary"><span className="h-1.5 w-1.5 rounded-full bg-primary" /> Control room / phase 01</div>
              <h2 className="font-display text-2xl font-bold tracking-[-0.04em] text-foreground md:text-3xl">Weather, without the guesswork.</h2>
              <p className="mt-1.5 max-w-xl text-sm text-muted-foreground">A trustworthy live read on the station your team is simulating.</p>
            </div>
            <div className="flex items-center gap-2 rounded-xl border border-border/80 bg-card/60 px-3 py-2 text-xs text-muted-foreground" data-testid="status-refresh">
              <RefreshCw className="h-3.5 w-3.5 text-primary" />
              <span>Auto-refreshing</span>
              <span className="font-data text-foreground">{formatTime(new Date().toISOString())}</span>
            </div>
          </header>

          {hasQueryError && (
            <div className="flex flex-wrap items-center gap-3 rounded-xl border border-[#e3b7a5] bg-[#fff4ed] px-4 py-3 text-sm text-[#854c38]" role="alert" data-testid="alert-query-error">
              <AlertTriangle className="h-4 w-4" />
              <span>Some station data is delayed. The live stream will backfill the dashboard when it reconnects.</span>
              <button type="button" className="ml-auto rounded-lg border border-[#d9a88f] px-3 py-1.5 text-xs font-bold hover:bg-[#fbe6da]" onClick={() => { health.refetch(); latest.refetch(); history.refetch(); simulator.refetch(); }} data-testid="button-retry-queries">Retry</button>
            </div>
          )}

          <StatusOverview status={simulator.data} health={health.data?.status} connection={connection} />

          <div className="grid gap-4 md:grid-cols-3">
            <MetricCard label="Temperature" value={reading?.temperature} unit="°C" detail="Air temperature · 2 m mast" type="temperature" accent="bg-[#e27951]" />
            <MetricCard label="Humidity" value={reading?.humidity} unit="%" detail="Relative humidity · shielded" type="humidity" accent="bg-[#3e9eb0]" />
            <MetricCard label="Pressure" value={reading?.pressure} unit="hPa" detail="Station pressure · corrected" type="pressure" accent="bg-[#d6a22d]" />
          </div>

          <div className="flex items-center gap-3 pt-2">
            <div className="h-px flex-1 bg-border/70" />
            <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground"><BarChart3 className="h-3.5 w-3.5 text-primary" /> 120-reading signal window</div>
            <div className="h-px flex-1 bg-border/70" />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <DashboardChart title="Thermal trace" subtitle="Ambient temperature" data={chartData} dataKey="temperature" color="#dc7653" unit="°C" />
            <DashboardChart title="Moisture trace" subtitle="Relative humidity" data={chartData} dataKey="humidity" color="#2a98a8" unit="%" domain={[0, 100]} />
            <DashboardChart title="Pressure trace" subtitle="Atmospheric pressure" data={chartData} dataKey="pressure" color="#c28a27" unit="hPa" />
          </div>

          <div className="grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(360px,.8fr)]">
            <HistoryTable readings={readings} loading={history.isLoading} error={history.isError} />
            <SimulatorControls status={simulator.data} />
          </div>

          <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-border/60 pb-3 pt-1 text-[10px] uppercase tracking-[0.13em] text-muted-foreground">
            <span className="flex items-center gap-2"><Server className="h-3.5 w-3.5" /> SkyGuard AI · Smart India Hackathon / Phase 1</span>
            <span className="flex items-center gap-2"><CircleHelp className="h-3.5 w-3.5" /> Synthetic station data for evaluation</span>
          </footer>
        </div>
      </main>
    </div>
  );
}

function Router() {
  return (
    <ErrorBoundary>
      <Switch>
        <Route path="/" component={Home} />
        <Route component={NotFound} />
      </Switch>
    </ErrorBoundary>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
          <Router />
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;