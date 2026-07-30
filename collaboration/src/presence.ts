import type { RedisClientType } from "redis";
import type { CollaborationClaims } from "./auth.js";

export type PresenceRecord = {
  userId: string;
  displayName: string;
  permission: "read" | "write";
  connectedAt: string;
};

export class PresenceStore {
  public constructor(
    private readonly redis: RedisClientType,
    private readonly ttlSeconds: number,
  ) {}

  private key(documentName: string, connectionId: string): string {
    return `collaboration:presence:${documentName}:${connectionId}`;
  }

  public async join(
    documentName: string,
    connectionId: string,
    claims: CollaborationClaims,
  ): Promise<void> {
    const record: PresenceRecord = {
      userId: claims.sub,
      displayName: claims.display_name,
      permission: claims.permission,
      connectedAt: new Date().toISOString(),
    };
    await this.redis.set(this.key(documentName, connectionId), JSON.stringify(record), {
      EX: this.ttlSeconds,
    });
  }

  public async leave(documentName: string, connectionId: string): Promise<void> {
    await this.redis.del(this.key(documentName, connectionId));
  }

  public async touch(documentName: string, connectionId: string): Promise<void> {
    await this.redis.expire(this.key(documentName, connectionId), this.ttlSeconds);
  }
}
