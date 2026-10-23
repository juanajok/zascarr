# Datos de la ejecución final — evaluación del lector RAR/CBR (#308)

> Salida íntegra de `resumen.md` (264 celdas = 11 muestras × 6 motores × 4 operaciones), generada por el banco en la Pi el **2026-10-23 ~00:15 (CEST)**. Contexto, método, criterios y conclusiones: `evaluacion-lector-rar-2026-10-23.md`. Las muestras se citan por código (`m01`…`m11`); no hay nombres de ficheros ni rutas del PO.
> Columnas: **primera** = tiempo de la primera de las 3 repeticiones (s); **mediana** = mediana de las 3 (s); **pico máx.** = memoria residente máxima de las 3 (MiB); **tmpfs** = bytes escritos en el `tmpfs` de trabajo (solo `unar`, que no escribe a la salida estándar).

| muestra | firma | sólido | motor | operación | estado | primera (s) | mediana (s) | pico máx. (MiB) | tmpfs (B) | causa del FAIL / nota |
|---|---|---|---|---|---|---|---|---|---|---|
| m01 | RAR4 (o anterior) | no | unar | listar | PASS | 0.194 | 0.048 | 20.4 | 0 |  |
| m01 | RAR4 (o anterior) | no | unar | primera | PASS | 0.054 | 0.05 | 24.3 | 800268 |  |
| m01 | RAR4 (o anterior) | no | unar | ultima | PASS | 0.035 | 0.035 | 23.8 | 96637 |  |
| m01 | RAR4 (o anterior) | no | unar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m01 | RAR4 (o anterior) | no | bsdtar | listar | PASS | 0.017 | 0.011 | 14.2 | 0 |  |
| m01 | RAR4 (o anterior) | no | bsdtar | primera | PASS | 0.015 | 0.015 | 14.2 | 0 |  |
| m01 | RAR4 (o anterior) | no | bsdtar | ultima | PASS | 0.006 | 0.005 | 14.7 | 0 |  |
| m01 | RAR4 (o anterior) | no | bsdtar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m01 | RAR4 (o anterior) | no | unrar | listar | PASS | 0.003 | 0.003 | 14.2 | 0 |  |
| m01 | RAR4 (o anterior) | no | unrar | primera | PASS | 0.014 | 0.014 | 14.7 | 0 |  |
| m01 | RAR4 (o anterior) | no | unrar | ultima | PASS | 0.004 | 0.004 | 14.7 | 0 |  |
| m01 | RAR4 (o anterior) | no | unrar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m01 | RAR4 (o anterior) | no | rarfile+unar | listar | PASS | 0.1 | 0.097 | 18.8 | 0 |  |
| m01 | RAR4 (o anterior) | no | rarfile+unar | primera | PASS | 0.181 | 0.181 | 23.8 | 0 |  |
| m01 | RAR4 (o anterior) | no | rarfile+unar | ultima | PASS | 0.165 | 0.165 | 23.3 | 0 |  |
| m01 | RAR4 (o anterior) | no | rarfile+unar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m01 | RAR4 (o anterior) | no | rarfile+bsdtar | listar | PASS | 0.078 | 0.078 | 18.8 | 0 |  |
| m01 | RAR4 (o anterior) | no | rarfile+bsdtar | primera | FAIL | 0.081 | 0.084 | 18.8 | 0 | LECTOR (la herramienta no pudo leerlo) |
| m01 | RAR4 (o anterior) | no | rarfile+bsdtar | ultima | FAIL | 0.081 | 0.081 | 18.8 | 0 | LECTOR (la herramienta no pudo leerlo) |
| m01 | RAR4 (o anterior) | no | rarfile+bsdtar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m01 | RAR4 (o anterior) | no | rarfile+unrar | listar | PASS | 0.081 | 0.075 | 18.8 | 0 |  |
| m01 | RAR4 (o anterior) | no | rarfile+unrar | primera | PASS | 0.124 | 0.124 | 22.9 | 0 |  |
| m01 | RAR4 (o anterior) | no | rarfile+unrar | ultima | PASS | 0.114 | 0.114 | 22.3 | 0 |  |
| m01 | RAR4 (o anterior) | no | rarfile+unrar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m02 | RAR4 (o anterior) | no | unar | listar | PASS | 0.032 | 0.032 | 20.5 | 0 |  |
| m02 | RAR4 (o anterior) | no | unar | primera | PASS | 0.038 | 0.037 | 23.9 | 214993 |  |
| m02 | RAR4 (o anterior) | no | unar | ultima | PASS | 0.033 | 0.032 | 20.3 | 126780 |  |
| m02 | RAR4 (o anterior) | no | unar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m02 | RAR4 (o anterior) | no | bsdtar | listar | PASS | 0.022 | 0.005 | 14.2 | 0 |  |
| m02 | RAR4 (o anterior) | no | bsdtar | primera | PASS | 0.007 | 0.007 | 14.7 | 0 |  |
| m02 | RAR4 (o anterior) | no | bsdtar | ultima | PASS | 0.005 | 0.005 | 14.7 | 0 |  |
| m02 | RAR4 (o anterior) | no | bsdtar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m02 | RAR4 (o anterior) | no | unrar | listar | PASS | 0.003 | 0.003 | 14.2 | 0 |  |
| m02 | RAR4 (o anterior) | no | unrar | primera | PASS | 0.006 | 0.006 | 14.7 | 0 |  |
| m02 | RAR4 (o anterior) | no | unrar | ultima | PASS | 0.003 | 0.003 | 14.7 | 0 |  |
| m02 | RAR4 (o anterior) | no | unrar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m02 | RAR4 (o anterior) | no | rarfile+unar | listar | PASS | 0.097 | 0.097 | 18.8 | 0 |  |
| m02 | RAR4 (o anterior) | no | rarfile+unar | primera | PASS | 0.17 | 0.17 | 23.4 | 0 |  |
| m02 | RAR4 (o anterior) | no | rarfile+unar | ultima | PASS | 0.161 | 0.141 | 23.4 | 0 |  |
| m02 | RAR4 (o anterior) | no | rarfile+unar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m02 | RAR4 (o anterior) | no | rarfile+bsdtar | listar | PASS | 0.081 | 0.078 | 18.8 | 0 |  |
| m02 | RAR4 (o anterior) | no | rarfile+bsdtar | primera | FAIL | 0.081 | 0.081 | 18.8 | 0 | LECTOR (la herramienta no pudo leerlo) |
| m02 | RAR4 (o anterior) | no | rarfile+bsdtar | ultima | PASS | 0.116 | 0.116 | 22.9 | 0 |  |
| m02 | RAR4 (o anterior) | no | rarfile+bsdtar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m02 | RAR4 (o anterior) | no | rarfile+unrar | listar | PASS | 0.075 | 0.075 | 18.8 | 0 |  |
| m02 | RAR4 (o anterior) | no | rarfile+unrar | primera | PASS | 0.115 | 0.115 | 22.4 | 0 |  |
| m02 | RAR4 (o anterior) | no | rarfile+unrar | ultima | PASS | 0.114 | 0.114 | 23.4 | 0 |  |
| m02 | RAR4 (o anterior) | no | rarfile+unrar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m03 | RAR4 (o anterior) | no | unar | listar | PASS | 0.043 | 0.042 | 21.5 | 0 |  |
| m03 | RAR4 (o anterior) | no | unar | primera | PASS | 0.051 | 0.051 | 24.4 | 505298 |  |
| m03 | RAR4 (o anterior) | no | unar | ultima | PASS | 0.046 | 0.046 | 24.5 | 234023 |  |
| m03 | RAR4 (o anterior) | no | unar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m03 | RAR4 (o anterior) | no | bsdtar | listar | PASS | 0.062 | 0.007 | 14.2 | 0 |  |
| m03 | RAR4 (o anterior) | no | bsdtar | primera | PASS | 0.013 | 0.013 | 14.7 | 0 |  |
| m03 | RAR4 (o anterior) | no | bsdtar | ultima | PASS | 0.009 | 0.009 | 14.2 | 0 |  |
| m03 | RAR4 (o anterior) | no | bsdtar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m03 | RAR4 (o anterior) | no | unrar | listar | PASS | 0.005 | 0.005 | 14.2 | 0 |  |
| m03 | RAR4 (o anterior) | no | unrar | primera | PASS | 0.011 | 0.011 | 14.7 | 0 |  |
| m03 | RAR4 (o anterior) | no | unrar | ultima | PASS | 0.007 | 0.007 | 14.7 | 0 |  |
| m03 | RAR4 (o anterior) | no | unrar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m03 | RAR4 (o anterior) | no | rarfile+unar | listar | PASS | 0.1 | 0.1 | 18.8 | 0 |  |
| m03 | RAR4 (o anterior) | no | rarfile+unar | primera | PASS | 0.178 | 0.178 | 23.9 | 0 |  |
| m03 | RAR4 (o anterior) | no | rarfile+unar | ultima | PASS | 0.172 | 0.171 | 23.4 | 0 |  |
| m03 | RAR4 (o anterior) | no | rarfile+unar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m03 | RAR4 (o anterior) | no | rarfile+bsdtar | listar | PASS | 0.079 | 0.08 | 18.8 | 0 |  |
| m03 | RAR4 (o anterior) | no | rarfile+bsdtar | primera | FAIL | 0.084 | 0.084 | 19.3 | 0 | LECTOR (la herramienta no pudo leerlo) |
| m03 | RAR4 (o anterior) | no | rarfile+bsdtar | ultima | FAIL | 0.084 | 0.084 | 18.8 | 0 | LECTOR (la herramienta no pudo leerlo) |
| m03 | RAR4 (o anterior) | no | rarfile+bsdtar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m03 | RAR4 (o anterior) | no | rarfile+unrar | listar | PASS | 0.08 | 0.08 | 18.8 | 0 |  |
| m03 | RAR4 (o anterior) | no | rarfile+unrar | primera | PASS | 0.124 | 0.124 | 22.9 | 0 |  |
| m03 | RAR4 (o anterior) | no | rarfile+unrar | ultima | PASS | 0.119 | 0.123 | 22.4 | 0 |  |
| m03 | RAR4 (o anterior) | no | rarfile+unrar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m04 | RAR4 (o anterior) | no | unar | listar | PASS | 0.03 | 0.03 | 20.5 | 0 | paquete |
| m04 | RAR4 (o anterior) | no | unar | primera | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m04 | RAR4 (o anterior) | no | unar | ultima | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m04 | RAR4 (o anterior) | no | unar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m04 | RAR4 (o anterior) | no | bsdtar | listar | PASS | 0.011 | 0.004 | 14.2 | 0 |  |
| m04 | RAR4 (o anterior) | no | bsdtar | primera | PASS | 0.007 | 0.006 | 14.7 | 0 |  |
| m04 | RAR4 (o anterior) | no | bsdtar | ultima | PASS | 0.004 | 0.004 | 14.7 | 0 |  |
| m04 | RAR4 (o anterior) | no | bsdtar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m04 | RAR4 (o anterior) | no | unrar | listar | PASS | 0.002 | 0.002 | 14.2 | 0 | paquete |
| m04 | RAR4 (o anterior) | no | unrar | primera | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m04 | RAR4 (o anterior) | no | unrar | ultima | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m04 | RAR4 (o anterior) | no | unrar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m04 | RAR4 (o anterior) | no | rarfile+unar | listar | PASS | 0.097 | 0.097 | 18.8 | 0 | paquete |
| m04 | RAR4 (o anterior) | no | rarfile+unar | primera | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m04 | RAR4 (o anterior) | no | rarfile+unar | ultima | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m04 | RAR4 (o anterior) | no | rarfile+unar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m04 | RAR4 (o anterior) | no | rarfile+bsdtar | listar | PASS | 0.077 | 0.077 | 18.8 | 0 | paquete |
| m04 | RAR4 (o anterior) | no | rarfile+bsdtar | primera | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m04 | RAR4 (o anterior) | no | rarfile+bsdtar | ultima | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m04 | RAR4 (o anterior) | no | rarfile+bsdtar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m04 | RAR4 (o anterior) | no | rarfile+unrar | listar | PASS | 0.074 | 0.074 | 18.8 | 0 | paquete |
| m04 | RAR4 (o anterior) | no | rarfile+unrar | primera | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m04 | RAR4 (o anterior) | no | rarfile+unrar | ultima | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m04 | RAR4 (o anterior) | no | rarfile+unrar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m05 | RAR4 (o anterior) | no | unar | listar | PASS | 0.042 | 0.041 | 21.5 | 0 |  |
| m05 | RAR4 (o anterior) | no | unar | primera | PASS | 0.05 | 0.05 | 24.9 | 466172 |  |
| m05 | RAR4 (o anterior) | no | unar | ultima | PASS | 0.05 | 0.048 | 24.9 | 388578 |  |
| m05 | RAR4 (o anterior) | no | unar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m05 | RAR4 (o anterior) | no | bsdtar | listar | PASS | 0.08 | 0.009 | 14.2 | 0 |  |
| m05 | RAR4 (o anterior) | no | bsdtar | primera | PASS | 0.014 | 0.014 | 14.7 | 0 |  |
| m05 | RAR4 (o anterior) | no | bsdtar | ultima | PASS | 0.013 | 0.013 | 14.7 | 0 |  |
| m05 | RAR4 (o anterior) | no | bsdtar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m05 | RAR4 (o anterior) | no | unrar | listar | PASS | 0.006 | 0.006 | 14.2 | 0 |  |
| m05 | RAR4 (o anterior) | no | unrar | primera | PASS | 0.012 | 0.012 | 14.2 | 0 |  |
| m05 | RAR4 (o anterior) | no | unrar | ultima | PASS | 0.011 | 0.011 | 14.7 | 0 |  |
| m05 | RAR4 (o anterior) | no | unrar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m05 | RAR4 (o anterior) | no | rarfile+unar | listar | PASS | 0.102 | 0.12 | 18.8 | 0 |  |
| m05 | RAR4 (o anterior) | no | rarfile+unar | primera | PASS | 0.19 | 0.178 | 23.9 | 0 |  |
| m05 | RAR4 (o anterior) | no | rarfile+unar | ultima | PASS | 0.179 | 0.198 | 23.9 | 0 |  |
| m05 | RAR4 (o anterior) | no | rarfile+unar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m05 | RAR4 (o anterior) | no | rarfile+bsdtar | listar | PASS | 0.089 | 0.087 | 18.8 | 0 |  |
| m05 | RAR4 (o anterior) | no | rarfile+bsdtar | primera | FAIL | 0.089 | 0.089 | 19.3 | 0 | LECTOR (la herramienta no pudo leerlo) |
| m05 | RAR4 (o anterior) | no | rarfile+bsdtar | ultima | FAIL | 0.086 | 0.086 | 19.3 | 0 | LECTOR (la herramienta no pudo leerlo) |
| m05 | RAR4 (o anterior) | no | rarfile+bsdtar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m05 | RAR4 (o anterior) | no | rarfile+unrar | listar | PASS | 0.086 | 0.084 | 18.8 | 0 |  |
| m05 | RAR4 (o anterior) | no | rarfile+unrar | primera | PASS | 0.127 | 0.13 | 22.9 | 0 |  |
| m05 | RAR4 (o anterior) | no | rarfile+unrar | ultima | PASS | 0.127 | 0.127 | 23.9 | 0 |  |
| m05 | RAR4 (o anterior) | no | rarfile+unrar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m06 | RAR5 | no | unar | listar | PASS | 0.047 | 0.03 | 18.9 | 0 |  |
| m06 | RAR5 | no | unar | primera | PASS | 0.044 | 0.044 | 20.4 | 522742 |  |
| m06 | RAR5 | no | unar | ultima | PASS | 0.047 | 0.047 | 20.4 | 615348 |  |
| m06 | RAR5 | no | unar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m06 | RAR5 | no | bsdtar | listar | PASS | 0.025 | 0.005 | 14.2 | 0 |  |
| m06 | RAR5 | no | bsdtar | primera | PASS | 0.014 | 0.014 | 14.7 | 0 |  |
| m06 | RAR5 | no | bsdtar | ultima | PASS | 0.015 | 0.015 | 14.8 | 0 |  |
| m06 | RAR5 | no | bsdtar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m06 | RAR5 | no | unrar | listar | PASS | 0.002 | 0.002 | 14.2 | 0 |  |
| m06 | RAR5 | no | unrar | primera | PASS | 0.011 | 0.01 | 14.7 | 0 |  |
| m06 | RAR5 | no | unrar | ultima | PASS | 0.011 | 0.011 | 14.7 | 0 |  |
| m06 | RAR5 | no | unrar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m06 | RAR5 | no | rarfile+unar | listar | PASS | 0.1 | 0.104 | 18.8 | 0 |  |
| m06 | RAR5 | no | rarfile+unar | primera | PASS | 0.175 | 0.174 | 22.9 | 0 |  |
| m06 | RAR5 | no | rarfile+unar | ultima | PASS | 0.193 | 0.184 | 22.9 | 0 |  |
| m06 | RAR5 | no | rarfile+unar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m06 | RAR5 | no | rarfile+bsdtar | listar | PASS | 0.08 | 0.08 | 18.8 | 0 |  |
| m06 | RAR5 | no | rarfile+bsdtar | primera | FAIL | 0.083 | 0.084 | 18.8 | 0 | LECTOR (la herramienta no pudo leerlo) |
| m06 | RAR5 | no | rarfile+bsdtar | ultima | FAIL | 0.083 | 0.084 | 18.8 | 0 | LECTOR (la herramienta no pudo leerlo) |
| m06 | RAR5 | no | rarfile+bsdtar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m06 | RAR5 | no | rarfile+unrar | listar | PASS | 0.079 | 0.079 | 18.8 | 0 |  |
| m06 | RAR5 | no | rarfile+unrar | primera | PASS | 0.128 | 0.128 | 22.9 | 0 |  |
| m06 | RAR5 | no | rarfile+unrar | ultima | PASS | 0.125 | 0.125 | 22.8 | 0 |  |
| m06 | RAR5 | no | rarfile+unrar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m07 | RAR5 | no | unar | listar | PASS | 0.047 | 0.035 | 18.9 | 0 |  |
| m07 | RAR5 | no | unar | primera | PASS | 0.036 | 0.036 | 20.4 | 110713 |  |
| m07 | RAR5 | no | unar | ultima | PASS | 0.033 | 0.033 | 19.4 | 84131 |  |
| m07 | RAR5 | no | unar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m07 | RAR5 | no | bsdtar | listar | PASS | 0.026 | 0.006 | 14.2 | 0 |  |
| m07 | RAR5 | no | bsdtar | primera | PASS | 0.008 | 0.008 | 14.7 | 0 |  |
| m07 | RAR5 | no | bsdtar | ultima | PASS | 0.006 | 0.006 | 14.7 | 0 |  |
| m07 | RAR5 | no | bsdtar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m07 | RAR5 | no | unrar | listar | PASS | 0.003 | 0.003 | 14.2 | 0 |  |
| m07 | RAR5 | no | unrar | primera | PASS | 0.006 | 0.006 | 14.7 | 0 |  |
| m07 | RAR5 | no | unrar | ultima | PASS | 0.003 | 0.003 | 14.8 | 0 |  |
| m07 | RAR5 | no | unrar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m07 | RAR5 | no | rarfile+unar | listar | PASS | 0.1 | 0.102 | 18.8 | 0 |  |
| m07 | RAR5 | no | rarfile+unar | primera | PASS | 0.164 | 0.165 | 22.3 | 0 |  |
| m07 | RAR5 | no | rarfile+unar | ultima | PASS | 0.136 | 0.136 | 22.4 | 0 |  |
| m07 | RAR5 | no | rarfile+unar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m07 | RAR5 | no | rarfile+bsdtar | listar | PASS | 0.081 | 0.081 | 18.8 | 0 |  |
| m07 | RAR5 | no | rarfile+bsdtar | primera | FAIL | 0.084 | 0.084 | 18.8 | 0 | LECTOR (la herramienta no pudo leerlo) |
| m07 | RAR5 | no | rarfile+bsdtar | ultima | PASS | 0.115 | 0.116 | 22.3 | 0 |  |
| m07 | RAR5 | no | rarfile+bsdtar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m07 | RAR5 | no | rarfile+unrar | listar | PASS | 0.079 | 0.078 | 18.8 | 0 |  |
| m07 | RAR5 | no | rarfile+unrar | primera | PASS | 0.124 | 0.119 | 22.4 | 0 |  |
| m07 | RAR5 | no | rarfile+unrar | ultima | PASS | 0.114 | 0.114 | 22.3 | 0 |  |
| m07 | RAR5 | no | rarfile+unrar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m08 | RAR4 (o anterior) | sí | unar | listar | PASS | 0.047 | 0.047 | 21.5 | 0 |  |
| m08 | RAR4 (o anterior) | sí | unar | primera | PASS | 0.051 | 0.051 | 25.3 | 422060 |  |
| m08 | RAR4 (o anterior) | sí | unar | ultima | PASS | 1.024 | 1.011 | 25.3 | 58445 |  |
| m08 | RAR4 (o anterior) | sí | unar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m08 | RAR4 (o anterior) | sí | bsdtar | listar | FAIL | 0.004 | 0.003 | 14.2 | 0 | LECTOR (la herramienta no pudo leerlo) |
| m08 | RAR4 (o anterior) | sí | bsdtar | primera | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m08 | RAR4 (o anterior) | sí | bsdtar | ultima | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m08 | RAR4 (o anterior) | sí | bsdtar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m08 | RAR4 (o anterior) | sí | unrar | listar | PASS | 0.005 | 0.005 | 14.2 | 0 |  |
| m08 | RAR4 (o anterior) | sí | unrar | primera | PASS | 0.011 | 0.011 | 14.7 | 0 |  |
| m08 | RAR4 (o anterior) | sí | unrar | ultima | PASS | 0.689 | 0.688 | 14.2 | 0 |  |
| m08 | RAR4 (o anterior) | sí | unrar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m08 | RAR4 (o anterior) | sí | rarfile+unar | listar | PASS | 0.101 | 0.101 | 18.8 | 0 |  |
| m08 | RAR4 (o anterior) | sí | rarfile+unar | primera | PASS | 0.189 | 0.189 | 24.8 | 0 |  |
| m08 | RAR4 (o anterior) | sí | rarfile+unar | ultima | PASS | 1.144 | 1.162 | 25.3 | 0 |  |
| m08 | RAR4 (o anterior) | sí | rarfile+unar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m08 | RAR4 (o anterior) | sí | rarfile+bsdtar | listar | PASS | 0.081 | 0.081 | 18.8 | 0 |  |
| m08 | RAR4 (o anterior) | sí | rarfile+bsdtar | primera | FAIL | 0.084 | 0.084 | 19.3 | 0 | LECTOR (la herramienta no pudo leerlo) |
| m08 | RAR4 (o anterior) | sí | rarfile+bsdtar | ultima | FAIL | 0.088 | 0.095 | 18.8 | 0 | LECTOR (la herramienta no pudo leerlo) |
| m08 | RAR4 (o anterior) | sí | rarfile+bsdtar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m08 | RAR4 (o anterior) | sí | rarfile+unrar | listar | PASS | 0.083 | 0.079 | 18.8 | 0 |  |
| m08 | RAR4 (o anterior) | sí | rarfile+unrar | primera | PASS | 0.125 | 0.126 | 22.9 | 0 |  |
| m08 | RAR4 (o anterior) | sí | rarfile+unrar | ultima | PASS | 0.808 | 0.804 | 22.3 | 0 |  |
| m08 | RAR4 (o anterior) | sí | rarfile+unrar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m09 | RAR4 (o anterior) | no | unar | listar | PASS | 0.031 | 0.031 | 20.5 | 0 |  |
| m09 | RAR4 (o anterior) | no | unar | primera | PASS | 0.042 | 0.042 | 24.3 | 474709 |  |
| m09 | RAR4 (o anterior) | no | unar | ultima | PASS | 0.038 | 0.038 | 20.3 | 1110159 |  |
| m09 | RAR4 (o anterior) | no | unar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m09 | RAR4 (o anterior) | no | bsdtar | listar | PASS | 0.014 | 0.005 | 14.2 | 0 |  |
| m09 | RAR4 (o anterior) | no | bsdtar | primera | PASS | 0.011 | 0.011 | 14.8 | 0 |  |
| m09 | RAR4 (o anterior) | no | bsdtar | ultima | PASS | 0.006 | 0.006 | 14.7 | 0 |  |
| m09 | RAR4 (o anterior) | no | bsdtar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m09 | RAR4 (o anterior) | no | unrar | listar | PASS | 0.003 | 0.003 | 14.2 | 0 |  |
| m09 | RAR4 (o anterior) | no | unrar | primera | PASS | 0.009 | 0.009 | 14.7 | 0 |  |
| m09 | RAR4 (o anterior) | no | unrar | ultima | PASS | 0.006 | 0.006 | 14.7 | 0 |  |
| m09 | RAR4 (o anterior) | no | unrar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m09 | RAR4 (o anterior) | no | rarfile+unar | listar | PASS | 0.122 | 0.1 | 18.8 | 0 |  |
| m09 | RAR4 (o anterior) | no | rarfile+unar | primera | PASS | 0.193 | 0.177 | 23.5 | 0 |  |
| m09 | RAR4 (o anterior) | no | rarfile+unar | ultima | PASS | 0.134 | 0.134 | 23.3 | 0 |  |
| m09 | RAR4 (o anterior) | no | rarfile+unar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m09 | RAR4 (o anterior) | no | rarfile+bsdtar | listar | PASS | 0.077 | 0.078 | 18.8 | 0 |  |
| m09 | RAR4 (o anterior) | no | rarfile+bsdtar | primera | FAIL | 0.081 | 0.081 | 18.8 | 0 | LECTOR (la herramienta no pudo leerlo) |
| m09 | RAR4 (o anterior) | no | rarfile+bsdtar | ultima | PASS | 0.114 | 0.114 | 23.3 | 0 |  |
| m09 | RAR4 (o anterior) | no | rarfile+bsdtar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m09 | RAR4 (o anterior) | no | rarfile+unrar | listar | PASS | 0.075 | 0.076 | 18.8 | 0 |  |
| m09 | RAR4 (o anterior) | no | rarfile+unrar | primera | PASS | 0.123 | 0.123 | 23.3 | 0 |  |
| m09 | RAR4 (o anterior) | no | rarfile+unrar | ultima | PASS | 0.112 | 0.112 | 23.3 | 0 |  |
| m09 | RAR4 (o anterior) | no | rarfile+unrar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m10 | RAR4 (o anterior) | no | unar | listar | PASS | 0.037 | 0.035 | 19.5 | 0 |  |
| m10 | RAR4 (o anterior) | no | unar | primera | PASS | 0.044 | 0.044 | 24.0 | 410364 |  |
| m10 | RAR4 (o anterior) | no | unar | ultima | PASS | 0.037 | 0.037 | 23.5 | 107663 |  |
| m10 | RAR4 (o anterior) | no | unar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m10 | RAR4 (o anterior) | no | bsdtar | listar | PASS | 0.021 | 0.005 | 14.2 | 0 |  |
| m10 | RAR4 (o anterior) | no | bsdtar | primera | PASS | 0.011 | 0.011 | 14.7 | 0 |  |
| m10 | RAR4 (o anterior) | no | bsdtar | ultima | PASS | 0.006 | 0.006 | 14.7 | 0 |  |
| m10 | RAR4 (o anterior) | no | bsdtar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m10 | RAR4 (o anterior) | no | unrar | listar | PASS | 0.003 | 0.003 | 14.2 | 0 |  |
| m10 | RAR4 (o anterior) | no | unrar | primera | PASS | 0.009 | 0.009 | 14.7 | 0 |  |
| m10 | RAR4 (o anterior) | no | unrar | ultima | PASS | 0.005 | 0.005 | 14.7 | 0 |  |
| m10 | RAR4 (o anterior) | no | unrar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m10 | RAR4 (o anterior) | no | rarfile+unar | listar | PASS | 0.098 | 0.098 | 18.8 | 0 |  |
| m10 | RAR4 (o anterior) | no | rarfile+unar | primera | PASS | 0.173 | 0.173 | 23.5 | 0 |  |
| m10 | RAR4 (o anterior) | no | rarfile+unar | ultima | PASS | 0.166 | 0.166 | 23.0 | 0 |  |
| m10 | RAR4 (o anterior) | no | rarfile+unar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m10 | RAR4 (o anterior) | no | rarfile+bsdtar | listar | PASS | 0.078 | 0.078 | 18.8 | 0 |  |
| m10 | RAR4 (o anterior) | no | rarfile+bsdtar | primera | FAIL | 0.082 | 0.082 | 18.8 | 0 | LECTOR (la herramienta no pudo leerlo) |
| m10 | RAR4 (o anterior) | no | rarfile+bsdtar | ultima | FAIL | 0.081 | 0.081 | 18.8 | 0 | LECTOR (la herramienta no pudo leerlo) |
| m10 | RAR4 (o anterior) | no | rarfile+bsdtar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m10 | RAR4 (o anterior) | no | rarfile+unrar | listar | PASS | 0.076 | 0.076 | 18.8 | 0 |  |
| m10 | RAR4 (o anterior) | no | rarfile+unrar | primera | PASS | 0.119 | 0.119 | 22.8 | 0 |  |
| m10 | RAR4 (o anterior) | no | rarfile+unrar | ultima | PASS | 0.121 | 0.118 | 22.3 | 0 |  |
| m10 | RAR4 (o anterior) | no | rarfile+unrar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m11 | ZIP | no | unar | listar | PASS | 0.047 | 0.036 | 19.5 | 0 |  |
| m11 | ZIP | no | unar | primera | PASS | 0.039 | 0.039 | 19.6 | 561707 |  |
| m11 | ZIP | no | unar | ultima | PASS | 0.044 | 0.044 | 19.6 | 1984823 |  |
| m11 | ZIP | no | unar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m11 | ZIP | no | bsdtar | listar | PASS | 0.024 | 0.006 | 14.2 | 0 |  |
| m11 | ZIP | no | bsdtar | primera | PASS | 0.009 | 0.009 | 14.7 | 0 |  |
| m11 | ZIP | no | bsdtar | ultima | PASS | 0.01 | 0.01 | 14.7 | 0 |  |
| m11 | ZIP | no | bsdtar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m11 | ZIP | no | unrar | listar | FAIL | 0.005 | 0.005 | 14.2 | 0 | LECTOR (la herramienta no pudo leerlo) |
| m11 | ZIP | no | unrar | primera | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m11 | ZIP | no | unrar | ultima | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m11 | ZIP | no | unrar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m11 | ZIP | no | rarfile+unar | listar | FAIL | 0.1 | 0.1 | 22.8 | 0 | LECTOR (la herramienta no pudo leerlo) |
| m11 | ZIP | no | rarfile+unar | primera | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m11 | ZIP | no | rarfile+unar | ultima | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m11 | ZIP | no | rarfile+unar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m11 | ZIP | no | rarfile+bsdtar | listar | FAIL | 0.084 | 0.082 | 22.8 | 0 | LECTOR (la herramienta no pudo leerlo) |
| m11 | ZIP | no | rarfile+bsdtar | primera | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m11 | ZIP | no | rarfile+bsdtar | ultima | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m11 | ZIP | no | rarfile+bsdtar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m11 | ZIP | no | rarfile+unrar | listar | FAIL | 0.078 | 0.078 | 22.8 | 0 | LECTOR (la herramienta no pudo leerlo) |
| m11 | ZIP | no | rarfile+unrar | primera | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m11 | ZIP | no | rarfile+unrar | ultima | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
| m11 | ZIP | no | rarfile+unrar | comicinfo | NOT RUN (no hay entrada aplicable) |  |  |  |  |  |
