"""The streaming sidecar must feed RTAB-Map a sane odometry covariance.

The policy itself (`odom_covariance.h`) is unit-tested in C++ by
`odom_covariance_test.cpp`, which the image build runs; these tests pin
that the sidecar uses it and that the build cannot skip the test.
"""

from pathlib import Path

STREAM_DIR = Path(__file__).parents[1] / "deploy" / "rtabmap-stream"


def test_slam_process_receives_the_prepared_odometry_covariance() -> None:
    # Given the streaming sidecar source
    source = (STREAM_DIR / "main.cpp").read_text(encoding="utf-8")

    # Then Rtabmap::process gets OdomCovariance's output, not the raw
    # matrix or the identity default that made the graph distrust odometry
    assert '#include "odom_covariance.h"' in source
    assert "odomCovariance.next(info.reg.covariance, odomPose.isIdentity())" in source
    assert "slam.process(data, odomPose);" not in source


def test_a_kept_keyframe_restarts_the_carried_covariance() -> None:
    # Given the streaming sidecar source
    source = (STREAM_DIR / "main.cpp").read_text(encoding="utf-8")

    # Then the carried covariance resets exactly where a new node is kept
    keyframe_branch = source.index("lastNodeId = nodeId;")
    assert source.index("odomCovariance.nodeKept();", keyframe_branch) < source.index(
        "cloudFromStereoImages", keyframe_branch
    )


def test_the_image_build_runs_the_covariance_unit_test() -> None:
    # Given the sidecar's build files
    dockerfile = (STREAM_DIR / "Dockerfile").read_text(encoding="utf-8")
    cmake = (STREAM_DIR / "CMakeLists.txt").read_text(encoding="utf-8")

    # Then the test is built and a failing expectation fails the build
    assert "add_executable(odom-covariance-test odom_covariance_test.cpp)" in cmake
    assert "odom_covariance.h odom_covariance_test.cpp" in dockerfile
    assert "&& ./build/odom-covariance-test" in dockerfile
