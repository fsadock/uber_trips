import duckdb
import gspread
from gspread_dataframe import set_with_dataframe

from config import load_config

cfg = load_config()


def write_spreadsheet():
    con = duckdb.connect(cfg.UBER_DUCKDB, read_only=True)
    # Só viagens de trabalho: as pessoais ficam no banco com trip_type nulo.
    query = """
        SELECT
            trip_date,
            trip_type,
            total_brl,
            distance_km,
            duration_min,
            time_start,
            from_address,
            time_end,
            to_address
        FROM main.stg_uber_trips
        WHERE trip_type IS NOT NULL
        ORDER BY trip_date, time_start
    """
    data = con.execute(query).df()
    gc = gspread.service_account(filename=cfg.GOOGLE_SERVICE_ACCOUNT)
    spreadsheet = gc.open_by_key(cfg.GOOGLE_API_KEY)
    worksheet = spreadsheet.get_worksheet(cfg.SHEET_ID)

    worksheet.clear()

    set_with_dataframe(
        worksheet,
        data,
        row=1,
        col=1,
        include_index=False,
        include_column_header=True,
    )
    return None


if __name__ == "__main__":
    write_spreadsheet()
