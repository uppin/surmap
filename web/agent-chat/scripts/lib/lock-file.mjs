const PUBLIC_REGISTRY = "https://registry.yarnpkg.com";

// ---------------------------------------------------------------------------
// yarn v1 lockfile: entries are kept as raw lines so untouched text stays byte-identical.
// ---------------------------------------------------------------------------

export function parseLock(text) {
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

export function parseKeys(header) {
  return header
    .slice(0, -1)
    .split(", ")
    .map((key) => (key.startsWith('"') ? JSON.parse(key) : key));
}

export function quoteKey(key) {
  const needsQuotes = /[:\s\n\\",[\]]/.test(key) || !/^[a-zA-Z]/.test(key) || /^(true|false)/.test(key);
  return needsQuotes ? JSON.stringify(key) : key;
}

export function formatLock(lock) {
  const entries = lock.entries.map((entry) => [entry.header, ...entry.body].join("\n"));
  return `${lock.head.join("\n")}\n\n\n${entries.join("\n\n")}\n`;
}

export function readField(entry, name) {
  const line = entry.body.find((l) => l.startsWith(`  ${name} `));
  if (line === undefined) return undefined;
  const raw = line.slice(name.length + 3);
  return name === "integrity" ? raw : JSON.parse(raw);
}

export function writeField(entry, name, value) {
  const line = `  ${name} ${name === "integrity" ? value : JSON.stringify(value)}`;
  const index = entry.body.findIndex((l) => l.startsWith(`  ${name} `));
  if (index >= 0) {
    entry.body[index] = line;
    return;
  }
  const after = entry.body.findIndex((l) => l.startsWith("  resolved "));
  entry.body.splice(after >= 0 ? after + 1 : 0, 0, line);
}

export function splitKey(key) {
  const at = key.indexOf("@", 1);
  return at < 0 ? { name: key, range: "" } : { name: key.slice(0, at), range: key.slice(at + 1) };
}

/** The unique registry packages the lock pins, keyed `name@version`. Non-registry entries are reported and skipped. */
export function lockedPackages(lock, log) {
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

export function publicTarballUrl(name, version, shasum) {
  const file = name.split("/").at(-1);
  return `${PUBLIC_REGISTRY}/${name}/-/${file}-${version}.tgz${shasum ? `#${shasum}` : ""}`;
}
