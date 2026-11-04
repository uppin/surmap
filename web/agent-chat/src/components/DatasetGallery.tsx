import { useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  cachedRunPrompt,
  datasetRunPrompt,
  datasetThumbnailUrl,
  filterDatasets,
  gpsPreviewPoints,
  runPreviewUrl,
} from "@/lib/dataset-gallery";
import type { DatasetRunMode, DatasetRunView, DatasetView } from "@/ports";

export interface DatasetGalleryProps {
  datasets: DatasetView[];
  serverUrl: string;
  /** Asks the agent (through the chat) to run a dataset in the chosen mode. */
  onRun: (text: string) => void;
}

/** The dataset gallery: one card per registered dataset, whatever its source. */
export function DatasetGallery(props: DatasetGalleryProps): ReactNode {
  const [query, setQuery] = useState("");
  const [modality, setModality] = useState<"all" | "grey" | "color">("all");
  if (props.datasets.length === 0) {
    return (
      <section aria-label="Dataset gallery" className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold">Dataset gallery</h2>
        <p className="text-xs text-muted-foreground">No datasets are available from the agent server yet.</p>
      </section>
    );
  }
  const shown = filterDatasets(props.datasets, query, modality);
  return (
    <section aria-label="Dataset gallery" className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">Dataset gallery</h2>
        <p className="text-xs text-muted-foreground">
          {shown.length} of {props.datasets.length} datasets. Run buttons ask the agent to use its
          RTAB-Map / SAM tools.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <input
          aria-label="Search datasets"
          className="min-w-52 flex-1 rounded-md border bg-background px-2 py-1.5 text-sm"
          placeholder="Search datasets, e.g. 2011_09_26 drive 0009"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <select
          aria-label="Modality filter"
          className="rounded-md border bg-background px-2 py-1.5 text-sm"
          value={modality}
          onChange={(event) => setModality(event.target.value as "all" | "grey" | "color")}
        >
          <option value="all">Grey + colour</option>
          <option value="grey">Grey only</option>
          <option value="color">Colour only</option>
        </select>
      </div>
      {shown.length === 0 ? (
        <p className="text-xs text-muted-foreground">No datasets match that search.</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {shown.map((dataset) => (
            <DatasetCard key={dataset.id} dataset={dataset} serverUrl={props.serverUrl} onRun={props.onRun} />
          ))}
        </div>
      )}
    </section>
  );
}

function DatasetCard(props: {
  dataset: DatasetView;
  serverUrl: string;
  onRun: (text: string) => void;
}): ReactNode {
  const { dataset } = props;
  const thumbnail = datasetThumbnailUrl(props.serverUrl, dataset);
  const run = (mode: DatasetRunMode) => props.onRun(datasetRunPrompt(dataset, mode));
  return (
    <article aria-label={dataset.title} className="flex flex-col gap-3 rounded-lg border bg-card p-3 text-card-foreground">
      {thumbnail !== null ? (
        <img
          src={thumbnail}
          alt={`First frame of ${dataset.title}`}
          className="aspect-[31/9] w-full rounded-md border object-cover"
          loading="lazy"
        />
      ) : (
        <div className="grid aspect-[31/9] w-full place-items-center rounded-md border bg-muted text-xs text-muted-foreground">
          Thumbnail available after preparation
        </div>
      )}
      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold">{dataset.title}</h3>
          <Badge variant={dataset.modality === "color" ? "default" : "secondary"}>
            {dataset.modality === "color" ? "Colour" : "Grey"}
          </Badge>
          <Badge variant="outline">{dataset.provider}</Badge>
          <Badge variant="outline">{dataset.prepared ? `${dataset.frameCount} pairs` : "Not prepared"}</Badge>
          {dataset.runs.length > 0 && <Badge>Cached</Badge>}
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground">{dataset.description}</p>
      </div>
      <GpsPreview dataset={dataset} />
      <p className="text-xs leading-relaxed">
        Licence:{" "}
        {dataset.licenseUrl ? (
          <a className="underline underline-offset-2" href={dataset.licenseUrl} target="_blank" rel="noreferrer">
            {dataset.licenseName}
          </a>
        ) : (
          dataset.licenseName
        )}{" "}
        · <span className="text-muted-foreground">{dataset.attribution}</span>
      </p>
      {dataset.runs.length > 0 && (
        <DatasetRuns dataset={dataset} serverUrl={props.serverUrl} onRun={props.onRun} />
      )}
      <div className="mt-auto flex flex-wrap gap-2">
        <Button type="button" size="sm" onClick={() => run("rtabmap")}>
          Run RTAB-Map
        </Button>
        <Button type="button" size="sm" variant="secondary" onClick={() => run("sam")}>
          Run SAM
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={() => run("both")}>
          Run both
        </Button>
        <a className="ml-auto text-xs text-muted-foreground underline underline-offset-2" href={dataset.officialUrl} target="_blank" rel="noreferrer">
          Official dataset
        </a>
      </div>
    </article>
  );
}

