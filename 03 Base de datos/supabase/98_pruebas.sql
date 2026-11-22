-- Simulador PAT en Supabase, archivo 98: pruebas de permisos (PAT 144 b, tarea T8, 20-11-2026).
-- Se ejecuta en SQL Editor después de 01 a 04. Crea cuentas de prueba DENTRO de una transacción, actúa como cada una
-- (set local role authenticated y request.jwt.claims, como lo hace la Data API) y al final deshace todo con rollback:
-- no deja cuentas, proyectos ni actividad. Si una regla falla, se detiene con «FALLA: …»; si todo está bien, el último
-- resultado dice «98_pruebas: todas las pruebas pasaron».

begin;

-- ---------------------------------------------------------------- cuentas de prueba (como administrador)
insert into privado.preasignaciones (email, rol, nombre) values
  ('prueba.docente@pruebas.invalid', 'docente', 'Docente de prueba'),
  ('prueba.est1@pruebas.invalid', 'estudiante', 'Estudiante uno'),
  ('prueba.est2@pruebas.invalid', 'estudiante', 'Estudiante dos')
on conflict (email) do update set rol = excluded.rol, nombre = excluded.nombre;

insert into auth.users (id, email, aud, role, raw_user_meta_data) values
  ('00000000-0000-4000-8000-00000000d001', 'prueba.docente@pruebas.invalid', 'authenticated', 'authenticated', '{}'),
  ('00000000-0000-4000-8000-00000000e001', 'prueba.est1@pruebas.invalid',    'authenticated', 'authenticated', '{}'),
  ('00000000-0000-4000-8000-00000000e002', 'prueba.est2@pruebas.invalid',    'authenticated', 'authenticated', '{}'),
  ('00000000-0000-4000-8000-00000000f001', 'prueba.visita@pruebas.invalid',  'authenticated', 'authenticated', '{}');

do $$
begin
  if (select rol from public.perfiles where id = '00000000-0000-4000-8000-00000000d001') is distinct from 'docente' then
    raise exception 'FALLA: la preasignación no dejó a la cuenta docente con su rol';
  end if;
  if (select rol from public.perfiles where id = '00000000-0000-4000-8000-00000000f001') is distinct from 'visita' then
    raise exception 'FALLA: una cuenta sin preasignación no partió como visita';
  end if;
  if (select usuario from public.perfiles where id = '00000000-0000-4000-8000-00000000e001') is distinct from 'prueba.est1' then
    raise exception 'FALLA: el usuario corto no es la parte del correo antes de la arroba';
  end if;
end $$;

-- ---------------------------------------------------------------- sin sesión (anon): nada
set local role anon;
do $$
begin
  begin
    perform 1 from public.proyectos limit 1;
    raise exception 'FALLA: anon pudo leer public.proyectos';
  exception when insufficient_privilege then null;
  end;
  begin
    perform public.guardar_proyecto(null, 'x', '{}'::jsonb);
    raise exception 'FALLA: anon pudo ejecutar guardar_proyecto';
  exception when insufficient_privilege then null;
  end;
  begin
    perform 1 from privado.preasignaciones limit 1;
    raise exception 'FALLA: anon pudo leer privado.preasignaciones';
  exception when insufficient_privilege then null;
  end;
end $$;
reset role;

-- ---------------------------------------------------------------- estudiante uno: guarda, versiona y choca con un conflicto
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"00000000-0000-4000-8000-00000000e001","role":"authenticated"}', true);
do $$
declare
  r jsonb;
  v_id bigint;
