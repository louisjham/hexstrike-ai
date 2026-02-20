---
description: US Masscan Vuln tool enhancement log — completed changes and next steps
last_updated: 2026-02-20T00:48:00-06:00
---

# US Masscan Vuln — Enhancement Log

## Status: ✅ ALL CODE CHANGES COMPLETE

All planned enhancements (P1–P13) have been applied to both files.

---

## Files Modified

### 1. `hexstrike_mcp.py` (MCP Client)

**Lines affected: ~442–562**

| Change | Detail |
|--------|--------|
| `application` parameter added | New first param on `us_masscan_vuln()` — `application: str = ""` |
| `output_dir` default fixed | `/tmp/us_masscan_vuln` → `./output/us_masscan_vuln` (Windows compat) |
| Docstring rewritten | Added `WHEN TO USE`, `DO NOT USE WHEN`, `APPLICATION / SERVICE HUNTING` sections |
| Args docs streamlined | Concise descriptions, `application` marked as PREFERRED over manual port/filter |
| `data` dict updated | Now includes `"application": application` in the POST body |
| Supported apps listed | ollama, jupyter, gradio, redis, elasticsearch, couchdb, minio, mongodb, memcached, etcd, k8s-api, docker-api, prometheus, grafana, openwebui, kibana, jenkins, gitlab, rabbitmq, consul |

### 2. `hexstrike_server.py` (Server)

**Lines affected: ~12108–12580**

| Change | Detail |
|--------|--------|
| `APP_PORT_REGISTRY` added (~line 12108) | 20-app dict mapping name → `{port, filter, fp_path, fp_match}` |
| `run_masscan_on_cidrs` rewritten (~line 12208) | Batch CIDRs via temp file (`-iL`), fallback to per-CIDR on failure. Returns `unconfirmed_ips` for hosts with open port but no banner match when `service_filter` is set |
| `check_host_exposures` enhanced (~line 12330) | HTTP probes ALL ports (not just 80/443/8080). Added `application` param for fingerprint checks via `APP_PORT_REGISTRY` endpoints |
| Endpoint `us_masscan_vuln()` rewritten (~line 12453) | Application auto-resolution from registry. Computes `total_ips_in_scope` estimate. Generates `top_findings`, `insight_aggregation` (Counter-based), `recommended_next_steps`, dynamic `confidence` (0.5–0.98). `insights` capped at 100 entries. `output_dir` default fixed |

#### New Report Fields
```json
{
  "application": "ollama | (none)",
  "hosts_checked": 1234567,       // estimated IPs in scope
  "hosts_open": 42,               // with port open
  "hosts_unconfirmed": 15,        // open but service unverified
  "top_findings": ["..."],        // most actionable summary lines
  "insight_aggregation": [        // grouped by title + count
    {"title": "Missing HSTS header", "count": 38, "severity": "medium"}
  ],
  "recommended_next_steps": ["..."],
  "confidence": 0.85              // dynamic
}
```

---

## What Was NOT Changed

- **Pre-existing lint errors**: Hundreds of Pyre2 type inference warnings exist across both files (lines 3072, 3137, 9897, etc.). These are NOT related to our changes and were present before this session.
- **Other tools**: No other MCP tools were modified.
- **Tests**: No test files were created or modified.

---

## Next Steps (Not Yet Done)

### Priority 1 — Testing
1. **Start the server** and verify it boots without import errors
   ```bash
   python hexstrike_server.py
   ```
2. **Smoke-test the endpoint** with curl or Postman:
   ```bash
   # Application-based call
   curl -X POST http://localhost:5000/api/tools/us-masscan-vuln \
     -H "Content-Type: application/json" \
     -d '{"application": "ollama", "max_cidrs": 5, "intensity": "low"}'

   # Manual port call (should still work as before)
   curl -X POST http://localhost:5000/api/tools/us-masscan-vuln \
     -H "Content-Type: application/json" \
     -d '{"port": 80, "max_cidrs": 5, "intensity": "low"}'
   ```
3. **Verify MCP client** registers the tool and exposes the `application` param in the schema

### Priority 2 — Refinements (Optional)
4. **Add more apps** to `APP_PORT_REGISTRY` as needed (e.g., Airflow, MLflow, Argo CD, Harbor)
5. **Add unconfirmed host probing** — Phase 3 currently only checks `discovered_ips` (confirmed). Could optionally probe `unconfirmed_ips` too for deeper coverage
6. **Rate-limit HTTP probes** — if discovered_ips is large (100+), consider threading/async with concurrency cap
7. **Add `--exclude` support** — allow excluding specific CIDRs from scan scope
8. **Persist scan state** — write intermediate state after each phase so a crashed scan can resume

### Priority 3 — Lint Cleanup (Low Priority)
9. The pre-existing Pyre2 lint errors across both files are type annotation issues in unrelated code. They can be batch-fixed separately but are not blocking.

---

## Quick Reference: Key Line Numbers

| Item | File | Approx Lines |
|------|------|--------------|
| `us_masscan_vuln` MCP tool def | `hexstrike_mcp.py` | 442–565 |
| `APP_PORT_REGISTRY` | `hexstrike_server.py` | 12108–12132 |
| `BANNER_VULN_SIGNATURES` | `hexstrike_server.py` | 12134–12154 |
| `run_masscan_on_cidrs` | `hexstrike_server.py` | 12208–12320 |
| `check_host_exposures` | `hexstrike_server.py` | 12330–12450 |
| `us_masscan_vuln` endpoint | `hexstrike_server.py` | 12453–12580 |
