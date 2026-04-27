class NginxConfig:
    """Конфигурация nginx"""
    default_domain = '.masterme.ru'
    nginx_filename = 'demo_nginx.conf'
    default_folder = '/home/deployer1'
    conf = """server {
    server_name %s%s; # test.masterme.ru
    root %s/django;
    listen 80;

    if ($http_user_agent ~* WordPress|BBBike|wget) {
        return 403;
    }

    location /openapi.json {
        proxy_pass http://127.0.0.1:%s;
    }

    location /assets/ {
        proxy_pass http://127.0.0.1:%s;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:%s;
    }

    location /docs/ {
        proxy_pass http://127.0.0.1:%s;
    }

    location / {
        proxy_pass http://127.0.0.1:%s;
    }

    client_max_body_size 12m;
}
"""


class DeployScriptConfig:
    """Скрипты автодеплоя
       TODO: упростить (например, не %s%s на путь к репе + группа, а в одну переменную)
    """
    default_gitlab_group = '/group/subgroup/'
    default_registry = 'registry.example.ru'

    login = 'admin'
    passwd = ''

    drop_filename = 'drop_dev.sh'
    update_filename = 'update_dev.sh'
    upgrade_filename = 'upgrade_dev.sh'
    run_filename = 'run_dev.sh'

    drop = """#!/bin/bash
APP_NAME="%s"

echo "stopping $APP_NAME"
docker stop $APP_NAME || true
echo "removing $APP_NAME"
docker rm $APP_NAME || true

echo "stopping ${APP_NAME}.django"
docker stop ${APP_NAME}.django || true
echo "removing ${APP_NAME}.django"
docker rm ${APP_NAME}.django || true

docker rmi $(docker images -f "dangling=true" -q)

POSTGRES_USER=admin
POSTGRES_PASSWORD=admin
POSTGRES_DB=$APP_NAME

export PGPASSWORD=$POSTGRES_PASSWORD
psql -h 127.0.0.1 -U ${POSTGRES_USER} -c "DROP DATABASE "${POSTGRES_DB}"" postgres || true
    """

    update = """#!/bin/bash
TAG_PREFIX=""
APP_NAME="%s"
REGISTRY="%s"
REGISTRY_GROUP="%s"

#docker rmi $(docker images -f "dangling=true" -q)

#docker rmi ${REGISTRY}${REGISTRY_GROUP}${APP_NAME}:${TAG_PREFIX}previous
#docker tag ${REGISTRY}${REGISTRY_GROUP}${APP_NAME}:${TAG_PREFIX}latest ${REGISTRY}${REGISTRY_GROUP}${APP_NAME}:${TAG_PREFIX}previous
#docker pull ${REGISTRY}${REGISTRY_GROUP}${APP_NAME}:${TAG_PREFIX}latest
    """

    upgrade = """#!/bin/bash
TAG_PREFIX=""
APP_NAME="%s"
REGISTRY="%s"
REGISTRY_GROUP="%s"

echo "SERVER_FOLDER=$SERVER_FOLDER"
echo "SERVICE_NAME=$SERVICE_NAME"

#docker tag ${REGISTRY}${REGISTRY_GROUP}${APP_NAME}:${TAG_PREFIX}latest ${REGISTRY}${REGISTRY_GROUP}${APP_NAME}:${TAG_PREFIX}forrun

echo $( dirname -- "$0"; )
$( dirname -- "$0"; )/run_dev.sh
    """

    run = """#!/bin/bash

TAG_PREFIX=""
APP_NAME="%s"
REGISTRY="%s"
REGISTRY_GROUP="%s"
PORT="%s"
PORT_DJANGO="%s"
ADMIN_LOGIN="%s"
ADMIN_PASSWD="%s"

DEBUG="true"

echo "stopping $APP_NAME"
docker stop $APP_NAME || true
echo "removing $APP_NAME"
docker rm $APP_NAME || true

# POSTGRES SETTINGS
POSTGRES_HOST=172.17.0.1
POSTGRES_PORT=5432
POSTGRES_USER=admin
POSTGRES_PASSWORD=mypass
POSTGRES_DB=$APP_NAME

REGISTER_GL_ADMIN="0"
#CACHE_URL="172.17.0.1:11211"
CACHE_URL="redis://172.17.0.1:6379"

echo "starting $APP_NAME"

export PGPASSWORD=$POSTGRES_PASSWORD
psql -h 127.0.0.1 -U ${POSTGRES_USER} -tc "SELECT 1 FROM pg_database WHERE datname=\"${POSTGRES_DB}\"" postgres | grep -q 1 || psql -h 127.0.0.1 -U ${POSTGRES_USER} -c "CREATE DATABASE \"${POSTGRES_DB}\"" postgres

MOUNTSRC="${SERVER_FOLDER}/${SERVICE_NAME}/app"
MOUNTDST="/opt/app" # приложение надо пускать из монтированной с хоста папки

echo "$MOUNTSRC mounting to $MOUNTDST" # приложение надо запускать из примонтированной папки
# в примонтированную папку необходимо скопировать все из образа если она пустая
# общая папка c кодом нужна для того, чтобы перезагружались все приложения (django, fastapi, ...)

docker run --ipc=private --restart unless-stopped \
           --env MKL_NUM_THREADS=2 --env OMP_NUM_THREADS=2 \
           --mount type=bind,source=$MOUNTSRC,destination=$MOUNTDST \
           -e "SERVICE_NAME=$APP_NAME" \
           -e "APP_NAME=$APP_NAME" \
           -e "DEBUG=$DEBUG" \
           -e "PORT=$PORT" \
           -e "POSTGRES_HOST=$POSTGRES_HOST" \
           -e "POSTGRES_PORT=$POSTGRES_PORT" \
           -e "POSTGRES_USER=$POSTGRES_USER" \
           -e "POSTGRES_PASSWORD=$POSTGRES_PASSWORD" \
           -e "POSTGRES_DB=$POSTGRES_DB" \
           -e "REGISTER_GL_ADMIN=$REGISTER_GL_ADMIN" \
           -e "CACHE_URL=$CACHE_URL" \
           --hostname=$HOSTNAME -p $PORT:$PORT/tcp \
           --name=$APP_NAME \
           --log-driver json-file \
           --log-opt tag="$APP_NAME" \
           -td ${REGISTRY}${REGISTRY_GROUP}${APP_NAME}:${TAG_PREFIX}latest &

# latest вместо forrun

sleep 3 # Ожидаем копирования файлов

echo "stopping $APP_NAME.django"
docker stop $APP_NAME.django || true
echo "removing $APP_NAME.django"
docker rm $APP_NAME.django || true

RUN_DJANGO_SCRIPT="gunicorn conf.wsgi -b 0.0.0.0:$PORT_DJANGO --reload"
PREPARE_USER_SCRIPT="python manage.py create_super_user --login=$ADMIN_LOGIN --passwd=$ADMIN_PASSWD"
MIGRATE_SCRIPT="python manage.py migrate"
COLLECT_STATIC_SCRIPT="python manage.py collectstatic --noinput"
REBUILD_PROJECT_CONSTRUCTOR="python manage.py rebuild_project_constructor"

docker run --ipc=private --restart unless-stopped \
           --env MKL_NUM_THREADS=2 --env OMP_NUM_THREADS=2 \
           --mount type=bind,source=$MOUNTSRC,destination=$MOUNTDST \
           -e "SERVICE_NAME=$APP_NAME" \
           -e "APP_NAME=$APP_NAME" \
           -e "DEBUG=$DEBUG" \
           -e "PORT=$PORT_DJANGO" \
           -e "POSTGRES_HOST=$POSTGRES_HOST" \
           -e "POSTGRES_PORT=$POSTGRES_PORT" \
           -e "POSTGRES_USER=$POSTGRES_USER" \
           -e "POSTGRES_PASSWORD=$POSTGRES_PASSWORD" \
           -e "POSTGRES_DB=$POSTGRES_DB" \
           -e "REGISTER_GL_ADMIN=$REGISTER_GL_ADMIN" \
           -e "CACHE_URL=$CACHE_URL" \
           --hostname=$HOSTNAME -p $PORT_DJANGO:$PORT_DJANGO/tcp \
           --name=$APP_NAME.django \
           --log-driver json-file \
           --log-opt tag="$APP_NAME.django" \
           -td ${REGISTRY}${REGISTRY_GROUP}${APP_NAME}:${TAG_PREFIX}latest \
           bash -c "cd /opt/app && $MIGRATE_SCRIPT && $COLLECT_STATIC_SCRIPT && $PREPARE_USER_SCRIPT && \
           $REBUILD_PROJECT_CONSTRUCTOR && $RUN_DJANGO_SCRIPT" &
           #bash -c "$MIGRATE_SCRIPT && $COLLECT_STATIC_SCRIPT && $PREPARE_USER_SCRIPT && $RUN_DJANGO_SCRIPT" &

# latest вместо forrun
    """


