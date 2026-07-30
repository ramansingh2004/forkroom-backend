import { jwtVerify, type JWTPayload } from "jose";

export type CollaborationPermission = "read" | "write";

export type CollaborationClaims = JWTPayload & {
  sub: string;
  type: "collaboration";
  workspace_id: string;
  decision_id: string;
  proposal_id: string;
  document_name: string;
  permission: CollaborationPermission;
  display_name: string;
};

const hasClaims = (payload: JWTPayload): payload is CollaborationClaims =>
  typeof payload.sub === "string" &&
  payload.type === "collaboration" &&
  typeof payload.workspace_id === "string" &&
  typeof payload.decision_id === "string" &&
  typeof payload.proposal_id === "string" &&
  typeof payload.document_name === "string" &&
  (payload.permission === "read" || payload.permission === "write") &&
  typeof payload.display_name === "string";

export const verifyCollaborationToken = async (
  token: string,
  secret: Uint8Array,
  requestedDocument: string,
): Promise<CollaborationClaims> => {
  const { payload } = await jwtVerify(token, secret, {
    algorithms: ["HS256"],
    audience: "forkroom-collaboration",
    issuer: "forkroom-api",
    requiredClaims: [
      "sub",
      "type",
      "jti",
      "workspace_id",
      "decision_id",
      "proposal_id",
      "document_name",
      "permission",
      "iat",
      "exp",
    ],
  });
  if (!hasClaims(payload) || payload.document_name !== requestedDocument) {
    throw new Error("Invalid collaboration token claims");
  }
  return payload;
};
