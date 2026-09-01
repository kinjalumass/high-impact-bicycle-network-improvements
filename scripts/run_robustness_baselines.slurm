#!/bin/bash
#SBATCH --job-name=bike-robase
#SBATCH -p cpu,cpu-preempt
#SBATCH -N 1
#SBATCH -c 16
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=slurm-%x-%j.out
#SBATCH --error=slurm-%x-%j.err

set -euo pipefail

module load conda/latest

MODE="$1"

REPO="${BIKE_REPO_ROOT:-$HOME/high-impact-bicycle-network-improvements}"
FINAL="$BIKE_FINAL_ROOT"
COURSE="$BIKE_COURSE_ROOT"

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
