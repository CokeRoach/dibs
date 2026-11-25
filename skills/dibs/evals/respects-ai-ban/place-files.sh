#!/usr/bin/env bash
set -eu
cp -R "$(dirname "$0")/files/." .
cd slugkit
git init -q -b main
git add -A
git -c user.name="slugkit maintainers" -c user.email="maintainers@example.com" commit -qm "slugkit 1.4.0"
