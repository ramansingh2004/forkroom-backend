export type CollaborationConfig = {
  host: string;
  port: number;
  allowedOrigins: Set<string>;
  jwtSecret: Uint8Array;
  databaseUrl: string;
  redisUrl: string;
  presenceTtlSeconds: number;
  logLevel: string;
};

const required = (name: string): string => {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
};

const positiveInteger = (name: string, fallback: number): number => {
  const value = Number(process.env[name] ?? fallback);
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new Error(`${name} must be a positive integer`);
  }
  return value;
};

export const loadConfig = (): CollaborationConfig => ({
  host: process.env.COLLABORATION_HOST ?? "0.0.0.0",
  port: positiveInteger("COLLABORATION_PORT", 1234),
  allowedOrigins: new Set(
    (process.env.COLLABORATION_ALLOWED_ORIGINS ?? "http://localhost:3000")
      .split(",")
      .map((origin) => origin.trim())
      .filter(Boolean),
  ),
  jwtSecret: new TextEncoder().encode(required("JWT_COLLABORATION_SECRET")),
  databaseUrl: required("DATABASE_URL"),
  redisUrl: required("REDIS_URL"),
  presenceTtlSeconds: positiveInteger("PRESENCE_TTL_SECONDS", 60),
  logLevel: process.env.LOG_LEVEL ?? "info",
});
