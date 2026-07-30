import { randomUUID } from "node:crypto";
import { Redis as RedisExtension } from "@hocuspocus/extension-redis";
import { Server } from "@hocuspocus/server";
import { Pool } from "pg";
import pino from "pino";
import { createClient } from "redis";
import * as Y from "yjs";
import { verifyCollaborationToken, type CollaborationClaims } from "./auth.js";
import { loadConfig } from "./config.js";
import { YjsPersistence } from "./persistence.js";
import { PresenceStore } from "./presence.js";

const config = loadConfig();
const logger = pino({ level: config.logLevel });
const pool = new Pool({ connectionString: config.databaseUrl });
const redis = createClient({ url: config.redisUrl });
redis.on("error", (error) => logger.error({ error }, "Redis client error"));
await redis.connect();

const persistence = new YjsPersistence(pool);
const presence = new PresenceStore(redis, config.presenceTtlSeconds);
const redisEndpoint = new URL(config.redisUrl);

type ConnectionContext = {
  claims: CollaborationClaims;
  connectionId: string;
  heartbeat?: ReturnType<typeof setInterval>;
};

const server = new Server({
  port: config.port,
  address: config.host,
  extensions: [
    new RedisExtension({
      host: redisEndpoint.hostname,
      port: Number(redisEndpoint.port || 6379),
      prefix: "forkroom:yjs",
      options: {
        ...(redisEndpoint.password ? { password: redisEndpoint.password } : {}),
        ...(redisEndpoint.pathname.length > 1
          ? { db: Number(redisEndpoint.pathname.slice(1)) }
          : {}),
      },
    }),
  ],
  async onAuthenticate({ token, documentName, requestHeaders, connectionConfig }) {
    const origin = requestHeaders.get("origin");
    if (!origin || !config.allowedOrigins.has(origin)) {
      throw new Error("WebSocket origin is not allowed");
    }
    if (!token) throw new Error("Collaboration token is required");
    const claims = await verifyCollaborationToken(token, config.jwtSecret, documentName);
    if (claims.permission === "read") connectionConfig.readOnly = true;
    const context: ConnectionContext = { claims, connectionId: randomUUID() };
    return context;
  },
  async onConnect({ documentName, context }) {
    const connection = context as ConnectionContext;
    await presence.join(documentName, connection.connectionId, connection.claims);
    connection.heartbeat = setInterval(
      () => void presence.touch(documentName, connection.connectionId),
      Math.max(1, Math.floor(config.presenceTtlSeconds / 2)) * 1000,
    );
    logger.info(
      {
        documentName,
        userId: connection.claims.sub,
        permission: connection.claims.permission,
      },
      "Collaboration client connected",
    );
  },
  async onLoadDocument({ documentName }) {
    const state = await persistence.fetch(documentName);
    const document = new Y.Doc();
    if (state) Y.applyUpdate(document, state);
    return document;
  },
  async onStoreDocument({ documentName, document }) {
    await persistence.store(documentName, Y.encodeStateAsUpdate(document));
  },
  async onDisconnect({ documentName, context }) {
    const connection = context as ConnectionContext | undefined;
    if (connection) {
      if (connection.heartbeat) clearInterval(connection.heartbeat);
      await presence.leave(documentName, connection.connectionId);
    }
  },
});

await server.listen();
logger.info({ host: config.host, port: config.port }, "Collaboration service listening");

const shutdown = async (signal: string): Promise<void> => {
  logger.info({ signal }, "Stopping collaboration service");
  await server.destroy();
  await Promise.all([pool.end(), redis.quit()]);
  process.exit(0);
};

process.on("SIGINT", () => void shutdown("SIGINT"));
process.on("SIGTERM", () => void shutdown("SIGTERM"));
