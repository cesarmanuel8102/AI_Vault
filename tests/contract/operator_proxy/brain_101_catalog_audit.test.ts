import test from "node:test";
import assert from "node:assert/strict";
import {join} from "node:path";
import {auditCatalogFile} from "../../../scripts/operator_proxy/brain_101_catalog_audit.js";

const catalogPath = join(process.cwd(), "..", "..", "docs", "roadmap", "BRAIN_101_CONTRACT_CATALOG.json");

test("BRAIN_101_CONTRACT_CATALOG.json passes programmatic audit", () => {
  const result = auditCatalogFile(catalogPath);
  if (result.errors.length > 0) {
    console.error(result.errors);
  }
  if (result.warnings.length > 0) {
    console.warn(result.warnings);
  }
  assert.equal(result.valid, true, `catalog audit failed: ${result.errors.join("; ")}`);
});
