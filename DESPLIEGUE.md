# Desplegar AWEBO en un servidor público

> **Para qué existe este documento.** Sin él no hay forma de comprobar que un
> servidor quedó como se quería, y ese es exactamente el hueco por el que se
> cuela un `SECRET_KEY` sin definir. La lista de comprobación del final no es
> un adorno: es la parte que de verdad hace falta.

Escrito el 21/09/2026, cuando AWEBO pasa de correr solo en un portátil a
querer atender a gente de fuera.

---

## Lo que cambia respecto a desarrollo

| | Desarrollo | Producción |
|---|---|---|
| Ficheros de Compose | `docker-compose.yml` + `override` **automático** | `docker-compose.yml` + `prod`, **nombrados a mano** |
| nginx | HTTP en el 8090 | HTTP en el 80 → redirige; HTTPS en el 443 |
| Certificado | ninguno | Let's Encrypt, renovado por `certbot` |
| Código | montado en caliente (`./api:/app`) | el de dentro de la imagen |
| Adminer | publicado en `127.0.0.1:8091` | **no se levanta** |
| Mailpit | sí | no: se configura un SMTP de verdad |
| `FLASK_ENV` | `development` | `production` |

---

## 1 · El servidor

Un VPS de los de suscripción mensual sirve de sobra. Lo que hace falta:

- **Docker** y **Docker Compose v2**.
- Los puertos **80** y **443** abiertos, y **ninguno más**. El resto del stack
  no debe verse desde fuera: Postgres ya va atado a `127.0.0.1` en el fichero
  base, pero eso protege del *publicado de Docker*, no del cortafuegos del
  proveedor. Cierra los dos a nivel de proveedor también.
- **2 GB de RAM** como mínimo si se va a usar la voz local: aHoTTS no es
  ligero. Sin voz, 1 GB va justo pero tira.

> ⚠️ **Docker se salta el cortafuegos del sistema.** Al publicar un puerto,
> Docker escribe sus propias reglas en `iptables` **por delante** de las de
> `ufw`, así que un `ufw deny 5433` no impide nada si el puerto está publicado
> en todas las interfaces. Es la razón de que los puertos vayan atados a
> `127.0.0.1` en el `docker-compose`: eso sí lo respeta, porque no es una
> regla de cortafuegos sino una dirección de escucha.

## 2 · El dominio

Let's Encrypt **valida contra un nombre, no contra una IP**, así que sin
dominio no hay certificado.

Hace falta un registro `A` apuntando a la IP del servidor. Comprueba que
resuelve **antes** de pedir el certificado; si no, el primer intento falla y
consume cuota:

```
dig +short TU-DOMINIO
```

## 3 · El `.env` del servidor

No se copia el de desarrollo. Se parte de `.env.example` y se rellena:

```
cp .env.example .env
```

Lo que **tiene** que cambiar:

| Variable | Qué poner |
|---|---|
| `FLASK_ENV` | `production` |
| `SECRET_KEY` | una generada, ver abajo |
| `POSTGRES_PASSWORD` | una generada, ver abajo |
| `DOMINIO` | tu dominio, sin `https://` |
| `URL_BASE` | `https://tu-dominio` |
| `CORREO_PROVEEDOR` | `smtp`, con `SMTP_*` de un servicio real |
| `AI_PROVIDER` y su clave | el proveedor que vayas a usar |

Los dos secretos, cada uno con su comando:

```
python -c "import secrets; print(secrets.token_hex(32))"
```

**La aplicación se niega a arrancar** si `SECRET_KEY` falta, es una de las
publicadas o mide menos de 32 caracteres. Es un error de arranque y no un
aviso, precisamente para que no se despliegue a medias: ver `app/secretos.py`.

> **`SECRET_KEY` no se rota a la ligera.** Firma la cookie de sesión y los
> enlaces de restablecer contraseña: cambiarla echa a todo el mundo e invalida
> los enlaces que estén en camino. Genérala una vez y guárdala.

## 4 · Primer arranque, sin certificado todavía

Es un huevo y una gallina: nginx no arranca sin certificado, y el certificado
no se puede pedir sin un servidor que responda en el 80. Se rompe pidiendo el
certificado con el `standalone` de certbot, **antes** de levantar nginx:

```
docker run --rm -p 80:80 -v "$PWD/certbot/conf:/etc/letsencrypt" -v "$PWD/certbot/www:/var/www/certbot" certbot/certbot certonly --standalone -d TU-DOMINIO --email TU-CORREO --agree-tos --no-eff-email
```

Aquí `--standalone` sí vale, porque todavía no hay nada ocupando el 80. Las
renovaciones posteriores usan `--webroot`, que es lo que hace el servicio
`certbot` del `docker-compose.prod.yml`.

> **Pruébalo antes con `--dry-run`.** Let's Encrypt limita a 5 fallos por hora
> y por dominio, y se agotan enseguida cuando el DNS todavía no ha propagado.

## 5 · Levantar el stack

**Siempre con los dos ficheros nombrados.** Compose carga
`docker-compose.override.yml` solo si no se nombra ninguno, y ese es el de
desarrollo: si se olvida, lo que se levanta es el stack de desarrollo contra
la base de datos de producción.

Para no depender de la memoria, un alias en el servidor:

```
echo "alias dc='docker compose -f docker-compose.yml -f docker-compose.prod.yml'" >> ~/.bashrc && . ~/.bashrc
```

Y a partir de ahí:

```
dc up -d --build
dc exec api flask db upgrade
```

El currículo se siembra una vez, con el comando que ya se usa en desarrollo
(ver `curriculo/README.md`). Son nueve salidas; sin esto la aplicación arranca
pero no ofrece ninguna materia.

## 6 · Subir el plazo de HSTS

La plantilla sale con `max-age=300` —cinco minutos— **a propósito**.

HSTS le dice al navegador «no vuelvas a hablar con este dominio por HTTP
durante N segundos», y eso **no se puede deshacer desde el servidor**: quien ya
la recibió la respeta hasta que caduque. Si el certificado se rompe, esos
visitantes no pueden entrar, y no hay nada que tocar en el servidor que lo
arregle.

Así que se empieza corto, se comprueba que todo va, y a los pocos días se sube
a un año en `nginx/prod.conf.template`:

```
add_header Strict-Transport-Security "max-age=31536000" always;
```

**No pongas `includeSubDomains` ni `preload`** salvo que sepas que *todos* los
subdominios van a tener HTTPS para siempre. `preload` es, además,
prácticamente irreversible: entra en una lista que viene compilada dentro de
los navegadores.

## 7 · Copias de seguridad

Un servidor con usuarios de fuera sin copias es cuestión de tiempo.

```
dc exec -T postgres pg_dump -U $POSTGRES_USER $POSTGRES_DB | gzip > awebo-$(date +%F).sql.gz
```

Lo que importa no es el volcado sino **haber restaurado uno**. Una copia que
nunca se ha restaurado es una suposición, no una copia.

---

## Lista de comprobación

Para pasar **después** de desplegar, no antes. Cada línea se comprueba de
verdad, no se recuerda.

### Secretos

- [ ] `dc exec api python -c "from flask import current_app; ..."` no hace
      falta: si `SECRET_KEY` fuera inválida la aplicación **no habría
      arrancado**. Que responda ya lo demuestra.
- [ ] `grep SECRET_KEY .env` no devuelve el marcador de posición del ejemplo.
- [ ] `POSTGRES_PASSWORD` no es `cambia-esta-contrasena`.

### TLS

- [ ] `curl -I http://TU-DOMINIO` devuelve **301** hacia `https://`.
- [ ] `curl -I https://TU-DOMINIO` devuelve **200** y trae
      `strict-transport-security`.
- [ ] El certificado es de Let's Encrypt y no el autofirmado de nadie:
      `echo | openssl s_client -connect TU-DOMINIO:443 2>/dev/null | openssl x509 -noout -issuer -dates`
- [ ] **La renovación funciona**, que es lo que falla a los 60 días y no hoy:
      `dc run --rm certbot renew --webroot -w /var/www/certbot --dry-run`

### Cabeceras

- [ ] `curl -sI https://TU-DOMINIO | grep -i -E "content-security-policy|x-frame|nosniff|referrer"` las
      saca las cuatro.
- [ ] La consola del navegador no muestra ningún error de CSP al navegar por
      la aplicación. **Esto no lo cubre ningún test**: la CSP se rompe en el
      navegador, no en el servidor.

### Lo que no debe verse desde fuera

- [ ] `nmap TU-IP` (desde otra máquina) muestra **solo** 80, 443 y el SSH.
- [ ] `curl http://TU-IP:5433` y `curl http://TU-IP:8091` no responden.
- [ ] `dc ps` no lista `adminer` ni `mailpit`.

### Que el proxy no rompa los límites

Esto se olvida siempre y no da la cara hasta que hay dos usuarios a la vez.
Los límites de los endpoints anónimos van por IP, y detrás de nginx **todos
los visitantes comparten la del proxy** si `PROXIES_DELANTE` no está puesto:
cinco intentos fallidos de cualquiera dejarían sin entrar a todo el mundo.

- [ ] `dc exec api python -c "from app.config import Config; print(Config.PROXIES_DELANTE)"`
      imprime `1`.
- [ ] En el registro de la aplicación, la IP de una petición es la tuya y no
      una `172.x` interna de Docker.

### Funcionamiento

- [ ] Se puede crear una cuenta y entrar.
- [ ] Llega el correo de verificación **de verdad**, no al registro.
- [ ] Los desplegables de comunidad y materia traen contenido: si salen
      vacíos, falta sembrar el currículo.
- [ ] Se genera una SdA y se exporta a PDF y a DOCX.
- [ ] El selector de idioma cambia el idioma al elegir, sin pulsar nada más.

---

## Lo que este documento todavía no cubre

Se deja escrito para que la ausencia sea una decisión y no un olvido:

- **Actualizaciones sin corte.** Hoy `dc up -d --build` reinicia la aplicación.
  Con usuarios reales conviene mirarlo.
- **Vigilancia.** No hay nada que avise de que el servicio se cayó: se descubre
  cuando alguien lo dice.
- **Rotación de registros.** Docker los acumula hasta llenar el disco si no se
  le pone `max-size`.
- **Protección de datos.** Con usuarios de fuera hay datos personales de por
  medio —correo, centro, y las SdA que escriben—, y eso trae obligaciones que
  no son técnicas. No es parte de este documento, pero tampoco desaparece por
  no estar aquí.
