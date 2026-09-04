WITH
    viagens AS (
        SELECT
            *,
            regexp_replace(
                lower(strip_accents(split_part(from_address, ',', 1))),
                '^(rua|r\.|av\.|avenida|praca)\s+',
                ''
            ) AS rua_origem,
            regexp_replace(
                lower(strip_accents(split_part(to_address, ',', 1))),
                '^(rua|r\.|av\.|avenida|praca)\s+',
                ''
            ) AS rua_destino
        FROM
            {{source ('uber', 'uber_trips')}}
        WHERE
            status = 'COMPLETED'
    ),
    -- Os trajetos de trabalho vêm do seed dbt/seeds/trajetos_trabalho.csv,
    -- que NÃO é versionado: são endereços pessoais. O repositório carrega só o
    -- .example.csv com o formato. Ajustar a regra = editar o CSV + `dbt seed`.
    trajetos AS (
        SELECT
            rua_origem,
            rua_destino,
            sentido
        FROM
            {{ ref('trajetos_trabalho') }}
    )
SELECT
    v.uuid,
    v.trip_date,
    v.time_start,
    v.time_end,
    v.total_brl,
    v.distance_km,
    v.duration_min,
    v.product,
    v.from_address,
    v.to_address,
    v.driver,
    v.begin_time_utc,
    v.dropoff_time_utc,
    CASE
        WHEN isodow(v.trip_date) BETWEEN 1 AND 5  THEN t.sentido
    END AS trip_type
FROM
    viagens v
    LEFT JOIN trajetos t ON v.rua_origem = t.rua_origem
    AND v.rua_destino = t.rua_destino