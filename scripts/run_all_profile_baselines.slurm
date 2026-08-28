#!/bin/bash

#SBATCH --job-name=bike-baseline
#SBATCH -p cpu,cpu-preempt
#SBATCH -N 1
#SBATCH -c 16
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --array=0-3
#SBATCH --output=/work/pi_plunkett_umass_edu/bcu/course_project/slurm_logs/baseline-%A_%a.out
#SBATCH --error=/work/pi_plunkett_umass_edu/bcu/course_project/slurm_logs/baseline-%A_%a.err

set -euo pipefail

module load conda/latest

REPO="$HOME/high-impact-bicycle-network-improvements"
DATA="/work/pi_plunkett_umass_edu/bcu/final"
COURSE="/work/pi_plunkett_umass_edu/bcu/course_project"

cd "$REPO"

export PYTHONPATH="$REPO/src:${PYTHONPATH:-}"

OD="$DATA/output/demand_scenarios/demand_scenario_1/greater_boston_all_pairs_demand_scenario_1.csv"

PROFILES=(
    "child"
    "low_confidence_adult"
    "typical_adult"
    "experienced_adult"
)

GRAPHS=(
    "$DATA/output/cost_scenarios/cost_scenario_1/greater_boston_cost_scenario_1_simplified.graphml"
    "$COURSE/profile_graphs/greater_boston_low_confidence_adult_scenario_6_simplified.graphml"
    "$COURSE/profile_graphs/greater_boston_typical_adult_scenario_11_simplified.graphml"
    "$COURSE/profile_graphs/greater_boston_experienced_adult_scenario_16_simplified.graphml"
)

PROFILE="${PROFILES[$SLURM_ARRAY_TASK_ID]}"
GRAPH="${GRAPHS[$SLURM_ARRAY_TASK_ID]}"
OUTPUT="$COURSE/baselines/$PROFILE"

mkdir -p "$OUTPUT"

echo "============================================================"
echo "Profile: $PROFILE"
echo "Graph: $GRAPH"
echo "Output: $OUTPUT"
echo "CPUs: $SLURM_CPUS_PER_TASK"
echo "Job: $SLURM_JOB_ID"
echo "============================================================"

python --version

python scripts/run_profile_baseline.py \
    --profile "$PROFILE" \
    --graph "$GRAPH" \
    --od "$OD" \
    --output-dir "$OUTPUT" \
    --workers "$SLURM_CPUS_PER_TASK"

echo
echo "Completed profile: $PROFILE"
