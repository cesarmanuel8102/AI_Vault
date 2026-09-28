#!/bin/bash
set -euo pipefail

inside=0
workspace=""
worker=""
script=""
timeout_seconds=""
nonce=""
script_args=()

while (($#)); do
    case "$1" in
        --inside) inside=1; shift ;;
        --workspace) workspace="$2"; shift 2 ;;
        --worker) worker="$2"; shift 2 ;;
        --script) script="$2"; shift 2 ;;
        --timeout) timeout_seconds="$2"; shift 2 ;;
        --nonce) nonce="$2"; shift 2 ;;
        --) shift; script_args=("$@"); break ;;
        *) printf 'unexpected launcher argument\n' >&2; exit 64 ;;
    esac
done

[[ "$workspace" == /mnt/[a-z]/* ]] || { printf 'invalid workspace path\n' >&2; exit 65; }
[[ "$worker" == /mnt/[a-z]/*/ibkr_paper_30d/research_worker_linux.py ]] || { printf 'invalid worker path\n' >&2; exit 65; }
[[ "$script" =~ ^tools/[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*\.py$ ]] || { printf 'invalid script path\n' >&2; exit 65; }
[[ "$timeout_seconds" =~ ^[0-9]+$ ]] && ((timeout_seconds >= 1 && timeout_seconds <= 300)) || { printf 'invalid timeout\n' >&2; exit 65; }
[[ "$nonce" =~ ^[a-f0-9]{32}$ ]] || { printf 'invalid nonce\n' >&2; exit 65; }
[[ -d "$workspace" && -f "$worker" ]] || { printf 'sandbox input unavailable\n' >&2; exit 66; }

if ((inside == 0)); then
    [[ "$(id -u)" == "0" ]] || { printf 'trusted launcher requires WSL root bootstrap\n' >&2; exit 77; }
    exec unshare --mount --pid --fork --net -- \
        /bin/bash "$0" --inside --workspace "$workspace" --worker "$worker" \
        --script "$script" --timeout "$timeout_seconds" --nonce "$nonce" -- "${script_args[@]}"
fi

mount --make-rprivate /
root="/tmp/codex-research-sandbox-$nonce"
[[ "$root" =~ ^/tmp/codex-research-sandbox-[a-f0-9]{32}$ ]] || exit 70
[[ ! -e "$root" ]] || { printf 'sandbox root collision\n' >&2; exit 70; }
mkdir -m 0700 "$root"

cleanup() {
    set +e
    umount -l "$root/proc" 2>/dev/null
    umount -l "$root/scratch" 2>/dev/null
    umount -l "$root/worker/research_worker_linux.py" 2>/dev/null
    for name in experiments datasets tools research memory; do
        umount -l "$root/workspace/$name" 2>/dev/null
    done
    umount -l "$root/usr" 2>/dev/null
    rm -rf -- "$root"
}
trap cleanup EXIT HUP INT TERM

mkdir -p "$root/usr" "$root/workspace" "$root/worker" "$root/scratch" "$root/proc"
mount --bind /usr "$root/usr"
mount -o remount,bind,ro "$root/usr"
ln -s usr/bin "$root/bin"
ln -s usr/lib "$root/lib"
ln -s usr/lib64 "$root/lib64"
ln -s usr/sbin "$root/sbin"

for name in memory research tools datasets experiments; do
    mkdir -p "$root/workspace/$name"
    mount --bind "$workspace/$name" "$root/workspace/$name"
done
touch "$root/worker/research_worker_linux.py"
mount --bind "$worker" "$root/worker/research_worker_linux.py"
mount -o remount,bind,ro "$root/worker/research_worker_linux.py"
mount -t tmpfs -o size=64m,nosuid,nodev,noexec tmpfs "$root/scratch"
mount -t proc -o nosuid,nodev,noexec proc "$root/proc"
chmod 0755 "$root"

exec_status=0
timeout --foreground --signal=TERM --kill-after=2s "${timeout_seconds}s" \
    chroot "$root" /usr/bin/setpriv \
        --reuid=65534 --regid=65534 --clear-groups \
        --bounding-set=-all --inh-caps=-all --ambient-caps=-all --no-new-privs \
        /usr/bin/env -i HOME=/nonexistent LANG=C.UTF-8 LC_ALL=C.UTF-8 \
        TMPDIR=/scratch PYTHONDONTWRITEBYTECODE=1 \
        /usr/bin/python3 -I /worker/research_worker_linux.py \
        --script "$script" --timeout "$timeout_seconds" -- "${script_args[@]}" || exec_status=$?

if ((exec_status == 124 || exec_status == 137)); then
    printf 'research worker timed out\n' >&2
fi
exit "$exec_status"
