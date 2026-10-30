// surmap-rtabmap-stream: live stereo -> RTAB-Map over stdin/stdout.
// Protocol: 4-byte LE length + JSON header (+ length-prefixed payloads
// for pairs) in; JSON lines out. Stereo only: no IMU, no wheel odom.
#include <rtabmap/core/Odometry.h>
#include <rtabmap/core/OdometryInfo.h>
#include <rtabmap/core/Rtabmap.h>
#include <rtabmap/core/SensorData.h>
#include <rtabmap/core/StereoCameraModel.h>
#include <rtabmap/core/Transform.h>
#include <rtabmap/core/util3d.h>
#include <rtabmap/core/util3d_transforms.h>

#include <opencv2/calib3d.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>

#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <map>
#include <string>
#include <vector>

namespace {

bool readExact(unsigned char* dst, size_t n) {
  size_t got = 0;
  while (got < n) {
    size_t r = std::fread(dst + got, 1, n - got, stdin);
    if (r == 0) return false;
    got += r;
  }
  return true;
}

bool readFramed(std::string& out) {
  unsigned char lenBuf[4];
  if (!readExact(lenBuf, 4)) return false;
  uint32_t len = lenBuf[0] | (lenBuf[1] << 8) | (lenBuf[2] << 16) | ((uint32_t)lenBuf[3] << 24);
  out.resize(len);
  return len == 0 || readExact(reinterpret_cast<unsigned char*>(out.data()), len);
}

// Minimal JSON string extraction (values we need are flat).
bool jsonString(const std::string& json, const std::string& key, std::string& out) {
  std::string pat = "\"" + key + "\"";
  size_t pos = json.find(pat);
  if (pos == std::string::npos) return false;
  pos = json.find(':', pos + pat.size());
  if (pos == std::string::npos) return false;
  pos = json.find('"', pos);
  if (pos == std::string::npos) return false;
  out.clear();
  for (size_t i = pos + 1; i < json.size(); ++i) {
    char c = json[i];
    if (c == '\\' && i + 1 < json.size()) {
      char n = json[++i];
      if (n == 'n') out += '\n';
      else if (n == 't') out += '\t';
      else if (n == 'r') out += '\r';
      else out += n;
    } else if (c == '"') {
      return true;
    } else {
      out += c;
    }
  }
  return false;
}

long jsonLong(const std::string& json, const std::string& key, long fallback) {
  std::string pat = "\"" + key + "\"";
  size_t pos = json.find(pat);
  if (pos == std::string::npos) return fallback;
  pos = json.find(':', pos + pat.size());
  if (pos == std::string::npos) return fallback;
  return std::strtol(json.c_str() + pos + 1, nullptr, 10);
}

double jsonDouble(const std::string& json, const std::string& key, double fallback) {
  std::string pat = "\"" + key + "\"";
  size_t pos = json.find(pat);
  if (pos == std::string::npos) return fallback;
  pos = json.find(':', pos + pat.size());
  if (pos == std::string::npos) return fallback;
  return std::strtod(json.c_str() + pos + 1, nullptr);
}

std::vector<double> numbersAfter(const std::string& text, const std::string& key) {
  std::vector<double> values;
  size_t pos = text.find(key);
  if (pos == std::string::npos) return values;
  size_t open = text.find('[', pos);
  size_t close = text.find(']', open);
  if (open == std::string::npos || close == std::string::npos) return values;
  std::string body = text.substr(open + 1, close - open - 1);
  const char* p = body.c_str();
  while (*p) {
    char* end = nullptr;
    double v = std::strtod(p, &end);
    if (end == p) { ++p; } else { values.push_back(v); p = end; }
  }
  return values;
}

struct CamCalib {
  cv::Mat K, D, Tbs;  // Tbs: 4x4
};

CamCalib parseCam(const std::string& yaml, int w, int h) {
  CamCalib c;
  auto intr = numbersAfter(yaml, "intrinsics:");
  auto dist = numbersAfter(yaml, "distortion_coefficients:");
  auto data = numbersAfter(yaml, "data:");
  c.K = (cv::Mat_<double>(3, 3) << intr[0], 0, intr[2], 0, intr[1], intr[3], 0, 0, 1);
  c.D = cv::Mat::zeros(1, dist.size(), CV_64F);
  for (size_t i = 0; i < dist.size(); ++i) c.D.at<double>(0, (int)i) = dist[i];
  c.Tbs = cv::Mat::eye(4, 4, CV_64F);
  if (data.size() == 16)
    for (int i = 0; i < 16; ++i) c.Tbs.at<double>(i / 4, i % 4) = data[i];
  (void)w; (void)h;
  return c;
}

std::string poseJson(const rtabmap::Transform& t) {
  // Rotation matrix -> quaternion (x,y,z,w).
  double r11 = t.r11(), r12 = t.r12(), r13 = t.r13();
  double r21 = t.r21(), r22 = t.r22(), r23 = t.r23();
  double r31 = t.r31(), r32 = t.r32(), r33 = t.r33();
  double qw, qx, qy, qz;
  double trace = r11 + r22 + r33;
  if (trace > 0) {
    double s = std::sqrt(trace + 1.0) * 2;
    qw = 0.25 * s; qx = (r32 - r23) / s; qy = (r13 - r31) / s; qz = (r21 - r12) / s;
  } else if (r11 > r22 && r11 > r33) {
    double s = std::sqrt(1.0 + r11 - r22 - r33) * 2;
    qw = (r32 - r23) / s; qx = 0.25 * s; qy = (r12 + r21) / s; qz = (r13 + r31) / s;
  } else if (r22 > r33) {
    double s = std::sqrt(1.0 + r22 - r11 - r33) * 2;
    qw = (r13 - r31) / s; qx = (r12 + r21) / s; qy = 0.25 * s; qz = (r23 + r32) / s;
  } else {
    double s = std::sqrt(1.0 + r33 - r11 - r22) * 2;
    qw = (r21 - r12) / s; qx = (r13 + r31) / s; qy = (r23 + r32) / s; qz = 0.25 * s;
  }
  char buf[256];
  std::snprintf(buf, sizeof(buf), "[%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f]",
                t.x(), t.y(), t.z(), qx, qy, qz, qw);
  return buf;
}

void emitGraph(const rtabmap::Rtabmap& slam, bool final) {
  const std::map<int, rtabmap::Transform>& poses = slam.getLocalOptimizedPoses();
  std::cout << "{\"type\":\"graph\",\"poses\":[";
  bool first = true;
  for (const auto& kv : poses) {
    if (!first) std::cout << ",";
    first = false;
    std::cout << "{\"node_id\":" << kv.first << ",\"pose\":" << poseJson(kv.second) << "}";
  }
  std::cout << "],\"final\":" << (final ? "true" : "false") << "}" << std::endl;
}

}  // namespace

