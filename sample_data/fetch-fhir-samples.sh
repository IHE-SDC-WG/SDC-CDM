#!/usr/bin/env bash

set -euxo pipefail

# Set current directory to that of the script, for consistent file IO
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$SCRIPT_DIR"

mkdir -p fhir
pushd fhir
curl -LJO https://github.com/IHE-SDC-WG/ConnectathonSampleData/raw/refs/heads/main/fsh-generated/resources/Bundle-CPDSBundleA.json
curl -LJO https://github.com/IHE-SDC-WG/ConnectathonSampleData/raw/refs/heads/main/fsh-generated/resources/Bundle-CPDSBundleB.json
popd