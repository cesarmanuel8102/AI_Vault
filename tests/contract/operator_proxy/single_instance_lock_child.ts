import {existsSync, readdirSync, readFileSync} from "node:fs";
import {lock} from "../../../scripts/operator_proxy/single_instance_lock.js";

const lockPath = process.argv[2];
const barrierPath = process.argv[3];
if (!lockPath || !barrierPath || !process.send) process.exit(2);

process.send({type: "ready"});
process.on("message", (message: any) => {
  if (message?.type === "go") {
    try {
      const release = lock(lockPath, {
        beforePublish: () => {
          process.send?.({type: "before_publish"});
          while (!existsSync(barrierPath)) Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 10);
        },
      });
      const epochs = readdirSync(lockPath).filter((name) => /^epoch-\d{16}\.json$/.test(name)).sort();
      const latest = JSON.parse(readFileSync(`${lockPath}/${epochs.at(-1)}`, "utf8"));
      process.send?.({type: "acquired", epoch: latest.epoch, owns: release.owns()});
      process.on("message", (command: any) => {
        if (command?.type === "release") {
          release();
          process.send?.({type: "released", owns: release.owns()});
          process.exit(0);
        }
      });
    } catch (error: any) {
      process.send?.({type: "rejected", message: String(error?.message ?? error)});
      process.exit(0);
    }
  }
});
