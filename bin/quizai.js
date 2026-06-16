#!/usr/bin/env node
"use strict";

// Thin launcher: downloads the QuizAI Windows executable from the matching
// GitHub Release (once, cached) and runs it. Lets users install in one go with
//   npx github:tanumay-deb/QuizAI
// No npm-registry publish required. Pure Node stdlib — no dependencies.

const https = require("https");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

const VERSION = "v1.3.0";
const ASSET = "QuizAI.exe";
const DOWNLOAD_URL = `https://github.com/tanumay-deb/QuizAI/releases/download/${VERSION}/${ASSET}`;
const RELEASES = "https://github.com/tanumay-deb/QuizAI/releases/latest";

if (process.platform !== "win32") {
  console.error(
    "QuizAI's prebuilt binary is Windows-only.\n" +
      "On macOS / Linux, install from source: " +
      "https://github.com/tanumay-deb/QuizAI#getting-started-step-by-step"
  );
  process.exit(1);
}

const cacheDir = path.join(os.homedir(), ".quizai-bin");
const exePath = path.join(cacheDir, `QuizAI-${VERSION}.exe`);

function launch() {
  const child = spawn(exePath, [], { detached: true, stdio: "ignore" });
  child.unref();
  console.log("QuizAI launched — look for the tray icon near the clock.");
  console.log("First run: it'll prompt for a free Gemini key (or pick Ollama in Settings).");
}

function download(url, dest, cb) {
  https
    .get(url, { headers: { "User-Agent": "quizai-npm-launcher" } }, (res) => {
      // GitHub release downloads redirect to a CDN — follow them.
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        download(res.headers.location, dest, cb);
        return;
      }
      if (res.statusCode !== 200) {
        res.resume();
        cb(new Error("HTTP " + res.statusCode));
        return;
      }
      const tmp = dest + ".part";
      const file = fs.createWriteStream(tmp);
      res.pipe(file);
      file.on("finish", () => file.close(() => {
        fs.renameSync(tmp, dest);
        cb(null);
      }));
      file.on("error", (e) => {
        try { fs.unlinkSync(tmp); } catch (_) {}
        cb(e);
      });
    })
    .on("error", cb);
}

if (fs.existsSync(exePath)) {
  launch();
} else {
  fs.mkdirSync(cacheDir, { recursive: true });
  console.log(`Downloading QuizAI ${VERSION} (first run only, ~one-time)…`);
  download(DOWNLOAD_URL, exePath, (err) => {
    if (err) {
      console.error("Download failed:", err.message);
      console.error("Download it manually instead: " + RELEASES);
      process.exit(1);
    }
    launch();
  });
}
