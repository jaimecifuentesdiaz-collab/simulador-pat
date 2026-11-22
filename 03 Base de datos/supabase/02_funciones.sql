-- Simulador PAT en Supabase, archivo 02 de 6: funciones (PAT 144 b, tarea T8, 20-11-2026).
-- Requiere 01_esquema.sql. Se puede volver a ejecutar («create or replace»).
-- Todas las funciones son «security definer» con «set search_path = ''»: cada nombre va con su esquema (public., privado., auth.)
-- y nadie puede desviar una función con un objeto propio del mismo nombre. Las que cambian datos revisan la sesión (auth.uid())
-- y el rol antes de escribir, porque una función security definer no pasa por RLS.

-- ---------------------------------------------------------------- funciones de permiso (las usan las reglas RLS)
create or replace function public.rol_actual()
returns text
language sql stable security definer set search_path = ''
as $$
  select p.rol from public.perfiles p where p.id = auth.uid()
$$;
comment on function public.rol_actual() is 'Rol de la cuenta con sesión (docente, estudiante o visita); null sin sesión';

create or replace function public.es_docente()
returns boolean
language sql stable security definer set search_path = ''
as $$
  select coalesce(public.rol_actual() = 'docente', false)
$$;

create or replace function public.puede_editar()
returns boolean
language sql stable security definer set search_path = ''
as $$
  select coalesce(public.rol_actual() in ('docente', 'estudiante'), false)
$$;
comment on function public.puede_editar() is 'true si la cuenta puede guardar proyectos (docente o estudiante); la visita es de solo lectura';

-- ---------------------------------------------------------------- perfiles y roles
create or replace function public.asignar_perfil(p_perfil uuid, p_rol text, p_nombre text default null)
returns jsonb
language plpgsql volatile security definer set search_path = ''
as $$
declare
  v_fila public.perfiles%rowtype;
begin
  if auth.uid() is null then
    raise exception 'Se requiere una sesión iniciada' using errcode = '28000';
  end if;
  if not public.es_docente() then
    raise exception 'Solo una cuenta con el rol docente asigna roles' using errcode = '42501';
  end if;
  if p_perfil = auth.uid() then
    raise exception 'Nadie puede cambiar su propio rol' using errcode = '42501';
  end if;
  if p_rol is null or p_rol not in ('docente', 'estudiante', 'visita') then
    raise exception 'Rol no válido: %', coalesce(p_rol, 'vacío') using errcode = '22023';
  end if;
  update public.perfiles
     set rol = p_rol,
         nombre = case when p_nombre is null then nombre else btrim(p_nombre) end
   where id = p_perfil
  returning * into v_fila;
  if not found then
    raise exception 'No existe la cuenta indicada' using errcode = 'P0002';
  end if;
  return jsonb_build_object('id', v_fila.id, 'usuario', v_fila.usuario, 'nombre', v_fila.nombre, 'rol', v_fila.rol);
end;
$$;
comment on function public.asignar_perfil(uuid, text, text) is 'El docente cambia el rol (y el nombre) de otra cuenta; nunca el propio';

create or replace function public.preasignar(p_email text, p_rol text, p_nombre text default '')
returns void
language plpgsql volatile security definer set search_path = ''
as $$
begin
  if auth.uid() is null or not public.es_docente() then
    raise exception 'Solo una cuenta con el rol docente preasigna roles' using errcode = '42501';
  end if;
  if p_rol is null or p_rol not in ('docente', 'estudiante', 'visita') then
    raise exception 'Rol no válido: %', coalesce(p_rol, 'vacío') using errcode = '22023';
  end if;
  insert into privado.preasignaciones (email, rol, nombre)
  values (lower(btrim(p_email)), p_rol, btrim(coalesce(p_nombre, '')))
  on conflict (email) do update set rol = excluded.rol, nombre = excluded.nombre;
end;
$$;
comment on function public.preasignar(text, text, text) is 'El docente deja el rol con que nacerá (o quedará) la cuenta de ese correo';

-- ---------------------------------------------------------------- guardado de proyectos con control de versión
create or replace function public.guardar_proyecto(
  p_id                bigint,
  p_nombre            text,
  p_datos             jsonb,
  p_resumen           jsonb default '{}'::jsonb,
  p_persona           text default '',
  p_nota              text default '',
  p_version_esperada  integer default null
)
returns jsonb
language plpgsql volatile security definer set search_path = ''
as $$
declare
  v_uid    uuid := auth.uid();
  v_nombre text := btrim(coalesce(p_nombre, ''));
  v_fila   public.proyectos%rowtype;
