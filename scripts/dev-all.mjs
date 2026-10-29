#!/usr/bin/env node
/**
 * Starts the DressMe FastAPI backend and the existing HelpMePack Vite frontend
 * with one command, reuses already-running ports, and stops both on exit.
 */

import { spawn, spawnSync } from "node:child_process";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const FRONTEND_DIR = path.join(ROOT, "DressMe UI Blueprint");
const BACKEND_PORT = Number(process.env.BACKEND_PORT || "8020");
const FRONTEND_PORT = Number(process.env.FRONTEND_PORT || "8443");
const IS_WINDOWS = process.platform === "win32";
const PYTHON = process.env.PYTHON || (IS_WINDOWS ? "python" : "python3");
const FRONTEND_PM = process.env.FRONTEND_PM || "pnpm";

const children = new Map();
let shuttingDown = false;

// Keep the launcher alive even when both services were already running and no
// child processes were spawned by this process.
setInterval(() => {}, 1 << 30);

function log(prefix, message) {
  for (const line of String(message).split(/\r?\n/)) {
    if (line.trim()) console.log(`[${prefix}] ${line}`);
  }
}

function isPortOpen(port, timeoutMs = 600) {
  return new Promise((resolve) => {
    const socket = net.connect({ host: "127.0.0.1", port });
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(value);
    };
    socket.setTimeout(timeoutMs);
    socket.once("connect", () => finish(true));
    socket.once("timeout", () => finish(false));
    socket.once("error", () => finish(false));
  });
}

function pipeOutput(prefix, child) {
  child.stdout?.on("data", (data) => log(prefix, data));
  child.stderr?.on("data", (data) => log(prefix, data));
}

function killProcessTree(child) {
  if (!child || child.killed) return;
  if (IS_WINDOWS && child.pid) {
    spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
      stdio: "ignore",
      windowsHide: true,
    });
    return;
  }
  child.kill("SIGTERM");
  setTimeout(() => {
    if (!child.killed) child.kill("SIGKILL");
  }, 3000).unref();
}

function shutdown(code = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  if (children.size === 0) {
    process.exit(code);
  }
  console.log("\nStopping DressMe services…");
  for (const child of children.values()) killProcessTree(child);
  children.clear();
  setTimeout(() => process.exit(code), 600).unref();
}

function startService(name, command, args, options) {
  log(name, `starting: ${command} ${args.join(" ")}`);
  const child = spawn(command, args, {
    cwd: options.cwd,
    env: options.env,
    shell: options.shell ?? false,
    windowsHide: false,
    stdio: ["ignore", "pipe", "pipe"],
  });
  children.set(name, child);
  pipeOutput(name, child);
  child.on("error", (error) => {
    log(name, `failed to start: ${error.message}`);
    shutdown(1);
  });
  child.on("exit", (code, signal) => {
    children.delete(name);
    if (shuttingDown) return;
    log(name, `exited (code=${code ?? "null"}, signal=${signal ?? "none"})`);
    if (code && code !== 0) {
      log(name, "Unexpected exit; stopping the other service.");
      shutdown(code);
    }
  });
  return child;
}

async function waitForPort(port, label, timeoutMs = 45_000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (await isPortOpen(port)) {
      log("dev", `${label} is ready on port ${port}`);
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  log("dev", `${label} did not open port ${port} within ${timeoutMs / 1000}s.`);
  return false;
}

async function main() {
  console.log("DressMe development launcher");
  console.log(`Repository: ${ROOT}`);
  console.log(`Backend:    http://127.0.0.1:${BACKEND_PORT}`);
  console.log(`Frontend:   http://localhost:${FRONTEND_PORT}`);
  console.log("");

  const backendRunning = await isPortOpen(BACKEND_PORT);
  const frontendRunning = await isPortOpen(FRONTEND_PORT);

  if (backendRunning) {
    log("backend", `port ${BACKEND_PORT} is already in use; reusing it.`);
  } else {
    startService(
      "backend",
      PYTHON,
      [
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        String(BACKEND_PORT),
      ],
      {
        cwd: ROOT,
        env: {
          ...process.env,
          BACKEND_PORT: String(BACKEND_PORT),
          PYTHONUNBUFFERED: "1",
        },
      },
    );
  }

  if (frontendRunning) {
    log("frontend", `port ${FRONTEND_PORT} is already in use; reusing it.`);
  } else {
    const frontendEnv = {
      ...process.env,
      PORT: String(FRONTEND_PORT),
      VITE_TRIP_API_URL:
        process.env.VITE_TRIP_API_URL || `http://127.0.0.1:${BACKEND_PORT}`,
    };
    if (IS_WINDOWS) {
      startService(
        "frontend",
        "cmd.exe",
        ["/d", "/s", "/c", `${FRONTEND_PM} dev`],
        { cwd: FRONTEND_DIR, env: frontendEnv },
      );
    } else {
      startService("frontend", FRONTEND_PM, ["dev"], {
        cwd: FRONTEND_DIR,
        env: frontendEnv,
      });
    }
  }

  const [backendReady, frontendReady] = await Promise.all([
    waitForPort(BACKEND_PORT, "Backend API"),
    waitForPort(FRONTEND_PORT, "HelpMePack frontend"),
  ]);

  if (!backendReady || !frontendReady) {
    log(
      "dev",
      "One or more services failed to become ready. Check the logs above.",
    );
    shutdown(1);
    return;
  }

  console.log("");
  console.log("============================================================");
  console.log(" DressMe is ready");
  console.log(` HelpMePack:  http://localhost:${FRONTEND_PORT}`);
  console.log(` API docs:    http://127.0.0.1:${BACKEND_PORT}/docs`);
  console.log(` API health:  http://127.0.0.1:${BACKEND_PORT}/api/health`);
  console.log(" Press Ctrl+C to stop all services.");
  console.log("============================================================");
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));
process.on("uncaughtException", (error) => {
  console.error("Launcher error:", error);
  shutdown(1);
});

main().catch((error) => {
  console.error("Launcher error:", error);
  shutdown(1);
});
