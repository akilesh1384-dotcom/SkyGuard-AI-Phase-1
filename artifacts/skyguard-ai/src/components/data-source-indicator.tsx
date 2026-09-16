import { Radio } from 'lucide-react';
import { getDataSource, getDataSourceLabel } from './data-source';

export default function DataSourceIndicator() {
  const source = getDataSource();
  const label = getDataSourceLabel(source);
  const isPhysical = source === 'PHYSICAL_AWS';

  return (
    <div
      className="fixed right-4 top-[4.2rem] z-50 flex items-center gap-2 rounded-xl border border-[#315d65] bg-[#123541]/95 px-3 py-2 text-[#eef8f5] shadow-lg backdrop-blur"
      data-testid="data-source-indicator"
      title={isPhysical ? 'Input adapter configured for the physical AWS prototype.' : 'Running without physical hardware. Simulator data is used through the same backend interface.'}
    >
      <Radio className="h-3.5 w-3.5 text-[#45d5c1]" />
      <span className="text-[9px] font-bold uppercase tracking-[0.14em] text-[#8db5b7]">Input</span>
      <span className="text-xs font-semibold">{label}</span>
    </div>
  );
}
