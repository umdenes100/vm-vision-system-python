import { initializeApp } from "firebase/app";
import { getStorage, listAll, ref, getMetadata, getDownloadURL } from "firebase/storage";
import * as database from "firebase/database";
import fs from "fs";
import path from "path";

// Your web app's Firebase configuration
const firebaseConfig = {
  apiKey: "AIzaSyBAMDAGYHNMtPaXAwJl-BRvxvl37E7Z3xE",
  projectId: "engr-enes100tool-inv-firebase",
  databaseURL: "https://engr-enes100tool-inv-firebase-model-watcher.firebaseio.com/",
  storageBucket: "engr-enes100tool-inv-firebase.appspot.com",
  appId: "1:763916402491:web:e598de3c258f7d4faa811e"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const storage = getStorage(app);
const rootref = ref(storage, "/studentmodels");

// Relative to repo root (RunVisionSystem.sh cd's to repo root)
const outputdir = "./components/machinelearning/models/";

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

async function downloadFile(filename) {
  const downloadURL = await getDownloadURL(ref(rootref, filename));
  const destination = path.join(outputdir, filename);
  const tmpDestination = destination + ".tmp";

  const res = await fetch(downloadURL);
  if (!res.ok) {
    throw new Error(`Failed fetch for ${filename}: HTTP ${res.status} ${res.statusText}`);
  }

  // Node 18: safest cross-compat approach is arrayBuffer -> Buffer
  const buf = Buffer.from(await res.arrayBuffer());

  // Atomic replace: write tmp then rename
  ensureDir(outputdir);
  if (fs.existsSync(tmpDestination)) fs.unlinkSync(tmpDestination);
  fs.writeFileSync(tmpDestination, buf);

  if (fs.existsSync(destination)) fs.unlinkSync(destination);
  fs.renameSync(tmpDestination, destination);
}

async function check() {
  ensureDir(outputdir);
  console.log("[listener] Executing check");

  const res = await listAll(rootref);
  const files = res.items;

  for (const file of files) {
    const metadata = await getMetadata(file);
    const localfile = path.join(outputdir, metadata.name);
    const remoteTime = new Date(metadata.updated).getTime();

    if (fs.existsSync(localfile)) {
      const stats = fs.statSync(localfile);
      const localTime = stats.mtimeMs;

      if (localTime < remoteTime) {
        console.log(`[listener] Downloading ${metadata.name} (local ${localTime} < remote ${remoteTime})`);
        await downloadFile(metadata.name);
        console.log(`[listener] Downloaded ${metadata.name}`);
      } else {
        console.log(`[listener] Skipping ${metadata.name} (local ${localTime} >= remote ${remoteTime})`);
      }
    } else {
      console.log(`[listener] Downloading ${metadata.name} (missing locally)`);
      await downloadFile(metadata.name);
      console.log(`[listener] Downloaded ${metadata.name}`);
    }
  }
}

// Debounce DB-change triggers to avoid rapid repeated downloads
let scheduled = false;
function scheduleCheck() {
  if (scheduled) return;
  scheduled = true;
  setTimeout(async () => {
    scheduled = false;
    try {
      await check();
    } catch (err) {
      console.error("[listener] check() failed:", err);
      process.exit(1);
    }
  }, 250);
}

async function main() {
  // Do an initial sync on startup (this was missing before)
  await check();

  // Listen for changes in the database
  const db = database.getDatabase(app);
  database.onValue(database.ref(db, "/"), (_snapshot) => {
    console.log("[listener] Database changed -> scheduling check");
    scheduleCheck();
  });

  // Stay alive forever
  await new Promise(() => {});
}

main().catch((err) => {
  console.error("[listener] Fatal error:", err);
  process.exit(1);
});
