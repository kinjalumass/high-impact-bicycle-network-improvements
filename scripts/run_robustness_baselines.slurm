#!/bin/bash
#SBATCH --job-name=bike-robase
#SBATCH -p cpu,cpu-preempt
#SBATCH -N 1
#SBATCH -c 16
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=/work/pi_plunkett_umass_edu/bcu/course_project/slurm_logs/robase-%A_%a.out
#SBATCH --error=/work/pi_plunkett_umass_edu/bcu/course_project/slurm_logs/robase-%A_%a.err

set -euo pipefail

module load conda/latest

MODE="$1"

REPO="$HOME/high-impact-bicycle-network-improvements"
FINAL="/work/pi_plunkett_umass_edu/bcu/final"
COURSE="/work/pi_plunkett_umass_edu/bcu/course_project"

cd "$REPO"

export PYTHONPATH="$REPO/src:${PYTHONPATH:-}"

PROFILES=(
  "child"
  "low_confidence_adult"
  "typical_adult"
  "experienced_adult"
)

PROFILE="${PROFILES[$SLURM_ARRAY_TASK_ID]}"

BASELINE_GRAPHS=(
  "$FINAL/output/cost_scenarios/cost_scenario_1/greater_boston_cost_scenario_1_simplified.graphml"
  "$COURSE/profile_graphs/greater_boston_low_confidence_adult_scenario_6_simplified.graphml"
  "$COURSE/profile_graphs/greater_boston_typical_adult_scenario_11_simplified.graphml"
  "$COURSE/profile_graphs/greater_boston_experienced_adult_scenario_16_simplified.graphml"
)

HIGH_AVERSION_GRAPHS=(
  "$COURSE/robustness/profile_graphs/greater_boston_child_scenario_5_simplified.graphml"
  "$COURSE/robustness/profile_graphs/greater_boston_low_confidence_adult_scenario_10_simplified.graphml"
  "$COURSE/robustness/profile_graphs/greater_boston_typical_adult_scenario_15_simplified.graphml"
  "$COURSE/robustness/profile_graphs/greater_boston_experienced_adult_scenario_20_simplified.graphml"
)

BASE_OD="$FINAL/output/demand_scenarios/demand_scenario_1/greater_boston_all_pairs_demand_scenario_1.csv"
ALT_OD="$COURSE/robustness/od_seed_684/greater_boston_all_pairs_seed_684.csv"

if [ "$MODE" = "high_aversion" ]; then
  GRAPH="${HIGH_AVERSION_GRAPHS[$SLURM_ARRAY_TASK_ID]}"
  OD="$BASE_OD"
  OUTPUT="$COURSE/robustness/baselines/high_aversion/$PROFILE"
elif [ "$MODE" = "od_seed_684" ]; then
  GRAPH="${BASELINE_GRAPHS[$SLURM_ARRAY_TASK_ID]}"
  OD="$ALT_OD"
  OUTPUT="$COURSE/robustness/baselines/od_seed_684/$PROFILE"
else
  echo "Unknown robustness mode: $MODE" >&2
  exit 2
fi

mkdir -p "$OUTPUT"

echo "Mode: $MODE"
echo "Profile: $PROFILE"
echo "Graph: $GRAPH"
echo "OD: $OD"
echo "Output: $OUTPUT"
echo

python scripts/run_profile_baseline.py \
  --profile "$PROFILE" \
  --graph "$GRAPH" \
  --od "$OD" \
  --output-dir "$OUTPUT" \
  --workers "$SLURM_CPUS_PER_TASK"