begin
  if v_uid is null then
    raise exception 'Se requiere una sesión iniciada' using errcode = '28000';
  end if;
  if not public.puede_editar() then
    raise exception 'La cuenta no tiene permiso para guardar proyectos (rol visita: solo lectura)' using errcode = '42501';
  end if;
  if p_datos is null or jsonb_typeof(p_datos) <> 'object' then
    raise exception 'Los datos del proyecto no son válidos' using errcode = '22023';
  end if;
  if octet_length(p_datos::text) > 15728640 then
    raise exception 'El proyecto supera los 15 MB' using errcode = '54000';
  end if;

  if p_id is null then                                     -- proyecto nuevo: versión 1
    if v_nombre = '' then
      raise exception 'El proyecto necesita un nombre' using errcode = '22023';
    end if;
    begin
      insert into public.proyectos (owner_id, nombre, persona, nota, datos, resumen, version)
      values (v_uid, v_nombre, btrim(coalesce(p_persona, '')), coalesce(p_nota, ''), p_datos, coalesce(p_resumen, '{}'::jsonb), 1)
      returning * into v_fila;
    exception when unique_violation then
      raise exception 'nombre_repetido: ya existe un proyecto llamado «%»', v_nombre using errcode = '23505';
    end;
    return jsonb_build_object('id', v_fila.id, 'nombre', v_fila.nombre, 'version', v_fila.version, 'nuevo', true,
                              'fecha', v_fila.updated_at);
  end if;

  select * into v_fila from public.proyectos where id = p_id for update;
  if not found then
    raise exception 'El proyecto % no existe', p_id using errcode = 'P0002';
  end if;
  if v_fila.owner_id <> v_uid then
    raise exception 'Solo la cuenta dueña puede guardar en este proyecto' using errcode = '42501';
  end if;
  if p_version_esperada is null then
    raise exception 'Falta la versión esperada del proyecto' using errcode = '22023';
  end if;
  if v_fila.version <> p_version_esperada then             -- otra sesión guardó antes: se rechaza para no pisar su trabajo
    raise exception 'conflicto_version: otra sesión guardó la versión % de «%»', v_fila.version, v_fila.nombre
      using errcode = 'PT409', detail = v_fila.version::text;
  end if;
  begin
    update public.proyectos
       set nombre  = case when v_nombre = '' then nombre else v_nombre end,
           persona = case when btrim(coalesce(p_persona, '')) = '' then persona else btrim(p_persona) end,
           nota    = coalesce(p_nota, ''),
           datos   = p_datos,
           resumen = coalesce(p_resumen, '{}'::jsonb),
           version = version + 1
     where id = p_id
    returning * into v_fila;
  exception when unique_violation then
    raise exception 'nombre_repetido: ya existe un proyecto llamado «%»', v_nombre using errcode = '23505';
  end;
  return jsonb_build_object('id', v_fila.id, 'nombre', v_fila.nombre, 'version', v_fila.version, 'nuevo', false,
                            'fecha', v_fila.updated_at);
end;
$$;
comment on function public.guardar_proyecto(bigint, text, jsonb, jsonb, text, text, integer) is
  'Guarda una versión numerada. Sin p_id crea el proyecto (versión 1). Con p_id exige p_version_esperada: si otra sesión guardó antes, rechaza con el código PT409';

create or replace function public.autoguardar_proyecto(
  p_id      bigint,
  p_datos   jsonb,
  p_resumen jsonb default '{}'::jsonb,
  p_huella  text default '',
  p_nombre  text default null,
  p_persona text default ''
)
returns jsonb
language plpgsql volatile security definer set search_path = ''
as $$
declare
  v_uid    uuid := auth.uid();
  v_nombre text := btrim(coalesce(p_nombre, ''));
  v_fila   public.proyectos%rowtype;
