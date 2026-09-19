// Driver invoked by tests/test_site_helpers.py via `node`. Exercises the
// real site/js helpers against input from stdin and prints results as JSON.
// Not loaded by the site itself -- test infrastructure only.
//
// site/js/app.js is an IIFE with no exports (it runs against a live DOM and
// has no module system), so its pure helpers are lifted out of the source
// text rather than required. That keeps the test honest -- it runs the
// shipped code, not a copy -- at the cost of being sensitive to the
// function signatures being renamed, which is what the "could not extract"
// error below reports.
const fs = require("fs");
const path = require("path");

const REPO_ROOT = path.join(__dirname, "..");
const { selectDailyConnectionId } = require(
  path.join(REPO_ROOT, "site", "js", "select-daily.js")
);

const appSrc = fs.readFileSync(path.join(REPO_ROOT, "site", "js", "app.js"), "utf8");

function grab(label, re) {
  const m = appSrc.match(re);
  if (!m) throw new Error(`could not extract ${label} from site/js/app.js`);
  return m[0];
}

const helpers = new Function(
  grab("CATEGORY_LABELS", /const CATEGORY_LABELS = \{[\s\S]*?\n  \};/) +
    grab("CATEGORY_LABELS_PLURAL", /const CATEGORY_LABELS_PLURAL = \{[\s\S]*?\n  \};/) +
    grab("CATEGORY_ORDER", /const CATEGORY_ORDER = \[[^\]]*\];/) +
    grab("escapeHtml", /function escapeHtml\([\s\S]*?\n  \}/) +
    grab("plural", /function plural\([\s\S]*?\n  \}/) +
    grab("describeSpread", /function describeSpread\([\s\S]*?\n  \}/) +
    "; return { escapeHtml, plural, describeSpread };"
)();

let input = "";
process.stdin.on("data", (chunk) => (input += chunk));
process.stdin.on("end", () => {
  const { op, args } = JSON.parse(input);
  let result;

  if (op === "plural") {
    result = helpers.plural(...args);
  } else if (op === "describeSpread") {
    result = helpers.describeSpread(args[0]);
  } else if (op === "escapeHtml") {
    result = helpers.escapeHtml(args[0]);
  } else if (op === "rotation") {
    // Walk the real rotation day by day and report anything unshowable.
    const { entities, connection_cycle: cycle } = JSON.parse(
      fs.readFileSync(path.join(REPO_ROOT, "site", "data", "entities.json"), "utf8")
    );
    const entries = JSON.parse(
      fs.readFileSync(path.join(REPO_ROOT, "site", "data", "entries.json"), "utf8")
    );
    const entryIds = new Set(entries.map((e) => e.id));
    const byId = new Map(entities.map((e) => [e.id, e]));
    const [startISO, days] = args;
    const start = Date.parse(startISO + "T00:00:00Z");

    const picks = [];
    const problems = [];
    for (let d = 0; d < days; d++) {
      const id = selectDailyConnectionId(cycle, byId, new Date(start + d * 86400000));
      const ent = byId.get(id);
      if (!ent) {
        problems.push(`day ${d}: unresolvable id ${id}`);
        continue;
      }
      if (ent.category_span < 2) problems.push(`day ${d}: ${ent.name} spans one category`);
      const dangling = ent.entry_ids.filter((i) => !entryIds.has(i));
      if (dangling.length) problems.push(`day ${d}: ${ent.name} has dangling ${dangling[0]}`);
      picks.push(id);
    }
    result = { distinct: new Set(picks).size, cycleLength: cycle.cycle.length, problems };
  } else {
    throw new Error(`unknown op ${op}`);
  }

  process.stdout.write(JSON.stringify({ result }));
});