class EntryPointConfig:
    """Точка входа по умолчанию для приложения
    """
    entrypoint_filename = 'entrypoint.sh'
    conf = """#!/bin/bash
# Копируем код в монтированную директорию, если она пустая
# ls -A exclude . or ..
if [ -z "$(ls -A /opt/app)" ]; then
    echo "/opt/app is empty, copying app"
    cp -fr /app /opt
else
    #echo "/opt/app not empty, passing copying"
    # удаляем, перезаписываем, чтобы код обновлялся
    echo "/opt/app is not empty, replacing"
    rm -rf "/opt/app/*"
    cp -fr /app /opt
fi

cp -fr /app/conf/main.py /opt/app/main.py
#cp -fr /app/bazis_models/ /opt/app/bazis_models/

# Start server
echo "Starting server"
# На gunicorn с воркером uvicorn.workers.UvicornWorker работает только перевая перезагрузка кода, дальше - нет
#gunicorn --chdir conf main:app --workers 1 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT} --reload
#uvicorn --app-dir /opt/app/conf main:app  --host 0.0.0.0 --port ${PORT} --reload
python /opt/app/main.py ${PORT}
    """


class DockerConfig:
    docker_filename = 'Dockerfile'
    conf = """#FROM python:3.10
#ENV LANG C.UTF-8
#ENV COLUMNS 5000
#ENV TERM xterm-color

FROM registry.example.ru/group/subgroup/project:main_latest

ARG SERVER_FOLDER="/opt/not_set"
ENV SERVER_FOLDER="$SERVER_FOLDER"
ARG SERVICE_NAME="/opt/not_set"
ENV SERVICE_NAME="SERVICE_NAME"

#COPY requirements.txt /app/requirements.txt
#RUN pip install -r /app/requirements.txt

COPY . /app
WORKDIR /app

COPY {} .
RUN chmod +x /app/{} && mkdir -p /opt/app

WORKDIR /opt/app

CMD ["/app/{}"]
    """.format(
        EntryPointConfig.entrypoint_filename,
        EntryPointConfig.entrypoint_filename,
        EntryPointConfig.entrypoint_filename,
    )


