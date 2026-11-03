import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { DatasetView } from "@/ports";
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
    locationLabel: "Karlsruhe, Germany (approx.)",
    gpsCentre: { lon: 8.425, lat: 49.015 },
    gpsTrack: [
      { lon: 8.42, lat: 49.01 },
      { lon: 8.43, lat: 49.02 },
    ],
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
});
