import { useEffect, useState } from 'react';
import { WifiOff } from 'lucide-react';

type SimulatorStatus = {
  status: string;
  mode: string;
  lastReadingAt?: string | null;
};

type GroundTruthEvent = {
  fault_type: string;
  start_timestamp: string;
  end_timestamp: string | null;
};

function formatDuration(seconds: number) {
  const safe = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(safe / 60);
  return minutes > 0 ? `${minutes}m ${safe % 60}s` : `${safe}s`;
}

export default function MissingDataBanner() {
  const [since, setSince] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    let stopped = false;
    let timer: number | undefined;

    const check = async () => {
      try {
        const [statusResponse, eventsResponse] = await Promise.all([
          fetch('/api/status', { cache: 'no-store' }),
          fetch('/api/ml/ground-truth', { cache: 'no-store' }),
        ]);
        if (!statusResponse.ok || !eventsResponse.ok) throw new Error('status unavailable');

        const status = (await statusResponse.json()) as SimulatorStatus;
        const events = (await eventsResponse.json()) as GroundTruthEvent[];
        const activeEvent = events
          .filter((event) => event.fault_type === 'MISSING_DATA' && !event.end_timestamp)
          .sort((a, b) => new Date(b.start_timestamp).getTime() - new Date(a.start_timestamp).getTime())[0];

        if (!stopped) {
          setSince(status.status === 'SIMULATING' && status.mode === 'MISSING_DATA' && activeEvent ? activeEvent.start_timestamp : null);
          setNow(Date.now());
        }
      } catch {
        // Do not disturb the main dashboard if the optional banner check fails.
      } finally {
        if (!stopped) timer = window.setTimeout(check, 1000);
      }
    };

    check();
    return () => {
      stopped = true;
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    if (!since) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [since]);

  if (!since) return null;

  const duration = (now - new Date(since).getTime()) / 1000;

  return (
    <div className="pointer-events-none fixed inset-x-0 top-3 z-[100] flex justify-center px-4" data-testid="banner-missing-data">
      <section className="pointer-events-auto flex w-full max-w-4xl items-center gap-4 rounded-2xl border border-[#f0ad4e]/70 bg-[#fff5df] px-4 py-3 text-[#754c10] shadow-lg">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#f7c76f] text-[#5d3d0d]"><WifiOff className="h-4 w-4" /></div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 text-sm font-bold">
            <span>Telemetry interrupted</span>
            <span className="rounded-full bg-[#f7c76f]/50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em]">Missing data</span>
          </div>
          <p className="mt-1 text-xs text-[#8b6324]">No new sensor readings are being received. The last valid reading remains on screen for reference.</p>
        </div>
        <div className="shrink-0 text-right font-data text-sm font-bold"><div>{formatDuration(duration)}</div><div className="text-[9px] uppercase tracking-[0.12em]">outage</div></div>
      </section>
    </div>
  );
}