begin
  r := public.guardar_proyecto(null, 'Proyecto de Estudiante uno 1', '{"planta":{"equipos":[]},"estado":{}}'::jsonb,
                               '{"equipos":0}'::jsonb, 'Estudiante uno', 'primera');
  v_id := (r ->> 'id')::bigint;
  perform set_config('pruebas.proyecto_e1', v_id::text, true);
  if (r ->> 'version')::int <> 1 or not (r ->> 'nuevo')::boolean then
    raise exception 'FALLA: el proyecto nuevo no quedó en la versión 1';
  end if;
  r := public.guardar_proyecto(v_id, '', '{"planta":{"equipos":[1]},"estado":{}}'::jsonb, '{}'::jsonb, '', 'segunda', 1);
  if (r ->> 'version')::int <> 2 then
    raise exception 'FALLA: la segunda versión no quedó en 2';
  end if;
  begin                                                    -- otra sesión que abrió la versión 1 intenta guardar
    perform public.guardar_proyecto(v_id, '', '{"planta":{},"estado":{}}'::jsonb, '{}'::jsonb, '', 'pisaría la 2', 1);
    raise exception 'FALLA: guardar con una versión vieja no se rechazó';
  exception when sqlstate 'PT409' then null;
  end;
  if (select count(*) from public.proyectos_versiones where proyecto_id = v_id) <> 2 then
    raise exception 'FALLA: el historial no tiene las 2 versiones';
  end if;
  begin                                                    -- nombre repetido de la misma cuenta
    perform public.guardar_proyecto(null, 'proyecto de estudiante uno 1', '{}'::jsonb);
    raise exception 'FALLA: se aceptó un nombre repetido';
  exception when unique_violation then null;
  end;
  r := public.autoguardar_proyecto(v_id, '{"planta":{"equipos":[1,2]},"estado":{}}'::jsonb, '{}'::jsonb, 'huella');
  if (select version from public.proyectos where id = v_id) <> 2
     or (select count(*) from public.proyectos_versiones where proyecto_id = v_id) <> 2 then
    raise exception 'FALLA: el guardado automático creó una versión';
  end if;
  if (select count(*) from public.actividad where registro = v_id::text and tabla = 'proyectos') <> 2 then
    raise exception 'FALLA: la actividad del proyecto no tiene exactamente el insert y la versión 2 (el guardado automático no se registra)';
  end if;
  begin                                                    -- nadie cambia su propio rol
    update public.perfiles set rol = 'docente' where id = auth.uid();
    raise exception 'FALLA: el estudiante cambió su propio rol';
  exception when insufficient_privilege then null;
  end;
  begin
    perform public.asignar_perfil('00000000-0000-4000-8000-00000000e002', 'docente');
    raise exception 'FALLA: un estudiante asignó un rol';
  exception when insufficient_privilege then null;
  end;
  begin                                                    -- los datos solo cambian con la función (control de versión)
    update public.proyectos set datos = '{}'::jsonb where id = v_id;
    raise exception 'FALLA: se pudo cambiar datos sin guardar_proyecto';
  exception when insufficient_privilege then null;
  end;
  begin
    insert into public.proyectos (owner_id, nombre) values (auth.uid(), 'directo');
    raise exception 'FALLA: se pudo insertar un proyecto sin guardar_proyecto';
  exception when insufficient_privilege then null;
  end;
  update public.perfiles set nombre = 'Estudiante uno (nombre propio)' where id = auth.uid();
  if (select nombre from public.perfiles where id = auth.uid()) <> 'Estudiante uno (nombre propio)' then
    raise exception 'FALLA: el estudiante no pudo cambiar su nombre';
  end if;
  if (select count(*) from public.perfiles) <> 1 then
    raise exception 'FALLA: el estudiante ve perfiles de otras cuentas';
  end if;
end $$;
reset role;

-- ---------------------------------------------------------------- estudiante dos: no ve ni toca lo del uno
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"00000000-0000-4000-8000-00000000e002","role":"authenticated"}', true);
do $$
declare
  v_id bigint := current_setting('pruebas.proyecto_e1')::bigint;
  n int;
begin
  if exists (select 1 from public.proyectos where id = v_id) then
    raise exception 'FALLA: el estudiante dos ve el proyecto del uno';
  end if;
  if exists (select 1 from public.proyectos_versiones where proyecto_id = v_id) then
    raise exception 'FALLA: el estudiante dos ve las versiones del uno';
  end if;
  begin
    perform public.guardar_proyecto(v_id, '', '{}'::jsonb, '{}'::jsonb, '', '', 2);
    raise exception 'FALLA: el estudiante dos guardó en el proyecto del uno';
  exception when insufficient_privilege then null;
  end;
  begin
    perform public.autoguardar_proyecto(v_id, '{}'::jsonb);
    raise exception 'FALLA: el guardado automático del dos escribió en el proyecto del uno';
  exception when insufficient_privilege then null;
  end;
  update public.proyectos set nombre = 'robado' where id = v_id;
  get diagnostics n = row_count;
  if n <> 0 then raise exception 'FALLA: el estudiante dos renombró el proyecto del uno'; end if;
  delete from public.proyectos where id = v_id;
  get diagnostics n = row_count;
  if n <> 0 then raise exception 'FALLA: el estudiante dos borró el proyecto del uno'; end if;
