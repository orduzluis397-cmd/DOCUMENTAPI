# Guía de despliegue de la demo técnica (costo cero) · CR-005

Esta guía explica, paso a paso y sin dar nada por sabido, cómo publicar la demo de Contable IA
para que otras personas suban documentos. Todo usa **planes gratuitos**.

> **Antes de empezar.** El primer despliegue necesita tu aprobación explícita (CLAUDE.md, regla
> 10). Ninguna clave va al repositorio: las claves se pegan **solo** en los paneles de Render,
> Vercel y GitHub. El archivo `.env.example` solo muestra los nombres de las variables.

## 1. Qué se publica

```
Navegador ──► Vercel (web Next.js) ──► Render (API FastAPI + worker Celery, un contenedor)
                     │                        │            │             │
                     └── Clerk (login) ◄──────┘            │             │
                                         Supabase Postgres  Supabase Storage  Upstash Redis
                                         (São Paulo)        (S3, privado)     (cola, TLS)
```

- La web pide el login a Clerk y manda el token a la API en cada petición.
- La API verifica el token, guarda los archivos en Supabase Storage y encola el procesamiento en
  Upstash. El worker (en el mismo contenedor) lee el archivo, extrae los datos y los guarda.
- **No se llama a ningún LLM externo** (`LLM_EXTERNAL_ENABLED=false`). XML y PDF con texto se
  procesan con código y OCR (Tesseract en español).

## 2. Límites gratuitos (verificados el 2026-11-04)

Cifras tomadas de las páginas oficiales en la fecha indicada. Lo que no se pudo confirmar dice
**no verificado**. Los planes cambian: revísalos al crear cada cuenta.

| Servicio | Límite del plan gratis | Fuente |
|---|---|---|
| **Vercel Hobby** | Solo uso personal y **no comercial**. Al mes: 100 GB de transferencia, 1.000.000 de invocaciones de funciones, 4 h de CPU activa. Deploy hooks: sí (5 por proyecto, 60 disparos por hora). | https://vercel.com/docs/plans/hobby · https://vercel.com/pricing · https://vercel.com/docs/limits |
| **Render free** | 0,1 CPU y **512 MB de RAM**. Se duerme tras **15 min** sin tráfico y tarda ~1 min en despertar. 750 horas de instancia al mes por workspace. Los *background workers* y el *pre-deploy command* **no** son gratis (por eso API y worker van en un solo contenedor y las migraciones las corre GitHub Actions). No hay región en Sudamérica. Deploy hooks y Blueprints en el plan free: **no verificado** (la documentación no menciona restricción). | https://render.com/docs/free · https://render.com/docs/compute-plans · https://render.com/docs/deploys · https://render.com/docs/regions |
| **Supabase free** | Base de 500 MB, 1 GB de archivos, 5 GB de egreso, archivos de máximo **50 MB**. El proyecto se **pausa tras 1 semana sin actividad**. 2 proyectos activos. Región São Paulo (`sa-east-1`) disponible. Postgres 17 por defecto: confirmado solo a medias (confírmalo al crear el proyecto). | https://supabase.com/pricing · https://supabase.com/docs/guides/storage/uploads/file-limits · https://supabase.com/docs/guides/platform/regions |
| **Upstash Redis free** | 500.000 comandos al mes, 250 MB de datos, 10 GB de ancho de banda, 1 base. TLS siempre activo. Se archiva tras 30 días sin actividad. Hay una mención a 10.000 comandos **por día** en la FAQ que no coincide con otra página: **no verificado**. Conexiones máximas: **no verificado**. | https://upstash.com/pricing/redis · https://upstash.com/docs/redis/overall/pricing · https://upstash.com/docs/redis/help/faq |
| **Clerk free** | 50.000 usuarios retenidos al mes (MRU) por aplicación. Organizations incluidas: hasta 20 miembros por organización y 100 organizaciones retenidas al mes (MRO). Sesión fija de 7 días, sin MFA. | https://clerk.com/pricing |

Qué significa para la demo:

