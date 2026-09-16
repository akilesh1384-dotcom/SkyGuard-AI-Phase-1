import { useState } from 'react';

export type SensorMode = 'FULL' | 'AWS';
const STORAGE_KEY = 'skyguard-sensor-mode';

export function getSensorMode(): SensorMode {
  if (typeof window === 'undefined') return 'FULL';
  return window.localStorage.getItem(STORAGE_KEY) === 'AWS' ? 'AWS' : 'FULL';
}

export default function SensorModeControl() {
  const [mode, setMode] = useState<SensorMode>(getSensorMode);

  const changeMode = (next: SensorMode) => {
    setMode(next);
    window.localStorage.setItem(STORAGE_KEY, next);
    window.dispatchEvent(new CustomEvent('skyguard-sensor-mode-change', { detail: next }));
    window.setTimeout(() => window.location.reload(), 150);
  };

  return (
    <div className="fixed right-4 top-4 z-50 flex items-center gap-2 rounded-xl border border-[#315d65] bg-[#123541]/95 px-3 py-2 text-[#eef8f5] shadow-lg backdrop-blur" data-testid="sensor-mode-control">
      <span className="text-[9px] font-bold uppercase tracking-[0.14em] text-[#8db5b7]">Sensor mode</span>
      <select value={mode} onChange={(event) => changeMode(event.target.value as SensorMode)} className="rounded-lg border border-[#407883] bg-[#173d48] px-2 py-1 text-xs font-semibold outline-none">
        <option value="FULL">FULL · T/RH/P</option>
        <option value="AWS">AWS · T/RH</option>
      </select>
    </div>
  );
}
