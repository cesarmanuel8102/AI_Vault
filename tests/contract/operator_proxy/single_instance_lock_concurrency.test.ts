import test from "node:test";
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {ChildProcess, spawn} from "node:child_process";
import {existsSync, mkdtempSync, readFileSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join, resolve} from "node:path";

const CHILD = resolve(process.cwd(), "../../tests/contract/operator_proxy/single_instance_lock_child.ts");
const TSX = resolve(process.cwd(), "node_modules/tsx/dist/cli.mjs");

interface WaveResult {winner: ChildProcess;epoch: number;acquired: number;rejected: number}

function waitForExit(child: ChildProcess): Promise<void> {
  return new Promise((resolve) => child.once("exit", () => resolve()));
}

async function wave(lockPath: string, root: string, number: number): Promise<WaveResult> {
  const barrier = join(root, `barrier-${number}`);
  const children = Array.from({length: 16}, () => spawn(process.execPath, [TSX, CHILD, lockPath, barrier], {stdio: ["ignore", "pipe", "pipe", "ipc"]}));
  const ready = new Set<ChildProcess>();
  const atPublish = new Set<ChildProcess>();
  const results: Array<{child: ChildProcess;message: any}> = [];

  await new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("concurrency wave ready timeout")), 30_000);
    for (const child of children) {
      child.on("message", (message: any) => {
        if (message?.type === "ready") {
          ready.add(child);
          if (ready.size === children.length) {
            for (const participant of children) participant.send({type: "go"});
          }
        } else if (message?.type === "before_publish") {
          atPublish.add(child);
          if (atPublish.size === children.length) writeFileSync(barrier, "go\n");
        } else if (message?.type === "acquired" || message?.type === "rejected") {
          results.push({child, message});
          if (results.length === children.length) {
            clearTimeout(timeout);
            resolve();
          }
        }
      });
      child.once("error", reject);
    }
  });

  const acquired = results.filter(({message}) => message.type === "acquired");
  const rejected = results.filter(({message}) => message.type === "rejected");
  assert.equal(acquired.length, 1);
  assert.equal(rejected.length, 15);
  assert.equal(acquired[0].message.owns, true);
  assert.ok(rejected.every(({message}) => /occupied/.test(message.message)));
  return {winner: acquired[0].child, epoch: acquired[0].message.epoch, acquired: acquired.length, rejected: rejected.length};
}

test("append-only lock elects one owner across crash recovery and normal release", {timeout: 120_000}, async () => {
  const root = mkdtempSync(join(tmpdir(), "operator-proxy-lock-race-"));
  const lockPath = join(root, "operator-proxy.lock");

  const first = await wave(lockPath, root, 1);
  assert.equal(first.epoch, 1);
  const firstPath = join(lockPath, "epoch-0000000000000001.json");
  const firstBytes = readFileSync(firstPath);
  const firstHash = createHash("sha256").update(firstBytes).digest("hex");
  first.winner.kill();
  await waitForExit(first.winner);

  const second = await wave(lockPath, root, 2);
  assert.equal(second.epoch, 2);
  assert.equal(createHash("sha256").update(readFileSync(firstPath)).digest("hex"), firstHash);
  second.winner.send({type: "release"});
  await waitForExit(second.winner);

  const third = await wave(lockPath, root, 3);
  assert.equal(third.epoch, 3);
  third.winner.send({type: "release"});
  await waitForExit(third.winner);

  assert.equal(existsSync(firstPath), true);
  assert.equal(createHash("sha256").update(readFileSync(firstPath)).digest("hex"), firstHash);
});
