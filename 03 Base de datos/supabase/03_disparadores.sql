-- Simulador PAT en Supabase, archivo 03 de 6: disparadores (PAT 144 b, tarea T8, 20-11-2026).
-- Requiere 01_esquema.sql y 02_funciones.sql. Se puede volver a ejecutar («drop trigger if exists»).

-- Cada cuenta nueva de Authentication recibe su perfil (con su preasignación o con el rol visita)
drop trigger if exists pat_crear_perfil on auth.users;
create trigger pat_crear_perfil
  after insert on auth.users
  for each row execute function privado.crear_perfil();

-- Una preasignación hecha después de crear la cuenta también cambia el rol de esa cuenta
drop trigger if exists pat_aplicar_preasignacion on privado.preasignaciones;
create trigger pat_aplicar_preasignacion
  after insert or update on privado.preasignaciones
  for each row execute function privado.aplicar_preasignacion();

-- Nadie cambia su propio rol, ni la cuenta o el correo de un perfil
drop trigger if exists pat_proteger_perfil on public.perfiles;
create trigger pat_proteger_perfil
  before update on public.perfiles
  for each row execute function privado.proteger_perfil();

drop trigger if exists pat_actividad_perfiles on public.perfiles;
create trigger pat_actividad_perfiles
  after insert or update on public.perfiles
  for each row execute function privado.registrar_actividad();

-- Proyectos: fecha de cambio, historial de versiones y registro de actividad
drop trigger if exists pat_proyectos_antes on public.proyectos;
create trigger pat_proyectos_antes
  before insert or update on public.proyectos
  for each row execute function privado.proyectos_antes();

drop trigger if exists pat_proyectos_version on public.proyectos;
create trigger pat_proyectos_version
  after insert or update of version on public.proyectos
  for each row execute function privado.proyectos_version();

drop trigger if exists pat_actividad_proyectos on public.proyectos;
create trigger pat_actividad_proyectos
  after insert or update or delete on public.proyectos
  for each row execute function privado.registrar_actividad();

-- Asignaciones del docente: solo a estudiantes, con el docente que asigna y su registro
drop trigger if exists pat_asignaciones_antes on public.asignaciones;
create trigger pat_asignaciones_antes
  before insert or update on public.asignaciones
  for each row execute function privado.asignaciones_antes();

drop trigger if exists pat_actividad_asignaciones on public.asignaciones;
create trigger pat_actividad_asignaciones
  after insert or update or delete on public.asignaciones
  for each row execute function privado.registrar_actividad();