class CIConfig:
    ci_filename = '.gitlab-ci.yml'
    conf = """
image: docker:20.10.6

variables:
  SERVICE_NAME: $CI_PROJECT_NAME
  IMAGE_TAG: $CI_REGISTRY_IMAGE:$CI_COMMIT_BRANCH
  IMAGE_TAG_LATEST: $CI_REGISTRY_IMAGE:latest
  SERVER_FOLDER: "/home/deployer1"
  BUILD_IMAGE_TAG: "default"
  BUILD_IMAGE_TAG_LATEST: "default:latest"

stages:
  - build
  - deploy
  - drop

run_drop:
  stage: drop
  tags:
    - example_tag
  variables:
    DROP_DEV_SCRIPT: '{}'
  before_script:
    - 'which ssh-agent || ( apk --update add openssh-client )'
    - eval $(ssh-agent -s)
    - chmod 400 "$ID_RSA"
    - ssh-add "$ID_RSA"
    - mkdir -p ~/.ssh
    - chmod 700 ~/.ssh
  script:
    - echo "drop step"
    - DROP_DEV_FILE=$(cat $DROP_DEV_SCRIPT)
    - echo $DROP_DEV_FILE
    - chmod og= $ID_RSA
    - ssh -i $ID_RSA -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP -p $SERVER_PORT "echo '$DROP_DEV_FILE' > '$SERVER_FOLDER/$SERVICE_NAME/$DROP_DEV_SCRIPT'"
    - ssh -i $ID_RSA -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP -p $SERVER_PORT "chmod 777 '$SERVER_FOLDER/$SERVICE_NAME/$DROP_DEV_SCRIPT'"
    - ssh -i $ID_RSA -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP -p $SERVER_PORT "$SERVER_FOLDER/$SERVICE_NAME/$DROP_DEV_SCRIPT"
  rules:
    - if: $CI_COMMIT_TAG =~ /^drop_project*/

run_build_image:
  stage: build
  tags:
    - example_tag
  before_script:
    - env
    - echo "$CI_REGISTRY_PASSWORD" | docker login -u "$CI_REGISTRY_USER" --password-stdin "$CI_REGISTRY"
    - docker info
    - cp $CI_SERVER_TLS_CA_FILE ./
  script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
    - docker build --build-arg SERVER_FOLDER="$SERVER_FOLDER" --build-arg SERVICE_NAME="$SERVICE_NAME" --build-arg CI_SERVER_TLS_CA_FILE=$CI_SERVER_TLS_CA_FILE --build-arg CI_JOB_TOKEN=$CI_JOB_TOKEN --tag $IMAGE_TAG_LATEST .
    # --tag $IMAGE_TAG убираем master образ - latest будет достаточно
    #- docker push $IMAGE_TAG
    #- docker push $IMAGE_TAG_LATEST
  rules:
    - if: $CI_COMMIT_BRANCH == "develop" || $CI_COMMIT_BRANCH == "master" # || $CI_COMMIT_TAG != null

deploy_dev:
  image: alpine:latest
  stage: deploy
  tags:
    - example_tag
  variables:
    UPDATE_DEV_SCRIPT: '{}'
    UPGRADE_DEV_SCRIPT: '{}'
    RUN_DEV_SCRIPT: '{}'
    NGINX_SCRIPT: '{}'
  before_script:
    - apk update && apk add openssh
  script:
    - UPDATE_DEV_FILE=$(cat $UPDATE_DEV_SCRIPT)
    - UPGRADE_DEV_FILE=$(cat $UPGRADE_DEV_SCRIPT)
    - RUN_DEV_FILE=$(cat $RUN_DEV_SCRIPT)
    - NGINX_FILE=$(cat $NGINX_SCRIPT)
    - echo $UPDATE_DEV_FILE
    - echo "token=$CI_BUILD_TOKEN, if empty, then use CI_JOB_TOKEN=$CI_JOB_TOKEN"
    - echo "registry=$CI_REGISTRY"
    - chmod og= $ID_RSA
    - ssh -i $ID_RSA -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP -p $SERVER_PORT "docker login -u gitlab-ci-token -p $CI_JOB_TOKEN $CI_REGISTRY"
    - ssh -i $ID_RSA -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP -p $SERVER_PORT "mkdir -p '$SERVER_FOLDER/$SERVICE_NAME/app'"
    - ssh -i $ID_RSA -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP -p $SERVER_PORT "echo '$UPDATE_DEV_FILE' > '$SERVER_FOLDER/$SERVICE_NAME/$UPDATE_DEV_SCRIPT'"
    - ssh -i $ID_RSA -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP -p $SERVER_PORT "echo '$UPGRADE_DEV_FILE' > '$SERVER_FOLDER/$SERVICE_NAME/$UPGRADE_DEV_SCRIPT'"
    - ssh -i $ID_RSA -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP -p $SERVER_PORT "echo '$RUN_DEV_FILE' > '$SERVER_FOLDER/$SERVICE_NAME/$RUN_DEV_SCRIPT'"
    - ssh -i $ID_RSA -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP -p $SERVER_PORT "chmod 777 '$SERVER_FOLDER/$SERVICE_NAME/$UPDATE_DEV_SCRIPT'"
    - ssh -i $ID_RSA -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP -p $SERVER_PORT "chmod 777 '$SERVER_FOLDER/$SERVICE_NAME/$UPGRADE_DEV_SCRIPT'"
    - ssh -i $ID_RSA -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP -p $SERVER_PORT "chmod 777 '$SERVER_FOLDER/$SERVICE_NAME/$RUN_DEV_SCRIPT'"
    - ssh -i $ID_RSA -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP -p $SERVER_PORT "$SERVER_FOLDER/$SERVICE_NAME/$UPDATE_DEV_SCRIPT"
    - ssh -i $ID_RSA -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP -p $SERVER_PORT "export SERVER_FOLDER='$SERVER_FOLDER' && export SERVICE_NAME='$SERVICE_NAME' && $SERVER_FOLDER/$SERVICE_NAME/$UPGRADE_DEV_SCRIPT"
    - ssh -i $ID_RSA -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP -p $SERVER_PORT "echo '$NGINX_FILE' > '/etc/nginx/sites-enabled/$SERVICE_NAME.conf'"
    - ssh -i $ID_RSA -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP -p $SERVER_PORT "sudo /usr/sbin/service nginx reload"
  rules:
    - if: $CI_COMMIT_BRANCH == "develop" || $CI_COMMIT_BRANCH == "master"
    """.format(
        DeployScriptConfig.drop_filename,
        DeployScriptConfig.update_filename,
        DeployScriptConfig.upgrade_filename,
        DeployScriptConfig.run_filename,
        NginxConfig.nginx_filename,
    )