begin
  if v_uid is null then
    raise exception 'Se requiere una sesión iniciada' using errcode = '28000';
  end if;
  if not public.puede_editar() then
    raise exception 'La cuenta no tiene permiso para guardar proyectos (rol visita: solo lectura)' using errcode = '42501';
  end if;
  if p_datos is null or jsonb_typeof(p_datos) <> 'object' then
    raise exception 'Los datos del proyecto no son válidos' using errcode = '22023';
  end if;
  if octet_length(p_datos::text) > 15728640 then
    raise exception 'El proyecto supera los 15 MB' using errcode = '54000';
  end if;

  if p_id is null then                                     -- primer cambio de la sesión: proyecto sin versiones numeradas
    if v_nombre = '' then
      raise exception 'El proyecto necesita un nombre' using errcode = '22023';
    end if;
    begin
      insert into public.proyectos (owner_id, nombre, persona, nota, datos, resumen, version, autoguardado, autoguardado_en,
                                    autoguardado_huella)
      values (v_uid, v_nombre, btrim(coalesce(p_persona, '')), 'Creado por el guardado automático', p_datos,
              coalesce(p_resumen, '{}'::jsonb), 0, p_datos, now(), coalesce(p_huella, ''))
      returning * into v_fila;
    exception when unique_violation then
      raise exception 'nombre_repetido: ya existe un proyecto llamado «%»', v_nombre using errcode = '23505';
    end;
    return jsonb_build_object('id', v_fila.id, 'nombre', v_fila.nombre, 'fecha', v_fila.autoguardado_en, 'nuevo', true);
  end if;

  select * into v_fila from public.proyectos where id = p_id for update;
  if not found then
    raise exception 'El proyecto % no existe', p_id using errcode = 'P0002';
  end if;
  if v_fila.owner_id <> v_uid then
    raise exception 'El guardado automático solo escribe en los proyectos propios' using errcode = '42501';
  end if;
  update public.proyectos
     set autoguardado = p_datos, autoguardado_en = now(), autoguardado_huella = coalesce(p_huella, '')
   where id = p_id
  returning * into v_fila;
  return jsonb_build_object('id', v_fila.id, 'nombre', v_fila.nombre, 'fecha', v_fila.autoguardado_en, 'nuevo', false);
end;
$$;
comment on function public.autoguardar_proyecto(bigint, jsonb, jsonb, text, text, text) is
  'Guardado automático: sobrescribe la ranura autoguardado del proyecto propio (no crea versiones ni registra actividad)';

create or replace function public.marcar_ejemplo(p_id bigint, p_valor boolean default true)
returns void
language plpgsql volatile security definer set search_path = ''
as $$
begin
  if auth.uid() is null or not public.es_docente() then
    raise exception 'Solo una cuenta con el rol docente publica ejemplos' using errcode = '42501';
  end if;
  update public.proyectos set es_ejemplo = coalesce(p_valor, false) where id = p_id;
  if not found then
    raise exception 'El proyecto % no existe', p_id using errcode = 'P0002';
  end if;
end;
$$;
comment on function public.marcar_ejemplo(bigint, boolean) is 'El docente publica (o retira) un proyecto como ejemplo visible para todas las cuentas';

-- ---------------------------------------------------------------- funciones de los disparadores (esquema privado)
create or replace function privado.crear_perfil()
returns trigger
language plpgsql security definer set search_path = ''
as $$
declare
  v_email  text := lower(coalesce(new.email, new.id::text));
  v_rol    text;
  v_nombre text;
begin
  select p.rol, p.nombre into v_rol, v_nombre from privado.preasignaciones p where p.email = v_email;
  insert into public.perfiles (id, email, usuario, nombre, rol)
  values (new.id, v_email, split_part(v_email, '@', 1),
          coalesce(nullif(v_nombre, ''), new.raw_user_meta_data ->> 'nombre', ''),
          coalesce(v_rol, 'visita'))
  on conflict (id) do nothing;
  return new;
end;
$$;
comment on function privado.crear_perfil() is 'Crea el perfil de cada cuenta nueva con su preasignación o, si no tiene, con el rol visita';

create or replace function privado.aplicar_preasignacion()
returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
  update public.perfiles
     set rol = new.rol,
         nombre = case when new.nombre <> '' then new.nombre else nombre end
   where email = new.email;
  return null;
end;
$$;
comment on function privado.aplicar_preasignacion() is 'Una preasignación nueva o cambiada se aplica también a la cuenta que ya existe';

create or replace function privado.proteger_perfil()
returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
  if auth.uid() is not null then                           -- desde la aplicación (en SQL Editor auth.uid() es null)
    if new.id is distinct from old.id or new.email is distinct from old.email then
      raise exception 'La cuenta y el correo de un perfil no se cambian desde la aplicación' using errcode = '42501';
    end if;
    if new.rol is distinct from old.rol and (new.id = auth.uid() or not public.es_docente()) then
      raise exception 'Nadie puede cambiar su propio rol: solo un docente cambia el rol de otra cuenta' using errcode = '42501';
    end if;
  end if;
  new.usuario := split_part(new.email, '@', 1);
  new.actualizado := now();
  return new;
