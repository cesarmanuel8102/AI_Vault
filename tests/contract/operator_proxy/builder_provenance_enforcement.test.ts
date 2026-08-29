import test from "node:test";
import assert from "node:assert/strict";
import {mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {join, resolve} from "node:path";
import {execFileSync} from "node:child_process";
import {routeControlPlaneBuild} from "../../../scripts/operator_proxy/builder_router.js";
import {BuilderAttemptProvenance} from "../../../scripts/operator_proxy/builder_attempt_provenance.js";
import {isEligibleFallback} from "../../../scripts/operator_proxy/builder_backend.js";
import type {ProxySpec} from "../../../scripts/operator_proxy/types.js";

function fakeBackendScript(mark: string, exitCode = 0): string {
  return `const fs=require("fs"),path=require("path"),{execFileSync}=require("child_process");
function isWorktreeRoot(d){if(!d)return false;try{execFileSync(process.env.GIT_PATH||"git",["-C",d,"rev-parse","--is-inside-work-tree"],{stdio:"pipe",timeout:10000});return true;}catch{return false;}}
function findWorktree(a){let idx=a.indexOf("-C");if(idx<0)idx=a.indexOf("--dir");if(idx>=0){const d=a[idx+1];if(isWorktreeRoot(d))return d;}for(let i=a.length-1;i>=2;i--){const d=a[i];if(isWorktreeRoot(d))return d;}return process.cwd();}
const correlation=process.env.OPERATOR_PROXY_PROVIDER_CORRELATION_ID;if(!correlation)process.exit(11);
const cwd=findWorktree(process.argv);
fs.mkdirSync(path.join(cwd,"docs"),{recursive:true});
fs.writeFileSync(path.join(cwd,"docs","x.md"),"${mark} build\\n");
execFileSync(process.env.GIT_PATH||"git",["-C",cwd,"add","docs/x.md"]);
execFileSync(process.env.GIT_PATH||"git",["-C",cwd,"commit","-m","feat(control-plane): complete BRAIN-101-R3.3-01"]);
const head=execFileSync(process.env.GIT_PATH||"git",["-C",cwd,"rev-parse","HEAD"],{encoding:"utf8"}).trim();
console.log("HEAD_SHA="+head);
console.log("PROVIDER_SESSION="+correlation);
console.log("BUILDER_BACKEND="+(process.env.OPERATOR_PROXY_BUILDER_BACKEND||"opencode_ollama"));
console.log("BUILDER_MODEL=opencode/kimi-k2.7-code");
process.exit(${exitCode});`;
}

function builderRepo(): {source: string; remote: string; root: string; worktree: string; base: string} {
  const tmp = mkdtempSync(join(tmpdir(), "prov-enforce-"));
  const source = join(tmp, "source");
  const remote = join(tmp, "remote.git");
  const worktrees = join(tmp, "worktrees");
  mkdirSync(source, {recursive: true});
  mkdirSync(remote, {recursive: true});
  const git = (args: string[], cwd = source) => execFileSync("git", args, {cwd, encoding: "utf8"});
  git(["init", "--bare", remote]);
  git(["init"]);
  git(["config", "user.email", "x@x.com"]);
  git(["config", "user.name", "x"]);
  writeFileSync(join(source, "README.md"), "base\n");
  git(["add", "README.md"]);
  git(["commit", "-m", "base"]);
  git(["remote", "add", "origin", remote]);
  git(["push", "origin", "HEAD:refs/heads/codex/own-capital-sustainable-return"]);
  const base = git(["rev-parse", "HEAD"]).trim();
  const worktree = resolve(worktrees, "BRAIN-101-R3.3-01");
  mkdirSync(join(worktree, ".."), {recursive: true});
  git(["worktree", "add", "-b", "control-plane/brain-101-r3.3-01", worktree, base]);
  const git2 = (args: string[]) => execFileSync("git", args, {cwd: worktree, encoding: "utf8"});
  git2(["config", "user.email", "x@x.com"]);
  git2(["config", "user.name", "x"]);
  return {source, remote, root: join(tmp, "root"), worktree, base};
}

const baseSpec = (r: ReturnType<typeof builderRepo>): ProxySpec => ({
  schema_version: 1,
  authorization_id: "AUTH-TEST",
  repository: "owner/repo",
  roadmap_id: "BRAIN-101",
  roadmap_version: "1.0.0",
  roadmap_item_id: "R3.3",
  expected_base_sha: r.base,
  executor: "codex_control_plane",
  risk: "MEDIUM",
  allowed_paths: ["docs/"],
  forbidden_paths: [".env"],
  acceptance: ["pass"],
  test_commands: [],
  deployment_allowed: false,
  work_branch: "control-plane/brain-101-r3.3-01",
  deployment_mode: "NO_DEPLOY",
  front_id: "BRAIN-101-R3.3-01",
});

class ThrowingCompletedProvenance extends BuilderAttemptProvenance {
  recordAttemptCompleted(receiptId: string, frontId: string, head: string, files: string[]): void {
    throw new Error("BUILDER_PROVENANCE_COMPLETED_WRITE_FAILED: simulated");
  }
}

function existsSync(path: string): boolean {
  try {
    readFileSync(path);
    return true;
  } catch {
    return false;
  }
}

test("campaign builder STARTED write failure invokes ZERO backend calls", async () => {
  const r = builderRepo();
  const opencodeEntry = join(r.source, "fake-opencode.js");
  writeFileSync(opencodeEntry, `process.exit(1);`);
  const priorOpenCode = process.env.OPEN_CODE_PATH;
  const priorRoot = process.env.OPERATOR_PROXY_ROOT;
  try {
    process.env.OPEN_CODE_PATH = opencodeEntry;
    process.env.OPERATOR_PROXY_ROOT = join(r.root, "state-file");
    mkdirSync(r.root, {recursive: true});
    writeFileSync(join(r.root, "state-file"), "not-a-directory\n");
    const spec = baseSpec(r);
    await assert.rejects(
      routeControlPlaneBuild(spec, 1, "prompt", 0, {provenanceRequired: true}, r.worktree),
      /BUILDER_PROVENANCE_START_WRITE_FAILED/,
    );
    const worktreeHead = execFileSync("git", ["-C", r.worktree, "rev-parse", "HEAD"], {encoding: "utf8"}).trim();
    assert.equal(worktreeHead, r.base, "backend must not have been invoked");
  } finally {
    if (priorOpenCode === undefined) delete process.env.OPEN_CODE_PATH; else process.env.OPEN_CODE_PATH = priorOpenCode;
    if (priorRoot === undefined) delete process.env.OPERATOR_PROXY_ROOT; else process.env.OPERATOR_PROXY_ROOT = priorRoot;
  }
});

test("campaign COMPLETED write failure performs ZERO push/publication", async () => {
  const r = builderRepo();
  const opencodeEntry = join(r.source, "fake-opencode.js");
  writeFileSync(opencodeEntry, fakeBackendScript("ok", 0));
  const priorOpenCode = process.env.OPEN_CODE_PATH;
  const priorRoot = process.env.OPERATOR_PROXY_ROOT;
  const priorBackendOverride = process.env.OPERATOR_PROXY_BUILDER_BACKEND;
  try {
    process.env.OPEN_CODE_PATH = opencodeEntry;
    process.env.OPERATOR_PROXY_ROOT = r.root;
    process.env.OPERATOR_PROXY_BUILDER_BACKEND = "opencode_ollama";
    mkdirSync(join(r.root, "state"), {recursive: true});
    const spec = baseSpec(r);
    const provenance = new ThrowingCompletedProvenance();
    await assert.rejects(
      routeControlPlaneBuild(spec, 1, "prompt", 0, {provenanceRequired: true, provenance}, r.worktree),
      /BUILDER_PROVENANCE_COMPLETED_WRITE_FAILED/,
    );
    const branchHead = execFileSync("git", ["-C", r.remote, "rev-parse", "refs/heads/codex/own-capital-sustainable-return"], {encoding: "utf8"}).trim();
    assert.equal(branchHead, r.base, "remote branch must not have published candidate");
  } finally {
    if (priorOpenCode === undefined) delete process.env.OPEN_CODE_PATH; else process.env.OPEN_CODE_PATH = priorOpenCode;
    if (priorRoot === undefined) delete process.env.OPERATOR_PROXY_ROOT; else process.env.OPERATOR_PROXY_ROOT = priorRoot;
    if (priorBackendOverride === undefined) delete process.env.OPERATOR_PROXY_BUILDER_BACKEND; else process.env.OPERATOR_PROXY_BUILDER_BACKEND = priorBackendOverride;
  }
});

test("configured invalid provenance root fails closed", async () => {
  const r = builderRepo();
  const priorRoot = process.env.OPERATOR_PROXY_ROOT;
  try {
    process.env.OPERATOR_PROXY_ROOT = join(r.root, "state-file");
    mkdirSync(r.root, {recursive: true});
    writeFileSync(join(r.root, "state-file"), "not-a-directory\n");
    const provenance = new BuilderAttemptProvenance();
    assert.throws(() => provenance.requireUsable("BRAIN-101-R3.3-01"), /BUILDER_PROVENANCE_ROOT_UNUSABLE/);
  } finally {
    if (priorRoot === undefined) delete process.env.OPERATOR_PROXY_ROOT; else process.env.OPERATOR_PROXY_ROOT = priorRoot;
  }
});

test("non-campaign legacy compatibility can still run only where contract allows", async () => {
  const r = builderRepo();
  const opencodeEntry = join(r.source, "fake-opencode.js");
  writeFileSync(opencodeEntry, fakeBackendScript("legacy", 0));
  const priorOpenCode = process.env.OPEN_CODE_PATH;
  const priorRoot = process.env.OPERATOR_PROXY_ROOT;
  const priorBackendOverride = process.env.OPERATOR_PROXY_BUILDER_BACKEND;
  try {
    delete process.env.OPERATOR_PROXY_ROOT;
    process.env.OPEN_CODE_PATH = process.execPath;
    process.env.OPERATOR_PROXY_BUILDER_BACKEND = "opencode_ollama";
    const spec: ProxySpec = {...baseSpec(r), executor: "agent_loop"};
    await assert.rejects(
      routeControlPlaneBuild(spec, 1, "prompt", 0, {}, r.worktree),
      /OPERATOR_PROXY_ROOT is required/,
    );
  } finally {
    if (priorOpenCode === undefined) delete process.env.OPEN_CODE_PATH; else process.env.OPEN_CODE_PATH = priorOpenCode;
    if (priorRoot === undefined) delete process.env.OPERATOR_PROXY_ROOT; else process.env.OPERATOR_PROXY_ROOT = priorRoot;
    if (priorBackendOverride === undefined) delete process.env.OPERATOR_PROXY_BUILDER_BACKEND; else process.env.OPERATOR_PROXY_BUILDER_BACKEND = priorBackendOverride;
  }
});

test("health-ledger failure does not equal provenance failure", async () => {
  const r = builderRepo();
  const priorRoot = process.env.OPERATOR_PROXY_ROOT;
  try {
    process.env.OPERATOR_PROXY_ROOT = r.root;
    mkdirSync(join(r.root, "state", "builder-health"), {recursive: true});
    rmSync(join(r.root, "state", "builder-health"), {recursive: true, force: true});
    writeFileSync(join(r.root, "state", "builder-health"), "not-a-directory\n");
    const provenance = new BuilderAttemptProvenance();
    assert.doesNotThrow(() => provenance.requireUsable("BRAIN-101-R3.3-01"));
  } finally {
    if (priorRoot === undefined) delete process.env.OPERATOR_PROXY_ROOT; else process.env.OPERATOR_PROXY_ROOT = priorRoot;
  }
});

test("provenance failure class maps to CONTROL_PLANE_DEFECT and SYSTEM_REPAIR receives fingerprint", async () => {
  const r = builderRepo();
  const priorRoot = process.env.OPERATOR_PROXY_ROOT;
  try {
    process.env.OPERATOR_PROXY_ROOT = join(r.root, "state-file");
    mkdirSync(r.root, {recursive: true});
    writeFileSync(join(r.root, "state-file"), "not-a-directory\n");
    let thrown: any;
    try {
      const spec = baseSpec(r);
      await routeControlPlaneBuild(spec, 1, "prompt", 0, {provenanceRequired: true}, r.worktree);
    } catch (err) {
      thrown = err;
    }
    assert.ok(thrown);
    assert.ok(thrown instanceof Error, "thrown must be Error");
    assert.ok((thrown as any).failureClass === "BUILDER_PROVENANCE_START_WRITE_FAILED", `expected BuilderBackendError, got ${(thrown as Error).message}`);
    const classified = isEligibleFallback(thrown);
    assert.equal(classified.eligible, false);
    assert.equal(classified.failure_class, "BUILDER_PROVENANCE_START_WRITE_FAILED");
  } finally {
    if (priorRoot === undefined) delete process.env.OPERATOR_PROXY_ROOT; else process.env.OPERATOR_PROXY_ROOT = priorRoot;
  }
});
