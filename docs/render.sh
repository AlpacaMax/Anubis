#!/bin/sh

echo 'Rendering design.md to design.pdf'

set -ex

cd mermaid
if ! [ -d node_modules ]; then
    yarn
fi
./render.sh
cd ..

exec pandoc design.md -s -o design.pdf -f markdown-implicit_figures
