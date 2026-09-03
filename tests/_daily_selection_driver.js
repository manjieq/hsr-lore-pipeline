// Driver invoked by tests/test_daily_selection_parity.py via `node`. Reads
// {cycleData, entriesById, dateStr} as JSON from stdin, calls the real
// site/js/select-daily.js implementation, and prints {result} as JSON.
// Not loaded by the site itself -- test infrastructure only.
const path = require("path");
const { selectDailyId } = require(path.join(__dirname, "..", "site", "js", "select-daily.js"));

let input = "";
process.stdin.on("data", (chunk) => (input += chunk));
process.stdin.on("end", () => {
  const { cycleData, entriesById, dateStr } = JSON.parse(input);
  const entriesMap = new Map(Object.entries(entriesById));
  const today = new Date(dateStr + "T00:00:00Z");
  const result = selectDailyId(cycleData, entriesMap, today);
  process.stdout.write(JSON.stringify({ result }));
});