- **Render se duerme.** La primera visita tras 15 minutos tarda ~1 minuto. Mientras haya
  documentos en proceso, la web consulta cada 3 s y lo mantiene despierto.
- **Supabase se pausa** a la semana: el workflow `keepalive.yml` lo evita con una consulta cada
  3 días (y de paso despierta Render).
- **Upstash cuenta comandos.** El worker espera tareas con esperas largas
  (`CELERY_BROKER_POLLING_INTERVAL_S=30`), sin backend de resultados ni eventos, y el contenedor
  se duerme sin tráfico, así que el consumo en reposo es bajo. Si aparece el límite diario, se
  nota como tareas que no avanzan: revisa el panel de Upstash.
- **Vercel Hobby es no comercial.** Sirve para la demo técnica; si la demo se vuelve un servicio
  con clientes, hay que pasar a un plan de pago.

## 3. Las 5 cuentas que hay que crear

Créalas con el mismo correo. Ninguna pide tarjeta para el plan gratis (verifícalo al crearla).

1. **Supabase** — https://supabase.com (base de datos y archivos).
2. **Upstash** — https://upstash.com (cola de tareas).
3. **Clerk** — https://clerk.com (inicio de sesión y organizaciones).
4. **Render** — https://render.com (API y worker). Conéctala a tu GitHub.
5. **Vercel** — https://vercel.com (web). Conéctala a tu GitHub.

Ve anotando cada valor en un gestor de contraseñas (no en un archivo del repositorio). En la
sección 5 hay una tabla con qué valor va dónde.

## 4. Paso a paso

### 4.1 Supabase: proyecto, seguridad y base

1. **New project.** Nombre: `contable-ia-demo`. Región: **South America (São Paulo)**. Genera
   una contraseña fuerte para la base y guárdala: es la del rol `postgres` (`<CLAVE_POSTGRES>`).
