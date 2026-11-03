#!/usr/bin/env node
/**
 * Resolves web/agent-chat/yarn.lock against the private npm registry, then
 * points every `resolved` URL back at the public registry.
 *
 * Why: this machine has no route to the public npm registry, but the private
 * registry serves the CVE-protected versions. The lock must pin exactly those
 * versions while staying installable from public runners.
 *
 *   node scripts/resolve-local-lock.mjs            rewrite yarn.lock (and package.json ranges)
 *   node scripts/resolve-local-lock.mjs --check    verify the committed lock, write nothing
 *   --project <dir>   project root (default: the directory above scripts/)
 *   LOCAL_REGISTRY_URL  private registry (default https://npm.dev.wixpress.com)
 *
 * Zero dependencies: yarn v1 lock parsing, semver and the package-cache readers
 * are inlined. Behaviour is ported from the bun-based resolver in tddy-coder.
 */
import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { homedir, platform } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_LOCAL_REGISTRY = "https://npm.dev.wixpress.com";
const PUBLIC_REGISTRY = "https://registry.yarnpkg.com";
const CONCURRENCY = 10;
const TIMEOUT_MS = 120_000;
const DEPENDENCY_SECTIONS = ["dependencies", "devDependencies", "optionalDependencies"];
const DEFAULT_PROJECT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

// ---------------------------------------------------------------------------
// Semver: exact versions, ^ ~ comparators, x-ranges, hyphen ranges and ||.
// ---------------------------------------------------------------------------

function parseVersion(text) {
  const m = /^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$/.exec(text);
  if (!m) return null;
  return {
    major: Number(m[1]),
    minor: Number(m[2]),
    patch: Number(m[3]),
    pre: m[4] ? m[4].split(".") : [],
  };
}

