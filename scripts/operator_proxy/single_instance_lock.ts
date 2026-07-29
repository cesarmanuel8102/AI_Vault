import {randomUUID} from "node:crypto";
import {
  closeSync,
  existsSync,
  fsyncSync,
  linkSync,
  lstatSync,
  mkdirSync,
  openSync,
  readdirSync,
  readFileSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import {join} from "node:path";

const PROTOCOL_VERSION = "append-only-epochs-v1";
const EPOCH_PATTERN = /^epoch-(\d{16})\.json$/;
const RELEASE_PATTERN = /^epoch-(\d{16})\.release\.json$/;
const CANDIDATE_PATTERN = /^\.candidate-(\d+)-([0-9a-f-]{36})\.(epoch|release)\.tmp$/;

export interface LeaseRelease {
  (): void;
  owns(): boolean;
}

export interface LockTestHooks {
  beforePublish?: (epoch: number) => void;
}

interface EpochRecord {
  schema_version: 1;
  epoch: number;
  pid: number;
  token: string;
  created_utc: string;
  protocol_version: typeof PROTOCOL_VERSION;
}

interface ReleaseRecord {
  epoch: number;
  pid: number;
  token: string;
  released_utc: string;
}

interface LockState {
  epochs: Map<number, EpochRecord>;
  releases: Map<number, ReleaseRecord>;
  latest?: EpochRecord;
}

function exactKeys(value: object, expected: string[]): boolean {
  return JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...expected].sort());
}

function validUuid(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(value);
}

function validTimestamp(value: unknown): value is string {
  return typeof value === "string" && !Number.isNaN(Date.parse(value));
}

function epochName(epoch: number): string {
  if (!Number.isSafeInteger(epoch) || epoch < 1) throw new Error("operator proxy lock epoch invalid");
  return `epoch-${String(epoch).padStart(16, "0")}.json`;
}

function releaseName(epoch: number): string {
  return epochName(epoch).replace(/\.json$/, ".release.json");
}

function epochFromName(name: string, pattern: RegExp): number {
  const match = pattern.exec(name);
  if (!match) throw new Error("operator proxy lock filename invalid");
  const epoch = Number(match[1]);
  if (!Number.isSafeInteger(epoch) || epoch < 1 || epochName(epoch).slice(6, 22) !== match[1]) {
    throw new Error("operator proxy lock filename epoch invalid");
  }
  return epoch;
}

function parseEpoch(path: string, filenameEpoch: number): EpochRecord {
  const value = JSON.parse(readFileSync(path, "utf8"));
  if (
    !value ||
    typeof value !== "object" ||
    !exactKeys(value, ["schema_version", "epoch", "pid", "token", "created_utc", "protocol_version"]) ||
    value.schema_version !== 1 ||
    value.epoch !== filenameEpoch ||
    !Number.isInteger(value.pid) ||
    value.pid < 1 ||
    !validUuid(value.token) ||
    !validTimestamp(value.created_utc) ||
    value.protocol_version !== PROTOCOL_VERSION
  ) {
    throw new Error("operator proxy lock epoch record invalid");
  }
  return value as EpochRecord;
}

function parseRelease(path: string, filenameEpoch: number): ReleaseRecord {
  const value = JSON.parse(readFileSync(path, "utf8"));
  if (
    !value ||
    typeof value !== "object" ||
    !exactKeys(value, ["epoch", "pid", "token", "released_utc"]) ||
    value.epoch !== filenameEpoch ||
    !Number.isInteger(value.pid) ||
    value.pid < 1 ||
    !validUuid(value.token) ||
    !validTimestamp(value.released_utc)
  ) {
    throw new Error("operator proxy lock release record invalid");
  }
  return value as ReleaseRecord;
}

function ensureLockDirectory(path: string): void {
  try {
    mkdirSync(path);
  } catch (error: any) {
    if (error?.code !== "EEXIST") throw new Error("operator proxy lock directory unavailable");
  }
  const stat = lstatSync(path);
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    throw new Error("operator proxy lock occupied: legacy or unsafe path");
  }
}

