import { useEffect, useMemo, useRef, useState } from 'react';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  BarChart3,
  CheckCircle2,
  CloudDrizzle,
  Play,
  Radio,
  Server,
  ShieldCheck,
  Square,
  Thermometer,
  Wifi,
  WifiOff,
} from 'lucide-react';
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
  useSetSimulatorMode,
  useStartSimulator,
  useStopSimulator,
  type SensorReading,
  type SimulatorStatus,
} from '@workspace/api-client-react';
import '@/index.css';

const awsQueryClient = new QueryClient();
const HISTORY_PARAMS = { limit: 120 };
const AWS_SIMULATOR_MODES = [
  SimulatorMode.NORMAL,
  SimulatorMode.TEMPERATURE_SPIKE,
  SimulatorMode.TEMPERATURE_DROP,
  SimulatorMode.HUMIDITY_SPIKE,
  SimulatorMode.FROZEN_SENSOR,
  SimulatorMode.GRADUAL_DRIFT,
  SimulatorMode.MISSING_DATA,
] as const;

const modeNames: Record<string, string> = {
  NORMAL: 'Normal baseline',
  TEMPERATURE_SPIKE: 'Temperature spike',
  TEMPERATURE_DROP: 'Temperature drop',
  HUMIDITY_SPIKE: 'Humidity spike',
  FROZEN_SENSOR: 'Frozen sensor',
  GRADUAL_DRIFT: 'Gradual drift',
  MISSING_DATA: 'Missing data',
};

function formatTime(value?: string | null) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(value));
}

function formatDate(value?: string | null) {
  if (!value) return 'Awaiting first reading';
  return new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(value));
}

