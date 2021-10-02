#!/bin/bash

# move to current directory
cd "$(dirname "$0")"

# perform infinite loop
while :
do
  echo "git pull ..."
  git pull
	echo "Run FoE bot. Press [CTRL+C] to stop..."
  python -m python.foebot
done
