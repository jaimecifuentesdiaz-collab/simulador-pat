-- Simulador PAT en Supabase, archivo 04 de 6: reglas RLS y permisos mínimos (PAT 144 b, tarea T8, 20-11-2026).
-- Requiere 01 a 03. Se puede volver a ejecutar («drop policy if exists»).
--
-- Quién ve y quién cambia qué:
--   estudiante  ve y edita solo sus proyectos; ve los ejemplos y su propia asignación
--   docente     ve todos los proyectos del curso (todas las cuentas), sus versiones y la actividad; asigna roles a otras cuentas,
--               publica ejemplos y escribe las asignaciones; edita solo sus propios proyectos
--   visita      solo lectura de los proyectos de ejemplo
--   anon        nada (sin sesión no se lee ni se escribe ninguna tabla)
-- Nadie cambia su propio rol: la columna rol no tiene permiso de update y el disparador pat_proteger_perfil lo impide.
-- Los datos de un proyecto solo cambian con public.guardar_proyecto y public.autoguardar_proyecto (control de versión).

-- ---------------------------------------------------------------- RLS activo (repetido a propósito: este archivo se basta solo)
alter table public.perfiles            enable row level security;
alter table privado.preasignaciones    enable row level security;
alter table public.proyectos           enable row level security;
alter table public.proyectos_versiones enable row level security;
alter table public.actividad           enable row level security;
alter table public.asignaciones        enable row level security;

-- ---------------------------------------------------------------- permisos de tablas: primero se quita todo
revoke all on table public.perfiles, public.proyectos, public.proyectos_versiones, public.actividad, public.asignaciones
  from public, anon, authenticated;
revoke all on table privado.preasignaciones from public, anon, authenticated;
revoke all on schema privado from public, anon, authenticated;

-- y después se da lo mínimo a las cuentas con sesión (authenticated)
grant usage on schema public to authenticated;
grant select on table public.perfiles to authenticated;
grant update (nombre) on table public.perfiles to authenticated;
grant select, delete on table public.proyectos to authenticated;
grant update (nombre) on table public.proyectos to authenticated;
grant select on table public.proyectos_versiones to authenticated;
grant select on table public.actividad to authenticated;
grant select, insert, update, delete on table public.asignaciones to authenticated;

-- ---------------------------------------------------------------- permisos de funciones
revoke all on function public.rol_actual()                                              from public, anon;
revoke all on function public.es_docente()                                              from public, anon;
revoke all on function public.puede_editar()                                            from public, anon;
revoke all on function public.asignar_perfil(uuid, text, text)                           from public, anon;
revoke all on function public.preasignar(text, text, text)                               from public, anon;
revoke all on function public.guardar_proyecto(bigint, text, jsonb, jsonb, text, text, integer) from public, anon;
revoke all on function public.autoguardar_proyecto(bigint, jsonb, jsonb, text, text, text) from public, anon;
revoke all on function public.marcar_ejemplo(bigint, boolean)                            from public, anon;
revoke all on function privado.crear_perfil()           from public, anon, authenticated;
revoke all on function privado.aplicar_preasignacion()  from public, anon, authenticated;
revoke all on function privado.proteger_perfil()        from public, anon, authenticated;
revoke all on function privado.proyectos_antes()        from public, anon, authenticated;
revoke all on function privado.proyectos_version()      from public, anon, authenticated;
revoke all on function privado.registrar_actividad()    from public, anon, authenticated;
revoke all on function privado.asignaciones_antes()     from public, anon, authenticated;

grant execute on function public.rol_actual()                                              to authenticated;
grant execute on function public.es_docente()                                              to authenticated;
grant execute on function public.puede_editar()                                            to authenticated;
grant execute on function public.asignar_perfil(uuid, text, text)                           to authenticated;
grant execute on function public.preasignar(text, text, text)                               to authenticated;
grant execute on function public.guardar_proyecto(bigint, text, jsonb, jsonb, text, text, integer) to authenticated;
grant execute on function public.autoguardar_proyecto(bigint, jsonb, jsonb, text, text, text) to authenticated;
grant execute on function public.marcar_ejemplo(bigint, boolean)                            to authenticated;

-- ---------------------------------------------------------------- reglas RLS: perfiles
drop policy if exists perfiles_ver on public.perfiles;
create policy perfiles_ver on public.perfiles
  for select to authenticated
  using (id = (select auth.uid()) or (select public.es_docente()));

drop policy if exists perfiles_editar_nombre on public.perfiles;
create policy perfiles_editar_nombre on public.perfiles
  for update to authenticated
  using (id = (select auth.uid()))
  with check (id = (select auth.uid()));
-- sin reglas de insert ni delete: los perfiles los crea el disparador y se borran con la cuenta

-- ---------------------------------------------------------------- reglas RLS: proyectos
drop policy if exists proyectos_ver on public.proyectos;
create policy proyectos_ver on public.proyectos
  for select to authenticated
  using (owner_id = (select auth.uid()) or es_ejemplo or (select public.es_docente()));

drop policy if exists proyectos_renombrar on public.proyectos;
create policy proyectos_renombrar on public.proyectos
  for update to authenticated
  using (owner_id = (select auth.uid()) and (select public.puede_editar()))
  with check (owner_id = (select auth.uid()));

drop policy if exists proyectos_eliminar on public.proyectos;
create policy proyectos_eliminar on public.proyectos
  for delete to authenticated
  using (owner_id = (select auth.uid()) and (select public.puede_editar()));
-- sin regla de insert: los proyectos se crean con public.guardar_proyecto o public.autoguardar_proyecto

-- ---------------------------------------------------------------- reglas RLS: versiones
drop policy if exists versiones_ver on public.proyectos_versiones;
create policy versiones_ver on public.proyectos_versiones
  for select to authenticated
  using (exists (select 1 from public.proyectos p
                  where p.id = proyecto_id
                    and (p.owner_id = (select auth.uid()) or p.es_ejemplo or (select public.es_docente()))));

-- ---------------------------------------------------------------- reglas RLS: actividad
drop policy if exists actividad_ver on public.actividad;
create policy actividad_ver on public.actividad
  for select to authenticated
  using (actor_id = (select auth.uid()) or (select public.es_docente()));

-- ---------------------------------------------------------------- reglas RLS: asignaciones
drop policy if exists asignaciones_ver on public.asignaciones;
create policy asignaciones_ver on public.asignaciones
  for select to authenticated
  using (estudiante_id = (select auth.uid()) or (select public.es_docente()));

drop policy if exists asignaciones_crear on public.asignaciones;
create policy asignaciones_crear on public.asignaciones
  for insert to authenticated
  with check ((select public.es_docente()));

drop policy if exists asignaciones_cambiar on public.asignaciones;
create policy asignaciones_cambiar on public.asignaciones
  for update to authenticated
  using ((select public.es_docente()))
  with check ((select public.es_docente()));

drop policy if exists asignaciones_quitar on public.asignaciones;
create policy asignaciones_quitar on public.asignaciones
  for delete to authenticated
  using ((select public.es_docente()));

-- privado.preasignaciones: RLS activo y sin reglas ni permisos; solo se escribe desde SQL Editor o con public.preasignar
