#!/bin/bash
#SBATCH --job-name=bike-od684
#SBATCH -p cpu,cpu-preempt
#SBATCH -N 1
#SBATCH -c 4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=/work/pi_plunkett_umass_edu/bcu/course_project/slurm_logs/od684-%j.out
#SBATCH --error=/work/pi_plunkett_umass_edu/bcu/course_project/slurm_logs/od684-%j.err

set -euo pipefail

module load conda/latest

REPO="$HOME/high-impact-bicycle-network-improvements"

cd "$REPO"

export PYTHONPATH="$REPO/src:${PYTHONPATH:-}"

python scripts/generate_robustness_od.py
