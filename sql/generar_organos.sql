-- Genera data/masters/organos.jsonl: un registro por cada combinación distinta de
-- (organo_nif, organo_nombre, organo_ciudad, dependencia, organo_tipo_code) vista en
-- todas las licitaciones parseadas, con:
--
--   n_licitaciones      cuántas licitaciones tiene esa combinación exacta.
--   organo_nombre_limpio  el organo_nombre del registro con más licitaciones dentro
--                         de su grupo (organismo_key), con los patrones de firma
--                         simplificados (ver limpiar_nombre_organo). Determinista:
--                         en caso de empate en n_licitaciones, desempata por orden
--                         alfabético de organo_nombre.
--   comunidad_autonoma  extraída de dependencia (solo para COMUNIDADES Y CIUDADES
--                         AUTÓNOMAS y ENTIDADES LOCALES; NULL en el resto). Muchos
--                         organo_nombre de organismos autonómicos no mencionan su
--                         propia comunidad (ej. "Consejería de Turismo, Industria y
--                         Comercio" de Canarias), así que buscar por comunidad
--                         autónoma sobre organo_nombre no los encontraría.
--   fiabilidad          'fiable' o 'revision'. Ver la lógica más abajo.
--   fecha_alta          cuándo se añadió la fila al fichero (timestamp de cuando
--                         se ejecutó este proceso y la detectó como nueva). NULL
--                         para las filas que ya existían antes de añadir esta
--                         columna (2026-08-20) -- no se conoce su fecha real de
--                         alta, y no se ha inventado una.
--
-- Requiere que sql/organismo_key.sql se haya cargado antes en la misma sesión
-- (define la macro organismo_key() que se usa aquí).
--
-- Lógica de fiabilidad, por organo_nif:
--   - Si dos organo_nombre distintos del mismo nif limpian al mismo texto
--     (limpiar_nombre_organo) -> 'fiable'. Señal independiente de dependencia,
--     válida incluso en categorías excluidas de la fusión (ej. Consejerías con
--     varias formas de firma que limpian igual).
--   - Si el nif solo tiene un grupo (organismo_key) en todos los datos -> 'fiable'.
--     No hay nada que decidir: es la única variante vista para ese nif.
--   - Si el nif tiene más de un grupo:
--       - 'fiable' si ese grupo concreto se formó fusionando por dependencia
--         (categoría validada + profundidad suficiente) Y no mezcla más de una
--         organo_ciudad.
--       - 'revision' en cualquier otro caso: o no se pudo fusionar por dependencia
--         (categoría excluida, como COMUNIDADES Y CIUDADES AUTÓNOMAS, o profundidad
--         insuficiente -- ambigüedad conocida sin resolver, caso Castilla y León),
--         o sí se fusionó pero mezcla varias organo_ciudad (posible fusión
--         incorrecta -- caso ENAIRE -- o solo variantes de texto libre de una misma
--         ciudad -- caso Siero; no se puede distinguir automáticamente sin más
--         señal, así que se marca para revisión en vez de decidir en silencio).

-- IMPORTANTE: este proceso ya NO sobrescribe data/masters/organos.jsonl sin más. Las filas
-- que ya existen en el fichero (incluida cualquier limpieza manual hecha a mano)
-- se conservan tal cual, byte a byte -- nunca se recalculan ni se tocan. Solo se
-- añaden filas nuevas cuya combinación (organo_nif, organo_nombre) no existiera
-- ya en el fichero. La comparación ignora mayúsculas/minúsculas, tildes y espacios (ver
-- normalizar_clave en sql/organismo_key.sql). Si la generación en fresco produce más de una fila candidata
-- para el mismo (organo_nif, organo_nombre) que aún no existe, se queda solo con
-- una (la de más licitaciones; en empate, por organo_ciudad/dependencia) para no
-- crear duplicados. Asume que data/masters/organos.jsonl ya existe -- si no existe, créalo
-- primero (p.ej. un fichero con una fila y bórrala, o ejecuta la versión anterior
-- de este proceso una vez).
CREATE OR REPLACE TABLE _organos_generado AS (
    WITH base AS (
        SELECT
            organo_nif,
            organo_nombre,
            organo_ciudad,
            dependencia,
            organo_tipo_code,
            count(*) AS n_licitaciones
        FROM read_ndjson_auto('data/licitaciones_parsed/*.jsonl')
        WHERE organo_nif IS NOT NULL AND organo_nombre IS NOT NULL
        GROUP BY 1, 2, 3, 4, 5
    ),
    con_clave AS (
        SELECT
            *,
            organismo_key(organo_nif, organo_nombre, dependencia) AS organismo,
            contains(organismo_key(organo_nif, organo_nombre, dependencia).clave, ' > ') AS fusionado_por_dependencia
        FROM base
    ),
    grupo_stats AS (
        SELECT organismo, count(DISTINCT organo_ciudad) AS n_ciudades, any_value(fusionado_por_dependencia) AS fusionado_por_dependencia
        FROM con_clave
        GROUP BY organismo
    ),
    nif_stats AS (
        SELECT organo_nif, count(DISTINCT organismo) AS n_grupos_nif
        FROM con_clave
        GROUP BY organo_nif
    ),
    -- Señal independiente de dependencia/ciudad: si dos organo_nombre distintos
    -- del mismo nif limpian al mismo texto (ver limpiar_nombre_organo -- p.ej.
    -- "Alcaldía del Ayuntamiento de X" y "Pleno del Ayuntamiento de X" limpian
    -- ambos a "Ayuntamiento de X"), eso ya confirma que es la misma entidad, sin
    -- necesitar dependencia. Sirve incluso en categorías excluidas de la fusión
    -- por dependencia (COMUNIDADES Y CIUDADES AUTÓNOMAS).
    con_limpio AS (
        SELECT *, limpiar_nombre_organo(organo_nombre) AS nombre_limpio_fila
        FROM con_clave
    ),
    limpio_stats AS (
        SELECT organo_nif, nombre_limpio_fila, count(DISTINCT organo_nombre) AS n_variantes
        FROM con_limpio
        GROUP BY 1, 2
    ),
    con_fiabilidad AS (
        SELECT
            c.*,
            CASE
                WHEN ls.n_variantes > 1 THEN 'fiable'
                -- conflicto de ciudad dentro del grupo: revisar siempre, se haya
                -- fusionado por dependencia o no (caso ENAIRE: 6 direcciones
                -- regionales colapsan en un único grupo por dependencia, pero con
                -- 6 ciudades distintas -- si solo mirásemos n_grupos_nif, este caso
                -- pasaría como "fiable" al tener un solo grupo).
                WHEN gs.n_ciudades > 1 THEN 'revision'
                WHEN gs.fusionado_por_dependencia THEN 'fiable'
                WHEN ns.n_grupos_nif = 1 THEN 'fiable'
                ELSE 'revision'
            END AS fiabilidad
        FROM con_limpio c
        JOIN grupo_stats gs ON gs.organismo = c.organismo
        JOIN nif_stats ns ON ns.organo_nif = c.organo_nif
        JOIN limpio_stats ls ON ls.organo_nif = c.organo_nif AND ls.nombre_limpio_fila = c.nombre_limpio_fila
    ),
    -- El nombre limpio solo se calcula uniendo registros dentro de grupos 'fiable'.
    -- Para grupos 'revision' no nos fiamos lo suficiente de la fusión como para
    -- sintetizar un nombre común (ver bug ENAIRE: colapsaba 6 direcciones
    -- regionales realmente distintas en un solo nombre) -- cada fila conserva su
    -- propio organo_nombre.
    ranked AS (
        SELECT *,
               row_number() OVER (
                   PARTITION BY organismo
                   ORDER BY n_licitaciones DESC, organo_nombre ASC
               ) AS rn
        FROM con_fiabilidad
        WHERE fiabilidad = 'fiable'
    ),
    nombre_limpio AS (
        SELECT organismo, organo_nombre AS organo_nombre_limpio
        FROM ranked
        WHERE rn = 1
    )
    SELECT
        f.fiabilidad,
        f.organo_nif,
        limpiar_nombre_organo(coalesce(nl.organo_nombre_limpio, f.organo_nombre)) AS organo_nombre_limpio,
        f.organo_nombre,
        f.organo_ciudad,
        CASE
            WHEN string_split(f.dependencia, ' > ')[2] IN ('COMUNIDADES Y CIUDADES AUTÓNOMAS', 'ENTIDADES LOCALES')
                THEN string_split(f.dependencia, ' > ')[3]
            ELSE NULL
        END AS comunidad_autonoma,
        -- provincia/municipio: la posición fija no sirve (la profundidad de
        -- dependencia varía según el tipo de entidad -- Ayuntamiento, Diputación,
        -- Mancomunidad, Cabildo...), así que se busca el segmento literal
        -- "Ayuntamientos" (solo existe en ENTIDADES LOCALES) y se toma el de antes
        -- (provincia) y el de después (municipio). NULL para Diputaciones,
        -- Mancomunidades, Cabildos y cualquier entidad cuya dependencia no pase por
        -- "Ayuntamientos" -- su propio nombre ya suele incluir la provincia/isla.
        string_split(f.dependencia, ' > ')[list_position(string_split(f.dependencia, ' > '), 'Ayuntamientos') - 1] AS provincia,
        string_split(f.dependencia, ' > ')[list_position(string_split(f.dependencia, ' > '), 'Ayuntamientos') + 1] AS municipio,
        f.dependencia,
        f.organo_tipo_code,
        f.n_licitaciones
    FROM con_fiabilidad f
    LEFT JOIN nombre_limpio nl ON nl.organismo = f.organismo
);

-- El fichero existente se materializa en una tabla ANTES de escribir nada, para
-- que el COPY de más abajo (que sobrescribe data/masters/organos.jsonl) no afecte a lo que
-- ya se ha leído.
CREATE OR REPLACE TABLE _organos_existente AS (
    SELECT * FROM read_ndjson_auto('data/masters/organos.jsonl')
);

-- De lo generado en fresco, solo las combinaciones (nif, nombre) que no existían
-- ya. Si hay varias candidatas nuevas para la misma combinación (distinta
-- ciudad/dependencia entre licitaciones), se queda con una sola -- determinista:
-- más licitaciones primero, empate por ciudad/dependencia.
CREATE OR REPLACE TABLE _organos_nuevos AS (
    WITH candidatos AS (
        SELECT g.*
        FROM _organos_generado g
        WHERE NOT EXISTS (
            SELECT 1 FROM _organos_existente e
            WHERE normalizar_clave(e.organo_nif) = normalizar_clave(g.organo_nif)
              AND normalizar_clave(e.organo_nombre) = normalizar_clave(g.organo_nombre)
        )
    ),
    ranked AS (
        SELECT *,
               row_number() OVER (
                   PARTITION BY normalizar_clave(organo_nif), normalizar_clave(organo_nombre)
                   ORDER BY n_licitaciones DESC, organo_ciudad, dependencia
               ) AS rn
        FROM candidatos
    )
    SELECT * EXCLUDE (rn), now()::TIMESTAMP AS fecha_alta FROM ranked WHERE rn = 1
);

COPY (
    SELECT * FROM _organos_existente
    UNION ALL
    SELECT * FROM _organos_nuevos
    ORDER BY fiabilidad DESC, organo_nif, organo_nombre
) TO 'data/masters/organos.jsonl' (FORMAT JSON);
