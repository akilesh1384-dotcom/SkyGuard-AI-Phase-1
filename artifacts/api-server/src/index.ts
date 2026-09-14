import { createServer } from "node:http";
import app from "./app";
import { logger } from "./lib/logger";
import { WebSocketServer } from "ws";
import { skyguardSimulator } from "./lib/skyguard";

const rawPort = process.env["PORT"];

if (!rawPort) {
  throw new Error(
    "PORT environment variable is required but was not provided.",
  );
}

const port = Number(rawPort);

if (Number.isNaN(port) || port <= 0) {
  throw new Error(`Invalid PORT value: "${rawPort}"`);
}

const server = createServer(app);
const webSocketServer = new WebSocketServer({ noServer: true });

webSocketServer.on("connection", (socket) => {
  skyguardSimulator.addClient(socket);
  socket.on("close", () => {
    skyguardSimulator.removeClient(socket);
  });
});

server.on("upgrade", (request, socket, head) => {
  const requestUrl = new URL(
    request.url ?? "/",
    `http://${request.headers.host ?? "localhost"}`,
  );
  if (requestUrl.pathname !== "/ws") {
    socket.destroy();
    return;
  }

  webSocketServer.handleUpgrade(request, socket, head, (client) => {
    webSocketServer.emit("connection", client, request);
  });
});

server.listen(port, async () => {
  logger.info({ port }, "Server listening");
  await skyguardSimulator.start();
});

server.on("error", (err) => {
  logger.error({ err }, "Error listening on port");
  process.exit(1);
});
