# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Only public host dependencies are baked into this image. SDK/license bind mounts
# are supplied at runtime, after the user obtains the full QNX 6.5 installation.
FROM ubuntu:22.04@sha256:076e7bf82319619f28dd0aa9c02ab34b055ad37100395b4f49a2ffba04fb5e11
ENV DEBIAN_FRONTEND=noninteractive
RUN dpkg --add-architecture i386 \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates make g++ gcc python3 git file binutils \
       libc6:i386 libstdc++6:i386 libgcc-s1:i386 zlib1g:i386 \
       libncurses5:i386 libtinfo5:i386 \
    && rm -rf /var/lib/apt/lists/*
ENV QNX_HOST=/opt/qnx650/host/linux/x86 \
    QNX_TARGET=/opt/qnx650/target/qnx6 \
    QNX_CONFIGURATION=/etc/qnx
COPY container.sh /usr/local/bin/qnx-build-entry
RUN chmod 755 /usr/local/bin/qnx-build-entry && mkdir -p /etc/qnx/license /src
WORKDIR /src
ENTRYPOINT ["/usr/local/bin/qnx-build-entry"]
CMD ["bash"]
