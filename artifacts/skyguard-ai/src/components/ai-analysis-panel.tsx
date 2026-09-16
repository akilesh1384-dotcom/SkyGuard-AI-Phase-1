import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Activity, BrainCircuit, CheckCircle2, CircleAlert, ChevronDown, Loader2, ShieldAlert, XCircle } from 'lucide-react';
import { getSensorMode, type SensorMode } from './sensor-mode-control';

type AnomalyResult = { timestamp: string; statistical_score: number; ml_score: number; diagnostic_score: number; multivariate_score: number; final_score: number; is_anomaly: boolean; alert_active: boolean; alert_state: string; diagnostic_anomaly: boolean; fault_type: string; affected_variable: string | null; reasons: string[]; };
type AnalysisResponse = { status: string; baseline_progress: number; baseline_required: number; baseline_initialized: boolean; sensor_mode: SensorMode; results: AnomalyResult[]; };
type StatusResponse = { status: string; readings_loaded: number; latest_reading_timestamp: string | null; baseline_initialized: boolean; baseline_progress: number; baseline_required: number; sensor_mode: SensorMode; };
function percent(value: number) { return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`; }
function faultLabel(value: string) { return value.toLowerCase().split('_').map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(' '); }
function toneForScore(score: number) { if (score >= 0.75) return 'bg-[#ef7168]'; if (score >= 0.5) return 'bg-[#ffbe55]'; return 'bg-[#45d5c1]'; }

export default function AiAnalysisPanel() {
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [storedReadings, setStoredReadings] = useState<number | null>(null);
  const [error, setError] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [mountNode, setMountNode] = useState<HTMLElement | null>(null);
  const [mode, setMode] = useState<SensorMode>(getSensorMode);
  const slotRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    let disposed = false;
    const findDashboardSlot = () => {
      if (disposed || slotRef.current) return;
      const metricCard = document.querySelector('[data-testid="card-metric-temperature"]');
      const metricGrid = metricCard?.parentElement;
      if (!metricGrid) return;
      const slot = document.createElement('div');
      slot.className = 'w-full';
      metricGrid.insertAdjacentElement('afterend', slot);
      slotRef.current = slot;
      setMountNode(slot);
    };
    findDashboardSlot();
    const observer = new MutationObserver(findDashboardSlot);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => { disposed = true; observer.disconnect(); if (slotRef.current?.parentElement) slotRef.current.parentElement.removeChild(slotRef.current); slotRef.current = null; };
  }, []);

  useEffect(() => {
    let disposed = false;
    let timer: number | undefined;
    const load = async () => {
      try {
        const [analysisResponse, statusResponse] = await Promise.all([
          fetch(`/api/ml/analyze?limit=1&sensor_mode=${mode}`, { cache: 'no-store' }),
          fetch(`/api/ml/status?sensor_mode=${mode}`, { cache: 'no-store' }),
        ]);
        if (!analysisResponse.ok) throw new Error(`ML analysis API ${analysisResponse.status}`);
        if (!statusResponse.ok) throw new Error(`ML status API ${statusResponse.status}`);
        const [analysisPayload, statusPayload] = await Promise.all([
          analysisResponse.json() as Promise<AnalysisResponse>,
          statusResponse.json() as Promise<StatusResponse>,
        ]);
        if (!disposed) {
          setAnalysis(analysisPayload);
          setStoredReadings(statusPayload.readings_loaded);
          setError(false);
        }
      } catch {
        if (!disposed) setError(true);
      } finally {
        if (!disposed) timer = window.setTimeout(load, 5000);
      }
    };
    load();
    return () => { disposed = true; if (timer) window.clearTimeout(timer); };
  }, [mode]);

  useEffect(() => {
    const handler = (event: Event) => setMode((event as CustomEvent<SensorMode>).detail);
    window.addEventListener('skyguard-sensor-mode-change', handler);
    return () => window.removeEventListener('skyguard-sensor-mode-change', handler);
  }, []);

  if (!mountNode) return null;
  const result = analysis?.results?.[0];
  const ready = Boolean(analysis?.baseline_initialized && result);
  const anomalous = Boolean(result?.is_anomaly);
  const active = Boolean(result?.alert_active);

  return createPortal(
    <section className="w-full overflow-hidden rounded-[1.15rem] border border-[#356872] bg-[#123541] text-[#eef8f5] shadow-[0_12px_35px_rgba(12,42,52,.16)]" data-testid="panel-ai-analysis">
      <button type="button" className="flex w-full items-center justify-between border-b border-[#315d65] px-5 py-4 text-left" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}>
        <div className="flex items-center gap-3"><span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#ffd06a] text-[#173844]"><BrainCircuit className="h-4 w-4" /></span><div><div className="flex items-center gap-2 text-sm font-bold">AI Analysis <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-[0.12em] text-[#8db5b7]"><Activity className="h-3 w-3" /> {mode} live</span></div><div className="text-[9px] uppercase tracking-[0.16em] text-[#8db5b7]">real-time anomaly engine · baseline {analysis ? `${analysis.baseline_progress}/${analysis.baseline_required}` : 'initializing'}</div></div></div>
        <div className="flex items-center gap-3">{ready && result ? <div className="hidden items-center gap-2 sm:flex"><span className={`h-2 w-2 rounded-full ${anomalous ? 'bg-[#ef7168]' : 'bg-[#45d5c1]'}`} /><span className="text-[10px] font-bold uppercase tracking-[0.12em] text-[#c7dfdc]">{anomalous ? 'Anomaly detected' : 'Station nominal'}</span><span className="font-data text-sm font-bold text-[#f0faf7]">{percent(result.final_score)}</span></div> : null}<ChevronDown className={`h-4 w-4 text-[#8db5b7] transition-transform ${expanded ? 'rotate-180' : ''}`} /></div>
      </button>
      {!ready && !error && <div className="flex items-center gap-2 px-5 py-4 text-xs text-[#b6d0d0]"><Loader2 className="h-4 w-4 animate-spin text-[#45d5c1]" />Initializing {mode} anomaly baseline…</div>}
      {error && <div className="flex items-start gap-2 px-5 py-4 text-xs text-[#ffd1c8]"><XCircle className="mt-0.5 h-4 w-4 shrink-0 text-[#ef7168]" /><div>ML service unavailable. The station dashboard is still running.</div></div>}
      {ready && result && <div className="px-5 pb-5 pt-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-[#315d65] bg-[#173d48]/80 p-3"><div className="flex items-center gap-2">{anomalous ? <CircleAlert className="h-4 w-4 text-[#ef7168]" /> : <CheckCircle2 className="h-4 w-4 text-[#45d5c1]" />}<div><div className="text-[9px] font-bold uppercase tracking-[0.12em] text-[#7da4a7]">Status</div><div className="mt-0.5 text-sm font-bold">{anomalous ? 'Anomaly detected' : 'Station nominal'}</div></div></div></div>
          <div className="rounded-xl border border-[#315d65] bg-[#173d48]/80 p-3"><div className="text-[9px] font-bold uppercase tracking-[0.12em] text-[#7da4a7]">Fault type</div><div className="mt-1 text-sm font-semibold">{faultLabel(result.fault_type)}</div></div>
          <div className="rounded-xl border border-[#315d65] bg-[#173d48]/80 p-3"><div className="text-[9px] font-bold uppercase tracking-[0.12em] text-[#7da4a7]">Affected</div><div className="mt-1 truncate text-sm font-semibold">{result.affected_variable ?? 'None'}</div></div>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3 rounded-xl bg-[#102f39]/80 px-3 py-2.5 text-[10px] text-[#9fc0c0]"><span>Mode <strong className="text-[#e9f6f3]">{mode}</strong></span><span>Alert <strong className="text-[#e9f6f3]">{active ? result.alert_state : 'NORMAL'}</strong></span><span>Final score <strong className="text-[#e9f6f3]">{percent(result.final_score)}</strong></span><span>Baseline <strong className="text-[#e9f6f3]">{analysis.baseline_progress}/{analysis.baseline_required}</strong></span><span>Stored readings <strong className="text-[#e9f6f3]">{storedReadings ?? '—'}</strong></span></div>
        {!expanded && <button type="button" onClick={() => setExpanded(true)} className="mt-3 w-full rounded-lg bg-[#183f49] px-3 py-2 text-[10px] font-semibold text-[#c7e1de] transition hover:bg-[#204955]">View detector breakdown and explanation</button>}
        {expanded && <div className="mt-4"><div className="mb-2 text-[9px] font-bold uppercase tracking-[0.13em] text-[#7da4a7]">Model signals</div><div className="grid gap-3 md:grid-cols-4">{[['Statistical', result.statistical_score], ['Isolation Forest', result.ml_score], ['Sensor diagnostics', result.diagnostic_score], ['Multivariate consistency', result.multivariate_score]].map(([label, score]) => <div key={label as string} className="rounded-lg bg-[#173d48]/80 p-3"><div className="mb-1 flex items-center justify-between text-[10px]"><span className="text-[#b5cecf]">{label as string}</span><span className="font-data font-semibold text-[#e8f5f2]">{percent(score as number)}</span></div><div className="h-1.5 overflow-hidden rounded-full bg-[#294f58]"><div className={`h-full rounded-full ${toneForScore(score as number)}`} style={{ width: `${Math.max(2, Math.min(100, (score as number) * 100))}%` }} /></div></div>)}</div><div className="mt-3 rounded-xl bg-[#102f39]/80 p-3"><div className="mb-2 flex items-center gap-2 text-[9px] font-bold uppercase tracking-[0.13em] text-[#7da4a7]"><ShieldAlert className="h-3 w-3" />{anomalous ? 'Why the engine flagged it' : 'Model explanation'}</div>{!anomalous && <div className="mb-2 text-[10px] leading-4 text-[#9fc0c0]">The detector signals are shown individually above, but the combined operational score remains below the anomaly alert threshold. This reading is therefore treated as nominal.</div>}<div className="flex flex-wrap gap-1.5">{result.reasons.length ? result.reasons.map((reason) => <span key={reason} className="rounded-full border border-[#3a6770] bg-[#183f49] px-2 py-1 text-[9px] font-semibold text-[#c7e1de]">{faultLabel(reason)}</span>) : <span className="text-[10px] text-[#88aeb0]">No active anomaly reason.</span>}</div></div><button type="button" onClick={() => setExpanded(false)} className="mt-3 text-[10px] font-semibold text-[#9fc0c0] underline decoration-[#4c7780] underline-offset-2 hover:text-[#eef8f5]">Collapse details</button></div>}
      </div>}
    </section>, mountNode,
  );
}
