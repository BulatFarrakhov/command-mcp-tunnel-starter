#!/usr/bin/env bash
# Run as agent inside the Ubuntu 24.04 appliance after copying the repo.
set -euo pipefail
umask 077

readonly repo=/home/agent/command-mcp-tunnel-starter
readonly guest_dir="$repo/vm/guest"
readonly config=/home/agent/.config/command-mcp-tunnel/config.json
readonly uv_version=0.13.0
readonly tunnel_version=v0.0.16

fail() { printf '%s\n' "$*" >&2; exit 1; }
[[ $(id -un) == agent && $HOME == /home/agent ]] || fail 'Run this script as the guest account agent, with HOME=/home/agent.'
[[ -f "$repo/uv.lock" && -f "$guest_dir/systemd/command-mcp.service" ]] || fail "Copy the complete source into $repo first."
# shellcheck source=/dev/null
source /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 ]] || fail 'This bootstrap supports Ubuntu 24.04 only.'
sudo -n true || fail 'The guest agent account needs passwordless sudo inside the VM.'
rm -f -- /home/agent/command-mcp.zip
for unit in command-mcp.service command-mcp-tunnel.service; do
    if systemctl is-active --quiet "$unit"; then
        fail "$unit is running. Finish active commands and stop both services before reprovisioning."
    fi
done

case $(uname -m) in
    x86_64)
        uv_arch=x86_64
        tunnel_arch=amd64
        uv_sha=1468ebd5a5541121837c5a2817b9972ba6090fa6caa3d142620850a47fb75154
        tunnel_sha=d60cdba019bce451bcc3a15478cc5b9cb11270b049f5b56ea39a80b517f8b117
        ;;
    aarch64)
        uv_arch=aarch64
        tunnel_arch=arm64
        uv_sha=3ccfb6af6e242433eb552f7d9676abd5412c6595c497e990d9c8cb7b5bd4d2c3
        tunnel_sha=963d0384aaa7c798778479c45673f9051a4039dd891aef8f8978d2a1a628b74f
        ;;
    *) fail 'Unsupported guest CPU architecture.' ;;
esac

sudo -n apt-get update
sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ca-certificates curl git python3.12 python3.12-venv iproute2 lvm2
install -d -m 0700 /home/agent/.local/bin /home/agent/.local/lib \
    /home/agent/.config/command-mcp-tunnel /home/agent/.local/state/command-mcp-tunnel
sudo -n install -d -m 0750 -o agent -g "$(id -gn)" /workspace
if [[ -n ${COMMAND_MCP_DISK_GIB:-} ]]; then
    [[ $COMMAND_MCP_DISK_GIB =~ ^[0-9]+$ ]] || fail 'Invalid requested VM disk size.'
    root_device=$(findmnt --noheadings --output SOURCE /)
    if sudo -n lvs --noheadings "$root_device" >/dev/null 2>&1; then
        vg_name=$(sudo -n lvs --noheadings --output vg_name "$root_device" | tr -d '[:space:]')
        free_extents=$(sudo -n vgs --noheadings --output vg_free_count "$vg_name" | tr -d '[:space:]')
        if [[ $free_extents =~ ^[0-9]+$ ]] && (( free_extents > 0 )); then
            sudo -n lvextend --resizefs --extents +100%FREE "$root_device"
        fi
    fi
    capacity_bytes=$(df --block-size=1 --output=size /workspace | tail -n 1 | tr -d '[:space:]')
    minimum_bytes=$((COMMAND_MCP_DISK_GIB * 1024 * 1024 * 1024 * 90 / 100))
    (( capacity_bytes >= minimum_bytes )) || fail "Workspace filesystem is too small for ${COMMAND_MCP_DISK_GIB} GiB disk."
    printf 'Workspace filesystem capacity: %s bytes\n' "$capacity_bytes"
fi
if [[ ! -e /workspace/AGENTS.md ]]; then
    install -m 0640 "$guest_dir/workspace-AGENTS.md" /workspace/AGENTS.md
fi

scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
curl --proto '=https' --tlsv1.2 -fLsS --retry 3 \
    "https://github.com/astral-sh/uv/releases/download/$uv_version/uv-$uv_arch-unknown-linux-gnu.tar.gz" \
    -o "$scratch/uv.tar.gz"
printf '%s  %s\n' "$uv_sha" "$scratch/uv.tar.gz" | sha256sum --check --status
tar -xzf "$scratch/uv.tar.gz" -C "$scratch"
install -m 0755 "$scratch/uv-$uv_arch-unknown-linux-gnu/uv" /home/agent/.local/bin/uv
curl --proto '=https' --tlsv1.2 -fLsS --retry 3 \
    "https://github.com/openai/tunnel-client/releases/download/$tunnel_version/tunnel-client-$tunnel_version-linux-$tunnel_arch.zip" \
    -o "$scratch/tunnel.zip"
printf '%s  %s\n' "$tunnel_sha" "$scratch/tunnel.zip" | sha256sum --check --status
python3 "$guest_dir/install_tunnel.py" "$scratch/tunnel.zip" \
    "/home/agent/.local/lib/tunnel-client-$tunnel_version"
ln -sfn "/home/agent/.local/lib/tunnel-client-$tunnel_version/tunnel-client" /home/agent/.local/bin/tunnel-client
/home/agent/.local/bin/tunnel-client help quickstart >/dev/null

cd "$repo"
export PATH="/home/agent/.local/bin:$PATH"
export UV_PYTHON_DOWNLOADS=never
uv sync --frozen --no-dev --python /usr/bin/python3.12
sudo -n install -m 0644 "$guest_dir/systemd/command-mcp.service" /etc/systemd/system/command-mcp.service
sudo -n install -m 0644 "$guest_dir/systemd/command-mcp-tunnel.service" /etc/systemd/system/command-mcp-tunnel.service
sudo -n systemctl daemon-reload
if [[ -f $config ]]; then
    chmod 0600 "$config"
    /bin/bash "$guest_dir/start-services.sh"
else
    printf '%s\n' 'Software installed. Services remain disabled until private configuration is supplied.' \
        "In the guest console, run: bash $guest_dir/setup.sh"
fi
