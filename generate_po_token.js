#!/usr/bin/env node
// Generates a YouTube PO token + visitor data pair and prints JSON to stdout.
// Called by the Python bot before each yt-dlp download session.
const { generate } = require("youtube-po-token-generator");

generate()
  .then(({ visitorData, poToken }) => {
    process.stdout.write(JSON.stringify({ visitorData, poToken }));
    process.exit(0);
  })
  .catch((err) => {
    process.stderr.write(String(err));
    process.exit(1);
  });
