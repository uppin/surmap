// Unit test for odom_covariance.h; the image build runs it and fails on
// any broken expectation.
#include "odom_covariance.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

namespace {

int failures = 0;

void expect(bool ok, const char* what) {
  if (!ok) {
    std::fprintf(stderr, "FAIL: %s\n", what);
    ++failures;
  }
}

cv::Mat variance(double v) { return cv::Mat::eye(6, 6, CV_64FC1) * v; }

double head(const cv::Mat& m) { return m.at<double>(0, 0); }

}  // namespace

int main() {
  {
    OdomCovariance c;
    expect(head(c.next(variance(0.01), false)) == 0.01, "a valid covariance is passed through");
  }
  {
    OdomCovariance c;
    expect(head(c.next(cv::Mat(), false)) == 1.0, "an empty covariance becomes the identity");
    expect(head(c.next(variance(-1.0), false)) == 1.0, "a negative variance becomes the identity");
    expect(head(c.next(variance(NAN), false)) == 1.0, "a NaN variance becomes the identity");
    expect(head(c.next(cv::Mat::eye(3, 3, CV_64FC1), false)) == 1.0,
           "a matrix of the wrong shape becomes the identity");
  }
  {
    OdomCovariance c;
    c.next(variance(0.04), false);
    expect(head(c.next(variance(0.01), false)) == 0.04,
           "the largest covariance since the last kept node is carried");
    c.nodeKept();
    expect(head(c.next(variance(0.01), false)) == 0.01, "a kept node starts the next link afresh");
  }
  {
    OdomCovariance c;
    c.next(variance(0.04), false);
    expect(head(c.next(variance(1.0), false)) == 0.04, "odometry's 1.0 'unknown' is not carried");
  }
  {
    OdomCovariance c;
    c.next(variance(0.04), false);
    cv::Mat out = c.next(variance(9999.0), false);
    expect(c.resetDetected(), "a 9999 variance after tracking is a reset");
    expect(head(out) == 9999.0, "the reset frame's own covariance reaches the graph");
    expect(head(c.next(variance(0.01), false)) == 9999.0,
           "the link spanning a reset stays uninformative until a node is kept");
  }
  {
    OdomCovariance c;
    c.next(variance(0.04), false);
    expect(head(c.next(variance(0.01), true)) == 0.01, "an identity pose after tracking clears what was carried");
    expect(c.resetDetected(), "an identity pose after tracking is a reset");
  }
  {
    OdomCovariance c;
    c.next(variance(0.01), true);
    expect(!c.resetDetected(), "the first frame's identity pose is not a reset");
  }
  if (failures == 0) std::printf("odom_covariance: all expectations hold\n");
  return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
