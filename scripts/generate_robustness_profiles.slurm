#!/bin/bash
#SBATCH --job-name=bike-robprof
#SBATCH -p cpu,cpu-preempt
#SBATCH -N 1
#SBATCH -c 4
#SBATCH --mem=16G
#SBATCH --time=01:30:00
#SBATCH --output=/work/pi_plunkett_umass_edu/bcu/course_project/slurm_logs/robprof-%A_%a.out
#SBATCH --error=/work/pi_plunkett_umass_edu/bcu/course_project/slurm_logs/robprof-%A_%a.err

set -euo pipefail

module load conda/latest

REPO="$HOME/high-impact-bicycle-network-improvements"

cd "$REPO"

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
