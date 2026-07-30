import { SignJWT } from "jose";
import { describe, expect, it } from "vitest";
import { verifyCollaborationToken } from "../src/auth.js";

const secret = new TextEncoder().encode("a-collaboration-secret-that-is-long");

const tokenFor = async (
  documentName: string,
  permission: "read" | "write" = "write",
): Promise<string> =>
  new SignJWT({
    type: "collaboration",
    workspace_id: "workspace-id",
    decision_id: "decision-id",
    proposal_id: "proposal-id",
    document_name: documentName,
    permission,
    display_name: "Raman Singh",
  })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuer("forkroom-api")
    .setAudience("forkroom-collaboration")
    .setSubject("user-id")
    .setJti("token-id")
    .setIssuedAt()
    .setExpirationTime("5m")
    .sign(secret);

describe("verifyCollaborationToken", () => {
  it("accepts a valid document-scoped token", async () => {
    const token = await tokenFor("proposal:123");
    const claims = await verifyCollaborationToken(token, secret, "proposal:123");
    expect(claims.permission).toBe("write");
    expect(claims.sub).toBe("user-id");
  });

  it("rejects reuse for another document", async () => {
    const token = await tokenFor("proposal:123");
    await expect(
      verifyCollaborationToken(token, secret, "proposal:456"),
    ).rejects.toThrow("Invalid collaboration token claims");
  });
});
