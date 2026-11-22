# Base de datos del simulador PAT en Supabase (PAT 144 b, tarea T8, 20-11-2026)

Proyecto: `https://<su-proyecto>.supabase.co`, región South America (São Paulo), *Data API* activa. Los archivos `.sql` de esta carpeta crean las cuentas con rol, los proyectos guardados en la nube, su historial de versiones, el registro de actividad y las asignaciones del docente, con reglas RLS en todas las tablas. La aplicación los usa con `pat_sim/datos/nube.py` y `ui/nube_ui.py`.

## Orden de ejecución

En el panel de Supabase: *SQL Editor*, *New query*. Se pega el archivo completo, se presiona *Run* y se espera «*Success*». Un archivo por vez, en este orden:

| N.° | Archivo | Qué hace | Resultado esperado |
|:---:|:---|:---|:---|
| 1 | `01_esquema.sql` | Esquema `privado`, tablas `perfiles`, `privado.preasignaciones`, `proyectos`, `proyectos_versiones`, `actividad` y `asignaciones`, con RLS activo | *Success. No rows returned* |
| 2 | `02_funciones.sql` | Funciones de permiso (`es_docente`, `rol_actual`, `puede_editar`), `asignar_perfil`, `preasignar`, `guardar_proyecto` (control de versión), `autoguardar_proyecto`, `marcar_ejemplo` y las de los disparadores | *Success. No rows returned* |
| 3 | `03_disparadores.sql` | Perfil al crear cada cuenta, preasignaciones, protección del rol, fecha de cambio, historial de versiones y actividad | *Success. No rows returned* |
| 4 | `04_rls_y_permisos.sql` | Quita todo a `anon`, da lo mínimo a `authenticated` y crea las reglas RLS | *Success. No rows returned* |
| 5 | `98_pruebas.sql` | Pruebas con cuentas de prueba dentro de una transacción que se deshace al final | Una fila: «98_pruebas: todas las pruebas pasaron» |
| 6 | `99_verificacion.sql` | Revisa RLS, permisos, funciones y disparadores; no cambia nada | Todas las filas con `ok = true` y la última «Controles que fallaron: 0» |

Los archivos 01 a 04 se pueden volver a ejecutar (por ejemplo, después de una corrección): usan `if not exists`, `create or replace` y `drop ... if exists`, y no borran datos. Si `98_pruebas.sql` se detiene con «FALLA: …», no se crea nada (la transacción se deshace) y el texto dice qué regla falló.

Después de correr los cuatro primeros, en *Database*, *Policies* ninguna tabla debe mostrar el botón «*Enable RLS*». Nunca presionar «*Disable RLS*».

Si la aplicación avisa que no encuentra una función recién creada, en *SQL Editor* se ejecuta `notify pgrst, 'reload schema';` para que la *Data API* relea el esquema.

## Roles y permisos

| Rol | Proyectos | Cuentas y asignaciones |
|:---|:---|:---|
| docente | Ve los de todas las cuentas del curso y sus versiones; guarda, renombra y elimina solo los propios; publica o retira ejemplos | Ve todas las cuentas y la actividad; cambia el rol de otras cuentas (nunca el propio); escribe las asignaciones |
| estudiante | Ve y cambia solo los propios; ve los ejemplos | Ve su perfil y su asignación |
| visita | Solo lectura de los ejemplos | Ve su perfil |
| sin sesión (`anon`) | Nada | Nada |

Toda cuenta nueva nace con el rol visita, salvo que su correo tenga una preasignación. Los datos de un proyecto solo cambian con `guardar_proyecto` (cada versión numerada, con la versión esperada) y `autoguardar_proyecto` (la ranura del guardado automático, sin versiones). Si otra sesión guardó antes, `guardar_proyecto` rechaza el cambio con el código `PT409` y la aplicación lo informa sin sobrescribir nada. El historial y la actividad los escriben solo los disparadores; la actividad nunca copia los datos del proyecto ni contraseñas.

## Usuario corto

La aplicación acepta «usuario01» y lo convierte en `usuario01@pat-sim.cl` (el dominio se cambia con el secreto `SUPABASE_DOMINIO`). Las cuentas se crean con ese correo. Esas cuentas no reciben correos: la contraseña olvidada la cambia el administrador en *Authentication*, *Users*.

## Preasignar o cambiar un rol con SQL

```sql
-- antes de crear la cuenta (o después: también cambia la cuenta existente)
insert into privado.preasignaciones (email, rol, nombre)
values ('docente01@pat-sim.cl', 'docente', 'Nombre del docente')
on conflict (email) do update set rol = excluded.rol, nombre = excluded.nombre;

-- cuenta que ya existe
update public.perfiles set rol = 'estudiante' where email = 'usuario01@pat-sim.cl';
```

Desde la aplicación, la cuenta docente cambia el rol de otras cuentas en Docente, «Cuentas de la nube y sus roles».

## Validación hecha antes de entregar

Los seis archivos se ejecutaron en un PostgreSQL 16 local con una simulación mínima de Supabase (roles `anon`, `authenticated` y `service_role`, `auth.users` y `auth.uid()`, y los permisos que Supabase da por defecto en `public`). Los archivos 01 a 04 corrieron dos veces seguidas sin error, `98_pruebas.sql` pasó y `99_verificacion.sql` dio 0 controles fallidos. Además se rompió a propósito una regla por vez (permiso de update en `proyectos`, rol editable, lectura abierta de proyectos, lectura de `anon`, sin disparador de versiones) y en cada caso `98_pruebas.sql` o `99_verificacion.sql` lo detectó. Falta correrlos en el proyecto real de Supabase.
