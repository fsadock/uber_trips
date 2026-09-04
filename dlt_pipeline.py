import dlt

from uber_web import PADRAO_VIAGENS, uber_trips


def run_dlt_pipeline(quantidade=PADRAO_VIAGENS):
    pipeline = dlt.pipeline(
        pipeline_name="uber_receipts",
        destination="duckdb",
        dataset_name="uber",
        export_schema_path="schemas/export",
        import_schema_path="schemas/import",
    )
    return pipeline.run(uber_trips(quantidade=quantidade))


if __name__ == "__main__":
    print(run_dlt_pipeline())
