# Cleanup helpers for owned B09 resources. Stdout contains only allowlisted status rows.

cleanup_record() {
    printf '%s\t%s\t%s\n' "$1" "$2" "$3"
}

process_gone() {
    local pid=$1 attempt
    for ((attempt=0; attempt<10; attempt++)); do
        if ! kill -0 "$pid" 2>/dev/null; then
            wait "$pid" 2>/dev/null || true
            return 0
        fi
        sleep 0.5
    done
    return 1
}

stop_owned_process() {
    local pid=$1
    process_gone "$pid" && return 0
    kill -TERM "$pid" 2>/dev/null || true
    process_gone "$pid" && return 0
    kill -KILL "$pid" 2>/dev/null || true
    process_gone "$pid"
}

cleanup_emulator() {
    if [[ -z "$emulator_pid" ]]; then
        cleanup_record emulator_process not_started -
        cleanup_record adb_unregister not_started -
        cleanup_record adb_reverse not_started -
        return 0
    fi
    local status=0 attempt listing adb_state=unverified
    if [[ "$reverse" == true ]]; then
        timeout 5 "$adb" reverse --remove tcp:18443 >/dev/null 2>&1 || true
    fi
    timeout 10 "$adb" emu kill >/dev/null 2>&1 || true
    if stop_owned_process "$emulator_pid"; then
        cleanup_record emulator_process removed -
    else
        cleanup_record emulator_process remaining -
        status=1
    fi
    # The ADB server can retain an offline transport briefly after QEMU exits.
    for ((attempt=1; attempt<=15; attempt++)); do
        if listing=$(timeout 3 "$adb" devices 2>/dev/null); then
            if ! awk -v serial="$ANDROID_SERIAL" '$1 == serial { found=1 } END { exit !found }' <<< "$listing"; then
                adb_state=removed
                break
            fi
            adb_state=remaining
        else
            adb_state=unverified
        fi
        if (( attempt < 15 )); then sleep 1; fi
    done
    cleanup_record adb_unregister "$adb_state" "polls=$attempt"
    [[ "$adb_state" == removed ]] || status=1
    if [[ "$reverse" != true ]]; then
        cleanup_record adb_reverse not_started -
    elif [[ "$adb_state" == removed ]]; then
        cleanup_record adb_reverse removed transport_gone
    elif listing=$(timeout 3 "$adb" reverse --list 2>/dev/null); then
        if awk '$2 == "tcp:18443" { found=1 } END { exit !found }' <<< "$listing"; then
            cleanup_record adb_reverse remaining -
            status=1
        else
            cleanup_record adb_reverse removed verified_list
        fi
    else
        cleanup_record adb_reverse unverified -
        status=1
    fi
    return "$status"
}

cleanup_docker_resource() {
    local resource=$1 attempt ids id count
    shift
    for ((attempt=1; attempt<=3; attempt++)); do
        if ids=$(timeout 15 docker "$@" --filter "label=$label" 2>/dev/null); then
            if [[ -z "$ids" ]]; then
                cleanup_record "$resource" removed "remaining=0"
                return 0
            fi
            while IFS= read -r id; do
                case "$resource" in
                    docker_containers) timeout 60 docker rm -fv "$id" >/dev/null 2>&1 || true ;;
                    docker_volumes) timeout 15 docker volume rm "$id" >/dev/null 2>&1 || true ;;
                    docker_networks) timeout 15 docker network rm "$id" >/dev/null 2>&1 || true ;;
                esac
            done <<< "$ids"
        fi
        sleep 1
    done
    if ! ids=$(timeout 15 docker "$@" --filter "label=$label" 2>/dev/null); then
        cleanup_record "$resource" unverified inventory_failed
    elif [[ -z "$ids" ]]; then
        cleanup_record "$resource" removed "remaining=0"
        return 0
    else
        count=$(wc -l <<< "$ids")
        cleanup_record "$resource" remaining "remaining=$count"
    fi
    return 1
}
