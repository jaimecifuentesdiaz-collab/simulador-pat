-- Simulador PAT en Supabase, archivo 99: verificación final (PAT 144 b, tarea T8, 20-11-2026).
-- Solo lee el catálogo de PostgreSQL: no cambia nada. Devuelve una fila por control con «ok» = true o false.
-- Todo debe salir true; la última fila resume cuántos controles fallaron.

with
tablas(esquema, tabla) as (
  values ('public', 'perfiles'), ('privado', 'preasignaciones'), ('public', 'proyectos'),
         ('public', 'proyectos_versiones'), ('public', 'actividad'), ('public', 'asignaciones')
),
funciones(firma) as (
  values ('public.rol_actual()'), ('public.es_docente()'), ('public.puede_editar()'),
         ('public.asignar_perfil(uuid,text,text)'), ('public.preasignar(text,text,text)'),
         ('public.guardar_proyecto(bigint,text,jsonb,jsonb,text,text,integer)'),
         ('public.autoguardar_proyecto(bigint,jsonb,jsonb,text,text,text)'), ('public.marcar_ejemplo(bigint,boolean)'),
         ('privado.crear_perfil()'), ('privado.aplicar_preasignacion()'), ('privado.proteger_perfil()'),
         ('privado.proyectos_antes()'), ('privado.proyectos_version()'), ('privado.registrar_actividad()'),
         ('privado.asignaciones_antes()')
),
controles(n, control, ok) as (
  -- 1. existe cada tabla y tiene RLS activo
  select 1, 'RLS activo en ' || t.esquema || '.' || t.tabla,
         coalesce((select c.relrowsecurity from pg_class c join pg_namespace s on s.oid = c.relnamespace
                    where s.nspname = t.esquema and c.relname = t.tabla and c.relkind = 'r'), false)
    from tablas t
  union all
  -- 2. ninguna tabla del esquema public queda sin RLS (en Database, Policies ninguna debe decir «Enable RLS»)
  select 2, 'Ninguna tabla de public sin RLS',
         not exists (select 1 from pg_class c join pg_namespace s on s.oid = c.relnamespace
                      where s.nspname = 'public' and c.relkind in ('r', 'p') and not c.relrowsecurity)
  union all
  -- 3. anon no tiene ningún permiso sobre las tablas del simulador
  select 3, 'anon sin permisos en ' || t.esquema || '.' || t.tabla,
         not (has_table_privilege('anon', format('%I.%I', t.esquema, t.tabla), 'select')
              or has_table_privilege('anon', format('%I.%I', t.esquema, t.tabla), 'insert')
              or has_table_privilege('anon', format('%I.%I', t.esquema, t.tabla), 'update')
              or has_table_privilege('anon', format('%I.%I', t.esquema, t.tabla), 'delete'))
    from tablas t
  union all
  -- 4. el esquema privado no está al alcance de anon ni de authenticated
  select 4, 'Esquema privado cerrado a anon y authenticated',
         not has_schema_privilege('anon', 'privado', 'usage') and not has_schema_privilege('authenticated', 'privado', 'usage')
  union all
  -- 5. nadie cambia su rol ni los datos de un proyecto por fuera de las funciones
  select 5, 'authenticated no puede actualizar perfiles.rol', not has_column_privilege('authenticated', 'public.perfiles', 'rol', 'update')
  union all
  select 5, 'authenticated no puede actualizar proyectos.datos', not has_column_privilege('authenticated', 'public.proyectos', 'datos', 'update')
  union all
  select 5, 'authenticated no puede actualizar proyectos.version', not has_column_privilege('authenticated', 'public.proyectos', 'version', 'update')
  union all
  select 5, 'authenticated no puede insertar proyectos directamente', not has_table_privilege('authenticated', 'public.proyectos', 'insert')
  union all
  select 5, 'authenticated no puede escribir versiones ni actividad',
         not (has_table_privilege('authenticated', 'public.proyectos_versiones', 'insert')
              or has_table_privilege('authenticated', 'public.proyectos_versiones', 'update')
              or has_table_privilege('authenticated', 'public.actividad', 'insert')
              or has_table_privilege('authenticated', 'public.actividad', 'update')
              or has_table_privilege('authenticated', 'public.actividad', 'delete'))
  union all
  -- 6. cada función es security definer con search_path vacío
  select 6, 'security definer y search_path vacío: ' || f.firma,
         coalesce((select p.prosecdef and coalesce(p.proconfig, '{}'::text[]) @> array['search_path=""']
                     from pg_proc p where p.oid = to_regprocedure(f.firma)), false)
    from funciones f
  union all
  -- 7. anon no ejecuta ninguna función del simulador
  select 7, 'anon no ejecuta ' || f.firma,
         to_regprocedure(f.firma) is not null and not has_function_privilege('anon', to_regprocedure(f.firma), 'execute')
    from funciones f
  union all
  -- 8. los disparadores están instalados
  select 8, 'Disparador ' || d.nombre,
         exists (select 1 from pg_trigger g where g.tgname = d.nombre and not g.tgisinternal)
    from (values ('pat_crear_perfil'), ('pat_aplicar_preasignacion'), ('pat_proteger_perfil'), ('pat_actividad_perfiles'),
                 ('pat_proyectos_antes'), ('pat_proyectos_version'), ('pat_actividad_proyectos'),
                 ('pat_asignaciones_antes'), ('pat_actividad_asignaciones')) as d(nombre)
  union all
  -- 9. cada tabla expuesta tiene al menos una regla RLS (preasignaciones queda sin reglas a propósito)
  select 9, 'Reglas RLS en public.' || t.tabla,
         exists (select 1 from pg_policies p where p.schemaname = 'public' and p.tablename = t.tabla)
    from tablas t where t.esquema = 'public'
  union all
  -- 10. no quedaron cuentas de prueba de 98_pruebas.sql
  select 10, 'Sin cuentas de prueba', not exists (select 1 from public.perfiles where email like '%@pruebas.invalid')
)
select n, control, ok from controles
union all
select 99, 'Controles que fallaron: ' || count(*) filter (where not ok), count(*) filter (where not ok) = 0 from controles
order by n, control;