2. **Apaga la API pública (Data API).** En *Project Settings → Data API*, desactiva **Enable
   Data API**. La app no la usa: habla con la base directamente. Con la Data API apagada, nadie
   puede leer tablas con la clave `anon` del proyecto. (Fuente:
   https://supabase.com/docs/guides/api/securing-your-api). Además, `bootstrap.sql` quita todos
   los permisos a los roles `anon` y `authenticated`, y todas las tablas tienen RLS forzado.
3. **Corre `bootstrap.sql`.** Abre *SQL Editor → New query*, pega el contenido completo de
   `infra/deploy/supabase/bootstrap.sql` y pulsa *Run*. Es idempotente (se puede repetir). Al
   final muestra una consulta que debe devolver **0 filas**. El script:
   - crea las extensiones `vector` y `unaccent`;
   - crea el rol de la app `contable_app` (sin superusuario, sin BYPASSRLS), **sin contraseña**;
   - le da los mismos permisos que en local (solo leer y escribir datos, nunca cambiar tablas);
   - quita todo permiso a `anon` y `authenticated` sobre el esquema `public`.
4. **Ponle contraseña a `contable_app`.** Genera otra contraseña fuerte (`<CLAVE_APP>`), solo
   letras y números para evitar problemas en la URL. Elige una forma:
   - Recomendada (la contraseña viaja cifrada): con `psql` instalado,
     `psql "<URL de postgres del paso 5>"` y luego `\password contable_app`.
   - Sencilla: en el SQL Editor, `ALTER ROLE contable_app WITH PASSWORD '<CLAVE_APP>';` y luego
     borra esa consulta del historial del editor.
5. **Copia la cadena del pooler en modo sesión.** Botón **Connect** (arriba) → *Session pooler*.
   Se ve así (el número `aws-<n>` y la región los da Supabase; cópialos tal cual):
   `postgresql://postgres.<REF>:[YOUR-PASSWORD]@aws-<n>-sa-east-1.pooler.supabase.com:5432/postgres`.
   Se usa el **modo sesión** (puerto **5432** del pooler) porque funciona por IPv4 (Render no
   tiene IPv6 hacia Supabase) y conserva la sesión como una conexión directa. `<REF>` es el
   identificador del proyecto.
6. **Arma las dos URLs** (con `+psycopg` y `?sslmode=require`):

   | Variable | Valor |
   |---|---|
   | `DATABASE_URL` (la app; RLS siempre aplica) | `postgresql+psycopg://contable_app.<REF>:<CLAVE_APP>@aws-<n>-sa-east-1.pooler.supabase.com:5432/postgres?sslmode=require` |
   | `DATABASE_URL_MIGRATIONS` (solo migraciones) | `postgresql+psycopg://postgres.<REF>:<CLAVE_POSTGRES>@aws-<n>-sa-east-1.pooler.supabase.com:5432/postgres?sslmode=require` |

   El usuario en el pooler es `<rol>.<REF>` (fuente:
   https://supabase.com/docs/guides/database/connecting-to-postgres).
7. **Storage.** *Storage → New bucket*: nombre `contable-ia-documents`, **Public bucket:
   apagado** (privado), límite de tamaño 20 MB. Luego *Project Settings → Storage → S3
   Connection*: activa la conexión S3, copia el **Endpoint**
   (`https://<REF>.storage.supabase.co/storage/v1/s3`) y la **Region**, y crea un par de
   **S3 access keys** (Access key ID y Secret access key). La app usa direccionamiento por
   ruta (path-style), que es lo que pide el ejemplo oficial
   (https://supabase.com/docs/guides/storage/s3/authentication).
8. **Migraciones.** Las corre `deploy.yml` en cada despliegue. Para la primera vez puedes
   correrlas tú desde tu computador:

   ```bash
   cd apps/api
   DATABASE_URL_MIGRATIONS='<la URL de migraciones>' uv run alembic upgrade head
   ```

   y después vuelve a correr `bootstrap.sql` en el SQL Editor (revoca a `anon`/`authenticated`
   cualquier permiso sobre lo que crearon las migraciones; `deploy.yml` también lo hace).

Notas técnicas confirmadas en las pruebas (`tests/test_supabase_bootstrap.py`, base local que
imita a Supabase): las migraciones —incluida la 0002, que crea el rol `contable_budget` y una
función `SECURITY DEFINER`— corren con un rol con CREATEROLE y sin superusuario, y el contexto de
organización (`set_config('app.organization_id', …, true)`) es por transacción, compatible con
el pooler en modo sesión (y también con el modo transacción).

### 4.2 Upstash: la cola

1. *Create Database* → tipo Redis, plan **Free**. Región: la más cercana a Render (Render queda
   en **Virginia, EE. UU.**; elige `us-east-1`).
2. En la página de la base copia la URL con TLS, que empieza por **`rediss://`**
   (`rediss://default:<TOKEN>@<host>.upstash.io:6379`). Esa es `CELERY_BROKER_URL`.

### 4.3 Clerk: login y organizaciones

1. *Create application*. Métodos de entrada: correo (y Google si quieres).
2. **Organizations:** *Configure → Organizations* → actívalas. Desactiva las cuentas personales
   ("personal accounts") para que todo usuario trabaje dentro de una organización. Sin
   organización activa la API responde 403 y la web no deja subir.
3. **Claims del token** (opcional, recomendado): *Configure → Sessions → Customize session
   token* y pega:

   ```json
   {
     "email": "{{user.primary_email_address}}",
     "name": "{{user.full_name}}",
     "org_name": "{{org.name}}"
   }
   ```

   Así la API guarda el correo del usuario y el nombre de la organización. Sin esto funciona
   igual, con un correo de relleno `<id>@clerk.invalid`.
4. Copia de *API keys*: **Publishable key** (`pk_…`), **Secret key** (`sk_…`) y la **Frontend
   API URL** (algo como `https://<nombre>.clerk.accounts.dev`): esa URL es `CLERK_ISSUER`.
5. Cuando tengas el dominio de Vercel (paso 4.5), vuelve a Clerk y agrégalo en *Domains/Allowed
   origins* si el panel lo pide.

Nota: una instancia de **desarrollo** de Clerk sirve para la demo con el dominio `*.vercel.app`.
Una instancia de **producción** de Clerk exige un dominio propio. Los límites exactos de la
instancia de desarrollo: **no verificado**.

### 4.4 Render: API y worker

1. *New → Blueprint* → elige el repositorio → Blueprint path `render.yaml` (en la raíz).
2. Render lee `render.yaml` (plan **free**, Docker, `/health`) y pide los valores marcados
   `sync: false`. Rellénalos con la tabla de la sección 5. Para `CORS_ORIGINS` y
   `CLERK_AUTHORIZED_PARTIES` pon por ahora `https://placeholder.vercel.app` y corrígelos al
   terminar el paso 4.5.
3. Crea el servicio. La primera construcción tarda varios minutos (instala Tesseract).
4. Copia la URL del servicio (`https://contable-ia-api-xxxx.onrender.com`).
5. *Settings → Deploy Hook*: copia la URL secreta del hook (`RENDER_DEPLOY_HOOK_URL`). El
   despliegue automático está apagado en `render.yaml` (`autoDeployTrigger: "off"`): lo dispara
   `deploy.yml` después de migrar.

La API **no arranca** si en producción falta `CLERK_ISSUER`, `CLERK_AUTHORIZED_PARTIES` o si
`AUTH_PROVIDER` no es `clerk`: es a propósito (falla cerrada).

### 4.5 Vercel: la web

1. *Add New → Project* → importa el repositorio. **Root Directory: `apps/web`**. Framework:
   Next.js (lo detecta solo).
2. *Environment Variables* (sección 5): `NEXT_PUBLIC_API_URL`,
   `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`, `NEXT_PUBLIC_CLERK_SIGN_IN_URL`,
   `NEXT_PUBLIC_CLERK_SIGN_UP_URL`.
3. *Deploy*. Copia el dominio (`https://<proyecto>.vercel.app`) y vuelve a Render a poner ese
   dominio en `CORS_ORIGINS` y `CLERK_AUTHORIZED_PARTIES` (sin barra final). Guarda: Render
   reinicia el servicio.
4. *Settings → Git → Deploy Hooks*: crea uno para la rama `main` y copia la URL
   (`VERCEL_DEPLOY_HOOK_URL`).
5. Opcional: para que la web solo se publique desde `deploy.yml` (después de las
   migraciones), desactiva el despliegue automático de Git en Vercel. Si lo dejas activo, la web
   se publica sola en cada push a `main`.

### 4.6 GitHub: secretos y activación del despliegue

En el repositorio: *Settings → Secrets and variables → Actions*.

- **Secrets** (pestaña *Secrets*): `DATABASE_URL`, `DATABASE_URL_MIGRATIONS`,
  `RENDER_DEPLOY_HOOK_URL`, `VERCEL_DEPLOY_HOOK_URL`, `RENDER_HEALTH_URL` (=
  `https://<servicio>.onrender.com/health`).
- **Variable** (pestaña *Variables*): `DEPLOY_ENABLED` = `true` **solo cuando apruebes el
  despliegue**. Mientras no exista o no valga `true`, `deploy.yml` no hace nada.
- Recomendado: *Settings → Environments → demo → Required reviewers* con tu usuario. Así cada
  despliegue espera tu clic de aprobación.

Qué hace cada workflow:

- `deploy.yml`: cuando la CI de `main` termina en verde (o a mano desde *Actions*), corre
  `bootstrap.sql` → `alembic upgrade head` → `bootstrap.sql` y luego dispara los hooks de Render
  y Vercel. Si la migración falla, no publica nada. Si falta un secreto, ese paso se salta con
  un aviso.
- `keepalive.yml`: cada 3 días, `SELECT 1` en Supabase (con el rol de la app) y `GET /health`
  en Render. Si faltan los secretos, termina en verde sin hacer nada. GitHub apaga los workflows
  programados de un repositorio público tras 60 días sin actividad: si pasa, reactívalo en
  *Actions*.

## 5. Qué valor va en qué variable y dónde

| Variable | Valor | Render | Vercel | GitHub |
|---|---|:-:|:-:|:-:|
| `DATABASE_URL` | URL de `contable_app` (4.1, paso 6) | ✔ | | ✔ secret |
| `DATABASE_URL_MIGRATIONS` | URL de `postgres` (4.1, paso 6) | | | ✔ secret |
| `CELERY_BROKER_URL` | `rediss://…` de Upstash | ✔ | | |
| `S3_ENDPOINT_URL` | `https://<REF>.storage.supabase.co/storage/v1/s3` | ✔ | | |
| `S3_REGION` | región de Storage (p. ej. `sa-east-1`) | ✔ | | |
| `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` | claves S3 de Supabase Storage | ✔ | | |
| `CLERK_ISSUER` | Frontend API URL de Clerk | ✔ | | |
| `CLERK_AUTHORIZED_PARTIES` | `https://<proyecto>.vercel.app` | ✔ | | |
| `CORS_ORIGINS` | `https://<proyecto>.vercel.app` | ✔ | | |
| `NEXT_PUBLIC_API_URL` | `https://<servicio>.onrender.com` | | ✔ | |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | `pk_…` | | ✔ | |
| `CLERK_SECRET_KEY` | `sk_…` | | ✔ | |
| `NEXT_PUBLIC_CLERK_SIGN_IN_URL` / `…_SIGN_UP_URL` | `/sign-in` / `/sign-up` | | ✔ | |
| `RENDER_DEPLOY_HOOK_URL` | hook de Render | | | ✔ secret |
| `VERCEL_DEPLOY_HOOK_URL` | hook de Vercel | | | ✔ secret |
| `RENDER_HEALTH_URL` | `https://<servicio>.onrender.com/health` | | | ✔ secret |
| `DEPLOY_ENABLED` | `true` (cuando apruebes) | | | ✔ variable |

Las demás variables de Render (`APP_ENV=production`, `AUTH_PROVIDER=clerk`,
`LLM_EXTERNAL_ENABLED=false`, límites de carga y OCR) ya vienen fijas en `render.yaml`.

## 6. Comprobar que todo funciona

1. `https://<servicio>.onrender.com/health` responde `{"status":"ok",…,"env":"production"}`
   (la primera vez puede tardar un minuto).
2. Abre la web, crea una cuenta, crea una organización.
3. En *Documentos* aparece la autorización (marcada **BORRADOR**): léela, marca la casilla y
   acepta. Sin aceptar no se puede subir.
4. Sube un XML o PDF de **prueba** (nunca uno real con datos sensibles). Debe pasar de "en cola"
   a "extraído" o "en revisión".
5. Bórralo con el botón **Borrar**: desaparece de la lista y del bucket de Supabase.
6. En el SQL Editor de Supabase: `SELECT action, occurred_at FROM audit_events ORDER BY id DESC
   LIMIT 10;` muestra el alta, la aceptación, la carga y el borrado.

## 7. Riesgos que debes conocer

- **Datos fuera de Colombia.** Supabase (São Paulo), Render (EE. UU.), Upstash (EE. UU.),
  Clerk y Vercel (EE. UU.). La Ley 1581 exige autorización previa: por eso la pantalla de
  autorización antes de la primera carga. El texto es un **borrador** que debe revisar un
  abogado antes de recibir documentos reales.
- **Aviso visible** en todas las páginas: "Demo técnica — no subas documentos sensibles".
- **El borrado** elimina el archivo y los datos extraídos. El evento de auditoría queda (es
  inmutable, regla dura 5) y no guarda el nombre del archivo; el evento de **carga** sí guarda
  el nombre que tenía el archivo al subirlo.
- **Arranque en frío** de Render (~1 min) y RAM de 512 MB: OCR limitado a 5 páginas a 200 dpi.
- **Pausas**: Supabase a la semana sin uso (keep-alive), Upstash a los 30 días sin uso.

## 8. Apagar la demo

1. GitHub: borra la variable `DEPLOY_ENABLED` (o ponla en `false`).
2. Render: *Suspend* el servicio. Vercel: *Settings → Delete project* o pausa.
3. Supabase: *Pause project* (los datos se conservan) o borrarlo (requiere tu aprobación: borra
   datos, regla dura 10).
