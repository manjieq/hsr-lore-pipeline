// Deterministic "one per calendar day" pickers for the site.
//
// selectDailyId (entries) is shared logic with pipeline/select_daily.py and
// any change to it must be mirrored there exactly -- see the note in that
// file; tests/test_daily_selection_parity.py runs both against the same
// inputs and fails if they disagree.
//
// selectDailyConnectionId (entities) has no Python counterpart on purpose.
// Python owns the *order* of the connection rotation (a seeded shuffle
// written into site/data/entities.json by pipeline/entities.py) and the
// browser owns only the day indexing, so there is no duplicated algorithm
// here to keep in sync.

// Days elapsed from a cycle's start date to today, folded into a valid
// index. Extracted so both pickers share one definition of "what day is it"
// rather than growing a second, subtly different copy.
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

function selectDailyId(cycleData, entriesById, todayUTC) {
  const cycle = cycleData.cycle;
  if (!cycle || cycle.length === 0) return null;

  const len = cycle.length;
  let index = cycleIndexForToday(cycleData.cycle_start_date, todayUTC, len);

  for (let tries = 0; tries < len; tries++) {
    const id = cycle[index];
    const entry = entriesById.get(id);
    if (entry && entry.reviewed && (!entry.qa_flags || entry.qa_flags.length === 0)) {
      return id;
    }
    index = (index + 1) % len;
  }
  return null;
}

// Today's featured connection. Unlike entries, an entity has no
// reviewed/qa_flags notion -- pipeline/entities.py already applied the
// eligibility rules (spans more than one category, clears the reach floor)
// when it built the cycle, so anything in the list is showable.
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
  module.exports = { selectDailyId, selectDailyConnectionId, cycleIndexForToday };
}
