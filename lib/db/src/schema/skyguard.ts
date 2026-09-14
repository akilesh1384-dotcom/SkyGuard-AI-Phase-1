import {
  doublePrecision,
  pgTable,
  serial,
  text,
  timestamp,
  uniqueIndex,
} from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const sensorReadingsTable = pgTable(
  "skyguard_sensor_readings",
  {
    id: serial("id").primaryKey(),
    timestamp: timestamp("timestamp", { withTimezone: true }).notNull(),
    temperature: doublePrecision("temperature").notNull(),
    humidity: doublePrecision("humidity").notNull(),
    pressure: doublePrecision("pressure").notNull(),
  },
  (table) => ({
    timestampUnique: uniqueIndex("skyguard_sensor_readings_timestamp_unique").on(
      table.timestamp,
    ),
  }),
);

export const simulatorEventsTable = pgTable("skyguard_simulator_events", {
  id: serial("id").primaryKey(),
  faultType: text("fault_type").notNull(),
  affectedVariable: text("affected_variable").notNull(),
  startTimestamp: timestamp("start_timestamp", {
    withTimezone: true,
  }).notNull(),
  endTimestamp: timestamp("end_timestamp", { withTimezone: true }),
});

export const insertSensorReadingSchema = createInsertSchema(
  sensorReadingsTable,
).omit({ id: true });
export type InsertSensorReading = z.infer<typeof insertSensorReadingSchema>;
export type SensorReading = typeof sensorReadingsTable.$inferSelect;

export const insertSimulatorEventSchema = createInsertSchema(
  simulatorEventsTable,
).omit({ id: true });
export type InsertSimulatorEvent = z.infer<typeof insertSimulatorEventSchema>;
export type SimulatorEvent = typeof simulatorEventsTable.$inferSelect;