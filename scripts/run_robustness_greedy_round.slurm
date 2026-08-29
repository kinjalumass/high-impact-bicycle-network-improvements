#!/bin/bash
#SBATCH --job-name=bike-rogreedy
#SBATCH -p cpu,cpu-preempt
#SBATCH -N 1
#SBATCH -c 16
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=/work/pi_plunkett_umass_edu/bcu/course_project/slurm_logs/rogreedy-%A_%a.out
#SBATCH --error=/work/pi_plunkett_umass_edu/bcu/course_project/slurm_logs/rogreedy-%A_%a.err

set -euo pipefail

module load conda/latest

MODE="$1"
BASE_IDS="$2"
REMAINING="$3"
ROUND="$4"

REPO="$HOME/high-impact-bicycle-network-improvements"
FINAL="/work/pi_plunkett_umass_edu/bcu/final"
COURSE="/work/pi_plunkett_umass_edu/bcu/course_project"

cd "$REPO"

export PYTHONPATH="$REPO/src:${PYTHONPATH:-}"

IFS=',' read -ra CANDIDATES <<< "$REMAINING"

PROFILES=(
  "child"
  "low_confidence_adult"
  "typical_adult"
  "experienced_adult"
)

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

WEIGHT_SCENARIOS=(
  "5"
  "10"
  "15"
  "20"
)

PROFILE_INDEX=$((SLURM_ARRAY_TASK_ID % 4))
CANDIDATE_INDEX=$((SLURM_ARRAY_TASK_ID / 4))

PROFILE="${PROFILES[$PROFILE_INDEX]}"
CANDIDATE="${CANDIDATES[$CANDIDATE_INDEX]}"

PACKAGE_IDS="${BASE_IDS},${CANDIDATE}"
PACKAGE_DIR="${PACKAGE_IDS//,/_}"

BASE_OD="$FINAL/output/demand_scenarios/demand_scenario_1/greater_boston_all_pairs_demand_scenario_1.csv"
ALT_OD="$COURSE/robustness/od_seed_684/greater_boston_all_pairs_seed_684.csv"

EXTRA_ARGS=()

if [ "$MODE" = "high_aversion" ]; then
  GRAPH="${HIGH_AVERSION_GRAPHS[$PROFILE_INDEX]}"
  OD="$BASE_OD"
  BASELINE="$COURSE/robustness/baselines/high_aversion/$PROFILE/od_routes.csv"

  EXTRA_ARGS=(
    --weight-scenario
    "${WEIGHT_SCENARIOS[$PROFILE_INDEX]}"
  )

elif [ "$MODE" = "od_seed_684" ]; then
  GRAPH="${BASELINE_GRAPHS[$PROFILE_INDEX]}"
  OD="$ALT_OD"
  BASELINE="$COURSE/robustness/baselines/od_seed_684/$PROFILE/od_routes.csv"

else
  echo "Unknown mode: $MODE" >&2
  exit 2
fi

OUTPUT="$COURSE/robustness/optimization/$MODE/round_${ROUND}/${PACKAGE_DIR}/${PROFILE}"

mkdir -p "$OUTPUT"

echo "Mode: $MODE"
echo "Round: $ROUND"
echo "Base package: $BASE_IDS"
echo "Candidate being tested: $CANDIDATE"
echo "Package: $PACKAGE_IDS"
echo "Profile: $PROFILE"
echo "Graph: $GRAPH"
echo "OD: $OD"
echo "Baseline: $BASELINE"

if [ "${#EXTRA_ARGS[@]}" -gt 0 ]; then
  echo "Weight scenario: ${WEIGHT_SCENARIOS[$PROFILE_INDEX]}"
else
  echo "Weight scenario: baseline profile"
fi

echo

python scripts/run_combination_intervention.py \
  --candidate-ids "$PACKAGE_IDS" \
  --profile "$PROFILE" \
  --graph "$GRAPH" \
  --od "$OD" \
  --candidates results/candidates/candidate_segments.csv \
  --baseline-routes "$BASELINE" \
  --output-dir "$OUTPUT" \
  --workers "$SLURM_CPUS_PER_TASK" \
  "${EXTRA_ARGS[@]}"
