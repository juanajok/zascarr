# Datos de la 2.ª tanda — evaluación del lector RAR/CBR (#308)

> Salida de los pasos 6, 7 y 8 del kit `scripts/medicion/evaluacion_rar/`, ejecutados **en la Pi** el 2026-10-23 (paso 6: 10:31; paso 7: 10:42). Contexto, método y conclusiones: `evaluacion-lector-rar-tanda2-2026-10-23.md`. Las muestras se citan por código (`m01`…`m11`, `s01`…`s26`). **Se ha omitido la columna `detalle`** de `resumen2.md` porque lleva nombres de páginas y de series del PO; los textos de error relevantes se citan en la ficha.

## Paso 6 — integridad, daños, topes, cifrado y ComicInfo (`resumen2.md`, sin la columna `detalle`)

| modo | muestra | variante | motor | operación | resultado | estado | s | pico MiB |
|---|---|---|---|---|---|---|---|---|
| integridad | m01 |  | lsar | esquema | {"formato": "RAR", "claves": ["RARAttributes", "RARCRC32", "RARCompressionMethod", "RARCompressionVersion", "RARFlags", "RAROS", "RAROSName", "RARSolidIndex", "XADCompressedSize", "XADCompressionName", "XADFileName", "XADFileSize", "XADIndex", "XADIsDirectory", "XADLastModificationDate", "XADSolidLength", "XADSolidObject", "XADSolidOffset", "XADWindowsFileAttributes"]} | INFO |  |  |
| integridad | m01 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.049 | 23.9 |
| integridad | m01 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.036 | 23.4 |
| integridad | m01 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.015 | 13.0 |
| integridad | m01 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.005 | 13.0 |
| integridad | m02 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.037 | 23.5 |
| integridad | m02 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.033 | 19.5 |
| integridad | m02 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.007 | 13.0 |
| integridad | m02 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.004 | 13.0 |
| integridad | m03 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.05 | 24.0 |
| integridad | m03 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.046 | 24.0 |
| integridad | m03 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.012 | 13.0 |
| integridad | m03 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.009 | 13.0 |
| integridad | m04 |  | lsar | paginas | NOT RUN (paquete) | NOT RUN | None | None |
| integridad | m05 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.05 | 24.4 |
| integridad | m05 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.048 | 24.5 |
| integridad | m05 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.013 | 13.0 |
| integridad | m05 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.012 | 13.0 |
| integridad | m06 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.054 | 19.4 |
| integridad | m06 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.048 | 19.4 |
| integridad | m06 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.012 | 13.0 |
| integridad | m06 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.011 | 13.0 |
| integridad | m07 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.062 | 19.4 |
| integridad | m07 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.035 | 18.4 |
| integridad | m07 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.006 | 13.0 |
| integridad | m07 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.004 | 13.0 |
| integridad | m08 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.087 | 23.9 |
| integridad | m08 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 1.062 | 23.9 |
| integridad | m08 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.023 | 13.1 |
| integridad | m08 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.734 | 13.0 |
| integridad | m09 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.043 | 22.8 |
| integridad | m09 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.046 | 18.8 |
| integridad | m09 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.01 | 13.0 |
| integridad | m09 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.006 | 13.0 |
| integridad | m10 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.044 | 23.3 |
| integridad | m10 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.038 | 22.8 |
| integridad | m10 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.01 | 13.0 |
| integridad | m10 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.006 | 13.0 |
| integridad | s01 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.077 | 23.9 |
| integridad | s01 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 3.972 | 24.9 |
| integridad | s01 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.034 | 13.1 |
| integridad | s01 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 2.827 | 13.0 |
| integridad | s02 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.051 | 24.3 |
| integridad | s02 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.925 | 24.3 |
| integridad | s02 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.011 | 13.1 |
| integridad | s02 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.615 | 13.0 |
| integridad | s03 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.055 | 23.4 |
| integridad | s03 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.039 | 19.4 |
| integridad | s03 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.011 | 13.0 |
| integridad | s03 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.006 | 13.0 |
| integridad | s04 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.035 | 19.4 |
| integridad | s04 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.032 | 19.4 |
| integridad | s04 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.005 | 13.0 |
| integridad | s04 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.004 | 13.0 |
| integridad | s05 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.034 | 19.4 |
| integridad | s05 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.034 | 19.4 |
| integridad | s05 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.005 | 13.0 |
| integridad | s05 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.005 | 13.0 |
| integridad | s06 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.04 | 19.9 |
| integridad | s06 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.05 | 24.4 |
| integridad | s06 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.006 | 13.2 |
| integridad | s06 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.013 | 13.0 |
| integridad | s07 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.043 | 23.9 |
| integridad | s07 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.04 | 23.9 |
| integridad | s07 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.01 | 13.0 |
| integridad | s07 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.007 | 13.0 |
| integridad | s08 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.046 | 23.4 |
| integridad | s08 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.039 | 23.4 |
| integridad | s08 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.01 | 13.0 |
| integridad | s08 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.009 | 13.0 |
| integridad | s09 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.038 | 23.4 |
| integridad | s09 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.127 | 23.4 |
| integridad | s09 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.007 | 13.0 |
| integridad | s09 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.07 | 13.0 |
| integridad | s10 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.039 | 23.4 |
| integridad | s10 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.039 | 23.4 |
| integridad | s10 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.009 | 13.0 |
| integridad | s10 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.008 | 13.0 |
| integridad | s11 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.04 | 23.4 |
| integridad | s11 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.037 | 23.4 |
| integridad | s11 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.01 | 13.0 |
| integridad | s11 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.007 | 13.0 |
| integridad | s12 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.07 | 23.4 |
| integridad | s12 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.037 | 23.4 |
| integridad | s12 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.029 | 13.0 |
| integridad | s12 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.007 | 13.0 |
| integridad | s13 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.042 | 20.4 |
| integridad | s13 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.043 | 20.4 |
| integridad | s13 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.009 | 13.0 |
| integridad | s13 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.01 | 13.0 |
| integridad | s14 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.047 | 18.4 |
| integridad | s14 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.046 | 18.4 |
| integridad | s14 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.009 | 13.0 |
| integridad | s14 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.008 | 13.0 |
| integridad | s15 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.047 | 17.9 |
| integridad | s15 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.046 | 18.4 |
| integridad | s15 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.01 | 13.0 |
| integridad | s15 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.008 | 13.0 |
| integridad | s16 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.044 | 19.4 |
| integridad | s16 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.045 | 19.4 |
| integridad | s16 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.007 | 13.0 |
| integridad | s16 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.008 | 13.0 |
| integridad | s17 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.048 | 23.4 |
| integridad | s17 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.044 | 23.4 |
| integridad | s17 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.016 | 13.0 |
| integridad | s17 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.011 | 13.0 |
| integridad | s18 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.036 | 23.4 |
| integridad | s18 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.036 | 23.4 |
| integridad | s18 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.007 | 13.0 |
| integridad | s18 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.007 | 13.0 |
| integridad | s19 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.053 | 23.4 |
| integridad | s19 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.052 | 23.4 |
| integridad | s19 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.017 | 13.0 |
| integridad | s19 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.016 | 13.2 |
| integridad | s20 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.042 | 19.9 |
| integridad | s20 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.04 | 19.9 |
| integridad | s20 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.011 | 13.0 |
| integridad | s20 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.01 | 13.0 |
| integridad | s21 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.034 | 19.4 |
| integridad | s21 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.042 | 23.4 |
| integridad | s21 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.005 | 13.0 |
| integridad | s21 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.011 | 13.0 |
| integridad | s22 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.039 | 23.4 |
| integridad | s22 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.041 | 23.4 |
| integridad | s22 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.009 | 13.0 |
| integridad | s22 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.01 | 13.0 |
| integridad | s23 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.035 | 19.4 |
| integridad | s23 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.052 | 23.4 |
| integridad | s23 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.005 | 13.0 |
| integridad | s23 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.012 | 13.0 |
| integridad | s24 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.033 | 19.4 |
| integridad | s24 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.034 | 19.4 |
| integridad | s24 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.005 | 13.0 |
| integridad | s24 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.005 | 13.0 |
| integridad | s25 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.063 | 22.4 |
| integridad | s25 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.037 | 21.9 |
| integridad | s25 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.018 | 13.0 |
| integridad | s25 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.009 | 13.0 |
| integridad | s26 |  | unar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.045 | 23.4 |
| integridad | s26 |  | unar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.034 | 22.9 |
| integridad | s26 |  | unrar | primera | tam_ok=True crc=True decodifica=True | PASS | 0.013 | 13.0 |
| integridad | s26 |  | unrar | ultima | tam_ok=True crc=True decodifica=True | PASS | 0.005 | 13.0 |
| corrupto | m01:RAR4 | truncado_50 | lsar | listar | LISTADO_CON_RC_0 | PASS | 0.036 | 19.4 |
| corrupto | m01:RAR4 | truncado_50 | unar | primera | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.067 | 23.4 |
| corrupto | m01:RAR4 | truncado_50 | unar | ultima | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.067 | 23.4 |
| corrupto | m01:RAR4 | truncado_50 | unrar | primera | ERROR_CLARO | PASS | 0.028 | 13.0 |
| corrupto | m01:RAR4 | truncado_50 | unrar | ultima | ERROR_CLARO | PASS | 0.028 | 13.0 |
| corrupto | m01:RAR4 | truncado_cabecera | lsar | listar | ERROR_SIN_MENSAJE | FAIL | 0.025 | 17.9 |
| corrupto | m01:RAR4 | truncado_cabecera | unar | primera | SIN_PAGINA_QUE_PEDIR | PASS | None | None |
| corrupto | m01:RAR4 | truncado_cabecera | unar | ultima | SIN_PAGINA_QUE_PEDIR | PASS | None | None |
| corrupto | m01:RAR4 | truncado_cabecera | unrar | primera | SIN_PAGINA_QUE_PEDIR | PASS | None | None |
| corrupto | m01:RAR4 | truncado_cabecera | unrar | ultima | SIN_PAGINA_QUE_PEDIR | PASS | None | None |
| corrupto | m01:RAR4 | byte_cabecera | lsar | listar | LISTADO_CON_RC_0 | PASS | 0.03 | 19.4 |
| corrupto | m01:RAR4 | byte_cabecera | unar | primera | SIN_PAGINA_QUE_PEDIR | PASS | None | None |
| corrupto | m01:RAR4 | byte_cabecera | unar | ultima | SIN_PAGINA_QUE_PEDIR | PASS | None | None |
| corrupto | m01:RAR4 | byte_cabecera | unrar | primera | SIN_PAGINA_QUE_PEDIR | PASS | None | None |
| corrupto | m01:RAR4 | byte_cabecera | unrar | ultima | SIN_PAGINA_QUE_PEDIR | PASS | None | None |
| corrupto | m01:RAR4 | byte_medio | lsar | listar | LISTADO_CON_RC_0 | PASS | 0.042 | 19.3 |
| corrupto | m01:RAR4 | byte_medio | unar | primera | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.035 | 22.9 |
| corrupto | m01:RAR4 | byte_medio | unar | ultima | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.035 | 22.9 |
| corrupto | m01:RAR4 | byte_medio | unrar | primera | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.005 | 13.0 |
| corrupto | m01:RAR4 | byte_medio | unrar | ultima | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.005 | 13.0 |
| corrupto | m01:RAR4 | ceros_medio | lsar | listar | LISTADO_CON_RC_0 | PASS | 0.042 | 19.4 |
| corrupto | m01:RAR4 | ceros_medio | unar | primera | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.035 | 22.9 |
| corrupto | m01:RAR4 | ceros_medio | unar | ultima | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.035 | 22.9 |
| corrupto | m01:RAR4 | ceros_medio | unrar | primera | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.005 | 13.0 |
| corrupto | m01:RAR4 | ceros_medio | unrar | ultima | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.005 | 13.0 |
| corrupto | m01:RAR4 | byte_final | lsar | listar | LISTADO_CON_RC_0 | PASS | 0.043 | 19.4 |
| corrupto | m01:RAR4 | byte_final | unar | primera | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.035 | 22.9 |
| corrupto | m01:RAR4 | byte_final | unar | ultima | ERROR_CLARO | PASS | 0.035 | 22.9 |
| corrupto | m01:RAR4 | byte_final | unrar | primera | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.006 | 13.0 |
| corrupto | m01:RAR4 | byte_final | unrar | ultima | ERROR_CLARO | PASS | 0.006 | 13.0 |
| corrupto | m01:RAR4 | byte_en_pagina | lsar | listar | LISTADO_CON_RC_0 | PASS | 0.042 | 19.4 |
| corrupto | m01:RAR4 | byte_en_pagina | unar | ventana | peor: ERROR_CLARO (4 de 5 páginas bien; 1 con error claro; 0 ausentes del listado) | PASS | 0.047 | 23.4 |
| corrupto | m01:RAR4 | byte_en_pagina | unrar | ventana | peor: ERROR_CLARO (4 de 5 páginas bien; 1 con error claro; 0 ausentes del listado) | PASS | 0.014 | 13.0 |
| corrupto | m01:RAR4 | ceros_en_pagina | lsar | listar | LISTADO_CON_RC_0 | PASS | 0.041 | 19.4 |
| corrupto | m01:RAR4 | ceros_en_pagina | unar | ventana | peor: ERROR_CLARO (4 de 5 páginas bien; 1 con error claro; 0 ausentes del listado) | PASS | 0.047 | 23.4 |
| corrupto | m01:RAR4 | ceros_en_pagina | unrar | ventana | peor: ERROR_CLARO (4 de 5 páginas bien; 1 con error claro; 0 ausentes del listado) | PASS | 0.014 | 13.0 |
| corrupto | m06:RAR5 | truncado_50 | lsar | listar | LISTADO_CON_RC_0 | PASS | 0.044 | 19.4 |
| corrupto | m06:RAR5 | truncado_50 | unar | primera | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.031 | 19.4 |
| corrupto | m06:RAR5 | truncado_50 | unar | ultima | ERROR_CLARO | PASS | 0.031 | 19.4 |
| corrupto | m06:RAR5 | truncado_50 | unrar | primera | ERROR_CLARO | PASS | 0.006 | 13.0 |
| corrupto | m06:RAR5 | truncado_50 | unrar | ultima | ERROR_CLARO | PASS | 0.006 | 13.0 |
| corrupto | m06:RAR5 | truncado_cabecera | lsar | listar | ERROR_SIN_MENSAJE | FAIL | 0.026 | 17.9 |
| corrupto | m06:RAR5 | truncado_cabecera | unar | primera | SIN_PAGINA_QUE_PEDIR | PASS | None | None |
| corrupto | m06:RAR5 | truncado_cabecera | unar | ultima | SIN_PAGINA_QUE_PEDIR | PASS | None | None |
| corrupto | m06:RAR5 | truncado_cabecera | unrar | primera | SIN_PAGINA_QUE_PEDIR | PASS | None | None |
| corrupto | m06:RAR5 | truncado_cabecera | unrar | ultima | SIN_PAGINA_QUE_PEDIR | PASS | None | None |
| corrupto | m06:RAR5 | byte_cabecera | lsar | listar | LISTADO_CON_RC_0 | PASS | 0.057 | 18.9 |
| corrupto | m06:RAR5 | byte_cabecera | unar | primera | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.047 | 19.4 |
| corrupto | m06:RAR5 | byte_cabecera | unar | ultima | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.047 | 19.4 |
| corrupto | m06:RAR5 | byte_cabecera | unrar | primera | ERROR_CLARO | PASS | 0.012 | 13.0 |
| corrupto | m06:RAR5 | byte_cabecera | unrar | ultima | ERROR_CLARO | PASS | 0.012 | 13.0 |
| corrupto | m06:RAR5 | byte_medio | lsar | listar | LISTADO_CON_RC_0 | PASS | 0.063 | 19.5 |
| corrupto | m06:RAR5 | byte_medio | unar | primera | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.047 | 19.4 |
| corrupto | m06:RAR5 | byte_medio | unar | ultima | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.047 | 19.4 |
| corrupto | m06:RAR5 | byte_medio | unrar | primera | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.011 | 13.0 |
| corrupto | m06:RAR5 | byte_medio | unrar | ultima | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.011 | 13.0 |
| corrupto | m06:RAR5 | ceros_medio | lsar | listar | LISTADO_CON_RC_0 | PASS | 0.057 | 19.4 |
| corrupto | m06:RAR5 | ceros_medio | unar | primera | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.047 | 19.4 |
| corrupto | m06:RAR5 | ceros_medio | unar | ultima | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.047 | 19.4 |
| corrupto | m06:RAR5 | ceros_medio | unrar | primera | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.012 | 13.0 |
| corrupto | m06:RAR5 | ceros_medio | unrar | ultima | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.012 | 13.0 |
| corrupto | m06:RAR5 | byte_final | lsar | listar | LISTADO_CON_RC_0 | PASS | 0.064 | 19.5 |
| corrupto | m06:RAR5 | byte_final | unar | primera | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.047 | 19.4 |
| corrupto | m06:RAR5 | byte_final | unar | ultima | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.047 | 19.4 |
| corrupto | m06:RAR5 | byte_final | unrar | primera | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.012 | 13.0 |
| corrupto | m06:RAR5 | byte_final | unrar | ultima | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.012 | 13.0 |
| corrupto | m06:RAR5 | byte_en_pagina | lsar | listar | LISTADO_CON_RC_0 | PASS | 0.057 | 19.4 |
| corrupto | m06:RAR5 | byte_en_pagina | unar | ventana | peor: ERROR_CLARO (4 de 5 páginas bien; 1 con error claro; 0 ausentes del listado) | PASS | 0.047 | 19.4 |
| corrupto | m06:RAR5 | byte_en_pagina | unrar | ventana | peor: ERROR_CLARO (4 de 5 páginas bien; 1 con error claro; 0 ausentes del listado) | PASS | 0.012 | 13.0 |
| corrupto | m06:RAR5 | ceros_en_pagina | lsar | listar | LISTADO_CON_RC_0 | PASS | 0.058 | 19.5 |
| corrupto | m06:RAR5 | ceros_en_pagina | unar | ventana | peor: ERROR_CLARO (4 de 5 páginas bien; 1 con error claro; 0 ausentes del listado) | PASS | 0.047 | 19.4 |
| corrupto | m06:RAR5 | ceros_en_pagina | unrar | ventana | peor: ERROR_CLARO (4 de 5 páginas bien; 1 con error claro; 0 ausentes del listado) | PASS | 0.012 | 13.0 |
| corrupto | m08:sólido | truncado_50 | lsar | listar | LISTADO_CON_RC_0 | PASS | 0.742 | 21.3 |
| corrupto | m08:sólido | truncado_50 | unar | primera | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.524 | 24.3 |
| corrupto | m08:sólido | truncado_50 | unar | ultima | ERROR_CLARO | PASS | 0.524 | 24.3 |
| corrupto | m08:sólido | truncado_50 | unrar | primera | ERROR_CLARO | PASS | 0.348 | 13.0 |
| corrupto | m08:sólido | truncado_50 | unrar | ultima | ERROR_CLARO | PASS | 0.348 | 13.0 |
| corrupto | m08:sólido | truncado_cabecera | lsar | listar | ERROR_SIN_MENSAJE | FAIL | 0.035 | 18.4 |
| corrupto | m08:sólido | truncado_cabecera | unar | primera | SIN_PAGINA_QUE_PEDIR | PASS | None | None |
| corrupto | m08:sólido | truncado_cabecera | unar | ultima | SIN_PAGINA_QUE_PEDIR | PASS | None | None |
| corrupto | m08:sólido | truncado_cabecera | unrar | primera | SIN_PAGINA_QUE_PEDIR | PASS | None | None |
| corrupto | m08:sólido | truncado_cabecera | unrar | ultima | SIN_PAGINA_QUE_PEDIR | PASS | None | None |
| corrupto | m08:sólido | byte_cabecera | lsar | listar | LISTADO_CON_RC_0 | PASS | 0.031 | 19.8 |
| corrupto | m08:sólido | byte_cabecera | unar | primera | SIN_PAGINA_QUE_PEDIR | PASS | None | None |
| corrupto | m08:sólido | byte_cabecera | unar | ultima | SIN_PAGINA_QUE_PEDIR | PASS | None | None |
| corrupto | m08:sólido | byte_cabecera | unrar | primera | SIN_PAGINA_QUE_PEDIR | PASS | None | None |
| corrupto | m08:sólido | byte_cabecera | unrar | ultima | SIN_PAGINA_QUE_PEDIR | PASS | None | None |
| corrupto | m08:sólido | byte_medio | lsar | listar | LISTADO_CON_RC_0 | PASS | 2.426 | 22.8 |
| corrupto | m08:sólido | byte_medio | unar | primera | OK_SIN_DANO_EN_LA_PAGINA | PASS | 1.018 | 24.3 |
| corrupto | m08:sólido | byte_medio | unar | ultima | OK_SIN_DANO_EN_LA_PAGINA | PASS | 1.018 | 24.3 |
| corrupto | m08:sólido | byte_medio | unrar | primera | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.69 | 13.1 |
| corrupto | m08:sólido | byte_medio | unrar | ultima | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.69 | 13.1 |
| corrupto | m08:sólido | ceros_medio | lsar | listar | LISTADO_CON_RC_0 | PASS | 2.435 | 22.8 |
| corrupto | m08:sólido | ceros_medio | unar | primera | OK_SIN_DANO_EN_LA_PAGINA | PASS | 1.012 | 24.2 |
| corrupto | m08:sólido | ceros_medio | unar | ultima | ERROR_CLARO | PASS | 1.012 | 24.2 |
| corrupto | m08:sólido | ceros_medio | unrar | primera | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.688 | 13.1 |
| corrupto | m08:sólido | ceros_medio | unrar | ultima | ERROR_CLARO | PASS | 0.688 | 13.1 |
| corrupto | m08:sólido | byte_final | lsar | listar | LISTADO_CON_RC_0 | PASS | 2.446 | 22.8 |
| corrupto | m08:sólido | byte_final | unar | primera | OK_SIN_DANO_EN_LA_PAGINA | PASS | 1.011 | 24.2 |
| corrupto | m08:sólido | byte_final | unar | ultima | OK_SIN_DANO_EN_LA_PAGINA | PASS | 1.011 | 24.2 |
| corrupto | m08:sólido | byte_final | unrar | primera | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.688 | 13.1 |
| corrupto | m08:sólido | byte_final | unrar | ultima | OK_SIN_DANO_EN_LA_PAGINA | PASS | 0.688 | 13.1 |
| topes | m01 |  | lsar | listado | 53 entradas; declarado 34 MiB; la mayor 1727 KiB | PASS | 0.049 | 19.8 |
| topes | m02 |  | lsar | listado | 82 entradas; declarado 20 MiB; la mayor 538 KiB | PASS | 0.075 | 19.8 |
| topes | m03 |  | lsar | listado | 214 entradas; declarado 55 MiB; la mayor 2575 KiB | PASS | 0.15 | 19.8 |
| topes | m04 |  | lsar | listado | 12 entradas; declarado 180 MiB; la mayor 22054 KiB | PASS | 0.042 | 19.8 |
| topes | m05 |  | lsar | listado | 324 entradas; declarado 180 MiB; la mayor 818 KiB | PASS | 0.186 | 20.8 |
| topes | m06 |  | lsar | listado | 132 entradas; declarado 66 MiB; la mayor 611 KiB | PASS | 0.075 | 20.4 |
| topes | m07 |  | lsar | listado | 171 entradas; declarado 55 MiB; la mayor 974 KiB | PASS | 0.121 | 19.8 |
| topes | m08 |  | lsar | listado | 221 entradas; declarado 56 MiB; la mayor 2192 KiB | PASS | 2.452 | 22.8 |
| topes | m09 |  | lsar | listado | 53 entradas; declarado 32 MiB; la mayor 1084 KiB | PASS | 0.059 | 19.3 |
| topes | m10 |  | lsar | listado | 88 entradas; declarado 43 MiB; la mayor 1480 KiB | PASS | 0.075 | 20.3 |
| topes | s01 |  | lsar | listado | 304 entradas; declarado 221 MiB; la mayor 1092 KiB | PASS | 4.691 | 23.8 |
| topes | s02 |  | lsar | listado | 211 entradas; declarado 48 MiB; la mayor 866 KiB | PASS | 2.265 | 21.8 |
| topes | s03 |  | lsar | listado | 53 entradas; declarado 31 MiB; la mayor 1084 KiB | PASS | 0.046 | 19.8 |
| topes | s04 |  | lsar | listado | 33 entradas; declarado 12 MiB; la mayor 548 KiB | PASS | 0.041 | 19.8 |
| topes | s05 |  | lsar | listado | 31 entradas; declarado 12 MiB; la mayor 542 KiB | PASS | 0.041 | 19.9 |
| topes | s06 |  | lsar | listado | 181 entradas; declarado 82 MiB; la mayor 3504 KiB | PASS | 0.088 | 20.3 |
| topes | s07 |  | lsar | listado | 147 entradas; declarado 34 MiB; la mayor 334 KiB | PASS | 0.074 | 19.2 |
| topes | s08 |  | lsar | listado | 23 entradas; declarado 9 MiB; la mayor 496 KiB | PASS | 0.037 | 19.8 |
| topes | s09 |  | lsar | listado | 28 entradas; declarado 5 MiB; la mayor 272 KiB | PASS | 0.07 | 19.8 |
| topes | s10 |  | lsar | listado | 25 entradas; declarado 8 MiB; la mayor 468 KiB | PASS | 0.038 | 19.9 |
| topes | s11 |  | lsar | listado | 23 entradas; declarado 6 MiB; la mayor 424 KiB | PASS | 0.038 | 19.8 |
| topes | s12 |  | lsar | listado | 25 entradas; declarado 10 MiB; la mayor 1835 KiB | PASS | 0.038 | 19.8 |
| topes | s13 |  | lsar | listado | 123 entradas; declarado 84 MiB; la mayor 1194 KiB | PASS | 0.073 | 19.2 |
| topes | s14 |  | lsar | listado | 52 entradas; declarado 123 MiB; la mayor 3120 KiB | PASS | 0.049 | 19.8 |
| topes | s15 |  | lsar | listado | 52 entradas; declarado 123 MiB; la mayor 3120 KiB | PASS | 0.051 | 19.8 |
| topes | s16 |  | lsar | listado | 42 entradas; declarado 90 MiB; la mayor 6499 KiB | PASS | 0.043 | 19.8 |
| topes | s17 |  | lsar | listado | 40 entradas; declarado 53 MiB; la mayor 2621 KiB | PASS | 0.042 | 19.3 |
| topes | s18 |  | lsar | listado | 14 entradas; declarado 6 MiB; la mayor 604 KiB | PASS | 0.034 | 19.8 |
| topes | s19 |  | lsar | listado | 37 entradas; declarado 49 MiB; la mayor 5430 KiB | PASS | 0.042 | 19.8 |
| topes | s20 |  | lsar | listado | 27 entradas; declarado 22 MiB; la mayor 1201 KiB | PASS | 0.039 | 19.9 |
| topes | s21 |  | lsar | listado | 30 entradas; declarado 14 MiB; la mayor 582 KiB | PASS | 0.039 | 19.8 |
| topes | s22 |  | lsar | listado | 41 entradas; declarado 17 MiB; la mayor 870 KiB | PASS | 0.042 | 19.8 |
| topes | s23 |  | lsar | listado | 31 entradas; declarado 14 MiB; la mayor 599 KiB | PASS | 0.04 | 19.8 |
| topes | s24 |  | lsar | listado | 24 entradas; declarado 10 MiB; la mayor 571 KiB | PASS | 0.038 | 19.8 |
| topes | s25 |  | lsar | listado | 46 entradas; declarado 85 MiB; la mayor 3776 KiB | PASS | 0.048 | 19.9 |
| topes | s26 |  | lsar | listado | 22 entradas; declarado 22 MiB; la mayor 2252 KiB | PASS | 0.04 | 19.8 |
| topes | m08 | FSIZE=14611B | unar | ultima | rc=-25; escribió 14611 B (tope 14611); sólido | PASS | 1.076 | 24.2 |
| topes | m08 | AS=96MiB | unar | ultima | rc=-11; sin página; sólido | PASS | 0.041 | 23.7 |
| topes | m08 | timeout=0,01s | unar | ultima | vencida=True; procesos «unar» vivos después: 0 | PASS | 0.013 | 13.0 |
| topes | - | bomba | - | descompresion | NOT RUN (no hay con qué crear un RAR-bomba y no se fabrica uno) | NOT RUN | None | None |
| cifrado | - |  | - | - | NOT RUN (el censo no encontró ningún RAR cifrado entre las muestras) | NOT RUN | None | None |
| comicinfo | - |  | - | - | NOT RUN (ninguna de las 36 muestras RAR trae ComicInfo.xml) | NOT RUN | None | None |

