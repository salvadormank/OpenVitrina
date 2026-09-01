# OpenVitrina

Convierte fotos de una propiedad en un reel vertical listo para publicar.

Subes las imágenes, cada una se anima con un modelo de video por IA, y el
resultado se ensambla con transiciones y música en un solo archivo. Pensado
para inmobiliarias y asesores que necesitan video de catálogo sin equipo de
producción.

**Estado:** proyecto en desarrollo temprano. Funciona de punta a punta, pero
todavía no está endurecido para producción.

---

## Cómo funciona

```
imágenes → un clip por imagen (Sora / Kling / Minimax) → transiciones → música → MP4
```

El trabajo pesado corre en Celery, así que la interfaz no se bloquea: subes las
fotos, la tarea se encola y la página muestra el avance (`% completado` y en qué
etapa va) mientras se generan los clips.

## Qué incluye

**Modelos de video** — Sora 2 y Sora 2 Pro vía OpenAI; Kling O3 (standard y pro)
y Minimax Video-01 vía fal.ai.

**Transiciones** — crossfade, fundido a negro, barrido lateral, zoom blur.

**Música** — tres pistas generadas (cinemática, inspiracional, lujo), subir la
tuya, o ninguna.

**Seguimiento** — cada proyecto pasa por `borrador → en cola → generando clips →
ensamblando → listo`, con el error guardado si algo falla.

## Instalación

Requiere Python 3.10+, Redis y ffmpeg.

```bash
git clone https://github.com/salvadormank/OpenVitrina.git
cd OpenVitrina
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # y edita las claves
python manage.py migrate
python manage.py createsuperuser
```

Levanta los dos procesos, en terminales separadas:

```bash
python manage.py runserver
celery -A reels_project worker -l info
```

## Configuración

Todo se lee del entorno; nada de claves en el código.

| Variable | Para qué |
|---|---|
| `SECRET_KEY` | Clave de Django. **Cámbiala en producción.** |
| `DEBUG` | `True` en desarrollo, `False` al desplegar |
| `ALLOWED_HOSTS` | Dominios permitidos, separados por coma |
| `REDIS_URL` | Broker de Celery. Por defecto `redis://localhost:6379/0` |
| `OPENAI_API_KEY` | Necesaria para Sora |
| `AI_VIDEO_MODEL` | `sora-2` o `sora-2-pro` |
| `FAL_KEY` | Solo si usas los modelos de fal.ai |

## Costos

La generación de video se paga por clip al proveedor. Como referencia, Sora 2
ronda los 0.10 USD por clip y Sora 2 Pro los 0.20. Un reel de diez fotos son
diez clips, así que conviene probar con pocas imágenes antes de lanzar un
proyecto grande.

## Stack

Django 4.2 · Celery · Redis · MoviePy · Pillow · OpenAI · fal.ai

## Licencia

MIT — ver [LICENSE](LICENSE). Úsalo, modifícalo y distribúyelo libremente,
incluso con fines comerciales, conservando el aviso de copyright.
