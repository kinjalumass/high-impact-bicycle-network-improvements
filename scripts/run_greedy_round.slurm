#!/bin/bash
#SBATCH --job-name=bike-greedy
#SBATCH -p cpu,cpu-preempt
#SBATCH -N 1
#SBATCH -c 16
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=/work/pi_plunkett_umass_edu/bcu/course_project/slurm_logs/greedy-%A_%a.out
#SBATCH --error=/work/pi_plunkett_umass_edu/bcu/course_project/slurm_logs/greedy-%A_%a.err

set -euo pipefail

module load conda/latest

BASE_IDS="$1"
REMAINING="$2"
ROUND="$3"

REPO="$HOME/high-impact-bicycle-network-improvements"
DATA="/work/pi_plunkett_umass_edu/bcu/final"
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

GRAPHS=(
  "$DATA/output/cost_scenarios/cost_scenario_1/greater_boston_cost_scenario_1_simplified.graphml"
  "$COURSE/profile_graphs/greater_boston_low_confidence_adult_scenario_6_simplified.graphml"
  "$COURSE/profile_graphs/greater_boston_typical_adult_scenario_11_simplified.graphml"
  "$COURSE/profile_graphs/greater_boston_experienced_adult_scenario_16_simplified.graphml"
)

PROFILE_INDEX=$((SLURM_ARRAY_TASK_ID % 4))
CANDIDATE_INDEX=$((SLURM_ARRAY_TASK_ID / 4))

PROFILE="${PROFILES[$PROFILE_INDEX]}"
CANDIDATE="${CANDIDATES[$CANDIDATE_INDEX]}"
GRAPH="${GRAPHS[$PROFILE_INDEX]}"

PACKAGE_IDS="${BASE_IDS},${CANDIDATE}"
PACKAGE_DIR="${PACKAGE_IDS//,/_}"

OD="$DATA/output/demand_scenarios/demand_scenario_1/greater_boston_all_pairs_demand_scenario_1.csv"
BASELINE="$COURSE/baselines/$PROFILE/od_routes.csv"
OUTPUT="$COURSE/optimization/round_${ROUND}/${PACKAGE_DIR}/${PROFILE}"

mkdir -p "$OUTPUT"

echo "Round: $ROUND"
echo "Task: $SLURM_ARRAY_TASK_ID"
echo "Base package: $BASE_IDS"
echo "Candidate being tested: $CANDIDATE"
echo "Package: $PACKAGE_IDS"
echo "Profile: $PROFILE"
echo "Output: $OUTPUT"
echo

python scripts/run_combination_intervention.py \
  --candidate-ids "$PACKAGE_IDS" \
  --profile "$PROFILE" \
  --graph "$GRAPH" \
  --od "$OD" \
  --candidates results/candidates/candidate_segments.csv \
  --baseline-routes "$BASELINE" \
  --output-dir "$OUTPUT" \
  --workers "$SLURM_CPUS_PER_TASK"
