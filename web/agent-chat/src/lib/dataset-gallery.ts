import type { DatasetRunMode, DatasetView } from "@/ports";

/** An SVG `points` string for a GPS track fitted into a `width`×`height` preview. */
export function gpsPreviewPoints(
  track: { lon: number; lat: number }[],
  width = 260,
  height = 120,
  pad = 10,
): string {
  if (track.length === 0) return "";
  const lons = track.map((point) => point.lon);
  const lats = track.map((point) => point.lat);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const spanLon = Math.max(maxLon - minLon, 1e-9);
  const spanLat = Math.max(maxLat - minLat, 1e-9);
  return track
    .map((point) => {
      const x = pad + ((point.lon - minLon) / spanLon) * (width - 2 * pad);
      const y = height - pad - ((point.lat - minLat) / spanLat) * (height - 2 * pad);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

/** The chat message a gallery run button sends: it names the split tool the agent should use. */
export function datasetRunPrompt(dataset: DatasetView, mode: DatasetRunMode): string {
  if (mode === "rtabmap") {
    return `Run RTAB-Map on the dataset "${dataset.id}" (${dataset.title}). Use run_rtabmap, then tell me the run id, frame and object counts.`;
  }
  if (mode === "sam") {
    return `Run SAM on the dataset "${dataset.id}" (${dataset.title}) looking for "${dataset.defaultPrompt}". Use run_sam_on_dataset, then summarise what it found.`;
  }
  return `Run the dataset "${dataset.id}" (${dataset.title}) with RTAB-Map and SAM looking for "${dataset.defaultPrompt}". Use run_demo, then tell me the run id, frame and object counts.`;
}

/** The thumbnail image URL for a prepared dataset, against the agent server. */
export function datasetThumbnailUrl(serverUrl: string, dataset: DatasetView): string | null {
  if (!dataset.thumbnailAvailable) return null;
  return `${serverUrl.replace(/\/$/, "")}/datasets/${encodeURIComponent(dataset.id)}/thumbnail.jpg`;
}
