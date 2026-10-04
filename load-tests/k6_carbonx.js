// k6 load test for the CarbonX API (marketplace read + calculator paths).
// Run: k6 run -e BASE=http://localhost:8000 load-tests/k6_carbonx.js
import http from "k6/http";
import { check, sleep } from "k6";

const BASE = __ENV.BASE || "http://localhost:8000";

export const options = {
  stages: [
    { duration: "30s", target: 20 },
    { duration: "1m", target: 50 },
    { duration: "30s", target: 0 },
  ],
  thresholds: {
    http_req_duration: ["p(95)<800", "p(99)<2000"],
    http_req_failed: ["rate<0.01"],
  },
};

export default function () {
  const listings = http.get(`${BASE}/marketplace/listings?limit=20`);
  check(listings, { "listings 200": (r) => r.status === 200 });

  const calc = http.post(`${BASE}/farms/earnings-calculator`,
    JSON.stringify({ area_hectares: 2.0, crop: "Rice", ndvi: 0.7 }),
    { headers: { "Content-Type": "application/json" } });
  check(calc, { "calc 200": (r) => r.status === 200 });

  sleep(1);
}
