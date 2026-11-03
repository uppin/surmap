cmake_minimum_required(VERSION 3.16)
project(surmap-rtabmap-stream C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(MPI REQUIRED COMPONENTS C CXX)
# Debian's VTK targets reference JsonCpp::JsonCpp without importing
# it; the jsoncpp package creates that target when found first.
find_package(jsoncpp REQUIRED)
find_package(RTABMap REQUIRED)
find_package(OpenCV REQUIRED)
add_executable(surmap-rtabmap-stream main.cpp)
target_link_libraries(surmap-rtabmap-stream rtabmap::core ${OpenCV_LIBRARIES})
# Header-only policy test (OpenCV only); the image build runs it.
add_executable(odom-covariance-test odom_covariance_test.cpp)
target_link_libraries(odom-covariance-test ${OpenCV_LIBRARIES})
