#!/usr/bin/env bash

set -euxo pipefail

pushd public
curl -LJO https://github.com/sql-js/sql.js/releases/download/v1.12.0/sqljs-all.zip
unzip sqljs-all.zip 'sql-wasm-debug.*'
rm sqljs-all.zip
popd