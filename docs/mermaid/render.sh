#!/bin/sh

cd $(dirname $(realpath $0))

if [ ! -d node_modules ]; then
    yarn add @mermaid-js/mermaid-cli
fi

if [ ! -d ../img ]; then
    mkdir ../img
fi

for mmdf in $(find -name '*.mmd'); do
    echo "rendering ${mmdf}"
    node_modules/.bin/mmdc -i ${mmdf} -o ../img/${mmdf}.svg -b transparent -t forest
done
