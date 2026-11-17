# Manual de Apetito de Riesgo y Políticas de Portafolio — Tarjetas de Crédito Banamex

## 1. Umbrales Máximos de Deterioro y Severidad
* **Límite de Pérdida Neta sobre Saldo (`NCL_RATE_PCT = NCLAMTS / ENRAMTS`):** Ningún segmento o cohorte madura (`MOB >= 6`) debe superar el **15.0%** de pérdida neta sobre saldo promedio. Cualquier segmento entre **12.0% y 15.0%** entra en estado de **Vigilancia Preventiva**; por encima de **15.0%** se clasifica como **Fuera de Apetito de Riesgo** y requiere dictamen de restricción o suspensión.
* **Límite de Morosidad Temprana (`OVER30_RATE_PCT = OVER30AMTS / ENRAMTS`):** Ningún segmento a partir de `MOB 6` debe superar el **25.0%** de saldo vencido a más de 30 días.

## 2. Reglas de Rentabilidad y Crecimiento (`NET_ROA_PCT` y `YIELD_RATE_PCT`)
* **Cuadrante Expandir:** Segmentos con `MOB >= 12`, `NCL_RATE_PCT <= 10.0%` y `NET_ROA_PCT > 0.0%` positivo sostenido. Elegibles para incremento de líneas de crédito y campañas de originación.
* **Cuadrante Restringir Línea:** Segmentos con `NCL_RATE_PCT` entre `10.0%` y `15.0%`, o `NET_ROA_PCT` cercano a cero (`-2.0%` a `0.0%`). Se recomienda reducir línea promedio en nuevas originaciones y endurecer corte de score.
* **Cuadrante Suspender Originación:** Segmentos con `NCL_RATE_PCT > 15.0%` o `OVER30_RATE_PCT > 25.0%` en `MOB >= 6`, especialmente si presentan utilidad neta negativa (`NET_PROFIT < 0`).

## 3. Gobernanza por Canal, Edad y Score
* **Segmentos Jóvenes (`01| Young < 25` y `02| Young 25-30`):** Requieren monitoreo estricto de `EXPENSES_ACQ` en `MOB = 0` frente a la recuperación de margen acumulado en `MOB 6` a `MOB 12`. Si el punto de equilibrio (*payback*) no se alcanza antes de `MOB 18`, debe revisarse el canal de colocación.
* **Canales de Alto Volumen (`Aeropuerto`, `Branch`, `F2F`):** Deben compararse en igualdad de madurez (`MOB >= 6`) y nunca mezclando escalas de score distintas (`Recalibration / r.Reca champ` vs. `DARIA 1.6 / 2.0`).
* **Eficiencia de Cobranza (`RECOVERY_RATE_PCT = RECOVERYAMTS / GCLAMTS`):** Una tasa de recuperación inferior al **40.0%** en segmentos con alta pérdida bruta (`GCLAMTS`) indica debilidad en estrategia de cobranza temprana y debe escalarse al Comité de Riesgo.
