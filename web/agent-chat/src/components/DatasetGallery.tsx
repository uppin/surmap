import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { datasetRunPrompt, datasetThumbnailUrl, gpsPreviewPoints } from "@/lib/dataset-gallery";
import type { DatasetRunMode, DatasetView } from "@/ports";

export interface DatasetGalleryProps {
  datasets: DatasetView[];
  serverUrl: string;
  /** Asks the agent (through the chat) to run a dataset in the chosen mode. */
  onRun: (text: string) => void;
}

/** The dataset gallery: one card per registered dataset, whatever its source. */
export function DatasetGallery(props: DatasetGalleryProps): ReactNode {
  if (props.datasets.length === 0) {
    return (
      <section aria-label="Dataset gallery" className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold">Dataset gallery</h2>
        <p className="text-xs text-muted-foreground">No datasets are available from the agent server yet.</p>
      </section>
    );
  }
  return (
    <section aria-label="Dataset gallery" className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">Dataset gallery</h2>
        <p className="text-xs text-muted-foreground">
          Grey and colour datasets. Run buttons ask the agent to use its RTAB-Map / SAM tools.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {props.datasets.map((dataset) => (
          <DatasetCard key={dataset.id} dataset={dataset} serverUrl={props.serverUrl} onRun={props.onRun} />
        ))}
      </div>
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
