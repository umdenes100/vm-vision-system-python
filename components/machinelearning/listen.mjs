import {initializeApp} from "firebase/app";
import {getStorage, listAll, ref, getMetadata, getDownloadURL} from "firebase/storage";
import * as database from "firebase/database";
import { Readable } from 'stream';
import { finished } from 'stream/promises';
import fs from 'fs';
import fetch from 'node-fetch'

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
const rootref = ref(storage, '/studentmodels');


// This file will be ran. It should inifnitely watch for files in the firebase storage.
// On startup, it should list files and see which ones need to be updated.
// It will then listen to the realtimedatabase. When the root updates, it will check the files again.

const outputdir = './models/';

async function downloadFile(filename) {
    const downloadURL = await getDownloadURL(ref(rootref, filename));
    const destination = outputdir + filename;
    const res = await fetch(downloadURL);
    if (fs.existsSync(destination)) {
        fs.unlinkSync(destination);
    }
    const fileStream = fs.createWriteStream(destination, { flags: 'wx' });
    await finished(Readable.from(res.body).pipe(fileStream));
}

async function check() {
    // make models directory if it doesn't exist
    if (!fs.existsSync(outputdir)) {
        fs.mkdirSync(outputdir);
    }
    console.log('Executing check');
    // Check the files in the storage and update the database accordingly
    const res = await listAll(rootref);
    const files =  res.items;
    for (const file of files) {
        const metadata = await getMetadata(file);
        // console.log(metadata.name, new Date(metadata.updated).getTime(), metadata.size);
        const localfile = outputdir + metadata.name;
        if (fs.existsSync(localfile)) {
            const stats = fs.statSync(localfile);
            const localtime = stats.mtimeMs;
            if (localtime < new Date(metadata.updated).getTime()) {
                console.log('Downloading ' + metadata.name, 'because local time is ' + localtime + ' and remote time is ' + new Date(metadata.updated).getTime())
                await downloadFile(metadata.name);
                console.log('Downloaded ' + metadata.name)
            } else {
                console.log('Skipping ' + metadata.name, 'because local time is ' + localtime + ' and remote time is ' + new Date(metadata.updated).getTime())
            }
        } else {
            console.log('Downloading ' + metadata.name, 'because it does not exist locally');
            await downloadFile(metadata.name);
            console.log('Downloaded ' + metadata.name)
        }
    }
}

// Listen for changes in the database
database.onValue(database.ref(database.getDatabase(), '/'), (snapshot) => {
    const data = snapshot.val();
    console.log('Database changed', data);
    check();
});

// Do nothing but this onValue, forever
await new Promise(() => {});