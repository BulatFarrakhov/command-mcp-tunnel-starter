#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
if [[ $(id -u) == 0 ]]; then echo 'Run as the intended non-root user.' >&2; exit 1; fi
if [[ $# == 0 ]]; then set -- install; fi
if [[ "$1" != install && -x .venv/bin/python ]]; then
  exec .venv/bin/python scripts/setup.py "$@"
fi
version=0.13.10
case "$(uname -m)" in
  x86_64) arch=x86_64; digest=bf65ac1a0af10f92c522d91ac096c7c0a39657647b155577e7836c2cbbb4526c ;;
  aarch64|arm64) arch=aarch64; digest=14590f644805a6234ffe071154340669e38137f38e60aa9629690119704107d2 ;;
  *) echo 'Unsupported Linux architecture.' >&2; exit 1 ;;
esac
if [[ $(uname -s) != Linux ]]; then echo 'This installer requires Linux.' >&2; exit 1; fi
export UV_PROJECT_ENVIRONMENT="$PWD/.venv"
unset VIRTUAL_ENV
if command -v uv >/dev/null; then
  uv_bin=$(command -v uv)
elif [[ -x ".bootstrap/uv-$version" ]]; then
  uv_bin="$PWD/.bootstrap/uv-$version"
else
  for tool in curl sha256sum tar; do
    command -v "$tool" >/dev/null || { echo "Missing prerequisite: $tool" >&2; exit 1; }
  done
  umask 077
  name="uv-$arch-unknown-linux-gnu"
  scratch=$(mktemp -d)
  trap 'rm -rf -- "$scratch"' EXIT
  curl --fail --silent --show-error --location --proto '=https' --connect-timeout 15 --max-time 180 \
    "https://github.com/astral-sh/uv/releases/download/$version/$name.tar.gz" -o "$scratch/uv.tar.gz"
  printf '%s  %s\n' "$digest" "$scratch/uv.tar.gz" | sha256sum --check --status
  tar -xzf "$scratch/uv.tar.gz" -C "$scratch" "$name/uv"
  mkdir -p .bootstrap
  install -m 0700 "$scratch/$name/uv" ".bootstrap/uv-$version"
  uv_bin="$PWD/.bootstrap/uv-$version"
fi
"$uv_bin" python install 3.12
"$uv_bin" run --frozen --python 3.12 python scripts/setup.py "$@"
