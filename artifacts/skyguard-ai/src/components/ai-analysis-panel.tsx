import { useEffect, useState } from 'react';
import { Activity, BrainCircuit, CheckCircle2, CircleAlert, Loader2, ShieldAlert, XCircle } from 'lucide-react';

type AnomalyResult = {
  timestamp: string;
  statistical_score: number;
  ml_score: number;
  diagnostic_score: number;
  final_score: number;
  is_anomaly: boolean;
  alert_active: boolean;
  alert_state: string;
  diagnostic_anomaly: boolean;
  fault_type: string;
  affected_variable: string | null;
  reasons: string[];
};

type AnalysisResponse = {
  status: string;
  baseline_progress: number;
  baseline_required: number;
  baseline_initialized: boolean;
  results: AnomalyResult[];
};

function percent(value: number) {
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;
}

function faultLabel(value: string) {
  return value
    .toLowerCase()
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function toneForScore(score: number) {
  if (score >= 0.75) return 'bg-[#ef7168]';
  if (score >= 0.5) return 'bg-[#ffbe55]';
  return 'bg-[#45d5c1]';
}

export default function AiAnalysisPanel() {
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let disposed = false;
    let timer: number | undefined;

    const load = async () => {
      try {
        const response = await fetch('/api/ml/analyze?limit=1', { cache: 'no-store' });
        if (!response.ok) throw new Error(`ML API ${response.status}`);
        const payload = (await response.json()) as AnalysisResponse;
        if (!disposed) {
          setAnalysis(payload);
          setError(false);
        }
      } catch {
        if (!disposed) setError(true);
      } finally {
        if (!disposed) timer = window.setTimeout(load, 5000);
      }
    };

    load();
    return () => {
      disposed = true;
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  const result = analysis?.results?.[0];
  const ready = Boolean(analysis?.baseline_initialized && result);
  const anomalous = Boolean(result?.is_anomaly);
  const active = Boolean(result?.alert_active);

  return (
    <section
      className="fixed bottom-4 right-4 z-50 w-[min(390px,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-[#356872] bg-[#123541]/95 text-[#eef8f5] shadow-[0_18px_55px_rgba(12,42,52,.32)] backdrop-blur-md"
      data-testid="panel-ai-analysis"
    >
      <div className="flex items-center justify-between border-b border-[#315d65] px-4 py-3">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#ffd06a] text-[#173844]">
            <BrainCircuit className="h-4 w-4" />
          </span>
          <div>
            <div className="text-sm font-bold">AI Analysis</div>
            <div className="text-[9px] uppercase tracking-[0.16em] text-[#8db5b7]">real-time anomaly engine</div>
          </div>
        </div>
        <div className="flex items-center gap-1.5 text-[9px] font-bold uppercase tracking-[0.12em] text-[#8db5b7]">
          <Activity className="h-3 w-3" /> live
        </div>
      </div>

      {!ready && !error && (
        <div className="flex items-center gap-2 px-4 py-5 text-xs text-[#b6d0d0]">
          <Loader2 className="h-4 w-4 animate-spin text-[#45d5c1]" />
          Initializing anomaly baseline…
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 px-4 py-5 text-xs text-[#ffd1c8]">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-[#ef7168]" />
          <div>ML service unavailable. The station dashboard is still running.</div>
        </div>
      )}

      {ready && result && (
        <div className="space-y-4 p-4">
          <div className="flex items-center justify-between rounded-xl border border-[#315d65] bg-[#173d48]/80 p-3">
            <div className="flex items-center gap-2.5">
              {anomalous ? (
                <CircleAlert className="h-5 w-5 text-[#ef7168]" />
              ) : (
                <CheckCircle2 className="h-5 w-5 text-[#45d5c1]" />
              )}
              <div>
                <div className="text-xs font-bold uppercase tracking-[0.12em]">
                  {anomalous ? 'Anomaly detected' : 'Station nominal'}
                </div>
                <div className="mt-0.5 text-[10px] text-[#91b4b6]">
                  Alert {active ? result.alert_state : 'NORMAL'}
                </div>
              </div>
            </div>
            <div className="text-right">
              <div className="font-data text-2xl font-bold">{percent(result.final_score)}</div>
              <div className="text-[9px] uppercase tracking-[0.12em] text-[#86aeb1]">final score</div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <div className="text-[9px] font-bold uppercase tracking-[0.13em] text-[#7da4a7]">Fault type</div>
              <div className="mt-1 font-semibold text-[#e9f6f3]">{faultLabel(result.fault_type)}</div>
            </div>
            <div>
              <div className="text-[9px] font-bold uppercase tracking-[0.13em] text-[#7da4a7]">Affected</div>
              <div className="mt-1 font-semibold text-[#e9f6f3]">{result.affected_variable ?? 'None'}</div>
            </div>
          </div>

          <div>
            <div className="mb-2 text-[9px] font-bold uppercase tracking-[0.13em] text-[#7da4a7]">Model signals</div>
            <div className="space-y-2.5">
              {[
                ['Statistical', result.statistical_score],
                ['Isolation Forest', result.ml_score],
                ['Diagnostic / multivariate', result.diagnostic_score],
              ].map(([label, score]) => (
                <div key={label as string}>
                  <div className="mb-1 flex items-center justify-between text-[10px]">
                    <span className="text-[#b5cecf]">{label as string}</span>
                    <span className="font-data font-semibold text-[#e8f5f2]">{percent(score as number)}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-[#294f58]">
                    <div className={`h-full rounded-full ${toneForScore(score as number)}`} style={{ width: `${Math.max(2, Math.min(100, (score as number) * 100))}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-xl bg-[#102f39]/80 p-3">
            <div className="mb-2 flex items-center gap-2 text-[9px] font-bold uppercase tracking-[0.13em] text-[#7da4a7]">
              <ShieldAlert className="h-3 w-3" /> Why the engine flagged it
            </div>
            <div className="flex flex-wrap gap-1.5">
              {result.reasons.length ? result.reasons.map((reason) => (
                <span key={reason} className="rounded-full border border-[#3a6770] bg-[#183f49] px-2 py-1 text-[9px] font-semibold text-[#c7e1de]">
                  {faultLabel(reason)}
                </span>
              )) : <span className="text-[10px] text-[#88aeb0]">No active anomaly reason.</span>}
            </div>
          </div>

          <div className="flex items-center justify-between border-t border-[#315d65] pt-3 text-[9px] uppercase tracking-[0.12em] text-[#78a0a3]">
            <span>Baseline</span>
            <span className="flex items-center gap-1.5 text-[#b9d5d2]">
              <span className="h-1.5 w-1.5 rounded-full bg-[#45d5c1]" />
              {analysis.baseline_progress}/{analysis.baseline_required} ready
            </span>
          </div>
        </div>
      )}
    </section>
  );
}
