# Next Actions

Ranked by value, risk, and dependency.

## Immediate (P0)

1. **HF-0002** — Create SPEC/ acceptance test validation script
   - Value: High (enables automated verification)
   - Risk: Low
   - Dependency: None

2. **HF-0003** — Create hyperflow CLI (`hyperflow` command)
   - Value: High (enables `hyperflow new`, `hyperflow assign`, `hyperflow receipt`)
   - Risk: Medium
   - Dependency: None

3. **HF-0004** — Create Xcode build capture script
   - Value: High (Apple platform verification)
   - Risk: Low
   - Dependency: Xcode project exists

## Short-term (P1)

4. **HF-0005** — Create GitHub Actions CI with receipt validation
   - Value: Medium (automated CI)
   - Risk: Low
   - Dependency: HF-0002

5. **HF-0006** — Create valuation packet generator
   - Value: High (financeable artifact layer)
   - Risk: Low
   - Dependency: HF-0003

6. **HF-0007** — Create agent prompt templates for ChatGPT/Claude/Codex
   - Value: Medium (standardized agent routing)
   - Risk: Low
   - Dependency: None

## Medium-term (P2)

7. **HF-0008** — MCP server integration with Windsurf Cascade
   - Value: Medium (IDE-native tool bridge)
   - Risk: Medium
   - Dependency: HF-0003

8. **HF-0009** — Automated failure classification from build logs
   - Value: Medium (reduces manual triage)
   - Risk: Low
   - Dependency: HF-0004

9. **HF-0010** — Artifact scoring automation
   - Value: High (economic value tracking)
   - Risk: Low
   - Dependency: HF-0006