## Paso 7 — lectura en frío (`frio.md`)

Antes de cada muestra: `sync; echo 3 > /proc/sys/vm/drop_caches`. Una repetición. Las copias están en el disco del sistema de la Pi, **no** en el USB de la biblioteca.

| muestra | motor | operación | estado | segundos (1ª lectura, caché vacía) | pico MiB |
|---|---|---|---|---|---|
| m01 | unar | listar | PASS | 0.22 | 20.8 |
| m01 | unar | primera | PASS | 0.052 | 24.9 |
| m01 | unar | ultima | PASS | 0.035 | 24.4 |
| m01 | unrar | listar | PASS | 0.003 | 14.1 |
| m01 | unrar | primera | PASS | 0.015 | 14.1 |
| m01 | unrar | ultima | PASS | 0.004 | 14.6 |
| m02 | unar | listar | PASS | 0.218 | 20.3 |
| m02 | unar | primera | PASS | 0.042 | 24.5 |
| m02 | unar | ultima | PASS | 0.033 | 20.8 |
| m02 | unrar | listar | PASS | 0.003 | 14.1 |
| m02 | unrar | primera | PASS | 0.007 | 14.1 |
| m02 | unrar | ultima | PASS | 0.003 | 14.6 |
| m03 | unar | listar | PASS | 0.251 | 21.3 |
| m03 | unar | primera | PASS | 0.054 | 24.9 |
| m03 | unar | ultima | PASS | 0.045 | 24.9 |
| m03 | unrar | listar | PASS | 0.005 | 14.1 |
| m03 | unrar | primera | PASS | 0.013 | 14.1 |
| m03 | unrar | ultima | PASS | 0.007 | 14.2 |
| m04 | unar | listar | PASS | 0.225 | 20.3 |
| m04 | unrar | listar | PASS | 0.002 | 14.1 |
| m05 | unar | listar | PASS | 0.227 | 21.8 |
| m05 | unar | primera | PASS | 0.054 | 25.4 |
| m05 | unar | ultima | PASS | 0.048 | 25.3 |
| m05 | unrar | listar | PASS | 0.006 | 14.1 |
| m05 | unrar | primera | PASS | 0.013 | 14.6 |
| m05 | unrar | ultima | PASS | 0.01 | 14.6 |
| m06 | unar | listar | PASS | 0.245 | 18.3 |
| m06 | unar | primera | PASS | 0.048 | 20.4 |
| m06 | unar | ultima | PASS | 0.048 | 20.4 |
| m06 | unrar | listar | PASS | 0.002 | 14.1 |
| m06 | unrar | primera | PASS | 0.011 | 14.2 |
| m06 | unrar | ultima | PASS | 0.01 | 14.7 |
| m07 | unar | listar | PASS | 0.254 | 19.3 |
| m07 | unar | primera | PASS | 0.04 | 20.4 |
| m07 | unar | ultima | PASS | 0.034 | 19.9 |
| m07 | unrar | listar | PASS | 0.002 | 14.1 |
| m07 | unrar | primera | PASS | 0.007 | 14.2 |
| m07 | unrar | ultima | PASS | 0.003 | 14.6 |
| m08 | unar | listar | PASS | 0.231 | 21.3 |
| m08 | unar | primera | PASS | 0.054 | 25.3 |
| m08 | unar | ultima | PASS | 1.079 | 25.4 |
| m08 | unrar | listar | PASS | 0.005 | 14.1 |
| m08 | unrar | primera | PASS | 0.012 | 14.2 |
| m08 | unrar | ultima | PASS | 0.686 | 14.1 |
| m09 | unar | listar | PASS | 0.217 | 20.8 |
| m09 | unar | primera | PASS | 0.045 | 24.3 |
| m09 | unar | ultima | PASS | 0.044 | 20.7 |
| m09 | unrar | listar | PASS | 0.003 | 14.1 |
| m09 | unrar | primera | PASS | 0.01 | 14.6 |
| m09 | unrar | ultima | PASS | 0.005 | 14.2 |
| m10 | unar | listar | PASS | 0.221 | 20.9 |
| m10 | unar | primera | PASS | 0.047 | 24.8 |
| m10 | unar | ultima | PASS | 0.036 | 24.3 |
| m10 | unrar | listar | PASS | 0.003 | 14.1 |
| m10 | unrar | primera | PASS | 0.01 | 14.6 |
| m10 | unrar | ultima | PASS | 0.005 | 14.6 |
| m11 | unar | listar | PASS | 0.259 | 20.4 |
| m11 | unar | primera | PASS | 0.045 | 20.8 |
| m11 | unar | ultima | PASS | 0.057 | 20.8 |
| m11 | unrar | listar | FAIL | 0.005 | 14.2 |
| s01 | unar | listar | PASS | 0.229 | 21.8 |
| s01 | unar | primera | PASS | 0.064 | 25.4 |
| s01 | unar | ultima | PASS | 3.924 | 25.8 |
| s01 | unrar | listar | PASS | 0.006 | 14.2 |
| s01 | unrar | primera | PASS | 0.016 | 14.7 |
| s01 | unrar | ultima | PASS | 2.692 | 14.2 |
| s02 | unar | listar | PASS | 0.225 | 21.8 |
| s02 | unar | primera | PASS | 0.053 | 25.4 |
| s02 | unar | ultima | PASS | 0.933 | 25.4 |
| s02 | unrar | listar | PASS | 0.005 | 14.2 |
| s02 | unrar | primera | PASS | 0.011 | 14.1 |
| s02 | unrar | ultima | PASS | 0.611 | 14.1 |
| s03 | unar | listar | PASS | 0.206 | 19.8 |
| s03 | unar | primera | PASS | 0.048 | 24.4 |
| s03 | unar | ultima | PASS | 0.039 | 20.7 |
| s03 | unrar | listar | PASS | 0.003 | 14.2 |
| s03 | unrar | primera | PASS | 0.011 | 14.7 |
| s03 | unrar | ultima | PASS | 0.005 | 14.6 |
| s04 | unar | listar | PASS | 0.217 | 20.8 |
| s04 | unar | primera | PASS | 0.047 | 20.7 |
| s04 | unar | ultima | PASS | 0.039 | 20.9 |
| s04 | unrar | listar | PASS | 0.002 | 14.1 |
| s04 | unrar | primera | PASS | 0.005 | 14.1 |
| s04 | unrar | ultima | PASS | 0.003 | 14.1 |
| s05 | unar | listar | PASS | 0.208 | 20.4 |
| s05 | unar | primera | PASS | 0.037 | 20.7 |
| s05 | unar | ultima | PASS | 0.034 | 20.7 |
| s05 | unrar | listar | PASS | 0.003 | 14.1 |
| s05 | unrar | primera | PASS | 0.005 | 14.2 |
| s05 | unrar | ultima | PASS | 0.003 | 14.1 |
| s06 | unar | listar | PASS | 0.219 | 21.3 |
| s06 | unar | primera | PASS | 0.044 | 21.2 |
| s06 | unar | ultima | PASS | 0.049 | 25.3 |
| s06 | unrar | listar | PASS | 0.004 | 14.1 |
| s06 | unrar | primera | PASS | 0.008 | 14.1 |
| s06 | unrar | ultima | PASS | 0.011 | 14.2 |
| s07 | unar | listar | PASS | 0.212 | 20.4 |
| s07 | unar | primera | PASS | 0.046 | 24.9 |
| s07 | unar | ultima | PASS | 0.038 | 24.9 |
| s07 | unrar | listar | PASS | 0.004 | 14.2 |
| s07 | unrar | primera | PASS | 0.01 | 14.1 |
| s07 | unrar | ultima | PASS | 0.006 | 14.1 |
| s08 | unar | listar | PASS | 0.209 | 20.3 |
| s08 | unar | primera | PASS | 0.045 | 24.3 |
| s08 | unar | ultima | PASS | 0.038 | 24.4 |
| s08 | unrar | listar | PASS | 0.002 | 14.1 |
| s08 | unrar | primera | PASS | 0.01 | 14.6 |
| s08 | unrar | ultima | PASS | 0.009 | 14.1 |
| s09 | unar | listar | PASS | 0.207 | 20.3 |
| s09 | unar | primera | PASS | 0.04 | 24.4 |
| s09 | unar | ultima | PASS | 0.126 | 24.4 |
| s09 | unrar | listar | PASS | 0.002 | 14.1 |
| s09 | unrar | primera | PASS | 0.008 | 14.2 |
| s09 | unrar | ultima | PASS | 0.069 | 14.6 |
| s10 | unar | listar | PASS | 0.207 | 19.9 |
| s10 | unar | primera | PASS | 0.043 | 24.4 |
| s10 | unar | ultima | PASS | 0.038 | 24.4 |
| s10 | unrar | listar | PASS | 0.002 | 14.2 |
| s10 | unrar | primera | PASS | 0.009 | 14.6 |
| s10 | unrar | ultima | PASS | 0.007 | 14.6 |
| s11 | unar | listar | PASS | 0.207 | 20.8 |
| s11 | unar | primera | PASS | 0.044 | 24.4 |
| s11 | unar | ultima | PASS | 0.036 | 24.3 |
| s11 | unrar | listar | PASS | 0.002 | 14.1 |
| s11 | unrar | primera | PASS | 0.01 | 14.1 |
| s11 | unrar | ultima | PASS | 0.006 | 14.1 |
| s12 | unar | listar | PASS | 0.206 | 20.8 |
| s12 | unar | primera | PASS | 0.073 | 24.4 |
| s12 | unar | ultima | PASS | 0.036 | 24.3 |
| s12 | unrar | listar | PASS | 0.002 | 14.1 |
| s12 | unrar | primera | PASS | 0.037 | 14.1 |
| s12 | unrar | ultima | PASS | 0.006 | 14.6 |
| s13 | unar | listar | PASS | 0.218 | 19.4 |
| s13 | unar | primera | PASS | 0.045 | 21.4 |
| s13 | unar | ultima | PASS | 0.042 | 21.4 |
| s13 | unrar | listar | PASS | 0.002 | 14.2 |
| s13 | unrar | primera | PASS | 0.011 | 14.6 |
| s13 | unrar | ultima | PASS | 0.008 | 14.1 |
| s14 | unar | listar | PASS | 0.203 | 19.8 |
| s14 | unar | primera | PASS | 0.05 | 19.9 |
| s14 | unar | ultima | PASS | 0.044 | 19.9 |
| s14 | unrar | listar | PASS | 0.002 | 14.1 |
| s14 | unrar | primera | PASS | 0.01 | 14.2 |
| s14 | unrar | ultima | PASS | 0.007 | 14.6 |
| s15 | unar | listar | PASS | 0.234 | 19.3 |
| s15 | unar | primera | PASS | 0.053 | 19.9 |
| s15 | unar | ultima | PASS | 0.044 | 19.9 |
| s15 | unrar | listar | PASS | 0.002 | 14.1 |
| s15 | unrar | primera | PASS | 0.009 | 14.6 |
| s15 | unrar | ultima | PASS | 0.007 | 14.2 |
| s16 | unar | listar | PASS | 0.208 | 20.8 |
| s16 | unar | primera | PASS | 0.047 | 20.7 |
| s16 | unar | ultima | PASS | 0.043 | 20.7 |
| s16 | unrar | listar | PASS | 0.003 | 14.1 |
| s16 | unrar | primera | PASS | 0.007 | 14.6 |
| s16 | unrar | ultima | PASS | 0.008 | 14.6 |
| s17 | unar | listar | PASS | 0.207 | 19.8 |
| s17 | unar | primera | PASS | 0.052 | 24.3 |
| s17 | unar | ultima | PASS | 0.042 | 24.4 |
| s17 | unrar | listar | PASS | 0.003 | 14.2 |
| s17 | unrar | primera | PASS | 0.015 | 14.1 |
| s17 | unrar | ultima | PASS | 0.01 | 14.1 |
| s18 | unar | listar | PASS | 0.206 | 20.8 |
| s18 | unar | primera | PASS | 0.039 | 23.9 |
| s18 | unar | ultima | PASS | 0.035 | 23.8 |
| s18 | unrar | listar | PASS | 0.002 | 14.2 |
| s18 | unrar | primera | PASS | 0.007 | 14.1 |
| s18 | unrar | ultima | PASS | 0.006 | 14.6 |
| s19 | unar | listar | PASS | 0.21 | 20.3 |
| s19 | unar | primera | PASS | 0.056 | 24.4 |
| s19 | unar | ultima | PASS | 0.05 | 24.4 |
| s19 | unrar | listar | PASS | 0.003 | 14.1 |
| s19 | unrar | primera | PASS | 0.017 | 14.1 |
| s19 | unrar | ultima | PASS | 0.015 | 14.6 |
| s20 | unar | listar | PASS | 0.197 | 19.3 |
| s20 | unar | primera | PASS | 0.045 | 20.8 |
| s20 | unar | ultima | PASS | 0.039 | 20.9 |
| s20 | unrar | listar | PASS | 0.002 | 14.1 |
| s20 | unrar | primera | PASS | 0.012 | 14.7 |
| s20 | unrar | ultima | PASS | 0.01 | 14.1 |
| s21 | unar | listar | PASS | 0.206 | 20.3 |
| s21 | unar | primera | PASS | 0.037 | 20.9 |
| s21 | unar | ultima | PASS | 0.041 | 24.4 |
| s21 | unrar | listar | PASS | 0.002 | 14.1 |
| s21 | unrar | primera | PASS | 0.005 | 14.6 |
| s21 | unrar | ultima | PASS | 0.01 | 14.6 |
| s22 | unar | listar | PASS | 0.207 | 20.8 |
| s22 | unar | primera | PASS | 0.047 | 24.4 |
| s22 | unar | ultima | PASS | 0.043 | 24.3 |
| s22 | unrar | listar | PASS | 0.003 | 14.1 |
| s22 | unrar | primera | PASS | 0.009 | 14.1 |
| s22 | unrar | ultima | PASS | 0.01 | 14.2 |
| s23 | unar | listar | PASS | 0.208 | 20.3 |
| s23 | unar | primera | PASS | 0.037 | 20.9 |
| s23 | unar | ultima | PASS | 0.043 | 24.4 |
| s23 | unrar | listar | PASS | 0.002 | 14.1 |
| s23 | unrar | primera | PASS | 0.005 | 14.2 |
| s23 | unrar | ultima | PASS | 0.011 | 14.6 |
| s24 | unar | listar | PASS | 0.207 | 20.8 |
| s24 | unar | primera | PASS | 0.036 | 20.9 |
| s24 | unar | ultima | PASS | 0.033 | 20.9 |
| s24 | unrar | listar | PASS | 0.002 | 14.1 |
| s24 | unrar | primera | PASS | 0.005 | 14.2 |
| s24 | unrar | ultima | PASS | 0.003 | 14.7 |
| s25 | unar | listar | PASS | 0.2 | 18.8 |
| s25 | unar | primera | PASS | 0.067 | 23.4 |
| s25 | unar | ultima | PASS | 0.036 | 22.9 |
| s25 | unrar | listar | PASS | 0.002 | 14.1 |
| s25 | unrar | primera | PASS | 0.019 | 14.6 |
| s25 | unrar | ultima | PASS | 0.007 | 14.1 |
| s26 | unar | listar | PASS | 0.207 | 20.9 |
| s26 | unar | primera | PASS | 0.048 | 24.4 |
| s26 | unar | ultima | PASS | 0.033 | 23.8 |
| s26 | unrar | listar | PASS | 0.002 | 14.1 |
| s26 | unrar | primera | PASS | 0.013 | 14.1 |
| s26 | unrar | ultima | PASS | 0.004 | 14.2 |


## Paso 8 — imagen con solo `unar` (`solo-unar.txt`)

```
# tamaños (bytes) de docker image inspect
zascarr-zascarr:latest	594261630
zascarr-eval-unar:local	617825475
zascarr-eval-rar:local	637071712
# paquetes añadidos por unar (KiB instalados, paquete)
7077	libgnustep-base1.28
6118	unar
1842	gnustep-base-runtime
738	libavahi-common-data
695	gnustep-base-common
516	libgc1
516	libdbus-1-3
293	libobjc4
262	gnustep-common
223	libwavpack1
110	libavahi-common3
109	libavahi-client3
# total KiB:
18499
```
