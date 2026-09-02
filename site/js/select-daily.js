// Deterministic "today's fact" picker, shared logic with pipeline/select_daily.py.
// Given a precomputed cycle (a shuffled list of entry ids) and the date that
// cycle started rotating from, picks one id per calendar day (UTC), skipping
// any id that's no longer eligible (e.g. removed or un-reviewed later on).
function selectDailyId(cycleData, entriesById, todayUTC) {
  const cycle = cycleData.cycle;
  if (!cycle || cycle.length === 0) return null;

  const start = new Date(cycleData.cycle_start_date + "T00:00:00Z");
  const today = todayUTC || new Date();
  const todayMidnightUTC = Date.UTC(
    today.getUTCFullYear(),
    today.getUTCMonth(),
    today.getUTCDate()
  );
  const msPerDay = 24 * 60 * 60 * 1000;
  const daysSinceStart = Math.floor((todayMidnightUTC - start.getTime()) / msPerDay);

  const len = cycle.length;
  // Normalize in case today is before cycle_start_date (shouldn't happen in
  // practice, but keeps the index valid rather than throwing).
  let index = ((daysSinceStart % len) + len) % len;

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

if (typeof module !== "undefined") {
  module.exports = { selectDailyId };
}
