import { desc, eq, sql } from "drizzle-orm";
import { WebSocket } from "ws";
import {
  db,
  sensorReadingsTable,
  simulatorEventsTable,
  type SensorReading,
} from "@workspace/db";
import {
  GetReadingHistoryResponseItem,
  GetSimulatorStatusResponse,
  SimulatorMode,
} from "@workspace/api-zod";
import { logger } from "./logger";

export type SimulatorModeValue = keyof typeof SimulatorMode;
export type SimulatorStatusValue =
  | "NORMAL"
  | "SIMULATING"
  | "STOPPED"
  | "ERROR";

type SensorReadingInput = {
  timestamp: Date;
  temperature: number;
  humidity: number;
  pressure: number;
};

type BroadcastMessage =
  | { type: "reading"; reading: SensorReading }
  | { type: "status"; status: Awaited<ReturnType<SkyguardSimulator["getStatus"]>> }
  | { type: "missing_data"; timestamp: string };

const modeMetadata: Record<
  Exclude<SimulatorModeValue, "NORMAL">,
  { faultType: string; affectedVariable: string }
> = {
  TEMPERATURE_SPIKE: {
    faultType: "TEMPERATURE_SPIKE",
    affectedVariable: "temperature",
  },
  TEMPERATURE_DROP: {
    faultType: "TEMPERATURE_DROP",
    affectedVariable: "temperature",
  },
  HUMIDITY_SPIKE: {
    faultType: "HUMIDITY_SPIKE",
    affectedVariable: "humidity",
  },
  PRESSURE_ANOMALY: {
    faultType: "PRESSURE_ANOMALY",
    affectedVariable: "pressure",
  },
  FROZEN_SENSOR: {
    faultType: "FROZEN_SENSOR",
    affectedVariable: "temperature, humidity, pressure",
  },
  GRADUAL_DRIFT: {
    faultType: "GRADUAL_DRIFT",
    affectedVariable: "temperature, humidity, pressure",
  },
  MISSING_DATA: {
    faultType: "MISSING_DATA",
    affectedVariable: "all",
  },
  MULTIVARIATE_INCONSISTENCY: {
    faultType: "MULTIVARIATE_INCONSISTENCY",
    affectedVariable: "temperature, humidity",
  },
};

const randomBetween = (min: number, max: number) =>
  min + Math.random() * (max - min);

const round = (value: number, digits = 2) => {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
};

const isFaultMode = (
  mode: SimulatorModeValue,
): mode is Exclude<SimulatorModeValue, "NORMAL"> => mode !== "NORMAL";

export function validateSensorReading(
  candidate: unknown,
): SensorReadingInput {
  if (!candidate || typeof candidate !== "object") {
    throw new Error("Sensor reading must be an object");
  }

  const reading = candidate as Record<string, unknown>;
  const timestamp = new Date(String(reading.timestamp));
  const numericFields = ["temperature", "humidity", "pressure"] as const;

  if (
    !reading.timestamp ||
    Number.isNaN(timestamp.getTime()) ||
    numericFields.some(
      (field) =>
        typeof reading[field] !== "number" || !Number.isFinite(reading[field]),
    )
  ) {
    throw new Error("Sensor reading has invalid required fields");
  }

  const temperature = reading.temperature as number;
  const humidity = reading.humidity as number;
  const pressure = reading.pressure as number;

  if (temperature < -80 || temperature > 70) {
    throw new Error("Temperature is outside physical sanity limits");
  }
  if (humidity < 0 || humidity > 100) {
    throw new Error("Humidity is outside physical sanity limits");
  }
  if (pressure < 850 || pressure > 1100) {
    throw new Error("Pressure is outside physical sanity limits");
  }

  return { timestamp, temperature, humidity, pressure };
}

export class SkyguardSimulator {
  private interval: NodeJS.Timeout | null = null;
  private mode: SimulatorModeValue = "NORMAL";
  private status: SimulatorStatusValue = "STOPPED";
  private lastGenerated: SensorReadingInput = {
    timestamp: new Date(),
    temperature: 24,
    humidity: 58,
    pressure: 1013,
  };
  private frozenReading: SensorReadingInput | null = null;
  private driftStep = 0;
  private missingTick = 0;
  private activeEventId: number | null = null;
  private activeEventLastTimestamp: Date | null = null;
  private readonly clients = new Set<WebSocket>();

