// ---------------------------------------------------------------------------
// Semver: exact versions, ^ ~ comparators, x-ranges, hyphen ranges and ||.
// ---------------------------------------------------------------------------

export function parseVersion(text) {
  const m = /^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$/.exec(text);
  if (!m) return null;
  return {
    major: Number(m[1]),
    minor: Number(m[2]),
    patch: Number(m[3]),
    pre: m[4] ? m[4].split(".") : [],
  };
}

export function compareVersions(a, b) {
  for (const key of ["major", "minor", "patch"]) {
    if (a[key] !== b[key]) return a[key] < b[key] ? -1 : 1;
  }
  if (a.pre.length === 0 || b.pre.length === 0) {
    return a.pre.length === b.pre.length ? 0 : a.pre.length === 0 ? 1 : -1;
  }
  for (let i = 0; i < Math.max(a.pre.length, b.pre.length); i++) {
    const x = a.pre[i];
    const y = b.pre[i];
    if (x === undefined) return -1;
    if (y === undefined) return 1;
    if (x === y) continue;
    const xNumeric = /^\d+$/.test(x);
    const yNumeric = /^\d+$/.test(y);
    if (xNumeric && yNumeric) return Number(x) < Number(y) ? -1 : 1;
    if (xNumeric) return -1;
    if (yNumeric) return 1;
    return x < y ? -1 : 1;
  }
  return 0;
}

export const PARTIAL = /^v?(\d+|x|X|\*)(?:\.(\d+|x|X|\*))?(?:\.(\d+|x|X|\*))?(?:-([0-9A-Za-z.-]+))?$/;

export function parsePartial(text) {
  const m = PARTIAL.exec(text);
  if (!m) return null;
  const num = (part) => (part === undefined || !/^\d+$/.test(part) ? null : Number(part));
  const major = num(m[1]);
  if (major === null) return { major: null, minor: null, patch: null, pre: [] };
  return { major, minor: num(m[2]), patch: num(m[3]), pre: m[4] ? m[4].split(".") : [] };
}

/** One comparison { op, version } for a single bound of a partial or full version. */
export function bounds(op, partial) {
  const { major, minor, patch, pre } = partial;
  const lower = [major, minor ?? 0, patch ?? 0];
  const nextMajor = [major + 1, 0, 0];
  const nextMinor = [major, (minor ?? 0) + 1, 0];
  const withVersion = (v, comparison) => ({ op: comparison, version: { major: v[0], minor: v[1], patch: v[2], pre } });
  const full = minor !== null && patch !== null;

  switch (op) {
    case "^": {
      if (major > 0 || minor === null) return [withVersion(lower, ">="), withVersion(nextMajor, "<")];
      if (minor > 0 || patch === null) return [withVersion(lower, ">="), withVersion(nextMinor, "<")];
      return [withVersion(lower, ">="), withVersion([0, 0, patch + 1], "<")];
    }
    case "~":
      return [withVersion(lower, ">="), withVersion(minor === null ? nextMajor : nextMinor, "<")];
    case ">":
      if (full) return [withVersion(lower, ">")];
      return [withVersion(minor === null ? nextMajor : nextMinor, ">=")];
    case ">=":
      return [withVersion(lower, ">=")];
    case "<":
      return [withVersion(lower, "<")];
    case "<=":
      if (full) return [withVersion(lower, "<=")];
      return [withVersion(minor === null ? nextMajor : nextMinor, "<")];
    default:
      if (full) return [withVersion(lower, "=")];
      return [withVersion(lower, ">="), withVersion(minor === null ? nextMajor : nextMinor, "<")];
  }
}

export function parseComparator(token) {
  const m = /^(\^|~|>=|<=|>|<|=)?\s*(.+)$/.exec(token);
  if (!m) throw new Error(`unsupported version range "${token}"`);
  const [, op = "=", body] = m;
  if (body === "*" || body === "x" || body === "X") return [];
  const partial = parsePartial(body);
  if (!partial || partial.major === null) throw new Error(`unsupported version range "${token}"`);
  return bounds(op, partial);
}

export function parseAlternative(text) {
  const hyphen = /^(\S+)\s+-\s+(\S+)$/.exec(text);
  if (hyphen) {
    const low = parsePartial(hyphen[1]);
    const high = parsePartial(hyphen[2]);
    if (!low || !high) throw new Error(`unsupported version range "${text}"`);
    return [...bounds(">=", low), ...bounds("<=", high)];
  }
  return text.split(/\s+/).filter(Boolean).flatMap(parseComparator);
}

/** Whether `version` satisfies the semver `range`; a pre-release only matches a range that names one on the same tuple. */
export function satisfies(version, range) {
  const parsed = parseVersion(version);
  if (!parsed) return false;
  const trimmed = range.trim();
  if (trimmed === "" || trimmed === "*" || trimmed === "x" || trimmed === "latest") return parsed.pre.length === 0;
  return trimmed.split("||").some((alternative) => {
    const conditions = parseAlternative(alternative.trim());
    const preAllowed =
      parsed.pre.length === 0 ||
      conditions.some(
        ({ version: v }) =>
          v.pre.length > 0 && v.major === parsed.major && v.minor === parsed.minor && v.patch === parsed.patch,
      );
    return (
      preAllowed &&
      conditions.every(({ op, version: v }) => {
        const order = compareVersions(parsed, v);
        switch (op) {
          case ">":
            return order > 0;
          case ">=":
            return order >= 0;
          case "<":
            return order < 0;
          case "<=":
            return order <= 0;
          default:
            return order === 0;
        }
      })
    );
  });
}

/** The version to resolve a locked one to: itself, else the highest at or below it, else dist-tags.latest, else the highest. */
export function bestVersion(available, locked, latestTag) {
  if (available.includes(locked)) return locked;
  const parsed = available.map((raw) => ({ raw, v: parseVersion(raw) })).filter((x) => x.v !== null);
  const highest = (items) => items.reduce((best, x) => (best === null || compareVersions(x.v, best.v) > 0 ? x : best), null);
  const lockedParsed = parseVersion(locked);
  if (lockedParsed) {
    const atOrBelow = highest(parsed.filter((x) => compareVersions(x.v, lockedParsed) <= 0));
    if (atOrBelow) return atOrBelow.raw;
  }
  if (latestTag && available.includes(latestTag)) return latestTag;
  return highest(parsed)?.raw ?? null;
}