int main(int argc, char** argv) {
  rtabmap::ParametersMap params;
  for (int i = 1; i + 1 < argc; i += 2) {
    if (std::string(argv[i]) == "--Param") {
      std::string kv = argv[i + 1];
      size_t eq = kv.find('=');
      if (eq != std::string::npos) params[kv.substr(0, eq)] = kv.substr(eq + 1);
    }
  }
  try {
    std::string header;
    if (!readFramed(header)) return 1;
    std::string cam0Yaml, cam1Yaml;
    if (!jsonString(header, "cam0_yaml", cam0Yaml) || !jsonString(header, "cam1_yaml", cam1Yaml)) {
      std::cout << "{\"type\":\"error\",\"message\":\"hello missing camera yaml\"}" << std::endl;
      return 1;
    }
    int width = (int)jsonLong(header, "width", 376);
    int height = (int)jsonLong(header, "height", 240);
    // Keyframe points beyond this come from 1-2 px disparities: too noisy
    // to map (6 m suits EuRoC at 376 px; a street with a wide baseline
    // maps further).
    float maxDepth = (float)jsonDouble(header, "max_depth_m", 6.0);
    CamCalib left = parseCam(cam0Yaml, width, height);
    CamCalib right = parseCam(cam1Yaml, width, height);

    // Left pose in right frame: inv(T_BS_right) * T_BS_left.
    cv::Mat leftInRight = right.Tbs.inv() * left.Tbs;
    cv::Mat Rlr = leftInRight(cv::Rect(0, 0, 3, 3)).clone();
    cv::Mat Tlr = leftInRight(cv::Rect(3, 0, 1, 3)).clone();

    cv::Mat R1, R2, P1, P2, Q;
    cv::Size size(width, height);
    cv::stereoRectify(left.K, left.D, right.K, right.D, size, Rlr, Tlr, R1, R2, P1, P2, Q);
    cv::Mat mapLx, mapLy, mapRx, mapRy;
    cv::initUndistortRectifyMap(left.K, left.D, R1, P1, size, CV_32F, mapLx, mapLy);
    cv::initUndistortRectifyMap(right.K, right.D, R2, P2, size, CV_32F, mapRx, mapRy);

    double fx = P1.at<double>(0, 0), fy = P1.at<double>(1, 1);
    double cx = P1.at<double>(0, 2), cy = P1.at<double>(1, 2);
    double baseline = std::abs(P2.at<double>(0, 3) / P2.at<double>(0, 0));
    rtabmap::StereoCameraModel stereoModel("surmap", fx, fy, cx, cy, baseline,
                                           rtabmap::Transform::getIdentity(), size);

    rtabmap::Odometry* odom = rtabmap::Odometry::create(params);
    rtabmap::Rtabmap slam;
    slam.init(params, "", false);
    // The left camera's rectification lets the host map rectified
    // keypoints back onto the raw image it displays.
    auto dist = [&](int i) { return i < left.D.cols ? left.D.at<double>(0, i) : 0.0; };
    std::cout << "{\"type\":\"ready\",\"version\":3,\"rectification\":{\"rotation\":[";
    for (int i = 0; i < 9; ++i) std::cout << (i ? "," : "") << R1.at<double>(i / 3, i % 3);
    std::cout << "],\"rectified\":[" << fx << "," << fy << "," << cx << "," << cy
              << "],\"raw\":[" << left.K.at<double>(0, 0) << "," << left.K.at<double>(1, 1) << ","
              << left.K.at<double>(0, 2) << "," << left.K.at<double>(1, 2)
              << "],\"distortion\":[" << dist(0) << "," << dist(1) << "," << dist(2) << ","
              << dist(3) << "]}}" << std::endl;

    int lastNodeId = 0;
    size_t lastGraphSize = 0;
    int lastGraphMaxId = 0;
    while (true) {
      std::string pairHeader;
      if (!readFramed(pairHeader)) break;  // EOF: finalize below
      long frameId = jsonLong(pairHeader, "frame_id", 0);
      long tNs = jsonLong(pairHeader, "t_ns", 0);
      std::string encoding;
      jsonString(pairHeader, "encoding", encoding);
      std::string leftPayload, rightPayload;
      if (!readFramed(leftPayload) || !readFramed(rightPayload)) break;
      auto decode = [&](const std::string& payload) {
        std::vector<unsigned char> bytes(payload.begin(), payload.end());
        if (encoding == "gray8")
          return cv::Mat(height, width, CV_8UC1, bytes.data()).clone();
        return cv::imdecode(bytes, cv::IMREAD_GRAYSCALE);
      };
      cv::Mat leftRaw = decode(leftPayload), rightRaw = decode(rightPayload);
      if (leftRaw.empty() || rightRaw.empty()) {
        std::cout << "{\"type\":\"error\",\"message\":\"undecodable pair\"}" << std::endl;
        return 1;
      }
      cv::Mat leftRect, rightRect;
      cv::remap(leftRaw, leftRect, mapLx, mapLy, cv::INTER_LINEAR);
      cv::remap(rightRaw, rightRect, mapRx, mapRy, cv::INTER_LINEAR);

      auto start = std::chrono::steady_clock::now();
      rtabmap::SensorData data(leftRect, rightRect, stereoModel, (int)frameId, tNs / 1e9);
      rtabmap::OdometryInfo info;
      rtabmap::Transform odomPose = odom->process(data, &info);
      bool lost = odomPose.isNull();
      // Feed SLAM only when tracking; a null pose must never be guessed.
      bool added = false;
      if (!lost) added = slam.process(data, odomPose);
      double ms = std::chrono::duration<double, std::milli>(
                      std::chrono::steady_clock::now() - start)
                      .count();

      std::cout << "{\"type\":\"odom\",\"frame_id\":" << frameId << ",\"t_ns\":" << tNs
                << ",\"pose\":" << (lost ? std::string("null") : poseJson(odomPose))
                << ",\"lost\":" << (lost ? "true" : "false") << ",\"ms\":" << ms
                << ",\"keypoints\":[";
      // This frame's inlier features: [word_id, u, v (rectified px), depth].
      if (!lost) {
        rtabmap::Transform worldToCamera = odomPose.inverse();
        bool firstKp = true;
        for (int wordId : info.reg.inliersIDs) {
          auto kp = info.words.find(wordId);
          auto landmark = info.localMap.find(wordId);
          if (kp == info.words.end() || landmark == info.localMap.end()) continue;
          cv::Point3f inCamera = rtabmap::util3d::transformPoint(landmark->second, worldToCamera);
          if (inCamera.z <= 0.f) continue;
          char buf[96];
          std::snprintf(buf, sizeof(buf), "%s[%d,%.1f,%.1f,%.2f]", firstKp ? "" : ",", wordId,
                        kp->second.pt.x, kp->second.pt.y, inCamera.z);
          std::cout << buf;
          firstKp = false;
        }
      }
      std::cout << "]}" << std::endl;

      int nodeId = slam.getLastLocationId();
      // A node RTAB-Map merged or discarded (e.g. too little motion) is
      // not in the graph: only nodes the graph keeps are keyframes.
      const auto& graphNow = slam.getLocalOptimizedPoses();
      bool kept = graphNow.find(nodeId) != graphNow.end();
      if (!lost && added && kept && nodeId > 0 && nodeId != lastNodeId) {
        lastNodeId = nodeId;
        auto cloud = rtabmap::util3d::cloudFromStereoImages(leftRect, rightRect, stereoModel);
        // Voxel-downsample (~5 cm): keep the first finite point per voxel.
        // x, y, z (camera frame) + grey sampled from the left rectified image.
        std::vector<std::array<float, 4>> points;
        if (cloud && !cloud->empty()) {
          std::map<std::tuple<int, int, int>, bool> seen;
          for (const auto& p : cloud->points) {
            if (!std::isfinite(p.x) || !std::isfinite(p.y) || !std::isfinite(p.z)) continue;
            auto key = std::make_tuple((int)std::floor(p.x / 0.05f),
                                       (int)std::floor(p.y / 0.05f),
                                       (int)std::floor(p.z / 0.05f));
            if (p.z <= 0.f || p.z > maxDepth) continue;
            if (!seen.emplace(key, true).second) continue;
            int u = (int)std::lround(fx * p.x / p.z + cx);
            int v = (int)std::lround(fy * p.y / p.z + cy);
            float grey = (u >= 0 && v >= 0 && u < leftRect.cols && v < leftRect.rows)
                             ? (float)leftRect.at<unsigned char>(v, u)
                             : 160.f;
            points.push_back({p.x, p.y, p.z, grey});
          }
        }
        rtabmap::Transform nodePose = graphNow.at(nodeId);
        std::cout << "{\"type\":\"keyframe\",\"node_id\":" << nodeId
                  << ",\"frame_id\":" << frameId << ",\"t_ns\":" << tNs
                  << ",\"pose\":" << poseJson(nodePose) << ",\"points_local\":[";
        bool first = true;
        for (const auto& p : points) {
          if (!first) std::cout << ",";
          first = false;
          char buf[128];
          int g = (int)p[3];
          std::snprintf(buf, sizeof(buf), "[%.3f,%.3f,%.3f,%d,%d,%d]", p[0], p[1], p[2], g, g, g);
          std::cout << buf;
        }
        std::cout << "]}" << std::endl;
      }
      // Re-emit when the node set changes: a merge can keep the size.
      const auto& posesNow = slam.getLocalOptimizedPoses();
      int maxId = posesNow.empty() ? 0 : posesNow.rbegin()->first;
      if (posesNow.size() != lastGraphSize || maxId != lastGraphMaxId) {
        lastGraphSize = posesNow.size();
        lastGraphMaxId = maxId;
        emitGraph(slam, false);
      }
    }
    emitGraph(slam, true);
    delete odom;
    return 0;
  } catch (const std::exception& exc) {
    std::fprintf(stderr, "surmap-rtabmap-stream: %s\n", exc.what());
    std::cout << "{\"type\":\"error\",\"message\":\"" << exc.what() << "\"}" << std::endl;
    return 1;
  }
}