function MetricCard({
  label,
  value,
  unit,
  detail,
  icon,
}: {
  label: string;
  value?: number;
  unit: string;
  detail: string;
  icon: 'temperature' | 'humidity';
}) {
  return (
    <section
      className="sg-panel rise-in relative overflow-hidden rounded-[1.15rem] p-5"
      data-testid={`card-metric-${icon}`}
    >
      <div className="relative flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.17em] text-muted-foreground">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10 text-foreground">
              {icon === 'temperature' ? <Thermometer className="h-4 w-4" /> : <CloudDrizzle className="h-4 w-4" />}
            </span>
            {label}
          </div>
          <div className="mt-5 flex items-baseline gap-1.5">
            <span className="reading-number font-display text-[2.65rem] font-semibold leading-none text-foreground">
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

function SignalChart({
  title,
  subtitle,
  data,
  dataKey,
  unit,
  domain,
}: {
  title: string;
  subtitle: string;
  data: Array<SensorReading & { shortTime: string }>;
  dataKey: 'temperature' | 'humidity';
  unit: string;
  domain?: [number, number];
}) {
  return (
    <section className="sg-panel min-w-0 rounded-[1.15rem] p-5">
      <div className="mb-4">
        <h3 className="font-display text-base font-semibold tracking-tight text-foreground">{title}</h3>
        <p className="mt-1 text-[11px] uppercase tracking-[0.13em] text-muted-foreground">{subtitle}</p>
      </div>
      <div className="h-[190px] w-full">
        {data.length < 2 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border/80 text-center text-xs text-muted-foreground">
            <Activity className="h-4 w-4 opacity-50" />
            Waiting for two readings to draw a trend
          </div>
        ) : (
          <div className="flex h-full flex-col items-center justify-center rounded-lg border border-dashed border-border/80 text-center text-xs text-muted-foreground">
            <span className="font-semibold text-foreground">{data[data.length - 1][dataKey]?.toFixed(1)} {unit}</span>
            <span className="mt-1">Live {dataKey} stream is active.</span>
            <span className="mt-1 text-[10px]">{data.length}-reading window · {domain ? `expected ${domain[0]}–${domain[1]} ${unit}` : 'baseline-relative'}</span>
          </div>
        )}
      </div>
    </section>
  );
}

function AwsHistory({ readings }: { readings: SensorReading[] }) {
  return (
    <section className="sg-panel overflow-hidden rounded-[1.15rem]">
      <div className="border-b border-border/70 px-5 py-4">
        <div className="flex items-center gap-2">
          <Radio className="h-4 w-4 text-primary" />
          <h2 className="font-display text-base font-bold">AWS telemetry history</h2>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">Only physical sensor channels are shown. Atmospheric pressure is unavailable on this prototype.</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[500px] text-left text-xs">
          <thead className="bg-secondary/50 text-[10px] uppercase tracking-[0.13em] text-muted-foreground">
            <tr>
              <th className="px-5 py-3 font-bold">Timestamp</th>
              <th className="px-3 py-3 font-bold">Temperature</th>
              <th className="px-3 py-3 font-bold">Humidity</th>
              <th className="px-5 py-3 text-right font-bold">Record</th>
            </tr>
          </thead>
          <tbody>
            {readings.slice(-20).reverse().map((reading) => (
              <tr key={`${reading.id}-${reading.timestamp}`} className="border-t border-border/60">
                <td className="px-5 py-3 font-data text-muted-foreground">{formatTime(reading.timestamp)}</td>
                <td className="px-3 py-3 font-data font-medium text-foreground">{(reading.temperature == null ? '—' : reading.temperature.toFixed(1))} °C</td>
                <td className="px-3 py-3 font-data font-medium text-foreground">{(reading.humidity == null ? '—' : reading.humidity.toFixed(1))} %</td>
                <td className="px-5 py-3 text-right font-data text-[10px] text-muted-foreground">#{reading.id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function AwsDashboardContent() {
  const queryClient = useQueryClient();
  const [connection, setConnection] = useState<'connecting' | 'live' | 'offline'>('connecting');
  const [streamReading, setStreamReading] = useState<SensorReading | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  const health = useHealthCheck({ query: { queryKey: getHealthCheckQueryKey(), refetchInterval: 30000 } });
  const latest = useGetLatestReading({ query: { queryKey: getGetLatestReadingQueryKey(), refetchInterval: 15000 } });
  const history = useGetReadingHistory(HISTORY_PARAMS, { query: { queryKey: getGetReadingHistoryQueryKey(HISTORY_PARAMS), refetchInterval: 30000 } });
  const simulator = useGetSimulatorStatus({ query: { queryKey: getGetSimulatorStatusQueryKey(), refetchInterval: 15000 } });
  const setSimulatorMode = useSetSimulatorMode();
  const startSimulator = useStartSimulator();
  const stopSimulator = useStopSimulator();

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
          if (typeof candidate.temperature === 'number' && typeof candidate.humidity === 'number') {
            const reading: SensorReading = {
              id: candidate.id ?? Date.now(),
              timestamp: candidate.timestamp ?? new Date().toISOString(),
              temperature: candidate.temperature,
              humidity: candidate.humidity,
              pressure: typeof candidate.pressure === 'number' ? candidate.pressure : null,
            };
            setStreamReading(reading);
            queryClient.setQueryData(getGetLatestReadingQueryKey(), reading);
            queryClient.setQueryData(getGetReadingHistoryQueryKey(HISTORY_PARAMS), (old: SensorReading[] | undefined) => [...(old ?? []), reading].slice(-120));
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

  return (
    <div className="skyguard-shell min-h-[100dvh]">
      <main className="skyguard-grid min-h-[100dvh] p-4 md:p-8">
        <div className="mx-auto max-w-[1480px] space-y-5">
          <header className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <div className="mb-2 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.18em] text-primary">
                <span className="h-1.5 w-1.5 rounded-full bg-primary" /> Physical AWS / field mode
              </div>
              <h1 className="font-display text-2xl font-bold tracking-[-0.04em] text-foreground md:text-3xl">Weather station — T / RH only</h1>
              <p className="mt-1.5 max-w-2xl text-sm text-muted-foreground">AWS mode intentionally excludes atmospheric pressure because the physical prototype provides only temperature and relative humidity.</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-2 rounded-xl border border-border/80 bg-card/60 px-3 py-2 text-xs font-semibold text-foreground">
                <span className="h-2 w-2 rounded-full bg-primary" /> AWS mode
              </div>
              <div className="flex items-center gap-2 rounded-xl border border-border/80 bg-card/60 px-3 py-2 text-xs text-muted-foreground">
                {connection === 'live' ? <Wifi className="h-3.5 w-3.5 text-primary" /> : <WifiOff className="h-3.5 w-3.5" />}
                {connection === 'live' ? 'WebSocket live' : connection === 'connecting' ? 'Opening stream' : 'Stream offline'}
              </div>
            </div>
          </header>

          <section className="sg-panel-dark rise-in overflow-hidden rounded-[1.15rem] p-5 text-[#e9f8f4] md:p-6">
            <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-center">
              <div className="flex items-start gap-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#ffd06a] text-[#173844]"><ShieldCheck className="h-6 w-6" /></div>
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="font-display text-xl font-bold tracking-tight">Live AWS overview</h2>
                    <span className="rounded-full border border-[#407883] bg-[#255762] px-2 py-0.5 font-data text-[9px] uppercase tracking-[0.14em] text-[#b3dfd9]">T/RH</span>
                  </div>
                  <p className="mt-1 text-sm text-[#9cc2c2]">Pressure channel: unavailable on physical prototype</p>
                </div>
              </div>
              <div className="flex items-center gap-2 rounded-full border border-[#315d65] bg-[#173b45]/75 px-3 py-2 text-xs">
                <CheckCircle2 className="h-3.5 w-3.5 text-[#45d5c1]" />
                ML configured for AWS mode
              </div>
            </div>
            <div className="mt-6 grid gap-4 border-t border-[#315d65] pt-4 sm:grid-cols-3">
              <div><div className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#749b9e]">Simulator</div><div className="mt-1 font-data text-sm text-[#d6ece9]">{modeNames[simulator.data?.mode ?? 'NORMAL']}</div></div>
              <div><div className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#749b9e]">Last reading</div><div className="mt-1 font-data text-sm text-[#d6ece9]">{formatDate(simulator.data?.lastReadingAt)}</div></div>
              <div><div className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#749b9e]">API health</div><div className="mt-1 font-data text-sm text-[#d6ece9]">{health.data?.status ?? 'Checking…'}</div></div>
            </div>
          </section>

          <div className="grid gap-4 md:grid-cols-2" data-testid="aws-metric-grid">
            <MetricCard label="Temperature" value={reading?.temperature} unit="°C" detail="Air temperature · physical sensor" icon="temperature" />
            <MetricCard label="Humidity" value={reading?.humidity} unit="%" detail="Relative humidity · physical sensor" icon="humidity" />
          </div>

          <div className="rounded-[1.15rem] border border-dashed border-border/90 bg-card/50 px-5 py-4 text-sm text-muted-foreground">
            <span className="font-semibold text-foreground">Pressure omitted by design.</span> No pressure value is generated, imputed, displayed, or fed into the AWS-mode ML pipeline.
          </div>

          <div className="flex items-center gap-3 pt-2">
            <div className="h-px flex-1 bg-border/70" />
            <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground"><BarChart3 className="h-3.5 w-3.5 text-primary" /> 120-reading T/RH window</div>
            <div className="h-px flex-1 bg-border/70" />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <SignalChart title="Thermal trace" subtitle="Ambient temperature" data={chartData} dataKey="temperature" unit="°C" />
            <SignalChart title="Moisture trace" subtitle="Relative humidity" data={chartData} dataKey="humidity" unit="%" domain={[0, 100]} />
          </div>

          <AwsHistory readings={readings} />

          <section className="sg-panel rounded-[1.15rem] p-5">
            <div className="flex items-center gap-2"><Activity className="h-4 w-4 text-primary" /><h2 className="font-display text-base font-bold">AWS test controls</h2></div>
            <p className="mt-1 text-xs text-muted-foreground">Pressure-dependent simulator scenarios are hidden while AWS mode is active.</p>
            <div className="mt-4 grid gap-3 md:grid-cols-[1fr_auto_auto]">
              <select
                value={simulator.data?.mode ?? SimulatorMode.NORMAL}
                onChange={(event) => setSimulatorMode.mutate({ data: { mode: event.target.value as SimulatorMode } })}
                disabled={setSimulatorMode.isPending}
                className="rounded-xl border border-input bg-background px-3 py-3 text-sm font-semibold"
              >
                {AWS_SIMULATOR_MODES.map((mode) => <option key={mode} value={mode}>{modeNames[mode]}</option>)}
              </select>
              <button type="button" onClick={() => startSimulator.mutate()} disabled={startSimulator.isPending || simulator.data?.status === 'SIMULATING'} className="flex h-11 items-center justify-center gap-2 rounded-xl bg-primary px-4 text-xs font-bold text-primary-foreground disabled:opacity-45"><Play className="h-3.5 w-3.5 fill-current" />Start</button>
              <button type="button" onClick={() => stopSimulator.mutate()} disabled={stopSimulator.isPending || simulator.data?.status === 'STOPPED'} className="flex h-11 items-center justify-center gap-2 rounded-xl border border-input px-4 text-xs font-bold disabled:opacity-45"><Square className="h-3.5 w-3.5 fill-current" />Stop</button>
            </div>
          </section>

          <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-border/60 pb-3 pt-1 text-[10px] uppercase tracking-[0.13em] text-muted-foreground">
            <span className="flex items-center gap-2"><Server className="h-3.5 w-3.5" /> SkyGuard AI · SIH 2026</span>
            <span>Physical prototype channels: temperature + relative humidity</span>
          </footer>
        </div>
      </main>
    </div>
  );
}

export default function AwsDashboard() {
  return (
    <QueryClientProvider client={awsQueryClient}>
      <AwsDashboardContent />
    </QueryClientProvider>
  );
}