function readState(path: string): LockState {
  const stat = lstatSync(path);
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    throw new Error("operator proxy lock occupied: legacy or unsafe path");
  }

  const epochs = new Map<number, EpochRecord>();
  const releases = new Map<number, ReleaseRecord>();
  for (const entry of readdirSync(path, {withFileTypes: true})) {
    const fullPath = join(path, entry.name);
    if (CANDIDATE_PATTERN.test(entry.name)) {
      if (!entry.isFile() || entry.isSymbolicLink()) throw new Error("operator proxy lock candidate invalid");
      continue;
    }
    const epochMatch = EPOCH_PATTERN.exec(entry.name);
    if (epochMatch) {
      if (!entry.isFile() || entry.isSymbolicLink()) throw new Error("operator proxy lock epoch path invalid");
      const epoch = epochFromName(entry.name, EPOCH_PATTERN);
      if (epochs.has(epoch)) throw new Error("operator proxy lock duplicate epoch");
      epochs.set(epoch, parseEpoch(fullPath, epoch));
      continue;
    }
    const releaseMatch = RELEASE_PATTERN.exec(entry.name);
    if (releaseMatch) {
      if (!entry.isFile() || entry.isSymbolicLink()) throw new Error("operator proxy lock release path invalid");
      const epoch = epochFromName(entry.name.replace(".release", ""), EPOCH_PATTERN);
      if (releases.has(epoch)) throw new Error("operator proxy lock duplicate release");
      releases.set(epoch, parseRelease(fullPath, epoch));
      continue;
    }
    throw new Error("operator proxy lock directory contains unexpected entry");
  }

  const orderedEpochs = [...epochs.keys()].sort((a, b) => a - b);
  for (let index = 0; index < orderedEpochs.length; index += 1) {
    if (orderedEpochs[index] !== index + 1) throw new Error("operator proxy lock epoch sequence invalid");
  }
  for (const [epoch, release] of releases) {
    const owner = epochs.get(epoch);
    if (!owner) throw new Error("operator proxy lock release has no epoch");
    if (release.pid !== owner.pid || release.token !== owner.token) {
      throw new Error("operator proxy lock release identity mismatch");
    }
  }
  return {epochs, releases, latest: orderedEpochs.length ? epochs.get(orderedEpochs.at(-1)!) : undefined};
}

function processIsActive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error: any) {
    // Permission and unexpected platform errors are ambiguous and therefore live.
    return error?.code !== "ESRCH";
  }
}

function writeCandidate(path: string, record: EpochRecord | ReleaseRecord, kind: "epoch" | "release"): string {
  const candidate = join(path, `.candidate-${process.pid}-${randomUUID()}.${kind}.tmp`);
  const fd = openSync(candidate, "wx");
  try {
    writeFileSync(fd, `${JSON.stringify(record)}\n`, "utf8");
    fsyncSync(fd);
  } finally {
    closeSync(fd);
  }
  return candidate;
}

function publishNoOverwrite(candidate: string, destination: string): boolean {
  try {
    linkSync(candidate, destination);
    return true;
  } catch (error: any) {
    if (error?.code === "EEXIST") return false;
    throw new Error("operator proxy atomic hard-link publication unavailable");
  } finally {
    try {
      unlinkSync(candidate);
    } catch {}
  }
}

function latestIsAvailable(state: LockState): boolean {
  if (!state.latest) return true;
  if (state.releases.has(state.latest.epoch)) return true;
  return !processIsActive(state.latest.pid);
}

export function lock(path: string, testHooks: LockTestHooks = {}): LeaseRelease {
  ensureLockDirectory(path);
  let ownRecord: EpochRecord | undefined;

  for (let attempt = 0; attempt < 64; attempt += 1) {
    const state = readState(path);
    if (!latestIsAvailable(state)) throw new Error("operator proxy lock occupied");
    const nextEpoch = (state.latest?.epoch ?? 0) + 1;
    const record: EpochRecord = {
      schema_version: 1,
      epoch: nextEpoch,
      pid: process.pid,
      token: randomUUID(),
      created_utc: new Date().toISOString(),
      protocol_version: PROTOCOL_VERSION,
    };
    const candidate = writeCandidate(path, record, "epoch");
    testHooks.beforePublish?.(nextEpoch);
    if (publishNoOverwrite(candidate, join(path, epochName(nextEpoch)))) {
      ownRecord = record;
      break;
    }

    const winner = readState(path).latest;
    if (winner && winner.epoch >= nextEpoch && processIsActive(winner.pid)) {
      throw new Error("operator proxy lock occupied");
    }
  }
  if (!ownRecord) throw new Error("operator proxy lock acquisition contention exceeded");

  let released = false;
  const owns = (): boolean => {
    if (released || !ownRecord) return false;
    try {
      const state = readState(path);
      return (
        state.latest?.epoch === ownRecord.epoch &&
        state.latest.pid === ownRecord.pid &&
        state.latest.token === ownRecord.token &&
        !state.releases.has(ownRecord.epoch)
      );
    } catch {
      return false;
    }
  };

  const release = (() => {
    if (released || !ownRecord) return;
    const state = readState(path);
    const owner = state.epochs.get(ownRecord.epoch);
    if (
      state.latest?.epoch !== ownRecord.epoch ||
      !owner ||
      owner.pid !== ownRecord.pid ||
      owner.token !== ownRecord.token
    ) {
      throw new Error("operator proxy lock ownership lost");
    }
    const existing = state.releases.get(ownRecord.epoch);
    if (existing) {
      released = true;
      return;
    }
    const record: ReleaseRecord = {
      epoch: ownRecord.epoch,
      pid: ownRecord.pid,
      token: ownRecord.token,
      released_utc: new Date().toISOString(),
    };
    const candidate = writeCandidate(path, record, "release");
    const published = publishNoOverwrite(candidate, join(path, releaseName(ownRecord.epoch)));
    if (!published) {
      const concurrent = readState(path).releases.get(ownRecord.epoch);
      if (!concurrent || concurrent.pid !== record.pid || concurrent.token !== record.token) {
        throw new Error("operator proxy lock release conflict");
      }
    }
    released = true;
  }) as LeaseRelease;
  release.owns = owns;
  return release;
}
