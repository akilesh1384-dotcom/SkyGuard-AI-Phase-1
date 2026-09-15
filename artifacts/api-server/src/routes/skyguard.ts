import { asc } from "drizzle-orm";
import { Router, type IRouter } from "express";
import {
  GetLatestReadingResponse,
  GetMlGroundTruthResponse,
  GetMlReadingsQueryParams,
  GetMlReadingsResponse,
  GetReadingHistoryQueryParams,
  GetReadingHistoryResponse,
  GetSimulatorStatusResponse,
  SetSimulatorModeBody,
  SetSimulatorModeResponse,
  StartSimulatorResponse,
  StopSimulatorResponse,
  ResetSimulatorResponse,
  SimulatorMode,
} from "@workspace/api-zod";
import {
  db,
  sensorReadingsTable,
  simulatorEventsTable,
} from "@workspace/db";
import {
  skyguardSimulator,
  type SimulatorModeValue,
} from "../lib/skyguard";

const router: IRouter = Router();

router.get("/latest", async (_req, res): Promise<void> => {
  const latest = await skyguardSimulator.getLatest();
  res.json(GetLatestReadingResponse.parse(latest));
});

router.get("/ml/readings", async (req, res): Promise<void> => {
  const query = GetMlReadingsQueryParams.safeParse(req.query);
  if (!query.success) {
    res.status(400).json({ error: query.error.message });
    return;
  }

  const baseQuery = db
    .select({
      timestamp: sensorReadingsTable.timestamp,
      temperature: sensorReadingsTable.temperature,
      humidity: sensorReadingsTable.humidity,
      pressure: sensorReadingsTable.pressure,
    })
    .from(sensorReadingsTable)
    .orderBy(asc(sensorReadingsTable.timestamp));

  const readings =
    query.data.limit === undefined
      ? await baseQuery
      : await baseQuery.limit(query.data.limit);

  res.json(GetMlReadingsResponse.parse(readings));
});

router.get("/ml/ground-truth", async (_req, res): Promise<void> => {
  const events = await db
    .select({
      fault_type: simulatorEventsTable.faultType,
      affected_variable: simulatorEventsTable.affectedVariable,
      start_timestamp: simulatorEventsTable.startTimestamp,
      end_timestamp: simulatorEventsTable.endTimestamp,
    })
    .from(simulatorEventsTable)
    .orderBy(asc(simulatorEventsTable.startTimestamp));

  res.json(GetMlGroundTruthResponse.parse(events));
});

router.get("/history", async (req, res): Promise<void> => {
  const query = GetReadingHistoryQueryParams.safeParse(req.query);
  if (!query.success) {
    res.status(400).json({ error: query.error.message });
    return;
  }

  const history = await skyguardSimulator.getHistory(query.data.limit);
  res.json(GetReadingHistoryResponse.parse(history));
});

router.get("/status", async (_req, res): Promise<void> => {
  res.json(GetSimulatorStatusResponse.parse(await skyguardSimulator.getStatus()));
});

router.post("/simulator/start", async (_req, res): Promise<void> => {
  res.json(StartSimulatorResponse.parse(await skyguardSimulator.start()));
});

router.post("/simulator/stop", async (_req, res): Promise<void> => {
  res.json(StopSimulatorResponse.parse(await skyguardSimulator.stop()));
});

router.post("/simulator/reset", async (_req, res): Promise<void> => {
  res.json(ResetSimulatorResponse.parse(await skyguardSimulator.reset()));
});

router.post("/simulator/mode", async (req, res): Promise<void> => {
  const body = SetSimulatorModeBody.safeParse(req.body);
  if (!body.success) {
    res.status(400).json({ error: body.error.message });
    return;
  }

  const mode = body.data.mode as SimulatorModeValue;
  if (!Object.values(SimulatorMode).includes(mode)) {
    res.status(400).json({ error: "Invalid simulator mode" });
    return;
  }

  res.json(
    SetSimulatorModeResponse.parse(await skyguardSimulator.setMode(mode)),
  );
});

export default router;