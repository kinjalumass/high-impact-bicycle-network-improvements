"""Validate and summarize the project experiment configuration."""

from bike_improvements.config import get_rider_profiles, load_config


def main() -> None:
    config = load_config()

    print(f"Project: {config['project']['name']}")
    print(f"Study area: {config['study_area']['name']}")
    print(f"Demand trips: {config['demand']['total_modeled_trips']}")
    print()

    print("Rider profiles:")
    for name, profile in get_rider_profiles(config).items():
        weights = profile["lts_weights"]
        print(
            f"  {name}: "
            f"LTS1={weights[1]}, "
            f"LTS2={weights[2]}, "
            f"LTS3={weights[3]}, "
            f"LTS4={weights[4]}"
        )

    print()
    print(
        "Routing algorithms:",
        ", ".join(config["routing"]["algorithms"]),
    )

    print(
        "Maximum candidates:",
        config["candidate_generation"]["maximum_candidates"],
    )

    print(
        "Full intervention simulations:",
        config["intervention_evaluation"]["maximum_full_simulations"],
    )


if __name__ == "__main__":
    main()
