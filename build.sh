#!/usr/bin/env bash
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
# SQLite no Render é efêmero: recarrega os dados de demo a cada deploy.
python manage.py carregar_demo
