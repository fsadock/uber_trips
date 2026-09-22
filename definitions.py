import subprocess

from dagster import (
    AssetExecutionContext,
    Config,
    DefaultScheduleStatus,
    Definitions,
    ScheduleDefinition,
    asset,
    define_asset_job,
)

from dlt_pipeline import run_dlt_pipeline
from write_spreadsheet import write_spreadsheet


class UberConfig(Config):
    """Quantas viagens buscar. 60 cobre um mês fechado com folga; para um
    backfill do histórico, dispare o job com um número bem maior (ex.: 500)."""

    quantidade: int = 60


@asset
def raw_uber_trips(context: AssetExecutionContext, config: UberConfig):
    context.log.info(str(run_dlt_pipeline(config.quantidade)))


@asset(deps=[raw_uber_trips])
def dbt_staging(context: AssetExecutionContext):
    # `build` em vez de `run`: carrega o seed dos trajetos, constrói o modelo e
    # roda os testes, na ordem de dependência. O `+` inclui o seed a montante.
    subprocess.run(
        ["dbt", "build", "--select", "+stg_uber_trips", "--profiles-dir", "."],
        cwd="dbt",
        check=True,
    )


@asset(deps=[dbt_staging])
def google_sheet(context: AssetExecutionContext):
    write_spreadsheet()


uber_job = define_asset_job("uber_job")

# Uma vez por mês, no dia 1º: as 60 viagens cobrem o mês que acabou de fechar e
# o merge pelo uuid absorve qualquer sobreposição com a execução anterior.
# Ligado por padrão e no fuso de Brasília: sem isso o Dagster sobe com o agendamento parado e conta o
# cron em UTC.
monthly_schedule = ScheduleDefinition(
    job=uber_job,
    cron_schedule="0 8 1 * *",
    execution_timezone="America/Sao_Paulo",
    default_status=DefaultScheduleStatus.RUNNING,
)

defs = Definitions(
    assets=[raw_uber_trips, dbt_staging, google_sheet],
    jobs=[uber_job],
    schedules=[monthly_schedule],
)
