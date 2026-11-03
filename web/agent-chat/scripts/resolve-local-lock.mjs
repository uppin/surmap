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
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { satisfies, bestVersion } from "./lib/semver.mjs";
import { parseLock, quoteKey, formatLock, readField, writeField, splitKey, lockedPackages, publicTarballUrl } from "./lib/lock-file.mjs";
import { createRegistry } from "./lib/registry.mjs";
import { hostOf, loadLocalPackageCache } from "./lib/local-cache.mjs";

const DEFAULT_LOCAL_REGISTRY = "https://npm.dev.wixpress.com";
const PUBLIC_REGISTRY = "https://registry.yarnpkg.com";
const CONCURRENCY = 10;
const DEPENDENCY_SECTIONS = ["dependencies", "devDependencies", "optionalDependencies"];
const DEFAULT_PROJECT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

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
