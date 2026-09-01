import pandas as pd

def read_lodes_data(
    data_type,
    state,
    segment,
    job_type,
    year,
    main=True,
    base="https://lehd.ces.census.gov/data/lodes/LODES8/",
):
    """
    Reads LODES RAC, WAC, or OD data based on the specified type.

    Parameters:
    - data_type (str): One of 'rac', 'wac', or 'od' to specify the dataset.
    - state (str): Lowercase two-character state abbreviation (e.g., 'nj').
    - segment (str): Segment type (e.g., 'SA01'). Ignored if 'data_type' is 'od'.
    - job_type (str): Job type (e.g., 'JT00').
    - year (int): Year of data (e.g., 2004).
    - main (bool): Whether to read the 'main' file type. Only used if 'data_type' is 'od'.
    - base (str): Base file path to read data from. Can be URL or local file path.

    Returns:
    - pd.DataFrame: The requested LODES dataset as a pandas DataFrame.
    """
    if data_type not in ["rac", "wac", "od"]:
        raise ValueError("Invalid data type. Choose from 'rac', 'wac', or 'od'.")
    if data_type == "od":
        if main:
            file_url = f"{base}{state}/od/{state}_od_main_{job_type}_{year}.csv.gz"
        else:
            file_url = f"{base}{state}/od/{state}_od_aux_{job_type}_{year}.csv.gz"
        dtype_mapping = {"h_geocode": str, "w_geocode": str}
    else:
        file_url = f"{base}{state}/{data_type}/{state}_{data_type}_{segment}_{job_type}_{year}.csv.gz"
        dtype_mapping = {"h_geocode": str} if data_type == "rac" else {"w_geocode": str}
    return pd.read_csv(file_url, dtype=dtype_mapping)


def read_crosswalk(
    state, cols="all", base="https://lehd.ces.census.gov/data/lodes/LODES8/"
):
    """
    Reads LODES Geography Crosswalk given state.

    Parameters:
    - state (str): Lowercase two-character state abbreviation (e.g., 'nj').
    - cols (list): List of columns to read from the crosswalk in addition to tabblk2020 (Block ID). If "all", all columns will be read and returned.
    - base (str): Base file path to read data from. Can be URL or local file path.

    Returns:
    - pd.DataFrame: The requested LODES crosswalk as a pandas DataFrame.
    """
    file_url = f"{base}{state}/{state}_xwalk.csv.gz"
    dtype_mapping = str
    if cols == "all":
        return pd.read_csv(file_url, dtype=dtype_mapping)
    cols = ["tabblk2020", *cols]
    return pd.read_csv(file_url, dtype=dtype_mapping, usecols=cols)