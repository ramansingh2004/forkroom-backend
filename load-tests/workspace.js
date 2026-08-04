import http from "k6/http";
import { check, fail, sleep } from "k6";

export const options = {
  scenarios: {
    workspace_reads: {
      executor: "constant-arrival-rate",
      rate: 20,
      timeUnit: "1s",
      duration: "1m",
      preAllocatedVUs: 10,
      maxVUs: 50,
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.02"],
    http_req_duration: ["p(95)<500", "p(99)<1000"],
  },
};

const baseUrl = __ENV.BASE_URL || "http://localhost:8000";
const token = __ENV.ACCESS_TOKEN;
const workspaceId = __ENV.WORKSPACE_ID;

export function setup() {
  if (!token || !workspaceId) {
    fail("ACCESS_TOKEN and WORKSPACE_ID are required");
  }
}

export default function () {
  const params = { headers: { Authorization: `Bearer ${token}` } };
  const decisions = http.get(
    `${baseUrl}/api/v1/workspaces/${workspaceId}/decisions`,
    params,
  );
  check(decisions, { "decision list succeeds": (response) => response.status === 200 });

  const search = http.get(
    `${baseUrl}/api/v1/workspaces/${workspaceId}/search?q=architecture&limit=20&offset=0`,
    params,
  );
  check(search, { "search succeeds": (response) => response.status === 200 });
  sleep(0.2);
}
