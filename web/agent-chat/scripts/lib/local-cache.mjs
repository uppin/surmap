import { readFileSync, readdirSync, statSync } from "node:fs";
import { homedir, platform } from "node:os";
import { join } from "node:path";

// ---------------------------------------------------------------------------
// Local package caches: a tarball already on disk from the private host proves
// the registry served that exact version.
// ---------------------------------------------------------------------------

export const NPM_KEY_PREFIX = "make-fetch-happen:request-cache:";
export const BUN_DEFAULT_HOST = "registry.npmjs.org";

export function listDir(dir) {
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

export function hostOf(url) {
  try {
    return new URL(url).host;
  } catch {
    return null;
  }
}

/** `https://<host>/<prefix>/<name>/-/<file>-<version>.tgz` to name and version, when the host matches. */
export function parseTarballUrl(url, host) {
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

export function readNpmCache(cacheDir, host, add) {
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

export function readYarnCache(cacheDir, host, add) {
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

export function readBunCache(cacheDir, host, add) {
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
export function loadLocalPackageCache(registryUrl, env) {
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
