import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  scenarios: {
    steady_health_traffic: {
      executor: "ramping-vus",
      stages: [
        { duration: "15s", target: 10 },
        { duration: "30s", target: 10 },
        { duration: "15s", target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<250"],
    checks: ["rate>0.99"],
  },
};

const baseUrl = __ENV.BASE_URL || "http://localhost:8000";

export default function () {
  const live = http.get(`${baseUrl}/api/v1/health/live`);
  check(live, {
    "liveness is 200": (response) => response.status === 200,
    "liveness reports ok": (response) => response.json("status") === "ok",
  });

  const ready = http.get(`${baseUrl}/api/v1/health/ready`);
  check(ready, {
    "readiness is 200": (response) => response.status === 200,
    "database is ready": (response) => response.json("checks.database") === "ok",
    "redis is ready": (response) => response.json("checks.redis") === "ok",
  });
  sleep(1);
}
