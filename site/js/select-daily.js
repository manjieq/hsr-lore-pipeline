// Picks the one connection featured on a given calendar day (UTC).
//
// There is deliberately no Python counterpart to keep in sync. Python owns
// the *order* of the rotation -- a seeded shuffle written into
// site/data/entities.json by pipeline/entities.py -- and the browser owns
// only the day indexing. An earlier design duplicated a whole selection
// algorithm across pipeline/select_daily.py and this file, which needed an
// automated parity test to stop the two drifting; splitting the
// responsibilities removed the duplication instead of policing it.

// Days elapsed from the cycle's start date to today, folded into a valid
// index.
function cycleIndexForToday(cycleStartDate, todayUTC, length) {
  const start = new Date(cycleStartDate + "T00:00:00Z");
  const today = todayUTC || new Date();
  const todayMidnightUTC = Date.UTC(
    today.getUTCFullYear(),
    today.getUTCMonth(),
    today.getUTCDate()
  );
  const msPerDay = 24 * 60 * 60 * 1000;
  const daysSinceStart = Math.floor((todayMidnightUTC - start.getTime()) / msPerDay);
  // Normalize in case today is before cycle_start_date (shouldn't happen in
  // practice, but keeps the index valid rather than throwing).
  return ((daysSinceStart % length) + length) % length;
}

// pipeline/entities.py already applied the eligibility rules when it built
// the cycle (spans more than one category, clears the reach floor, built
// only from entries that passed QA), so anything still in the list is
// showable.
function selectDailyConnectionId(cycleData, entitiesById, todayUTC) {
  const cycle = cycleData && cycleData.cycle;
  if (!cycle || cycle.length === 0) return null;

  const len = cycle.length;
  let index = cycleIndexForToday(cycleData.cycle_start_date, todayUTC, len);

  // The cycle is rebuilt from scratch on each pipeline run while a reader's
  // browser may still hold a cached entities.json, so an id can go missing.
  // Walk forward rather than showing an empty hero.
  for (let tries = 0; tries < len; tries++) {
    const id = cycle[index];
    if (entitiesById.get(id)) return id;
    index = (index + 1) % len;
  }
  return null;
}

if (typeof module !== "undefined") {
  module.exports = { selectDailyConnectionId, cycleIndexForToday };
}
