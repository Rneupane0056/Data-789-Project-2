# Blue-Green Deployment Design

## 1. Strategy
Two identical copies of the API run side by side: `api-blue` and `api-green`
(`deployment/docker-compose.blue-green.yml`). Clients only ever call nginx on
`http://localhost:8080`; nginx forwards every request to whichever version is
listed as the active `server` in its `fraud_backend` upstream. A new release is
started as the idle colour while the live colour keeps serving.

## 2. Cutover
`deployment/switch_traffic.sh` comments out the active server line in
`deployment/nginx/nginx.conf`, uncomments the standby one, and runs
`nginx -s reload`. On reload nginx starts new worker processes with the new
upstream while the old workers finish their in-flight requests before exiting,
so no connection is cut and no request is dropped.

## 3. Health gate and rollback
Before touching nginx, the script polls the target's `/health` endpoint
(port 8001 for blue, 8002 for green) up to 20 times. If the target never
answers 200, the script exits and traffic stays on the current version.
Rollback is the same operation in reverse: running the script again flips
traffic back, and because the old version was never stopped it takes effect
immediately.

## 4. Mapping to Kubernetes
Blue and green become two Deployments whose pods carry a `version: blue` or
`version: green` label. The nginx upstream becomes a Service whose selector
names the live version; cutover is a `kubectl patch` of that selector, and the
health gate becomes each Deployment's readiness probe on `/health`, so the
Service only routes to pods that are ready.

## 5. Evidence
While the provided load harness sent 10,000 requests through nginx
(`python tests/test_performance.py --n 10000 --url http://localhost:8080`),
traffic was switched blue -> green and then rolled back green -> blue. The
harness reported 0 errors (`results_bluegreen.json`), and the container logs
show requests moving from `api-blue` to `api-green` at the switch.

![Blue-green switch under load](bluegreen_switch.png)