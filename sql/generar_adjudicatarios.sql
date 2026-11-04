-- Genera data/masters/adjudicatarios.jsonl: un registro por cada combinación distinta de
-- (nif_adjudicatario, adjudicatario) vista en las licitaciones y contratos menores
-- parseados, con:
--
--   nif_normalizado     nif_adjudicatario en mayúsculas, sin espacios/puntos/guiones/
--                         barras y sin prefijo "ES" de IVA intracomunitario
--                         ("B-79418471", "ESB79418471" -> "B79418471").
--   nif_agrupable       si nif_normalizado parece un NIF/NIE español o un IVA
--                         extranjero. False para NIFs anonimizados de personas
--                         físicas ("***2317**"), identificadores numéricos internos
--                         ("334643", típicos de UTEs) y basura ("N/A", "U/K"...):
--                         agrupar por ellos juntaría entidades distintas.
--   es_ute              Unión Temporal de Empresas: NIF que empieza por U, o nombre
--                         que empieza por "UTE"/"U.T.E." o contiene "Unión Temporal".
--   adjudicatario_limpio  nombre canónico del grupo (ver adjudicatario_key): la
--                         variante más frecuente, en mayúsculas y con la forma
--                         societaria unificada (ver limpiar_nombre_adjudicatario). En empate, la de
--                         adjudicación más reciente (cubre cambios de razón social).
--   fiabilidad          'fiable' si el nombre de la fila se parece al canónico del
--                         grupo (uno contiene al otro, o jaro-winkler >= 0.85), si no
--                         'revision': cambio de razón social, nombre comercial,
--                         error de NIF... (ej. "AULOCE SA (ESPUBLICO)" bajo el NIF de
--                         Espublico Servicios para la Administración).
--   n_contratos         licitaciones/contratos menores distintos (por id) con esa
--                         combinación exacta.
--   fecha_ultima_adjudicacion  la más reciente de esa combinación exacta.
--   fecha_alta          cuándo se añadió la fila al fichero.
--
-- Clave de agrupación: el NIF es la identidad jurídica de una empresa, así que basta
-- con agrupar por nif_normalizado (a diferencia de los órganos, que comparten NIF con
-- su matriz -- ver sql/organismo_key.sql). Excepciones:
--   - UTE con el NIF de una de sus socias (pasa en ~1.500 filas, p.ej. "UTE TdE -
--     TSOL" con el NIF de Telefónica de España): se agrupa por (nif, nombre) para no
--     fusionar la UTE con la empresa socia.
--   - nif no agrupable: se agrupa solo por nombre normalizado.
--
-- Igual que sql/generar_organos.sql, este proceso NO sobrescribe las filas que ya
-- existen en data/masters/adjudicatarios.jsonl (incluida cualquier corrección manual): solo
-- añade combinaciones (nif_adjudicatario, adjudicatario) nuevas, comparando con
-- normalizar_clave. Una fila nueva de un grupo que ya existe en el fichero hereda el
-- adjudicatario_limpio que tenga ese grupo en el fichero, para que una corrección
-- manual se propague a las variantes que aparezcan después.
--
-- Al cruzar con las licitaciones, usar normalizar_clave() en ambos lados (las
-- variantes que solo difieren en mayúsculas/tildes/espacios comparten una fila).
--
-- Requiere que sql/organismo_key.sql se haya cargado antes en la misma sesión
-- (define normalizar_clave). Si data/masters/adjudicatarios.jsonl no existe, crearlo vacío
-- (touch) antes de la primera ejecución:
--
--   touch data/masters/adjudicatarios.jsonl
--   duckdb -c ".read sql/organismo_key.sql" -c ".read sql/generar_adjudicatarios.sql"

CREATE OR REPLACE MACRO normalizar_nif(nif) AS (
    regexp_replace(
        regexp_replace(upper(trim(nif)), '[\s.\-/]', '', 'g'),
        '^ES([A-HJ-NP-SUVW][0-9]{7}[0-9A-J]|[0-9]{8}[A-Z]|[XYZKLM][0-9]{7}[A-Z])$', '\1'
    )
);

-- Recibe un nif ya normalizado. Español: CIF (letra + 7 dígitos + control), DNI
-- (8 dígitos + letra) o NIE (X/Y/Z/K/L/M + 7 dígitos + letra). Extranjero: prefijo
-- de país de 2 letras + al menos 6 caracteres. Se descartan los de relleno con 7+
-- ceros seguidos ("00000000X", "A00000000", "U00000000"...): bajo cada uno aparecen
-- decenas de empresas sin relación entre sí.
CREATE OR REPLACE MACRO nif_agrupable(nif) AS (
    (regexp_matches(nif, '^([A-HJ-NP-SUVW][0-9]{7}[0-9A-J]|[0-9]{8}[A-Z]|[XYZKLM][0-9]{7}[A-Z])$')
     OR regexp_matches(nif, '^[A-Z]{2}[0-9A-Z]{6,}$'))
    AND NOT contains(nif, '0000000')
);

CREATE OR REPLACE MACRO es_ute(nif, nombre) AS (
    nif LIKE 'U%'
    OR regexp_matches(nombre, '^\W*U\.?\s?T\.?\s?E\b', 'i')
    OR regexp_matches(strip_accents(nombre), 'union temporal', 'i')
);

-- Unifica la forma societaria al final del nombre ("S.A.U." / "SAU" / "S.A.U," /
-- "S. A. U." -> ", S.A.U.") y quita comillas y puntuación sobrante. Las formas más
-- largas se prueban antes que las cortas (SLU antes que SL) y se exige un separador
-- delante, para no tocar palabras que acaban igual ("EMPRESA").
CREATE OR REPLACE MACRO _forma_societaria(n) AS (
    CASE
        WHEN regexp_matches(n, '[\s,]+(S\.?\s?A\.?\s?U\.?|Sociedad An[oó]nima Unipersonal)$', 'i')
            THEN regexp_replace(n, '[\s,]+(S\.?\s?A\.?\s?U\.?|Sociedad An[oó]nima Unipersonal)$', ', S.A.U.', 'i')
        WHEN regexp_matches(n, '[\s,]+(S\.?\s?L\.?\s?U\.?|Sociedad Limitada Unipersonal)$', 'i')
            THEN regexp_replace(n, '[\s,]+(S\.?\s?L\.?\s?U\.?|Sociedad Limitada Unipersonal)$', ', S.L.U.', 'i')
        WHEN regexp_matches(n, '[\s,]+S\.?\s?L\.?\s?L\.?$', 'i')
            THEN regexp_replace(n, '[\s,]+S\.?\s?L\.?\s?L\.?$', ', S.L.L.', 'i')
        WHEN regexp_matches(n, '[\s,]+(S\.?\s?L\.?|Sociedad Limitada)$', 'i')
            THEN regexp_replace(n, '[\s,]+(S\.?\s?L\.?|Sociedad Limitada)$', ', S.L.', 'i')
        WHEN regexp_matches(n, '[\s,]+(S\.?\s?A\.?|Sociedad An[oó]nima)$', 'i')
            THEN regexp_replace(n, '[\s,]+(S\.?\s?A\.?|Sociedad An[oó]nima)$', ', S.A.', 'i')
        ELSE n
    END
);

CREATE OR REPLACE MACRO _sin_ruido(nombre) AS (
    regexp_replace(trim(regexp_replace(regexp_replace(upper(nombre),'["“”«»]', '', 'g'), '\s+', ' ', 'g')), '[\s,;]+$', '')
);

-- "S.M.E." (sociedad mercantil estatal) va detrás de la forma societaria
-- ("Correos y Telégrafos, S.A., S.M.E."), así que se separa, se limpia el resto y se
-- vuelve a añadir.
CREATE OR REPLACE MACRO limpiar_nombre_adjudicatario(nombre) AS (
    CASE
        WHEN regexp_matches(_sin_ruido(nombre), '[\s,]+S\.?\s?M\.?\s?E\.?$', 'i')
            THEN _forma_societaria(_sin_ruido(regexp_replace(_sin_ruido(nombre), '[\s,]+S\.?\s?M\.?\s?E\.?$', '', 'i'))) || ', S.M.E.'
        ELSE _forma_societaria(_sin_ruido(nombre))
    END
);

CREATE OR REPLACE MACRO adjudicatario_key(nif_normalizado, nif_agrupable, es_ute, adjudicatario) AS (
    CASE
        WHEN NOT nif_agrupable THEN {'nif': NULL, 'nombre': normalizar_clave(limpiar_nombre_adjudicatario(adjudicatario))}
        WHEN es_ute AND nif_normalizado NOT LIKE 'U%' THEN {'nif': nif_normalizado, 'nombre': normalizar_clave(limpiar_nombre_adjudicatario(adjudicatario))}
        ELSE {'nif': nif_normalizado, 'nombre': NULL}
    END
);

-- Palabras ordenadas alfabéticamente: las personas físicas aparecen tanto como
-- "Nombre Apellidos" como "APELLIDOS, NOMBRE".
CREATE OR REPLACE MACRO _palabras_ordenadas(n) AS (
    array_to_string(list_sort(list_filter(regexp_split_to_array(normalizar_clave(n), '[^a-z0-9]+'), lambda p: p <> '')), ' ')
);

CREATE OR REPLACE MACRO _parecidos(a, b) AS (
    contains(normalizar_clave(a), normalizar_clave(b))
    OR contains(normalizar_clave(b), normalizar_clave(a))
    OR jaro_winkler_similarity(normalizar_clave(a), normalizar_clave(b)) >= 0.85
    OR jaro_winkler_similarity(_palabras_ordenadas(a), _palabras_ordenadas(b)) >= 0.85
);

CREATE OR REPLACE MACRO fiabilidad_adjudicatario(adjudicatario, adjudicatario_limpio) AS (
    CASE WHEN _parecidos(limpiar_nombre_adjudicatario(adjudicatario), adjudicatario_limpio) THEN 'fiable' ELSE 'revision' END
);

CREATE OR REPLACE TABLE _adjudicatarios_generado AS (
    WITH fuente AS (
        SELECT id, nif_adjudicatario, adjudicatario, fecha_adjudicacion
        FROM read_ndjson(['data/licitaciones_parsed/*.jsonl', 'data/contratos_menores_parsed/*.jsonl'], columns = {
            'id': 'VARCHAR', 'nif_adjudicatario': 'VARCHAR', 'adjudicatario': 'VARCHAR', 'fecha_adjudicacion': 'DATE'
        })
        WHERE nif_adjudicatario IS NOT NULL AND adjudicatario IS NOT NULL
    ),
    base AS (
        SELECT
            nif_adjudicatario,
            adjudicatario,
            normalizar_nif(nif_adjudicatario) AS nif_normalizado,
            nif_agrupable(normalizar_nif(nif_adjudicatario)) AS nif_agrupable,
            es_ute(normalizar_nif(nif_adjudicatario), adjudicatario) AS es_ute,
            count(DISTINCT id) AS n_contratos,
            max(fecha_adjudicacion) AS fecha_ultima_adjudicacion
        FROM fuente
        GROUP BY 1, 2
    ),
    con_clave AS (
        SELECT
            *,
            adjudicatario_key(nif_normalizado, nif_agrupable, es_ute, adjudicatario) AS grupo,
            normalizar_clave(limpiar_nombre_adjudicatario(adjudicatario)) AS variante
        FROM base
    ),
    -- Votos por variante normalizada (así "TELEFÓNICA ..." y "Telefonica ..." suman
    -- juntos); dentro de la variante ganadora, la grafía con más contratos.
    variantes AS (
        SELECT grupo, variante, sum(n_contratos) AS n, max(fecha_ultima_adjudicacion) AS ultima,
               arg_max(adjudicatario, n_contratos) AS grafia
        FROM con_clave
        GROUP BY 1, 2
    ),
    canonico AS (
        SELECT grupo, arg_max(limpiar_nombre_adjudicatario(grafia), (n, ultima, grafia)) AS adjudicatario_limpio
        FROM variantes
        GROUP BY 1
    )
    SELECT
        fiabilidad_adjudicatario(c.adjudicatario, k.adjudicatario_limpio) AS fiabilidad,
        c.nif_adjudicatario,
        c.nif_normalizado,
        k.adjudicatario_limpio,
        c.adjudicatario,
        c.nif_agrupable,
        c.es_ute,
        c.n_contratos,
        c.fecha_ultima_adjudicacion
    FROM con_clave c
    JOIN canonico k USING (grupo)
);

-- El fichero existente se materializa ANTES del COPY que lo sobrescribe. Columnas
-- explícitas para que funcione también con el fichero vacío de la primera ejecución.
CREATE OR REPLACE TABLE _adjudicatarios_existente AS (
    SELECT * FROM read_ndjson('data/masters/adjudicatarios.jsonl', columns = {
        'fiabilidad': 'VARCHAR', 'nif_adjudicatario': 'VARCHAR', 'nif_normalizado': 'VARCHAR',
        'adjudicatario_limpio': 'VARCHAR', 'adjudicatario': 'VARCHAR', 'nif_agrupable': 'BOOLEAN',
        'es_ute': 'BOOLEAN', 'n_contratos': 'BIGINT', 'fecha_ultima_adjudicacion': 'DATE',
        'fecha_alta': 'TIMESTAMP'
    })
);

CREATE OR REPLACE TABLE _adjudicatarios_nuevos AS (
    WITH candidatos AS (
        SELECT g.*
        FROM _adjudicatarios_generado g
        WHERE NOT EXISTS (
            SELECT 1 FROM _adjudicatarios_existente e
            WHERE normalizar_clave(e.nif_adjudicatario) = normalizar_clave(g.nif_adjudicatario)
              AND normalizar_clave(e.adjudicatario) = normalizar_clave(g.adjudicatario)
        )
    ),
    ranked AS (
        SELECT *,
               row_number() OVER (
                   PARTITION BY normalizar_clave(nif_adjudicatario), normalizar_clave(adjudicatario)
                   ORDER BY n_contratos DESC, adjudicatario
               ) AS rn
        FROM candidatos
    ),
    -- Nombre que ya tiene cada grupo en el fichero (el más repetido, por si se ha
    -- corregido a mano solo en parte de sus filas).
    limpio_existente AS (
        SELECT adjudicatario_key(nif_normalizado, nif_agrupable, es_ute, adjudicatario) AS grupo,
               mode(adjudicatario_limpio) AS adjudicatario_limpio
        FROM _adjudicatarios_existente
        GROUP BY 1
    )
    SELECT r.* EXCLUDE (rn, fiabilidad, adjudicatario_limpio),
           fiabilidad_adjudicatario(r.adjudicatario, coalesce(le.adjudicatario_limpio, r.adjudicatario_limpio)) AS fiabilidad,
           coalesce(le.adjudicatario_limpio, r.adjudicatario_limpio) AS adjudicatario_limpio,
           now()::TIMESTAMP AS fecha_alta
    FROM ranked r
    LEFT JOIN limpio_existente le
        ON le.grupo = adjudicatario_key(r.nif_normalizado, r.nif_agrupable, r.es_ute, r.adjudicatario)
    WHERE r.rn = 1
);

COPY (
    SELECT * FROM _adjudicatarios_existente
    UNION ALL BY NAME
    SELECT * FROM _adjudicatarios_nuevos
    ORDER BY fiabilidad DESC, nif_normalizado, adjudicatario
) TO 'data/masters/adjudicatarios.jsonl' (FORMAT JSON);
