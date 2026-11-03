-- Clave de agrupación de organismos, a partir de organo_nif + organo_nombre + dependencia.
--
-- organo_nif por sí solo junta entidades legalmente distintas que comparten NIF con su
-- matriz (p.ej. cada aeropuerto de AENA, cada Consejería de una comunidad autónoma).
-- organo_nombre por sí solo sobre-fragmenta (Alcaldía/Pleno/Junta de Gobierno de un mismo
-- ayuntamiento aparecen como "organismos" distintos).
--
-- dependencia (la cadena de ParentLocatedParty declarada por cada organismo en su propio
-- XML) es más fiable, pero su profundidad es inconsistente: cada organismo declara el
-- detalle que quiere, sin validación central. Solo se usa como clave de fusión cuando su
-- profundidad alcanza el mínimo validado empíricamente para su categoría (ver sesión de
-- 2026-08-19: comprobado con casos reales de Siero, Castilla y León, Canarias, AENA...).
--
-- COMUNIDADES Y CIUDADES AUTÓNOMAS queda fuera a propósito: ninguna profundidad fija
-- resultó fiable (ej. Servicio Canario de la Salud sigue mezclando 11 hospitales/áreas de
-- salud distintas incluso a profundidad 5).

CREATE OR REPLACE MACRO organismo_key(organo_nif, organo_nombre, dependencia) AS (
    CASE
        WHEN dependencia IS NULL THEN
            {'nif': organo_nif, 'clave': organo_nombre}
        WHEN string_split(dependencia, ' > ')[2] = 'ENTIDADES LOCALES'
             AND len(string_split(dependencia, ' > ')) >= 6 THEN
            {'nif': organo_nif, 'clave': dependencia}
        WHEN string_split(dependencia, ' > ')[2] = 'ADMINISTRACIÓN GENERAL DEL ESTADO'
             AND len(string_split(dependencia, ' > ')) >= 5 THEN
            {'nif': organo_nif, 'clave': dependencia}
        WHEN string_split(dependencia, ' > ')[2] = 'OTRAS ENTIDADES DEL SECTOR PÚBLICO'
             AND len(string_split(dependencia, ' > ')) >= 5 THEN
            {'nif': organo_nif, 'clave': dependencia}
        ELSE
            {'nif': organo_nif, 'clave': organo_nombre}
    END
);

-- organismo_key() aún puede fusionar de más: comprobado con datos reales, ENAIRE
-- (organo_nif Q2822001J) tiene 5 direcciones regionales en 5 ciudades distintas
-- ("ENAIRE. Dirección Región Balear", "...Región Sur", ...) pero su dependencia se
-- para en "ENAIRE" sin bajar a la dirección regional, así que a la profundidad
-- mínima validada para OTRAS ENTIDADES DEL SECTOR PÚBLICO (5) las fusiona por error
-- — mismo patrón de fondo que Castilla y León.
--
-- Se probó a corregirlo automáticamente deshaciendo la fusión cuando organo_ciudad
-- varía dentro del grupo, pero organo_ciudad es texto libre poco fiable (ver Siero:
-- "Pola de Siero" / "La Pola de Siero" / "La Pola Siero" son la misma ciudad) y esa
-- corrección rompía fusiones correctas. Por eso NO se corrige aquí en silencio — ver
-- sql/generar_organos.sql, que en su lugar marca estos casos con fiabilidad='revision'
-- para que se revisen a mano.

-- Normaliza un texto para compararlo: ignora mayúsculas/minúsculas, tildes y
-- diacríticos, espacios al principio/final y espacios repetidos
-- ("Alcaldía  de X " == "alcaldia de x"). Solo se usa para comparar, nunca para el
-- valor que se guarda.
CREATE OR REPLACE MACRO normalizar_clave(texto) AS (
    regexp_replace(strip_accents(lower(trim(texto))), '\s+', ' ', 'g')
);

