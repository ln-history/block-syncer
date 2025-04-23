#!/bin/sh

echo "Waiting for Tor SOCKS5 to be ready..."

while ! curl --socks5-hostname tor:9050 https://check.torproject.org --silent --fail > /dev/null; do
  echo "Still waiting..."
  sleep 5
done

echo "Tor is healthy. Starting block-syncer..."
exec "$@"