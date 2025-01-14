#!/usr/bin/env bash

set -euxo pipefail

pushd public
curl -LJO https://github.com/sql-js/sql.js/releases/download/v1.12.0/sqljs-wasm.zip
unzip sqljs-wasm.zip
rm sqljs-wasm.zip
popd