function compareVersions(a, b) {
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

const PARTIAL = /^v?(\d+|x|X|\*)(?:\.(\d+|x|X|\*))?(?:\.(\d+|x|X|\*))?(?:-([0-9A-Za-z.-]+))?$/;

function parsePartial(text) {
  const m = PARTIAL.exec(text);
  if (!m) return null;
  const num = (part) => (part === undefined || !/^\d+$/.test(part) ? null : Number(part));
  const major = num(m[1]);
  if (major === null) return { major: null, minor: null, patch: null, pre: [] };
  return { major, minor: num(m[2]), patch: num(m[3]), pre: m[4] ? m[4].split(".") : [] };
}

/** One comparison { op, version } for a single bound of a partial or full version. */
function bounds(op, partial) {
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

function parseComparator(token) {
  const m = /^(\^|~|>=|<=|>|<|=)?\s*(.+)$/.exec(token);
  if (!m) throw new Error(`unsupported version range "${token}"`);
  const [, op = "=", body] = m;
  if (body === "*" || body === "x" || body === "X") return [];
  const partial = parsePartial(body);
  if (!partial || partial.major === null) throw new Error(`unsupported version range "${token}"`);
  return bounds(op, partial);
}

function parseAlternative(text) {
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
function satisfies(version, range) {
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
function bestVersion(available, locked, latestTag) {
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

// ---------------------------------------------------------------------------
// yarn v1 lockfile: entries are kept as raw lines so untouched text stays byte-identical.
// ---------------------------------------------------------------------------

function parseLock(text) {
  const head = [];
  const entries = [];
  let current = null;
  for (const line of text.split("\n")) {
    if (line === "") {
      current = null;
    } else if (!line.startsWith(" ") && !line.startsWith("#")) {
      current = { header: line, keys: parseKeys(line), body: [] };
      entries.push(current);
    } else if (current) {
      current.body.push(line);
    } else {
      head.push(line);
    }
  }
  return { head, entries };
}

function parseKeys(header) {
  return header
    .slice(0, -1)
    .split(", ")
    .map((key) => (key.startsWith('"') ? JSON.parse(key) : key));
}

function quoteKey(key) {
  const needsQuotes = /[:\s\n\\",[\]]/.test(key) || !/^[a-zA-Z]/.test(key) || /^(true|false)/.test(key);
  return needsQuotes ? JSON.stringify(key) : key;
}

function formatLock(lock) {
  const entries = lock.entries.map((entry) => [entry.header, ...entry.body].join("\n"));
  return `${lock.head.join("\n")}\n\n\n${entries.join("\n\n")}\n`;
}

function readField(entry, name) {
  const line = entry.body.find((l) => l.startsWith(`  ${name} `));
  if (line === undefined) return undefined;
  const raw = line.slice(name.length + 3);
  return name === "integrity" ? raw : JSON.parse(raw);
}

function writeField(entry, name, value) {
  const line = `  ${name} ${name === "integrity" ? value : JSON.stringify(value)}`;
  const index = entry.body.findIndex((l) => l.startsWith(`  ${name} `));
  if (index >= 0) {
    entry.body[index] = line;
    return;
  }
  const after = entry.body.findIndex((l) => l.startsWith("  resolved "));
  entry.body.splice(after >= 0 ? after + 1 : 0, 0, line);
}

function splitKey(key) {
  const at = key.indexOf("@", 1);
  return at < 0 ? { name: key, range: "" } : { name: key.slice(0, at), range: key.slice(at + 1) };
}

/** The unique registry packages the lock pins, keyed `name@version`. Non-registry entries are reported and skipped. */
function lockedPackages(lock, log) {
  const packages = new Map();
  for (const entry of lock.entries) {
    const version = readField(entry, "version");
    const resolved = readField(entry, "resolved");
    const { name } = splitKey(entry.keys[0]);
    if (version === undefined) continue;
    if (resolved === undefined || !/^https?:\/\//.test(resolved)) {
      log.push(`[SKIP] ${name}@${version}: not a registry package`);
      continue;
    }
    packages.set(`${name}@${version}`, { name, version });
  }
  return packages;
}

function publicTarballUrl(name, version, shasum) {
  const file = name.split("/").at(-1);
  return `${PUBLIC_REGISTRY}/${name}/-/${file}-${version}.tgz${shasum ? `#${shasum}` : ""}`;
}

// ---------------------------------------------------------------------------
// Private registry client.
// ---------------------------------------------------------------------------

async function getJson(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(url, { headers: { accept: "application/json" }, signal: controller.signal });
    if (response.status === 404) return null;
    if (!response.ok) throw new Error(`${url} answered ${response.status}`);
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

function createRegistry(base) {
  const encode = (name) => name.replace("/", "%2F");
  return {
    base,
    /** The exact version document, or null when the registry does not serve that version. */
    async version(name, version) {
      const doc = await getJson(`${base}/${encode(name)}/${version}`);
      return doc && doc.version === version ? doc : null;
    },
    /** The package document listing every version, or null when the package is unknown. */
    packument(name) {
      return getJson(`${base}/${encode(name)}`);
    },
  };
}

// ---------------------------------------------------------------------------
// Local package caches: a tarball already on disk from the private host proves
// the registry served that exact version.
// ---------------------------------------------------------------------------

const NPM_KEY_PREFIX = "make-fetch-happen:request-cache:";
const BUN_DEFAULT_HOST = "registry.npmjs.org";

function listDir(dir) {
  try {
    return readdirSync(dir);
  } catch {
    return [];
  }
}

function* walkFiles(dir) {
  for (const entry of listDir(dir)) {
    const path = join(dir, entry);
    let stats;
    try {
      stats = statSync(path);
    } catch {
      continue;
    }
    if (stats.isDirectory()) yield* walkFiles(path);
    else if (stats.isFile()) yield path;
  }
}

function hostOf(url) {
  try {
    return new URL(url).host;
  } catch {
    return null;
  }
}

/** `https://<host>/<prefix>/<name>/-/<file>-<version>.tgz` to name and version, when the host matches. */
function parseTarballUrl(url, host) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  if (parsed.host !== host || !parsed.pathname.endsWith(".tgz")) return null;
  const path = decodeURIComponent(parsed.pathname);
  const sep = path.lastIndexOf("/-/");
  if (sep < 0) return null;
  const segments = path.slice(0, sep).split("/").filter(Boolean);
  const last = segments.at(-1);
  if (!last) return null;
  const scope = segments.at(-2);
  const name = last.includes("/") ? last : scope?.startsWith("@") ? `${scope}/${last}` : last;
  const file = path.slice(sep + 3, -".tgz".length);
  const basename = name.split("/").at(-1);
  for (const prefix of [`${name}-`, `${basename}-`]) {
    if (file.startsWith(prefix)) return { name, version: file.slice(prefix.length) };
  }
  return null;
}

function readNpmCache(cacheDir, host, add) {
  for (const file of walkFiles(join(cacheDir, "index-v5"))) {
    for (const line of readFileSync(file, "utf-8").split("\n")) {
      const tab = line.indexOf("\t");
      if (tab < 0) continue;
      let record;
      try {
        record = JSON.parse(line.slice(tab + 1));
      } catch {
        continue;
      }
      if (!record.key?.startsWith(NPM_KEY_PREFIX) || !record.integrity) continue;
      const pkg = parseTarballUrl(record.key.slice(NPM_KEY_PREFIX.length), host);
      if (pkg) add(pkg.name, pkg.version, { source: "npm", integrity: record.integrity });
    }
  }
}

function* packageDirs(modulesDir) {
  for (const entry of listDir(modulesDir)) {
    if (entry.startsWith("@")) {
      for (const scoped of listDir(join(modulesDir, entry))) yield join(modulesDir, entry, scoped);
    } else {
      yield join(modulesDir, entry);
    }
  }
}

function readYarnCache(cacheDir, host, add) {
  for (const entry of listDir(cacheDir)) {
    if (!entry.startsWith("npm-")) continue;
    for (const pkgDir of packageDirs(join(cacheDir, entry, "node_modules"))) {
      let metadata;
      try {
        metadata = JSON.parse(readFileSync(join(pkgDir, ".yarn-metadata.json"), "utf-8"));
      } catch {
        continue;
      }
      const { name, version } = metadata.manifest ?? {};
      const resolved = metadata.remote?.resolved;
      if (!name || !version || !resolved || hostOf(resolved) !== host) continue;
      add(name, version, { source: "yarn", integrity: metadata.remote?.integrity });
    }
  }
}

function readBunCache(cacheDir, host, add) {
  const parseEntry = (entry) => {
    const m = /^(.+)@@@\d+$/.exec(entry);
    if (!m) return;
    let spec = m[1];
    let entryHost = BUN_DEFAULT_HOST;
    const hostSep = spec.lastIndexOf("@@");
    if (hostSep >= 0) {
      entryHost = spec.slice(hostSep + 2);
      spec = spec.slice(0, hostSep);
    }
    const at = spec.lastIndexOf("@");
    if (entryHost !== host || at <= 0) return;
    add(spec.slice(0, at), spec.slice(at + 1), { source: "bun" });
  };
  for (const entry of listDir(cacheDir)) {
    if (entry.startsWith("@")) {
      for (const scoped of listDir(join(cacheDir, entry))) parseEntry(`${entry}/${scoped}`);
    } else {
      parseEntry(entry);
    }
  }
}

/** `name@version` to cache record, for tarballs fetched from `registryUrl`'s host; npm, then yarn, then bun. */
function loadLocalPackageCache(registryUrl, env) {
  const host = new URL(registryUrl).host;
  const home = homedir();
  const index = new Map();
  const add = (name, version, entry) => {
    const key = `${name}@${version}`;
    if (!index.has(key)) index.set(key, entry);
  };
  const npmDir = join(env.npm_config_cache ?? join(home, ".npm"), "_cacache");
  const yarnDir =
    env.YARN_CACHE_FOLDER ??
    (platform() === "darwin"
      ? join(home, "Library", "Caches", "Yarn", "v6")
      : join(env.XDG_CACHE_HOME ?? join(home, ".cache"), "yarn", "v6"));
  const bunDir = env.BUN_INSTALL_CACHE_DIR ?? join(env.BUN_INSTALL ?? join(home, ".bun"), "install", "cache");
  readNpmCache(npmDir, host, add);
  readYarnCache(yarnDir, host, add);
  readBunCache(bunDir, host, add);
  return index;
}

// ---------------------------------------------------------------------------
// Resolution.
// ---------------------------------------------------------------------------

async function mapLimit(items, limit, fn) {
  const results = new Array(items.length);
  let next = 0;
  const worker = async () => {
    while (next < items.length) {
      const index = next++;
      results[index] = await fn(items[index]);
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return results;
}

/** What the private registry (or a local cache) says `name@locked` resolves to. */
async function resolvePackage({ name, version: locked }, registry, cache) {
  const served = await registry.version(name, locked);
  if (served) return { name, locked, version: locked, dist: served.dist, source: "registry" };

  const cached = cache().get(`${name}@${locked}`);
  if (cached) return { name, locked, version: locked, dist: { integrity: cached.integrity }, source: `cache:${cached.source}` };

  const packument = await registry.packument(name);
  if (!packument) throw new Error(`${name}@${locked}: unknown to the private registry`);
  const best = bestVersion(Object.keys(packument.versions ?? {}), locked, packument["dist-tags"]?.latest);
  if (!best) throw new Error(`${name}@${locked}: the private registry has no version to resolve it to`);
  return { name, locked, version: best, dist: packument.versions[best].dist, source: "registry" };
}

function declaredSpec(pkg, name) {
  for (const section of DEPENDENCY_SECTIONS) {
    if (pkg[section]?.[name] !== undefined) return { section, spec: pkg[section][name] };
  }
  return null;
}

/** Rewrites one lock entry to a resolved result; pins the package.json range when the new version falls outside it. */
function applyResult(entry, result, pkg, log) {
  const { name, locked, version, dist } = result;
  if (version === locked) {
    writeField(entry, "resolved", publicTarballUrl(name, version, dist.shasum));
    if (dist.integrity) writeField(entry, "integrity", dist.integrity);
    return 0;
  }
  log.push(`[CHANGED] ${name}: ${locked} -> ${version}`);
  let pinned = 0;
  const keys = entry.keys.map((key) => {
    const { name: keyName, range } = splitKey(key);
    const declared = declaredSpec(pkg, keyName);
    if (!declared || declared.spec !== range || satisfies(version, range)) return key;
    pkg[declared.section][keyName] = version;
    pinned += 1;
    log.push(`[PINNED] package.json ${keyName}: ${range} -> ${version}`);
    return `${keyName}@${version}`;
  });
  if (keys.some((key, i) => key !== entry.keys[i])) {
    entry.keys = keys;
    entry.header = `${keys.map(quoteKey).join(", ")}:`;
  }
  writeField(entry, "version", version);
  writeField(entry, "resolved", publicTarballUrl(name, version, dist.shasum));
  if (dist.integrity) writeField(entry, "integrity", dist.integrity);
  return pinned;
}

async function resolveLock(project, registryUrl, log) {
  const lockPath = join(project, "yarn.lock");
  const packagePath = join(project, "package.json");
  const lock = parseLock(readFileSync(lockPath, "utf-8"));
  const pkg = JSON.parse(readFileSync(packagePath, "utf-8"));
  const registry = createRegistry(registryUrl);
  let cache = null;
  const lazyCache = () => {
    cache ??= loadLocalPackageCache(registryUrl, process.env);
    return cache;
  };

  const packages = [...lockedPackages(lock, log).values()];
  const results = new Map();
  for (const result of await mapLimit(packages, CONCURRENCY, (p) => resolvePackage(p, registry, lazyCache))) {
    results.set(`${result.name}@${result.locked}`, result);
  }

  let pinned = 0;
  for (const entry of lock.entries) {
    const version = readField(entry, "version");
    const resolved = readField(entry, "resolved");
    if (version === undefined || resolved === undefined || !/^https?:\/\//.test(resolved)) continue;
    const { name } = splitKey(entry.keys[0]);
    pinned += applyResult(entry, results.get(`${name}@${version}`), pkg, log);
  }

  const counts = { registry: 0, cache: 0, changed: 0 };
  for (const result of results.values()) {
    if (result.source === "registry") counts.registry += 1;
    else counts.cache += 1;
    if (result.version !== result.locked) counts.changed += 1;
  }
  writeFileSync(lockPath, formatLock(lock));
  if (pinned > 0) writeFileSync(packagePath, `${JSON.stringify(pkg, null, 2)}\n`);
  return { ...counts, total: results.size, pinned };
}

async function checkLock(project, registryUrl, log) {
  const lock = parseLock(readFileSync(join(project, "yarn.lock"), "utf-8"));
  const pkg = JSON.parse(readFileSync(join(project, "package.json"), "utf-8"));
  const registry = createRegistry(registryUrl);
  const problems = [];

  const lockedKeys = new Set(lock.entries.flatMap((entry) => entry.keys));
  for (const section of DEPENDENCY_SECTIONS) {
    for (const [name, spec] of Object.entries(pkg[section] ?? {})) {
      if (!lockedKeys.has(`${name}@${spec}`)) problems.push(`[STALE] ${name}@${spec}: not in yarn.lock`);
    }
  }

  const checks = [];
  for (const entry of lock.entries) {
    const version = readField(entry, "version");
    const resolved = readField(entry, "resolved");
    if (version === undefined || resolved === undefined) continue;
    const { name } = splitKey(entry.keys[0]);
    const label = `${name}@${version}`;
    if (!resolved.startsWith(`${PUBLIC_REGISTRY}/`)) {
      problems.push(`[HOST] ${label}: resolved points at ${hostOf(resolved)}, not ${new URL(PUBLIC_REGISTRY).host}`);
      continue;
    }
    checks.push({ name, version, label, resolved, integrity: readField(entry, "integrity") });
  }

  const unique = new Map(checks.map((c) => [c.label, c]));
  await mapLimit([...unique.values()], CONCURRENCY, async (c) => {
    const served = await registry.version(c.name, c.version);
    if (!served) {
      problems.push(`[MISSING] ${c.label}: not served by ${registryUrl}`);
      return;
    }
    if (served.dist.integrity && c.integrity !== served.dist.integrity) {
      problems.push(`[INTEGRITY] ${c.label}: yarn.lock integrity differs from ${registryUrl}`);
    }
    const shasum = c.resolved.split("#")[1];
    if (shasum && served.dist.shasum && shasum !== served.dist.shasum) {
      problems.push(`[SHASUM] ${c.label}: resolved #${shasum} differs from ${registryUrl}`);
    }
  });

  for (const problem of problems.sort()) log.push(problem);
  return { total: unique.size, problems: problems.length };
}

async function main(argv) {
  const options = { check: false, project: DEFAULT_PROJECT };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--check") options.check = true;
    else if (argv[i] === "--project") options.project = resolve(argv[++i] ?? "");
    else throw new Error(`unknown argument: ${argv[i]}`);
  }
  const registryUrl = (process.env.LOCAL_REGISTRY_URL ?? DEFAULT_LOCAL_REGISTRY).replace(/\/+$/, "");
  const log = [];

  if (options.check) {
    const { total, problems } = await checkLock(options.project, registryUrl, log);
    for (const line of log) console.log(line);
    if (problems > 0) {
      console.error(`resolve-local-lock: yarn.lock failed the check (${problems} problem(s) across ${total} package(s))`);
      return 1;
    }
    console.log(`resolve-local-lock: yarn.lock OK, ${total} package(s) on ${PUBLIC_REGISTRY} and served by ${registryUrl}`);
    return 0;
  }

  const summary = await resolveLock(options.project, registryUrl, log);
  for (const line of log) console.log(line);
  console.log(
    `resolve-local-lock: ${summary.total} package(s): ${summary.registry} served by ${registryUrl}, ` +
      `${summary.cache} kept from a local cache, ${summary.changed} changed, ${summary.pinned} package.json range(s) pinned`,
  );
  return 0;
}

main(process.argv.slice(2))
  .then((code) => {
    process.exitCode = code;
  })
  .catch((error) => {
    console.error(`resolve-local-lock: ${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
  });
