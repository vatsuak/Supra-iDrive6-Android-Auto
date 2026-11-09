#!/bin/sh
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
set -eu
export PATH="$QNX_HOST/usr/bin:$PATH"
export LD_LIBRARY_PATH="$QNX_HOST/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$@"
