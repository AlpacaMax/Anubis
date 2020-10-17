#!/bin/bash

cd $(dirname $(realpath $0))


kubectl config use-context minikube
eval $(minikube -p minikube docker-env)

if ! kubectl get namespace | grep anubis &> /dev/null; then
    kubectl create namespace anubis
fi

if ! kubectl get secrets -n anubis | grep api &> /dev/null; then
    kubectl create secret generic api \
            --from-literal=database-uri=mysql+pymysql://anubis:anubis@mariadb.mariadb.svc.cluster.local/anubis \
            --from-literal=secret-key=$(head -c10 /dev/urandom | openssl sha1 -hex | awk '{print $2}') \
            -n anubis

    kubectl create secret generic oauth \
            --from-literal=consumer-key='aaa' \
            --from-literal=consumer-secret='aaa' \
            -n anubis
fi



pushd ..
docker-compose build api
docker-compose build --parallel web logstash
if ! docker image ls | awk '{print $1}' | grep 'registry.osiris.services/anubis/api-dev' &>/dev/null; then
    docker-compose build api-dev
fi
popd

../pipeline/build.sh

if helm list -n anubis | grep anubis &> /dev/null; then
    helm upgrade anubis ./helm -n anubis \
         --set "imagePullPolicy=IfNotPresent" \
         --set "elasticsearch.storageClassName=standard" \
         --set "debug=true" \
         --set "domain=localhost" \
         --set "elasticsearch.initContainer=false" $@
else
    helm install anubis ./helm -n anubis \
         --set "imagePullPolicy=IfNotPresent" \
         --set "elasticsearch.storageClassName=standard" \
         --set "debug=true" \
         --set "domain=localhost" \
         --set "elasticsearch.initContainer=false" $@
fi

kubectl rollout restart deployments.apps/anubis-api -n anubis
kubectl rollout restart deployments.apps/anubis-pipeline-api -n anubis
kubectl rollout restart deployments.apps/anubis-rpc-workers  -n anubis
