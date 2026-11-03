## PROYECTO: CARACTERIZACIÓN Y MEJORA DE PRECISIÓN CON DOS MIGHTY MOUSE GPS

Curso: Comunicaciones Satelitales – Laboratorio C

Integrantes: Franco Jesus Cahua Soto – Elisban Huamani Quispe

## 1. Descripción del proyecto

El proyecto propone estudiar el comportamiento de dos receptores GPS Mighty Mouse 3GPS con antena activa y utilizar un VNA (Analizador Vectorial de Redes) para caracterizar su respuesta en frecuencia. Primero se determinarán las características de la antena y su frecuencia de resonancia; posteriormente se evaluarán otras posibles frecuencias resonantes y, finalmente, se analizará el uso de dos receptores GPS para mejorar la precisión mediante una configuración diferencial.

## 2. Objetivo general

Caracterizar el sistema de antena/receptor Mighty Mouse 3GPS, identificar sus frecuencias de resonancia y evaluar experimentalmente cuánto puede mejorar la precisión de posicionamiento al emplear dos unidades en una configuración GPS diferencial.

## 3. Objetivos específicos

- Identificar las características eléctricas de la antena activa del Mighty Mouse 3GPS.

- Medir con el VNA la respuesta de la antena, principalmente S11, impedancia y ROE/VSWR.

- Determinar la frecuencia o frecuencias de resonancia y el ancho de banda útil.

- Comparar las mediciones con la banda de operación GPS y detectar posibles resonancias adicionales.

- Realizar mediciones de posición utilizando un solo Mighty Mouse como referencia experimental.

- Implementar dos Mighty Mouse para estudiar una solución diferencial y comparar el error de posicionamiento.

## 4. Metodología propuesta

| Etapa Actividad principal | Resultado |
| --- | --- |
| 1 Inspección y documentación de los dos Mighty Mouse y sus antenas.Características iniciales. |   |
| 2 Calibración del VNA y conexión de la antena activa según el procedimiento de medición.Sistema listo para medir. |   |
| 3 Barrido de frecuencia y medición de S11, impedancia y VSWR. | Curva de respuesta. |
| 4 Identificación de mínimos de S11 y frecuencias resonantes. | Frecuencias de resonancia. |
| 5 Comparación con las bandas GPS utilizadas por el receptor. | Banda de operación caracterizada. |
| 6 Pruebas de posicionamiento con un receptor y registro de coordenadas.Error/precisión base. |   |
| 7 Pruebas con dos Mighty Mouse: uno como referencia y otro como móvil.Datos diferenciales. |   |
| 8 Comparación estadística de error, estabilidad y repetibilidad. | Mejora experimental obtenida. |

## 5. Caracterización con VNA

El VNA permitirá observar cómo se comporta la antena frente a diferentes frecuencias. Se registrará principalmente S11, que permite evaluar la adaptación de impedancias. Los mínimos de S11 indicarán posibles frecuencias de resonancia. También se obtendrán impedancia compleja y VSWR, con el propósito de identificar la zona de mejor adaptación.

Parámetros a registrar: frecuencia, S11 (dB), impedancia, VSWR, ancho de banda y frecuencia central de cada resonancia.

## 6. GPS diferencial con dos Mighty Mouse

Se instalarán dos receptores en condiciones de observación similares. Uno actuará como estación de referencia en una posición conocida y el segundo como móvil. Las observaciones se registrarán simultáneamente y se analizarán las diferencias de posición para reducir errores comunes, como parte de la evaluación de una solución diferencial.

Comparación: precisión con 1 Mighty Mouse vs. precisión con 2 Mighty Mouse. Se evaluarán error horizontal, dispersión de coordenadas, estabilidad temporal y repetibilidad.

## 7. Resultado esperado


Obtener una caracterización experimental de la antena Mighty Mouse 3GPS, determinar sus frecuencias de resonancia y establecer las condiciones de operación de interés. Finalmente, cuantificar experimentalmente la variación de precisión obtenida al utilizar dos receptores en una configuración diferencial, dejando una metodología reproducible para su uso posterior.

## 8. Equipos principales

- 2 × Mighty Mouse 3GPS con antena activa • 1 × VNA (Analizador Vectorial de Redes) • Computadora para adquisición y procesamiento de datos • Cables y adaptadores RF apropiados

- Fuente/alimentación y elementos de montaje necesarios
