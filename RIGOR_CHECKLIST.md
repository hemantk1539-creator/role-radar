# 🛡️ DEPLOYMENT RIGOR CHECKLIST
*This file is a MANDATORY INTERLOCK. Skip = Violation.*

## 1. PRE-PUSH (Local)
- [ ] **Full-Pass Trace:** Trace every modified variable through the entire file.
- [ ] **Contradiction Audit:** Check new logic against "Live System Configuration" in `PROJECT_STATE.md`.
- [ ] **Adversarial Test:** Attempt to break the code with extreme inputs (e.g., empty API responses, 100-year-old dates).
- [ ] **Sanity Script:** Run `master_verification_vX.py` and DOCUMENT output.

## 2. POST-PUSH (Server)
- [ ] **Integrity Scan:** `git ls-tree` to verify only clinical files exist on server.
- [ ] **Post-Push Audit:** Cross-reference live `config.yaml` against "Master Directive."
- [ ] **Live Logic Test:** Run a 1-city execution check on the server (if possible) or via logic simulation.
