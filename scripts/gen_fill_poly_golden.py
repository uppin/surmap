"""Golden `cv::fillPoly` masks for tests/fixtures/fill_poly_golden.json.

`surmap.slam.dense.fill_poly` must cover exactly the pixels the
streaming sidecar's OpenCV does. Run this inside the sidecar's base
image, so the goldens come from that OpenCV (4.6) rather than a
pip wheel (5.x clips off-frame edges differently):

    docker run --rm --platform linux/amd64 -v "$PWD:/work" --entrypoint python3 \
        introlab3it/rtabmap@sha256:14a58ac31565f0a0ab2421fa861f6fc43010e54345e13a6a1ccde32d3b0ffdb8 \
        /work/scripts/gen_fill_poly_golden.py /work/tests/fixtures/fill_poly_golden.json
"""

import json, sys
import numpy as np, cv2

W, H = 64, 40
rng = np.random.default_rng(7)
cases = {
    "axis_square": [[10, 10], [30, 10], [30, 25], [10, 25]],
    "slanted_quad": [[5, 3], [40, 9], [33, 31], [2, 22]],
    "concave_arrow": [[4, 20], [30, 4], [24, 18], [50, 20], [24, 22], [30, 36]],
    "self_intersecting_bowtie": [[6, 6], [50, 34], [50, 6], [6, 34]],
    "thin_sliver": [[2, 2], [60, 3], [61, 4]],
    "off_frame": [[-10, -5], [70, 12], [40, 55], [-3, 30]],
    "horizontal_degenerate": [[5, 10], [40, 10], [20, 10]],
    "sam_like_outline": [
        [int(32 + r * np.cos(a)), int(20 + 0.6 * r * np.sin(a))]
        for a, r in zip(np.linspace(0, 2 * np.pi, 37)[:-1], 14 + 6 * rng.random(36))
    ],
}
golden = {"cv2_version": cv2.__version__, "width": W, "height": H, "cases": []}
for name, poly in cases.items():
    mask = np.zeros((H, W), np.uint8)
    cv2.fillPoly(mask, [np.array(poly, np.int32).reshape(-1, 1, 2)], 255)
    rows = [[int(v), *np.flatnonzero(mask[v] > 0).tolist()] for v in range(H) if mask[v].any()]
    golden["cases"].append({"name": name, "polygon": poly, "rows": rows})
json.dump(golden, open(sys.argv[1], "w"), separators=(",", ":"))
print({c["name"]: sum(len(r) - 1 for r in c["rows"]) for c in golden["cases"]})
