import { useEffect, useState } from 'react';
import { Radio, Wifi, WifiOff } from 'lucide-react';

interface PhysicalDevice {
  deviceId: string;
  rssi: number | null;
  lastSeen: string;
  online: boolean;
}

interface DeviceStatusResponse {
  source: 'PHYSICAL_AWS';
  device: PhysicalDevice | null;
}

export default function PhysicalDeviceStatus() {
  const [device, setDevice] = useState<PhysicalDevice | null>(null);

  useEffect(() => {
    let disposed = false;

    const load = async () => {
      try {
        const response = await fetch('/api/physical/device-status');
        if (!response.ok) return;
        const payload = (await response.json()) as DeviceStatusResponse;
        if (!disposed) setDevice(payload.device);
      } catch {
        // Keep the last known device state on transient API failures.
      }
    };

    void load();
    const timer = window.setInterval(load, 3000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, []);

  const ageSeconds = device ? Math.max(0, Math.floor((Date.now() - new Date(device.lastSeen).getTime()) / 1000)) : null;
  const online = device?.online === true && ageSeconds !== null && ageSeconds <= 15;

  return (
    <section className="sg-panel rounded-[1.15rem] p-5" data-testid="physical-device-status">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.17em] text-muted-foreground">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10 text-foreground">
              <Radio className="h-4 w-4" />
            </span>
            Physical device
          </div>
          <div className="mt-3 font-display text-lg font-semibold text-foreground">
            {device?.deviceId ?? 'Waiting for ESP32'}
          </div>
        </div>
        <div className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.12em] ${online ? 'border-primary/30 bg-primary/10 text-primary' : 'border-border bg-secondary/40 text-muted-foreground'}`}>
          {online ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}
          {online ? 'Online' : 'Offline'}
        </div>
      </div>
      <div className="mt-4 grid gap-3 border-t border-border/70 pt-4 sm:grid-cols-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Wi-Fi RSSI</div>
          <div className="mt-1 font-data text-sm font-semibold text-foreground">{device?.rssi == null ? '—' : `${device.rssi} dBm`}</div>
        </div>
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Last seen</div>
          <div className="mt-1 font-data text-sm font-semibold text-foreground">{ageSeconds == null ? '—' : `${ageSeconds}s ago`}</div>
        </div>
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Input</div>
          <div className="mt-1 font-data text-sm font-semibold text-foreground">ESP32 + DHT11</div>
        </div>
      </div>
    </section>
  );
}
