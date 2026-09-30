#!/usr/bin/env bash
# sourceme.sh - create (if needed) and activate the project Python venv
# Usage: source ./sourceme.sh
#        PYTHON=python3.12 source ./sourceme.sh
#
# Creates .venv on first use and (re)installs requirements.txt whenever that
# file or pyproject.toml is newer than the last install.

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo " - Note: run 'source ./sourceme.sh' to activate the venv in your shell"
  exit 1
fi

_sm_python="${PYTHON:-python3.13}"
_sm_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_sm_venv="${_sm_root}/.venv"
_sm_reqs="${_sm_root}/requirements.txt"
_sm_pyproject="${_sm_root}/pyproject.toml"
_sm_stamp="${_sm_venv}/.requirements.stamp"

_sm_setup() {
  if [[ ! -x "${_sm_venv}/bin/python" ]]; then
    if ! command -v "${_sm_python}" >/dev/null 2>&1; then
      echo " - ERROR: Python executable '${_sm_python}' not found" >&2
      return 1
    fi
    echo " - Creating virtual environment with ${_sm_python}"
    "${_sm_python}" -m venv --prompt "$(basename "${_sm_root}")" "${_sm_venv}" || return 1
  fi

  # shellcheck disable=SC1091
  . "${_sm_venv}/bin/activate" || return 1

  if [[ ! -f "${_sm_stamp}" || "${_sm_reqs}" -nt "${_sm_stamp}" \
        || "${_sm_pyproject}" -nt "${_sm_stamp}" ]]; then
    echo " - Installing packages from requirements.txt"
    python -m pip install --quiet --upgrade pip || return 1
    # requirements.txt holds `-e .`, which pip resolves against the cwd.
    (cd "${_sm_root}" && python -m pip install --quiet -r "${_sm_reqs}") || return 1
    touch "${_sm_stamp}"
  fi

  echo " - Virtual environment active: ${_sm_venv}"
}

_sm_setup
_sm_rc=$?
[[ ${_sm_rc} -eq 0 ]] || echo " - ERROR: failed to set up the virtual environment" >&2

unset -f _sm_setup
unset _sm_python _sm_root _sm_venv _sm_reqs _sm_pyproject _sm_stamp
return "${_sm_rc}"
