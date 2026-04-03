#!/bin/sh
set -e
if [ ! -d /app/.signal ]; then
    signal init --profile blank
fi
exec signal "$@"
