import { describe, expect, it, vi } from "vitest";
import { YjsPersistence } from "../src/persistence.js";

describe("YjsPersistence", () => {
  it("loads binary document state", async () => {
    const query = vi.fn().mockResolvedValue({ rows: [{ ydoc_state: Buffer.from([1, 2]) }] });
    const persistence = new YjsPersistence({ query } as never);
    await expect(persistence.fetch("proposal:123")).resolves.toEqual(
      new Uint8Array([1, 2]),
    );
  });

  it("increments the version when storing a state", async () => {
    const query = vi.fn().mockResolvedValue({ rowCount: 1 });
    const persistence = new YjsPersistence({ query } as never);
    await persistence.store("proposal:123", new Uint8Array([3, 4]));
    expect(query).toHaveBeenCalledWith(expect.stringContaining("state_version + 1"), [
      "proposal:123",
      Buffer.from([3, 4]),
    ]);
  });

  it("rejects an unknown document", async () => {
    const query = vi.fn().mockResolvedValue({ rowCount: 0 });
    const persistence = new YjsPersistence({ query } as never);
    await expect(
      persistence.store("proposal:missing", new Uint8Array([1])),
    ).rejects.toThrow("Unknown collaboration document");
  });
});
