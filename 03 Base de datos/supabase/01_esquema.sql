-- Simulador PAT en Supabase, archivo 01 de 6: esquema (PAT 144 b, tarea T8, 20-11-2026).
-- Se pega completo en SQL Editor y se ejecuta con «Run». Se puede volver a ejecutar: usa «if not exists».
-- Crea las tablas del simulador y deja RLS activo en todas desde el primer momento (las reglas van en 04_rls_y_permisos.sql).
--
-- Tablas:
--   public.perfiles          una fila por cuenta de Authentication (la crea el disparador de 03_disparadores.sql)
--   privado.preasignaciones  rol y nombre que recibe una cuenta al crearse, por correo (esquema no expuesto en la Data API)
--   public.proyectos         proyectos del simulador: planta y estado de la sesión en «datos» (jsonb) y control de versión
--   public.proyectos_versiones  historial de versiones numeradas (lo escribe solo un disparador)
--   public.actividad         registro de actividad (lo escriben solo los disparadores)
--   public.asignaciones      planta y demanda que el docente asigna a cada estudiante

create schema if not exists privado;
comment on schema privado is 'Datos internos del simulador PAT: no se expone en la Data API';
revoke all on schema privado from public;

-- ---------------------------------------------------------------- perfiles
create table if not exists public.perfiles (
  id          uuid primary key references auth.users (id) on delete cascade,
  email       text not null unique,
  usuario     text not null default '',
  nombre      text not null default '',
  rol         text not null default 'visita' check (rol in ('docente', 'estudiante', 'visita')),
  creado      timestamptz not null default now(),
  actualizado timestamptz not null default now()
);
comment on table public.perfiles is 'Una fila por cuenta. rol: docente, estudiante o visita (la cuenta nueva parte como visita)';
comment on column public.perfiles.usuario is 'Usuario corto: la parte del correo antes de la arroba (usuario01 de usuario01@dominio)';
create index if not exists perfiles_usuario_idx on public.perfiles (lower(usuario));

-- ---------------------------------------------------------------- preasignaciones (esquema privado)
create table if not exists privado.preasignaciones (
  email  text primary key check (email = lower(btrim(email)) and position('@' in email) > 1),
  rol    text not null check (rol in ('docente', 'estudiante', 'visita')),
  nombre text not null default '',
  creado timestamptz not null default now()
);
comment on table privado.preasignaciones is 'Rol y nombre con que nace una cuenta, por correo en minúsculas';

-- ---------------------------------------------------------------- proyectos
create table if not exists public.proyectos (
  id                  bigint generated always as identity primary key,
  owner_id            uuid not null default auth.uid() references public.perfiles (id) on delete cascade,
  nombre              text not null check (length(btrim(nombre)) between 1 and 200),
  persona             text not null default '',
  nota                text not null default '',
  datos               jsonb not null default '{}'::jsonb check (jsonb_typeof(datos) = 'object'),
  resumen             jsonb not null default '{}'::jsonb,
  version             integer not null default 0 check (version >= 0),
  autoguardado        jsonb,
  autoguardado_en     timestamptz,
  autoguardado_huella text not null default '',
  es_ejemplo          boolean not null default false,
  creado              timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);
comment on table public.proyectos is 'Proyectos del simulador. datos = {planta, estado}; version = número de la última versión numerada (0 si solo tiene guardado automático)';
comment on column public.proyectos.autoguardado is 'Último guardado automático de la sesión (no crea versiones)';
comment on column public.proyectos.es_ejemplo is 'Proyecto de ejemplo: lo ven todas las cuentas, también la visita (lo marca un docente)';
create unique index if not exists proyectos_owner_nombre_key on public.proyectos (owner_id, lower(nombre));
create index if not exists proyectos_updated_idx on public.proyectos (updated_at desc);
create index if not exists proyectos_ejemplo_idx on public.proyectos (es_ejemplo) where es_ejemplo;

-- ---------------------------------------------------------------- versiones de los proyectos
create table if not exists public.proyectos_versiones (
  id          bigint generated always as identity primary key,
  proyecto_id bigint not null references public.proyectos (id) on delete cascade,
  numero      integer not null check (numero >= 1),
  nombre      text not null default '',
  nota        text not null default '',
  datos       jsonb not null,
  resumen     jsonb not null default '{}'::jsonb,
  autor_id    uuid references public.perfiles (id) on delete set null,
  fecha       timestamptz not null default now(),
  unique (proyecto_id, numero)
);
comment on table public.proyectos_versiones is 'Historial de versiones numeradas; lo escribe solo el disparador de public.proyectos';

-- ---------------------------------------------------------------- actividad
create table if not exists public.actividad (
  id       bigint generated always as identity primary key,
  fecha    timestamptz not null default now(),
  actor_id uuid,
  tabla    text not null,
  accion   text not null,
  registro text not null default '',
  detalle  jsonb not null default '{}'::jsonb
);
comment on table public.actividad is 'Registro de actividad; lo escriben solo los disparadores (nunca guarda contraseñas ni los datos del proyecto)';
create index if not exists actividad_fecha_idx on public.actividad (fecha desc);
create index if not exists actividad_actor_idx on public.actividad (actor_id, fecha desc);

-- ---------------------------------------------------------------- asignaciones del docente
create table if not exists public.asignaciones (
  estudiante_id uuid primary key references public.perfiles (id) on delete cascade,
  docente_id    uuid default auth.uid() references public.perfiles (id) on delete set null,
  curso         text not null default '',
  familia       text not null default '',
  datos         jsonb not null default '{}'::jsonb check (jsonb_typeof(datos) = 'object'),
  updated_at    timestamptz not null default now()
);
comment on table public.asignaciones is 'Planta y demanda (o desafío de tomate o de agar agar) asignadas a cada estudiante por el docente';

-- ---------------------------------------------------------------- RLS activo en todas las tablas
alter table public.perfiles            enable row level security;
alter table privado.preasignaciones    enable row level security;
alter table public.proyectos           enable row level security;
alter table public.proyectos_versiones enable row level security;
alter table public.actividad           enable row level security;
alter table public.asignaciones        enable row level security;
