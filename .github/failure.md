---
title: Falha na execução do workflow {{ env.WORKFLOW_NAME }} em {{ date | date() }}
labels: bug
---

Consultar o [log de erro da execução](https://github.com/{{ env.REPOSITORY }}/actions/runs/{{ env.RUN_ID }}/job/{{ env.JOB_ID }}).
