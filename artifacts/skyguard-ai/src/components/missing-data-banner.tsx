import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { RadioTower, TriangleAlert } from 'lucide-react';

type SimulatorStatus = {
  status: string;
  mode: string;
  lastReadingAt?: string | null;
  readingsStored?: number;
};

type GroundTruthEvent = {
  fault_type: string;
  affected_variable: string;
  start_timestamp: string;
  end_timestamp: string | null;
};

function formatDuration(seconds: number) {
  const safe = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(safe / 60);
  const remaining = safe % 60;
  return minutes > 0 ? `${minutes}m ${remaining}s` : `${remaining}s`;
}

export default function MissingDataBanner() {
  const [status, setStatus] = useState<SimulatorStatus | null>(null);
  const [event, setEvent] = useState<GroundTruthEvent | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [mountNode, setMountNode] = useState<HTMLElement | null>(null);

  useEffect(() => {
    let disposed = false;
    let observer: MutationObserver | undefined;

    const findSlot = () => {
      if (disposed || mountNode) return;
      const statusSection = document.querySelector('[data-testid="section-status-overview"]');
      if (!statusSection || !statusSection.parentElement) return;
      const slot = document.createElement('div');
      slot.className = 'w-full';
      statusSection.insertAdjacentElement('afterend', slot);
      setMountNode(slot);
    };

    findSlot();
    observer = new MutationObserver(findSlot);
    observer.observe(document.body, { childList: true, subtree: true });

    return () => {
      disposed = true;
      observer?.disconnect();
      if (mountNode?.parentElement) mountNode.parentElement.removeChild(mountNode);
    };
  }, [mountNode]);

  useEffect(() => {
    let disposed = false;
    let timer: number | undefined;

    const load = async () => {
      try {
        const [statusResponse, eventsResponse] = await Promise.all([
          fetch('/api/status', { cache: 'no-store' }),
          fetch('/api/ml/ground-truth', { cache: 'no-store' }),
        ]);
        if (!statusResponse.ok || !eventsResponse.ok) throw new Error('status fetch failed');

        const nextStatus = (await statusResponse.json()) as SimulatorStatus;
        const events = (await eventsResponse.json()) as GroundTruthEvent[];
        const latest = events
          .filter((item) => item.fault_type === 'MISSING_DATA')
          .sort((a, b) => new Date(b.start_timestamp).getTime() - new Date(a.start_timestamp).getTime())[0] ?? null;

        if (!disposed) {
          setStatus(nextStatus);
          setEvent(latest?.end_timestamp ? null : latest);
          setNow(Date.now());
        }
      } catch {
        // The main dashboard already exposes connectivity/service state.
      } finally {
        if (!disposed) timer = window.setTimeout(load, 1000);
      }
    };

    load();
    return () => {
      disposed = true;
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    if (!event) return;
    const interval = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [event]);

  if (!mountNode || !status || status.status !== 'SIMULATING' || status.mode !== 'MISSING_DATA' || !event) return null;

  const duration = (now - new Date(event.start_timestamp).getTime()) / 1000;

  return createPortal(
    <section
      className="mx-auto mb-5 flex w-full items-center gap-4 rounded-[1rem] border border-[#f0ad4e]/55 bg-[#fff5df] px-4 py-3 text-[#754c10] shadow-sm"
      role="status"
      aria-live="polite"
      data-testid="banner-missing-data"
    >
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#f7c76f] text-[#5d3d0d]">
        <RadioTower className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2 text-sm font-bold">
          <span>Telemetry interrupted</span>
          <span className="rounded-full bg-[#f7c76f]/45 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em]">Missing data</span>
        </div>
        <div className="mt-1 text-xs text-[#8b6324]">
          No new sensor readings are being received. Last valid reading: {status.lastReadingAt ? new Date(status.lastReadingAt).toLocaleTimeString('en-IN') : 'unknown'}.
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2 font-data text-sm font-bold text-[#754c10]">
        <TriangleAlert className="h-4 w-4" />
        {formatDuration(duration)}
      </div>
    </section>,
    mountNode,
  );
}