  addClient(client: WebSocket) {
    this.clients.add(client);
    void this.sendStatus(client);
  }

  removeClient(client: WebSocket) {
    this.clients.delete(client);
  }

  getClientCount() {
    return this.clients.size;
  }

  async getHistory(limit = 60) {
    const rows = await db
      .select()
      .from(sensorReadingsTable)
      .orderBy(desc(sensorReadingsTable.timestamp))
      .limit(limit);
    return rows.reverse().map((row) => GetReadingHistoryResponseItem.parse(row));
  }

  async getLatest() {
    const rows = await db
      .select()
      .from(sensorReadingsTable)
      .orderBy(desc(sensorReadingsTable.timestamp))
      .limit(1);
    return rows[0] ? GetReadingHistoryResponseItem.parse(rows[0]) : null;
  }

  async getStatus() {
    const [countResult, latest] = await Promise.all([
      db
        .select({ count: sql<number>`count(*)` })
        .from(sensorReadingsTable),
      this.getLatest(),
    ]);

    return GetSimulatorStatusResponse.parse({
      status: this.status,
      mode: this.mode,
      connectedClients: this.clients.size,
      lastReadingAt: latest?.timestamp ?? null,
      readingsStored: Number(countResult[0]?.count ?? 0),
    });
  }

  async start() {
    if (this.interval) {
      return this.getStatus();
    }

    this.status = "SIMULATING";
    this.interval = setInterval(() => {
      void this.tick();
    }, 1000);
    await this.tick();
    return this.getStatus();
  }

  async stop() {
    if (this.interval) {
      clearInterval(this.interval);
      this.interval = null;
    }
    this.status = "STOPPED";
    await this.closeActiveEvent();
    const status = await this.getStatus();
    this.broadcast({ type: "status", status });
    return status;
  }

  async reset() {
    await this.stop();
    await db.delete(sensorReadingsTable);
    await db.delete(simulatorEventsTable);
    this.mode = "NORMAL";
    this.lastGenerated = {
      timestamp: new Date(),
      temperature: 24,
      humidity: 58,
      pressure: 1013,
    };
    this.frozenReading = null;
    this.driftStep = 0;
    this.missingTick = 0;
    this.activeEventId = null;
    const status = await this.getStatus();
    this.broadcast({ type: "status", status });
    return status;
  }

  async setMode(mode: SimulatorModeValue) {
    if (mode === this.mode) {
      return this.getStatus();
    }

    await this.closeActiveEvent();
    this.mode = mode;
    this.frozenReading = null;
    this.driftStep = 0;
    this.missingTick = 0;
    this.activeEventLastTimestamp = null;

    const status = await this.getStatus();
    this.broadcast({ type: "status", status });
    return status;
  }

  private async tick() {
    try {
      const timestamp = new Date();
      const nextReading = this.generateReading(timestamp);

      if (!nextReading) {
        await this.markActiveFaultTimestamp(timestamp);
        this.missingTick += 1;
        // MISSING_DATA is intentionally a telemetry outage: there is no sensor
        // row to insert. Keep the simulator visibly active by broadcasting a
        // missing-data heartbeat every tick rather than only every third tick.
        this.broadcast({
          type: "missing_data",
          timestamp: timestamp.toISOString(),
        });
        return;
      }

      const reading = await this.ingestReading(nextReading);
      this.missingTick = 0;
      this.broadcast({ type: "reading", reading });
    } catch (error) {
      this.status = "ERROR";
      logger.error({ err: error }, "SkyGuard simulator tick failed");
      const status = await this.getStatus();
      this.broadcast({ type: "status", status });
    }
  }

  async ingestReading(candidate: unknown) {
    const reading = validateSensorReading(candidate);
    const [stored] = await db
      .insert(sensorReadingsTable)
      .values(reading)
      .onConflictDoNothing({
        target: sensorReadingsTable.timestamp,
      })
      .returning();

    if (!stored) {
      throw new Error("Duplicate sensor reading timestamp");
    }

    this.lastGenerated = reading;
    await this.markActiveFaultTimestamp(reading.timestamp);
    return stored;
  }

