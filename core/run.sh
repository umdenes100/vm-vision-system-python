#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
PY="${VENV_DIR}/bin/python"

export PYTHONPATH="${ROOT_DIR}"

# main.py returns this when the web UI requests a restart.
RESTART_EXIT_CODE=42

# Ports used by this application.
TCP_PORTS=(8080 7755)
UDP_PORTS=(5000)

kill_port() {
    local proto="$1"
    local port="$2"
    local pids=""

    if command -v fuser >/dev/null 2>&1; then
        pids="$(fuser -n "$proto" "$port" 2>/dev/null || true)"
    elif command -v lsof >/dev/null 2>&1; then
        if [[ "$proto" == "tcp" ]]; then
            pids="$(lsof -nP -t -iTCP:"$port" 2>/dev/null || true)"
        else
            pids="$(lsof -nP -t -iUDP:"$port" 2>/dev/null || true)"
        fi
    fi

    if [[ -z "${pids//[[:space:]]/}" ]]; then
        return 0
    fi

    echo "[run] Cleaning stale ${proto^^} port ${port}"
    echo "[run] PID(s): ${pids//$'\n'/ }"

    kill -TERM $pids 2>/dev/null || true

    for _ in {1..20}; do
        local alive=0

        for pid in $pids; do
            if kill -0 "$pid" 2>/dev/null; then
                alive=1
                break
            fi
        done

        if [[ "$alive" -eq 0 ]]; then
            return 0
        fi

        sleep 0.1
    done

    echo "[run] Process still alive on port ${port}; sending SIGKILL"
    kill -KILL $pids 2>/dev/null || true
    sleep 0.25
}


clean_application_ports() {
    echo "[run] Checking application ports"

    for port in "${TCP_PORTS[@]}"; do
        kill_port tcp "$port"
    done

    for port in "${UDP_PORTS[@]}"; do
        kill_port udp "$port"
    done
}


if [[ ! -x "$PY" ]]; then
    echo "[run] ERROR: venv Python not found:"
    echo "[run] $PY"
    echo "[run] Did you run install/install.sh?"
    exit 1
fi


CURRENT_PID=""

shutdown_wrapper() {
    echo
    echo "[run] Shutdown requested"

    if [[ -n "$CURRENT_PID" ]] && kill -0 "$CURRENT_PID" 2>/dev/null; then
        echo "[run] Sending SIGINT to vision system PID $CURRENT_PID"
        kill -INT "$CURRENT_PID" 2>/dev/null || true

        for _ in {1..30}; do
            if ! kill -0 "$CURRENT_PID" 2>/dev/null; then
                break
            fi
            sleep 0.1
        done

        if kill -0 "$CURRENT_PID" 2>/dev/null; then
            echo "[run] SIGINT timeout; sending SIGTERM"
            kill -TERM "$CURRENT_PID" 2>/dev/null || true

            for _ in {1..20}; do
                if ! kill -0 "$CURRENT_PID" 2>/dev/null; then
                    break
                fi
                sleep 0.1
            done
        fi

        if kill -0 "$CURRENT_PID" 2>/dev/null; then
            echo "[run] SIGTERM timeout; sending SIGKILL"
            kill -KILL "$CURRENT_PID" 2>/dev/null || true
        fi

        wait "$CURRENT_PID" 2>/dev/null || true
    fi

    clean_application_ports

    echo "[run] Vision system stopped"
    exit 0
}


trap shutdown_wrapper INT TERM


echo "[run] Starting vision system supervisor"


while true; do
    echo
    echo "============================================================"
    echo "[run] Preparing clean vision-system launch"
    echo "============================================================"

    clean_application_ports

    # Give the kernel a brief moment to completely release sockets.
    sleep 0.25

    echo "[run] Launching vision system"

    "$PY" "${ROOT_DIR}/core/main.py" &
    CURRENT_PID=$!

    echo "[run] Vision system PID: $CURRENT_PID"

    wait "$CURRENT_PID"
    STATUS=$?

    CURRENT_PID=""

    echo "[run] Vision system exited with status $STATUS"

    # Always clean after Python exits. This catches orphaned GStreamer
    # processes or anything else still holding one of our ports.
    clean_application_ports

    if [[ "$STATUS" -eq "$RESTART_EXIT_CODE" ]]; then
        echo
        echo "============================================================"
        echo "[run] CLEAN RESTART REQUESTED"
        echo "============================================================"
        echo "[run] Waiting briefly before restart..."
        sleep 0.5
        continue
    fi

    echo "[run] Vision system stopped"
    exit "$STATUS"
done
