import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { DatasetRunView, DatasetView } from "@/ports";
import { DatasetGallery } from "./DatasetGallery";

function aDataset(overrides: Partial<DatasetView> = {}): DatasetView {
  return {
    id: "kitti-2011-09-26-drive-0009-color",
    title: "KITTI drive 0009 (colour)",
    description: "Karlsruhe city drive.",
    provider: "KITTI",
    licenseName: "CC BY-NC-SA 3.0",
    licenseUrl: "https://creativecommons.org/licenses/by-nc-sa/3.0/",
    attribution: "KITTI raw data, Geiger et al., CC BY-NC-SA 3.0",
    modality: "color",
    officialUrl: "https://www.cvlibs.net/datasets/kitti/raw_data.php",
    defaultPrompt: "car",
    prepared: true,
    frameCount: 447,
    thumbnailAvailable: true,
    thumbnailUrl: "",
    locationLabel: "Karlsruhe, Germany (approx.)",
    gpsCentre: { lon: 8.425, lat: 49.015 },
    gpsTrack: [
      { lon: 8.42, lat: 49.01 },
      { lon: 8.43, lat: 49.02 },
    ],
    runs: [],
    ...overrides,
  };
}

function aRun(overrides: Partial<DatasetRunView> = {}): DatasetRunView {
  return {
    cacheKey: "rtabmap+sam=car",
    runId: "r-1",
    title: "KITTI drive 0009 (colour) · SAM: car",
    frames: 447,
    createdAt: 1_700_000_000,
    previewFrameId: 3,
    ...overrides,
  };
}

describe("dataset gallery", () => {
  it("shows a thumbnail, the licence and a GPS map preview for a dataset", () => {
    // Given a prepared colour KITTI dataset with a GPS track
    render(<DatasetGallery datasets={[aDataset()]} serverUrl="http://127.0.0.1:8780" onRun={() => {}} />);

    // Then its card carries the thumbnail, colour badge, licence link and GPS preview
    expect(screen.getByAltText(/First frame of KITTI/)).toHaveAttribute(
      "src",
      "http://127.0.0.1:8780/datasets/kitti-2011-09-26-drive-0009-color/thumbnail.jpg",
    );
    expect(screen.getByText("Colour")).toBeVisible();
    expect(screen.getByRole("link", { name: "CC BY-NC-SA 3.0" })).toHaveAttribute(
      "href",
      "https://creativecommons.org/licenses/by-nc-sa/3.0/",
    );
    expect(screen.getByLabelText(/GPS map preview/)).toBeVisible();
    expect(screen.getByText(/GPS track/)).toBeVisible();
  });

  it("asks the agent to run RTAB-Map alone when its button is clicked", async () => {
    // Given a gallery with one dataset
    const onRun = vi.fn();
    render(<DatasetGallery datasets={[aDataset()]} serverUrl="http://127.0.0.1:8780" onRun={onRun} />);

    // When RTAB-Map is chosen
    await userEvent.click(screen.getByRole("button", { name: "Run RTAB-Map" }));

    // Then the agent is asked with the split RTAB-Map tool named
    expect(onRun).toHaveBeenCalledWith(expect.stringContaining("run_rtabmap"));
    expect(onRun).toHaveBeenCalledWith(expect.stringContaining("kitti-2011-09-26-drive-0009-color"));
  });

  it("asks the agent to run SAM alone when its button is clicked", async () => {
    // Given a gallery with one dataset
    const onRun = vi.fn();
    render(<DatasetGallery datasets={[aDataset()]} serverUrl="http://127.0.0.1:8780" onRun={onRun} />);

    // When SAM is chosen
    await userEvent.click(screen.getByRole("button", { name: "Run SAM" }));

    // Then the agent is asked with the split SAM tool and the default concept
    expect(onRun).toHaveBeenCalledWith(expect.stringContaining("run_sam_on_dataset"));
    expect(onRun).toHaveBeenCalledWith(expect.stringContaining('"car"'));
  });

  it("filters the gallery by search text and modality", async () => {
    // Given colour and grey datasets
    const datasets = [
      aDataset(),
      aDataset({ id: "euroc-v1-01-easy", title: "EuRoC V1_01_easy", modality: "grey" }),
    ];
    render(<DatasetGallery datasets={datasets} serverUrl="http://127.0.0.1:8780" onRun={() => {}} />);

    // When the search names only EuRoC
    await userEvent.type(screen.getByLabelText("Search datasets"), "EuRoC");

    // Then only its card remains
    expect(screen.getByText("EuRoC V1_01_easy")).toBeVisible();
    expect(screen.queryByText(/KITTI drive 0009/)).not.toBeInTheDocument();
    expect(screen.getByText(/1 of 2 datasets/)).toBeVisible();
  });

  it("shows a grey badge and no-GPS note for an indoor grey dataset", () => {
    // Given an indoor grey dataset without GPS
    const dataset = aDataset({
      id: "euroc-v1-01-easy",
      title: "EuRoC V1_01_easy",
      modality: "grey",
      thumbnailAvailable: false,
      gpsCentre: null,
      gpsTrack: [],
      locationLabel: "Vicon Room 1 (indoor, no GPS)",
    });
    render(<DatasetGallery datasets={[dataset]} serverUrl="http://127.0.0.1:8780" onRun={() => {}} />);

    // Then it is badged grey, has no thumbnail image, and says why there is no map track
    expect(screen.getByText("Grey")).toBeVisible();
    expect(screen.queryByAltText(/First frame/)).not.toBeInTheDocument();
    expect(screen.getByText(/no GPS/)).toBeVisible();
  });

  it("badges a built dataset Cached and lists its runs with a preview frame", () => {
    // Given a dataset with an RTAB-Map + SAM run and an RTAB-Map-only run
    const runs = [aRun(), aRun({ cacheKey: "rtabmap;frames=100", runId: "r-2", frames: 100 })];
    render(<DatasetGallery datasets={[aDataset({ runs })]} serverUrl="http://127.0.0.1:8780" onRun={() => {}} />);

    // Then the card is badged Cached and its Runs list each key with a preview of the run
    expect(screen.getByText("Cached")).toBeVisible();
    const list = screen.getByRole("list", { name: "Runs" });
    expect(within(list).getByText("rtabmap+sam=car")).toBeVisible();
    expect(within(list).getByText("rtabmap;frames=100")).toBeVisible();
    expect(within(list).getByAltText("Preview of run rtabmap+sam=car")).toHaveAttribute(
      "src",
      "http://127.0.0.1:8780/frames/r-1/3.jpg?max_side=320",
    );
  });

  it("asks the agent to run a cached run when its Run button is clicked", async () => {
    // Given a dataset with a cached run
    const onRun = vi.fn();
    render(
      <DatasetGallery datasets={[aDataset({ runs: [aRun()] })]} serverUrl="http://127.0.0.1:8780" onRun={onRun} />,
    );

    // When that run is run
    await userEvent.click(screen.getByRole("button", { name: "Run cached rtabmap+sam=car" }));

    // Then the agent is asked to use run_cached on that run id
    expect(onRun).toHaveBeenCalledWith(expect.stringContaining("run_cached"));
    expect(onRun).toHaveBeenCalledWith(expect.stringContaining('"r-1"'));
  });

  it("shows no Cached badge or Runs list before the first build", () => {
    // Given a dataset never built
    render(<DatasetGallery datasets={[aDataset()]} serverUrl="http://127.0.0.1:8780" onRun={() => {}} />);

    // Then it has neither
    expect(screen.queryByText("Cached")).not.toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Runs" })).not.toBeInTheDocument();
  });
});
