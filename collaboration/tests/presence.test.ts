import { describe, expect, it, vi } from "vitest";
import type { CollaborationClaims } from "../src/auth.js";
import { PresenceStore } from "../src/presence.js";

const claims = {
  sub: "user-id",
  display_name: "Raman Singh",
  permission: "write",
} as CollaborationClaims;

describe("PresenceStore", () => {
  it("stores expiring presence and removes it on disconnect", async () => {
    const redis = {
      set: vi.fn().mockResolvedValue("OK"),
      del: vi.fn().mockResolvedValue(1),
      expire: vi.fn().mockResolvedValue(true),
    };
    const store = new PresenceStore(redis as never, 60);
    await store.join("proposal:123", "connection-id", claims);
    expect(redis.set).toHaveBeenCalledWith(
      "collaboration:presence:proposal:123:connection-id",
      expect.stringContaining('"userId":"user-id"'),
      { EX: 60 },
    );
    await store.touch("proposal:123", "connection-id");
    expect(redis.expire).toHaveBeenCalledWith(
      "collaboration:presence:proposal:123:connection-id",
      60,
    );
    await store.leave("proposal:123", "connection-id");
    expect(redis.del).toHaveBeenCalledOnce();
  });
});