end;
$$;

create or replace function privado.proyectos_antes()
returns trigger
language plpgsql security definer set search_path = ''
as $$
declare
  v_solo_auto text[] := array['autoguardado', 'autoguardado_en', 'autoguardado_huella', 'updated_at'];
begin
  if tg_op = 'INSERT' then
    new.creado := now();
    new.updated_at := now();
    return new;
  end if;
  if auth.uid() is not null and new.owner_id is distinct from old.owner_id then
    raise exception 'La cuenta dueña de un proyecto no se cambia desde la aplicación' using errcode = '42501';
  end if;
  new.creado := old.creado;
  if (to_jsonb(new) - v_solo_auto) is distinct from (to_jsonb(old) - v_solo_auto) then
    new.updated_at := now();                               -- cambió algo más que el guardado automático
  else
    new.updated_at := old.updated_at;
  end if;
  return new;
end;
$$;

create or replace function privado.proyectos_version()
returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
  if new.version > 0 and (tg_op = 'INSERT' or new.version is distinct from old.version) then
    insert into public.proyectos_versiones (proyecto_id, numero, nombre, nota, datos, resumen, autor_id)
    values (new.id, new.version, new.nombre, new.nota, new.datos, new.resumen,
            (select p.id from public.perfiles p where p.id = auth.uid()))
    on conflict (proyecto_id, numero) do nothing;
  end if;
  return null;
end;
$$;
comment on function privado.proyectos_version() is 'Cada versión numerada nueva queda en public.proyectos_versiones';

create or replace function privado.registrar_actividad()
returns trigger
language plpgsql security definer set search_path = ''
as $$
declare
  v_fila      jsonb;
  v_antes     jsonb;
  v_detalle   jsonb := '{}'::jsonb;
  v_solo_auto text[] := array['autoguardado', 'autoguardado_en', 'autoguardado_huella', 'updated_at'];
begin
  if tg_op = 'DELETE' then
    v_fila := to_jsonb(old);
  else
    v_fila := to_jsonb(new);
  end if;
  if tg_op = 'UPDATE' then
    v_antes := to_jsonb(old);
  end if;
  if tg_table_name = 'proyectos' then
    if tg_op = 'UPDATE' and (v_fila - v_solo_auto) = (v_antes - v_solo_auto) then
      return null;                                         -- el guardado automático no llena el registro
    end if;
    v_detalle := jsonb_build_object('nombre', v_fila -> 'nombre', 'version', v_fila -> 'version',
                                    'owner_id', v_fila -> 'owner_id', 'es_ejemplo', v_fila -> 'es_ejemplo');
  elsif tg_table_name = 'perfiles' then
    if tg_op = 'UPDATE' and v_fila -> 'rol' = v_antes -> 'rol' and v_fila -> 'nombre' = v_antes -> 'nombre' then
      return null;
    end if;
    v_detalle := jsonb_build_object('usuario', v_fila -> 'usuario', 'rol', v_fila -> 'rol');
    if tg_op = 'UPDATE' then
      v_detalle := v_detalle || jsonb_build_object('rol_anterior', v_antes -> 'rol');
    end if;
  elsif tg_table_name = 'asignaciones' then
    v_detalle := jsonb_build_object('estudiante_id', v_fila -> 'estudiante_id', 'curso', v_fila -> 'curso',
                                    'familia', v_fila -> 'familia');
  end if;
  insert into public.actividad (actor_id, tabla, accion, registro, detalle)
  values (auth.uid(), tg_table_name, lower(tg_op), coalesce(v_fila ->> 'id', v_fila ->> 'estudiante_id', ''), v_detalle);
  return null;
end;
$$;
comment on function privado.registrar_actividad() is 'Escribe public.actividad; nunca copia los datos del proyecto';

create or replace function privado.asignaciones_antes()
returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
  if not exists (select 1 from public.perfiles p where p.id = new.estudiante_id and p.rol = 'estudiante') then
    raise exception 'Solo se asigna a cuentas con el rol estudiante' using errcode = '22023';
  end if;
  if auth.uid() is not null then
    new.docente_id := auth.uid();
  end if;
  new.updated_at := now();
  return new;
end;
$$;