  private generateReading(timestamp: Date): SensorReadingInput | null {
    const previous = this.lastGenerated;

    if (this.mode === "MISSING_DATA") {
      return null;
    }

    if (this.mode === "FROZEN_SENSOR") {
      this.frozenReading ??= { ...previous };
      return { ...this.frozenReading, timestamp };
    }

    if (this.mode === "TEMPERATURE_SPIKE") {
      return {
        timestamp,
        temperature: round(33 + randomBetween(-0.4, 0.4)),
        humidity: round(42 + randomBetween(-1.2, 1.2)),
        pressure: round(previous.pressure + randomBetween(-0.3, 0.3)),
      };
    }

    if (this.mode === "TEMPERATURE_DROP") {
      return {
        timestamp,
        temperature: round(13 + randomBetween(-0.4, 0.4)),
        humidity: round(77 + randomBetween(-1.2, 1.2)),
        pressure: round(previous.pressure + randomBetween(-0.3, 0.3)),
      };
    }

    if (this.mode === "HUMIDITY_SPIKE") {
      return {
        timestamp,
        temperature: round(previous.temperature + randomBetween(-0.15, 0.15)),
        humidity: round(94 + randomBetween(-1.5, 1.5)),
        pressure: round(previous.pressure + randomBetween(-0.3, 0.3)),
      };
    }

    if (this.mode === "PRESSURE_ANOMALY") {
      return {
        timestamp,
        temperature: round(previous.temperature + randomBetween(-0.15, 0.15)),
        humidity: round(previous.humidity + randomBetween(-0.4, 0.4)),
        pressure: round(1060 + randomBetween(-2, 2)),
      };
    }

    if (this.mode === "GRADUAL_DRIFT") {
      this.driftStep += 1;
      return {
        timestamp,
        temperature: round(24 + this.driftStep * 0.18 + randomBetween(-0.1, 0.1)),
        humidity: round(58 - this.driftStep * 0.24 + randomBetween(-0.2, 0.2)),
        pressure: round(1013 + this.driftStep * 0.42 + randomBetween(-0.2, 0.2)),
      };
    }

    if (this.mode === "MULTIVARIATE_INCONSISTENCY") {
      return {
        timestamp,
        temperature: round(34 + randomBetween(-0.4, 0.4)),
        humidity: round(94 + randomBetween(-1, 1)),
        pressure: round(previous.pressure + randomBetween(-0.3, 0.3)),
      };
    }

    const temperature = round(
      previous.temperature + randomBetween(-0.18, 0.18),
    );
    return {
      timestamp,
      temperature,
      humidity: round(
        Math.max(
          20,
          Math.min(90, 58 - (temperature - 24) * 1.35 + randomBetween(-0.7, 0.7)),
        ),
      ),
      pressure: round(previous.pressure + randomBetween(-0.25, 0.25)),
    };
  }

  private async closeActiveEvent() {
    if (this.activeEventId === null) {
      return;
    }

    await db
      .update(simulatorEventsTable)
      .set({
        endTimestamp: this.activeEventLastTimestamp ?? new Date(),
      })
      .where(eq(simulatorEventsTable.id, this.activeEventId));
    this.activeEventId = null;
    this.activeEventLastTimestamp = null;
  }

  private async markActiveFaultTimestamp(timestamp: Date) {
    if (!isFaultMode(this.mode)) {
      return;
    }

    if (this.activeEventId === null) {
      const metadata = modeMetadata[this.mode];
      const [event] = await db
        .insert(simulatorEventsTable)
        .values({
          faultType: metadata.faultType,
          affectedVariable: metadata.affectedVariable,
          startTimestamp: timestamp,
        })
        .returning({ id: simulatorEventsTable.id });
      this.activeEventId = event?.id ?? null;
    }

    this.activeEventLastTimestamp = timestamp;
  }

  private async sendStatus(client: WebSocket) {
    try {
      const status = await this.getStatus();
      if (client.readyState === WebSocket.OPEN) {
        client.send(JSON.stringify({ type: "status", status }));
      }
    } catch (error) {
      logger.warn({ err: error }, "Unable to send SkyGuard client status");
    }
  }

  private broadcast(message: BroadcastMessage) {
    const payload = JSON.stringify(message);
    for (const client of this.clients) {
      if (client.readyState === WebSocket.OPEN) {
        client.send(payload);
      }
    }
  }
}

export const skyguardSimulator = new SkyguardSimulator();