-- Simplifica los 4 patrones de firma de un ayuntamiento (Alcaldía / Junta de
-- Gobierno [Local] / Pleno / Concejal[ía]... -- incluye "Concejal Presidente del
-- Tagoror...") "... del Ayuntamiento de X" a un único "Ayuntamiento de X". Solo
-- actúa cuando el nombre EMPIEZA por uno de esos términos, para no tocar entidades
-- dependientes con NIF distinto cuyo nombre también contiene "Ayuntamiento de X"
-- sin serlo (ej. el EPEL "Consejo de Administración de Fiestas de Santa Cruz de
-- Tenerife ... del Excmo. Ayuntamiento de Santa Cruz de Tenerife").
-- Mismo criterio para sociedades/entidades con consejo de administración:
-- "Consejo de Administración de [la] X" -> "X" (el "la" es opcional -- "Consejo
-- de Administración de Aguas de Torrelavega" también cuenta), buscando la frase
-- donde sea que aparezca en el nombre, no solo al principio (cubre "Comisión
-- Ejecutiva del Consejo de Administración de..."). Esto también simplifica el
-- EPEL de Santa Cruz de Tenerife ("Consejo de Administración de Fiestas de Santa
-- Cruz de Tenerife...") a "Fiestas de Santa Cruz de Tenerife..." -- pierde el
-- prefijo de firma igual que los demás, pero sigue sin coincidir con
-- "Ayuntamiento de Santa Cruz de Tenerife" (nif distinto, texto distinto), así
-- que no hay riesgo de fusión.
CREATE OR REPLACE MACRO limpiar_nombre_organo(nombre) AS (
    CASE
        WHEN regexp_matches(nombre, '^(Alcaldía|Alcaldia|Junta de Gobierno( Local)?|Pleno|Concejal(ía)?)\b.*Ayuntamiento de ', 'i')
            THEN 'Ayuntamiento de ' || regexp_extract(nombre, 'Ayuntamiento de (.+)$', 1, 'i')
        WHEN regexp_matches(nombre, 'Consejo de Administración de (la )?')
            THEN regexp_extract(nombre, 'Consejo de Administración de (?:la )?(.+)$', 1)
        -- "Pleno del Consell X" / "Presidencia del Consell X" -> "Consell X"
        -- (equivalente valenciano/balear de Ayuntamiento). No coincide con
        -- "Consell d'Administració de..." (es "consejo de administración" en
        -- catalán, otro concepto) porque esa cadena no empieza por Pleno/Presidencia.
        WHEN regexp_matches(nombre, '^(Pleno|Presidencia) del Consell ')
            THEN regexp_extract(nombre, '(Consell .+)$', 1)
        -- Genérico: "Presidencia de la X" / "Pleno de la X" -> "X" (Diputaciones,
        -- Agencias, Asociaciones...). Usa "de la" (femenino), así que no coincide
        -- con "Pleno del Ayuntamiento..." (masculino, "del") ni con los casos ya
        -- cubiertos arriba -- se evalúa después de esos, por si acaso.
        WHEN nombre LIKE 'Presidencia de la %'
            THEN regexp_extract(nombre, '^Presidencia de la (.+)$', 1)
        WHEN nombre LIKE 'Pleno de la %'
            THEN regexp_extract(nombre, '^Pleno de la (.+)$', 1)
        WHEN nombre LIKE 'Junta de Gobierno de la %'
            THEN regexp_extract(nombre, '^Junta de Gobierno de la (.+)$', 1)
        -- Equivalentes en masculino ("del" en vez de "de la"): Cabildos, Consejos
        -- Comarcales, Consorcios... Se evalúan los últimos porque son los más
        -- genéricos -- así, variantes mal escritas de Ayuntamiento que no
        -- coincidieron con la regla específica de arriba (typos, "Ajuntament",
        -- falta el "de") al menos pierden el prefijo de firma, aunque no lleguen a
        -- la forma "Ayuntamiento de X" completa.
        WHEN nombre LIKE 'Pleno del %'
            THEN regexp_extract(nombre, '^Pleno del (.+)$', 1)
        WHEN nombre LIKE 'Presidencia del %'
            THEN regexp_extract(nombre, '^Presidencia del (.+)$', 1)
        WHEN nombre LIKE 'Vicepresidencia del %'
            THEN regexp_extract(nombre, '^Vicepresidencia del (.+)$', 1)
        WHEN nombre LIKE 'Dirección de la %'
            THEN regexp_extract(nombre, '^Dirección de la (.+)$', 1)
        WHEN nombre LIKE 'Gerencia de la %'
            THEN regexp_extract(nombre, '^Gerencia de la (.+)$', 1)
        WHEN nombre LIKE 'Dirección del %'
            THEN regexp_extract(nombre, '^Dirección del (.+)$', 1)
        ELSE nombre
    END
);
