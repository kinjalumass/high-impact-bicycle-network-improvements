#!/bin/bash
#SBATCH --job-name=bike-intervention
#SBATCH -p cpu,cpu-preempt
#SBATCH -N 1
#SBATCH -c 16
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --array=0-39%10
#SBATCH --output=slurm-%x-%j.out
#SBATCH --error=slurm-%x-%j.err

set -euo pipefail

module load conda/latest

REPO="${BIKE_REPO_ROOT:-$HOME/high-impact-bicycle-network-improvements}"
DATA="$BIKE_FINAL_ROOT"
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

OD="$DATA/output/demand_scenarios/demand_scenario_1/greater_boston_all_pairs_demand_scenario_1.csv"
CANDIDATES="$REPO/results/candidates/candidate_segments.csv"

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

PROFILE_INDEX=$((SLURM_ARRAY_TASK_ID % 4))
CANDIDATE_NUMBER=$((SLURM_ARRAY_TASK_ID / 4 + 1))

PROFILE="${PROFILES[$PROFILE_INDEX]}"
GRAPH="${GRAPHS[$PROFILE_INDEX]}"

printf -v CANDIDATE "C%03d" "$CANDIDATE_NUMBER"

BASELINE="$COURSE/baselines/$PROFILE/od_routes.csv"
OUTPUT="$COURSE/interventions/$CANDIDATE/$PROFILE"

mkdir -p "$OUTPUT"

echo "Task: $SLURM_ARRAY_TASK_ID"
echo "Candidate: $CANDIDATE"
echo "Profile: $PROFILE"
echo "Graph: $GRAPH"
echo "Output: $OUTPUT"
echo

python scripts/run_candidate_intervention.py \
  --candidate-id "$CANDIDATE" \
  --profile "$PROFILE" \
  --graph "$GRAPH" \
  --od "$OD" \
  --candidates "$CANDIDATES" \
  --baseline-routes "$BASELINE" \
  --output-dir "$OUTPUT" \
  --workers "$SLURM_CPUS_PER_TASK"