end $$;
reset role;

-- ---------------------------------------------------------------- visita: solo lectura de ejemplos
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"00000000-0000-4000-8000-00000000f001","role":"authenticated"}', true);
do $$
begin
  if exists (select 1 from public.proyectos) then
    raise exception 'FALLA: la visita ve proyectos que no son ejemplos';
  end if;
  begin
    perform public.guardar_proyecto(null, 'Proyecto de visita', '{}'::jsonb);
    raise exception 'FALLA: la visita guardó un proyecto';
  exception when insufficient_privilege then null;
  end;
end $$;
reset role;

-- ---------------------------------------------------------------- docente: ve todo, asigna roles y publica ejemplos
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"00000000-0000-4000-8000-00000000d001","role":"authenticated"}', true);
do $$
declare
  v_id bigint := current_setting('pruebas.proyecto_e1')::bigint;
begin
  if not exists (select 1 from public.proyectos where id = v_id) then
    raise exception 'FALLA: el docente no ve el proyecto del estudiante';
  end if;
  if (select count(*) from public.perfiles) < 4 then
    raise exception 'FALLA: el docente no ve todas las cuentas';
  end if;
  begin
    perform public.guardar_proyecto(v_id, '', '{}'::jsonb, '{}'::jsonb, '', '', 2);
    raise exception 'FALLA: el docente sobrescribió el proyecto del estudiante';
  exception when insufficient_privilege then null;
  end;
  begin
    perform public.asignar_perfil(auth.uid(), 'visita');
    raise exception 'FALLA: el docente cambió su propio rol';
  exception when insufficient_privilege then null;
  end;
  perform public.asignar_perfil('00000000-0000-4000-8000-00000000e002', 'visita');
  if (select rol from public.perfiles where id = '00000000-0000-4000-8000-00000000e002') <> 'visita' then
    raise exception 'FALLA: el docente no pudo asignar un rol';
  end if;
  perform public.asignar_perfil('00000000-0000-4000-8000-00000000e002', 'estudiante');
  insert into public.asignaciones (estudiante_id, curso, familia, datos)
  values ('00000000-0000-4000-8000-00000000e001', 'PAT prueba', 'tomate', '{"planta_id":"tomate"}');
  begin
    insert into public.asignaciones (estudiante_id, curso, familia, datos)
    values ('00000000-0000-4000-8000-00000000f001', 'PAT prueba', 'tomate', '{}');
    raise exception 'FALLA: se asignó una planta a una cuenta de visita';
  exception when invalid_parameter_value then null;
  end;
  perform public.marcar_ejemplo(v_id, true);
  if (select count(*) from public.actividad where tabla = 'perfiles' and accion = 'update') < 2 then
    raise exception 'FALLA: los cambios de rol no quedaron en la actividad';
  end if;
end $$;
reset role;

-- ---------------------------------------------------------------- el estudiante ve su asignación; la visita ve el ejemplo
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"00000000-0000-4000-8000-00000000e001","role":"authenticated"}', true);
do $$
begin
  if (select count(*) from public.asignaciones) <> 1 then
    raise exception 'FALLA: el estudiante no ve su asignación (o ve otras)';
  end if;
  begin
    delete from public.asignaciones;
    if exists (select 1 from public.asignaciones) is false then
      raise exception 'FALLA: el estudiante borró su asignación';
    end if;
  end;
end $$;
reset role;

set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"00000000-0000-4000-8000-00000000f001","role":"authenticated"}', true);
do $$
declare
  v_id bigint := current_setting('pruebas.proyecto_e1')::bigint;
  n int;
begin
  if not exists (select 1 from public.proyectos where id = v_id and es_ejemplo) then
    raise exception 'FALLA: la visita no ve el ejemplo publicado';
  end if;
  if (select count(*) from public.proyectos_versiones where proyecto_id = v_id) <> 2 then
    raise exception 'FALLA: la visita no ve las versiones del ejemplo';
  end if;
  update public.proyectos set nombre = 'cambiado por la visita' where id = v_id;
  get diagnostics n = row_count;
  if n <> 0 then raise exception 'FALLA: la visita renombró el ejemplo'; end if;
end $$;
reset role;

rollback;

-- solo se llega aquí si ninguna prueba falló (un error detiene el script antes)
select '98_pruebas: todas las pruebas pasaron' as resultado;
