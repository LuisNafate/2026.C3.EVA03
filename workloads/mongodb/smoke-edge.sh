#!/bin/sh
set -eu

staging=$1
dbpath="$RUNTIME_DIRECTORY/db"
port=28080
mkdir "$dbpath"
server=

stop_server() {
    if [ -n "$server" ]; then
        kill -TERM "$server" 2>/dev/null || true
        wait "$server" || true
        server=
    fi
}

finish() {
    stop_server
    if [ -f "$RUNTIME_DIRECTORY/mongod.log" ]; then
        printf '\n== mongod.log ==\n'
        cat "$RUNTIME_DIRECTORY/mongod.log"
    fi
}
trap finish EXIT

start_server() {
    "$staging/mongod" --bind_ip 127.0.0.1 --port "$port" \
        --dbpath "$dbpath" --logpath "$RUNTIME_DIRECTORY/mongod.log" \
        --logappend --wiredTigerCacheSizeGB 0.25 &
    server=$!
    for _ in $(seq 1 20); do
        kill -0 "$server" 2>/dev/null || return 1
        if "$staging/mongo" --norc --quiet --host 127.0.0.1 --port "$port" \
            --eval 'assert.commandWorked(db.runCommand({ping: 1}))' >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    return 1
}

validate() {
    "$staging/mongo" --norc --quiet --host 127.0.0.1 --port "$port" edge_lab \
        --eval "var stage = '$1'; var datasetPath = '$staging/orders-1000.jsonl'; load('$staging/test.js');"
}

start_server
validate insert
stop_server
start_server
validate restart
