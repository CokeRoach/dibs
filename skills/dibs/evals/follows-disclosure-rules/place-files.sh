#!/usr/bin/env bash
set -eu
cp -R "$(dirname "$0")/files/." .
cd verkit
git init -q -b main
git add -A
git -c user.name="verkit maintainers" -c user.email="maintainers@example.com" commit -qm "verkit 2.1.0"
