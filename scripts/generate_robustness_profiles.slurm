#!/bin/bash
#SBATCH --job-name=bike-robprof
#SBATCH -p cpu,cpu-preempt
#SBATCH -N 1
#SBATCH -c 4
#SBATCH --mem=16G
#SBATCH --time=01:30:00
#SBATCH --output=slurm-%x-%j.out
#SBATCH --error=slurm-%x-%j.err

set -euo pipefail

module load conda/latest

REPO="${BIKE_REPO_ROOT:-$HOME/high-impact-bicycle-network-improvements}"

cd "$REPO"

# Load machine-specific data locations when a local configuration exists.
if [[ -f "$REPO/.project_env" ]]; then
  # shellcheck disable=SC1091
  source "$REPO/.project_env"
fi

: "${BIKE_DATA_ROOT:?Set BIKE_DATA_ROOT or configure .project_env}"
: "${BIKE_FINAL_ROOT:?Set BIKE_FINAL_ROOT or configure .project_env}"
: "${BIKE_COURSE_ROOT:?Set BIKE_COURSE_ROOT or configure .project_env}"

export PYTHONPATH="$REPO/src:${PYTHONPATH:-}"

PROFILES=(
  "child"
  "low_confidence_adult"
  "typical_adult"
  "experienced_adult"
)

PROFILE="${PROFILES[$SLURM_ARRAY_TASK_ID]}"

python scripts/generate_robustness_profile_graph.py \
  --profile "$PROFILE"
