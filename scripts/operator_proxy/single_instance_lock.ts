import {randomUUID} from "node:crypto";
import {
  closeSync,
  fsyncSync,
  openSync,
  readFileSync,
  statSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";

export interface LeaseRelease {
  (): void;
  owns(): boolean;
}

interface LockRecord {
  schema_version: 1;
  pid: number;
  token: string;
  created_utc: string;
}

interface LockSnapshot {
  record: LockRecord;
  bytes: string;
  ino: bigint;
  size: bigint;
  mtimeNs: bigint;
}

function parseRecord(bytes: string): LockRecord {
  const value = JSON.parse(bytes);
  const keys = Object.keys(value).sort();
  if (
    JSON.stringify(keys) !== JSON.stringify(["created_utc", "pid", "schema_version", "token"]) ||
    value.schema_version !== 1 ||
    !Number.isInteger(value.pid) ||
    value.pid < 1 ||
    typeof value.token !== "string" ||
    !/^[0-9a-f-]{36}$/.test(value.token) ||
    typeof value.created_utc !== "string" ||
    Number.isNaN(Date.parse(value.created_utc))
  ) {
    throw new Error("operator proxy lock record invalid");
  }
  return value;
}

function snapshot(path: string): LockSnapshot {
  const bytes = readFileSync(path, "utf8");
  const stat = statSync(path, {bigint: true});
  return {record: parseRecord(bytes), bytes, ino: stat.ino, size: stat.size, mtimeNs: stat.mtimeNs};
}

function sameSnapshot(left: LockSnapshot, right: LockSnapshot): boolean {
  return (
    left.bytes === right.bytes &&
    left.ino === right.ino &&
    left.size === right.size &&
    left.mtimeNs === right.mtimeNs
  );
}

function processIsActive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error: any) {
    // Permission and unexpected platform errors are treated as a live owner.
    return error?.code !== "ESRCH";
  }
}

function create(path: string, record: LockRecord): number {
  const fd = openSync(path, "wx");
  try {
    writeFileSync(fd, `${JSON.stringify(record)}\n`, "utf8");
    fsyncSync(fd);
    return fd;
  } catch (error) {
    closeSync(fd);
    try {
      unlinkSync(path);
    } catch {}
    throw error;
  }
}

export function lock(path: string): LeaseRelease {
  const record: LockRecord = {
    schema_version: 1,
    pid: process.pid,
    token: randomUUID(),
    created_utc: new Date().toISOString(),
  };
  let fd: number;
  try {
    fd = create(path, record);
  } catch (error: any) {
    if (error?.code !== "EEXIST") throw error;

    let prior: LockSnapshot;
    try {
      prior = snapshot(path);
    } catch {
      throw new Error("operator proxy lock occupied: legacy or corrupt record");
    }
    if (processIsActive(prior.record.pid)) throw new Error("operator proxy lock occupied");

    // Re-read identity immediately before removal. Any replacement or mutation
    // blocks recovery rather than risking deletion of a newly acquired lease.
    let current: LockSnapshot;
    try {
      current = snapshot(path);
    } catch {
      throw new Error("operator proxy stale lock recovery lost race");
    }
    if (!sameSnapshot(prior, current)) throw new Error("operator proxy stale lock recovery lost race");

    try {
      unlinkSync(path);
      fd = create(path, record);
    } catch {
      throw new Error("operator proxy stale lock recovery lost race");
    }
  }

  let owned = true;
  const release = (() => {
    if (!owned) return;
    closeSync(fd);
    owned = false;
    try {
      const current = snapshot(path).record;
      if (current.pid === record.pid && current.token === record.token) unlinkSync(path);
    } catch {}
  }) as LeaseRelease;
  release.owns = () => owned;
  return release;
}
