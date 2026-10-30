#!/usr/bin/env node
// Keep npm and the PowerShell entry point on the same service list and lifecycle.
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

if (process.platform !== "win32") {
  console.error("The all-services launcher currently requires Windows PowerShell.");
  process.exit(1);
}

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path.join(root, "start_all.ps1")];
if (process.argv[2] === "stop") args.push("-Stop");
const result = spawnSync("powershell.exe", args, { cwd: root, stdio: "inherit" });
if (result.error) console.error(`Could not run PowerShell: ${result.error.message}`);
process.exit(result.status ?? 1);
