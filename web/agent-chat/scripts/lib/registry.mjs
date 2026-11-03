const TIMEOUT_MS = 120_000;

// ---------------------------------------------------------------------------
// Private registry client.
// ---------------------------------------------------------------------------

export async function getJson(url) {
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

export function createRegistry(base) {
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
