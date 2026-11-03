// Odometry covariance for Rtabmap::process, prepared the way RTAB-Map's
// own RtabmapThread prepares it (corelib/src/RtabmapThread.cpp):
//
// - a covariance is used only when it is 6x6 CV_64FC1 with a finite,
//   positive (0,0) that is not exactly 1.0 (odometry's "unknown");
// - between two nodes the graph keeps, the largest such covariance is
//   carried, so the link stays honest when RTAB-Map drops intermediate
//   nodes for too little motion (RGBD/LinearUpdate) — it is then
//   independent of the odometry frame rate;
// - an odometry reset (identity pose after tracking, or (0,0) >= 9999)
//   clears what was carried. RtabmapThread also starts a new map there;
//   the sidecar does not: the reset frame's own 9999 covariance reaches
//   the graph as a link with near-zero information, and keyframes keep
//   one map frame for the host.
//
// With nothing usable carried, the identity (RTAB-Map's default) is used.
#pragma once

#include <opencv2/core.hpp>

#include <cmath>

class OdomCovariance {
 public:
  static constexpr double kResetVariance = 9999.0;

  // One tracked frame: its odometry covariance and whether its pose is
  // the identity. Returns the covariance to pass to Rtabmap::process.
  cv::Mat next(const cv::Mat& covariance, bool poseIsIdentity) {
    resetDetected_ =
        tracked_ && (poseIsIdentity || (isSquare6(covariance) && covariance.at<double>(0, 0) >= kResetVariance));
    if (resetDetected_) carried_ = cv::Mat();
    tracked_ = !poseIsIdentity;
    if (isUsable(covariance) &&
        (carried_.empty() || covariance.at<double>(0, 0) > carried_.at<double>(0, 0))) {
      carried_ = covariance.clone();
    }
    return carried_.empty() ? cv::Mat::eye(6, 6, CV_64FC1) : carried_.clone();
  }

  // The graph kept a new node: the next link starts from it.
  void nodeKept() { carried_ = cv::Mat(); }

  bool resetDetected() const { return resetDetected_; }

 private:
  static bool isSquare6(const cv::Mat& m) {
    return m.rows == 6 && m.cols == 6 && m.type() == CV_64FC1;
  }
  static bool isUsable(const cv::Mat& m) {
    if (!isSquare6(m)) return false;
    double v = m.at<double>(0, 0);
    return std::isfinite(v) && v > 0.0 && v != 1.0;
  }

  cv::Mat carried_;
  bool tracked_ = false;
  bool resetDetected_ = false;
};
