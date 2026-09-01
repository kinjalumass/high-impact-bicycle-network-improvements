#!/bin/bash
#SBATCH --job-name=bike-roint
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

cd "$REPO"

# Load machine-specific data locations when a local configuration exists.
if [[ -f "$REPO/.project_env" ]]; then
  # shellcheck disable=SC1091
  source "$REPO/.project_env"
fi

: "${BIKE_DATA_ROOT:?Set BIKE_DATA_ROOT or configure .project_env}"
: "${BIKE_FINAL_ROOT:?Set BIKE_FINAL_ROOT or configure .project_env}"
: "${BIKE_COURSE_ROOT:?Set BIKE_COURSE_ROOT or configure .project_env}"

FINAL="$BIKE_FINAL_ROOT"
COURSE="$BIKE_COURSE_ROOT"

export PYTHONPATH="$REPO/src:${PYTHONPATH:-}"

CANDIDATES=(
  "C001"
  "C002"
  "C003"
  "C004"
  "C005"
  "C006"
  "C007"
  "C008"
  "C009"
  "C010"
)

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

BASE_OD="$FINAL/output/demand_scenarios/demand_scenario_1/greater_boston_all_pairs_demand_scenario_1.csv"
ALT_OD="$COURSE/robustness/od_seed_684/greater_boston_all_pairs_seed_684.csv"

EXTRA_ARGS=()

if [ "$MODE" = "high_aversion" ]; then
  GRAPH="${HIGH_AVERSION_GRAPHS[$PROFILE_INDEX]}"
  OD="$BASE_OD"
  BASELINE="$COURSE/robustness/baselines/high_aversion/$PROFILE/od_routes.csv"
  OUTPUT="$COURSE/robustness/interventions/high_aversion/$CANDIDATE/$PROFILE"

  EXTRA_ARGS=(
    --weight-scenario
    "${WEIGHT_SCENARIOS[$PROFILE_INDEX]}"
  )

elif [ "$MODE" = "od_seed_684" ]; then
  GRAPH="${BASELINE_GRAPHS[$PROFILE_INDEX]}"
  OD="$ALT_OD"
  BASELINE="$COURSE/robustness/baselines/od_seed_684/$PROFILE/od_routes.csv"
  OUTPUT="$COURSE/robustness/interventions/od_seed_684/$CANDIDATE/$PROFILE"

else
  echo "Unknown robustness mode: $MODE" >&2
  exit 2
fi

mkdir -p "$OUTPUT"

echo "Mode: $MODE"
echo "Task: $SLURM_ARRAY_TASK_ID"
echo "Candidate: $CANDIDATE"
echo "Profile: $PROFILE"
echo "Graph: $GRAPH"
echo "OD: $OD"
echo "Baseline: $BASELINE"
echo "Output: $OUTPUT"

if [ "${#EXTRA_ARGS[@]}" -gt 0 ]; then
  echo "Weight scenario: ${WEIGHT_SCENARIOS[$PROFILE_INDEX]}"
else
  echo "Weight scenario: baseline profile"
fi

echo

python scripts/run_candidate_intervention.py \
  --candidate-id "$CANDIDATE" \
  --profile "$PROFILE" \
  --graph "$GRAPH" \
  --od "$OD" \
  --candidates results/candidates/candidate_segments.csv \
  --baseline-routes "$BASELINE" \
  --output-dir "$OUTPUT" \
  --workers "$SLURM_CPUS_PER_TASK" \
  "${EXTRA_ARGS[@]}"
