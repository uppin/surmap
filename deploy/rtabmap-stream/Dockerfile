FROM introlab3it/rtabmap@sha256:14a58ac31565f0a0ab2421fa861f6fc43010e54345e13a6a1ccde32d3b0ffdb8
WORKDIR /build
COPY CMakeLists.txt main.cpp ./
RUN cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j"$(nproc)"
ENTRYPOINT ["/build/build/surmap-rtabmap-stream"]