/** The dataset's runs: one cached build per cache key, each with a preview frame and a Run button. */
function DatasetRuns(props: { dataset: DatasetView; serverUrl: string; onRun: (text: string) => void }): ReactNode {
  const { dataset } = props;
  return (
    <section className="flex flex-col gap-1">
      <h4 className="text-xs font-semibold">Runs</h4>
      <ul aria-label="Runs" className="flex flex-col gap-2">
        {dataset.runs.map((run) => (
          <DatasetRunRow
            key={run.runId}
            run={run}
            serverUrl={props.serverUrl}
            onRun={() => props.onRun(cachedRunPrompt(dataset, run))}
          />
        ))}
      </ul>
    </section>
  );
}

function DatasetRunRow(props: { run: DatasetRunView; serverUrl: string; onRun: () => void }): ReactNode {
  const { run } = props;
  const preview = runPreviewUrl(props.serverUrl, run);
  return (
    <li className="flex items-center gap-2 rounded-md border p-1.5">
      {preview !== null ? (
        <a href={preview.replace(/\?max_side=\d+$/, "")} target="_blank" rel="noreferrer" className="shrink-0">
          <img
            src={preview}
            alt={`Preview of run ${run.cacheKey}`}
            className="h-10 w-16 rounded border object-cover"
            loading="lazy"
          />
        </a>
      ) : (
        <div className="grid h-10 w-16 shrink-0 place-items-center rounded border bg-muted text-[10px] text-muted-foreground">
          No frame
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <code className="truncate text-xs">{run.cacheKey}</code>
        <span className="text-[11px] text-muted-foreground">
          {run.frames} frames · {new Date(run.createdAt * 1000).toLocaleString()}
        </span>
      </div>
      <Button type="button" size="sm" variant="outline" aria-label={`Run cached ${run.cacheKey}`} onClick={props.onRun}>
        Run
      </Button>
    </li>
  );
}

/** A small map preview of the dataset's GPS: the recorded track, or its known centre. */
function GpsPreview(props: { dataset: DatasetView }): ReactNode {
  const { dataset } = props;
  if (dataset.gpsTrack.length > 1) {
    return (
      <figure aria-label={`GPS map preview of ${dataset.title}`} className="flex flex-col gap-1">
        <svg viewBox="0 0 260 120" className="w-full rounded-md border bg-muted/40" role="img" aria-label="GPS track">
          <polyline points={gpsPreviewPoints(dataset.gpsTrack)} fill="none" stroke="currentColor" strokeWidth="2" />
        </svg>
        <figcaption className="text-xs text-muted-foreground">
          GPS track · {dataset.locationLabel || "recorded positions"}
        </figcaption>
      </figure>
    );
  }
  if (dataset.gpsCentre !== null) {
    return (
      <p className="text-xs text-muted-foreground">
        Map preview: {dataset.locationLabel || "GPS centre"} ({dataset.gpsCentre.lat.toFixed(4)},{" "}
        {dataset.gpsCentre.lon.toFixed(4)}) · full GPS track after preparation
      </p>
    );
  }
  return <p className="text-xs text-muted-foreground">Map preview: no GPS for this dataset{dataset.locationLabel ? ` · ${dataset.locationLabel}` : ""}</p>;
}
