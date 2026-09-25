# Aviso Legal — ZascArr

> **Importante:** Este documento no constituye asesoramiento jurídico. El autor del software no es abogado. Si tienes dudas sobre el uso que vas a dar a esta herramienta, consulta con un profesional del derecho de propiedad intelectual en tu jurisdicción.

---

## 1. Propósito del software

ZascArr es una herramienta de **gestión de bibliotecas personales de cómics y tebeos**. Su ámbito de uso legítimo es organizar, enriquecer con metadatos y secuenciar contenido que el usuario posee o tiene derecho a utilizar (ej. escaneos propios de obras de dominio público, adquisiciones digitales legales, o material bajo licencias abiertas).

El software **no distribuye, aloja ni facilita el acceso** a contenido protegido por derechos de autor. No incluye indexadores, fuentes de descarga ni enlaces a repositorios de terceros. Cualquier flujo de descarga que el usuario configure es responsabilidad exclusiva del usuario.

---

## 2. Marco legal aplicable (España / Unión Europea)

### 2.1 Copia privada (art. 31.2 LPI)

El artículo 31.2 del Texto Refundido de la Ley de Propiedad Intelectual establece el límite de copia privada, pero exige que la reproducción se realice **"a partir de una fuente lícita y sin vulnerar las condiciones de acceso"** [web:168].

Esto significa que:
- Descargar contenido protegido desde una fuente no autorizada (ej. redes P2P sin permiso del titular) **no está cubierto** por la excepción de copia privada según la redacción vigente.
- La doctrina académica califica estas descargas como "reproducción ilícita" desde el punto de vista civil [web:175].

### 2.2 Compartir en redes P2P / eD2K

Aunque **no es delito penal** descargar o compartir contenido sin ánimo de lucro (doctrina reiterada de la Fiscalía General del Estado) [web:179][web:173], puede constituir una **infracción civil** por "comunicación pública no autorizada" [web:173].

En la práctica:
- El usuario no enfrenta riesgo penal si no hay ánimo de lucro.
- El usuario puede ser demandado civilmente por los titulares de derechos.
- **ZascArr no controla ni audita** las fuentes que el usuario configure; esa elección es responsabilidad exclusiva del usuario.

### 2.3 Derecho *sui generis* sobre bases de datos (Directiva 96/9/CE)

La Directiva 96/9/CE, transpuesta a la LPI española (arts. 133-137), protege las bases de datos fruto de una inversión sustancial [web:167][web:170].

Implicaciones para ZascArr:
- El código del proyecto es GPL-3.0 (licencia de software).
- Los **metadatos enriquecidos** que el usuario descargue (ej. de Tebeosfera, Whakoom, Comic Vine) están sujetos a las licencias o términos de uso de esas fuentes.
- **No se redistribuye** ninguna base de datos pre-poblada con el software. Todo enriquecimiento es cache local del usuario final, para uso privado.

---

## 3. Lo que este proyecto NO hace

| Afirmación | Realidad |
|---|---|
| ✗ Distribuye contenido con copyright | ✗ Falso. El software no incluye ni un solo CBZ, portada o metadato pre-cargado |
| ✗ Incluye indexadores o fuentes de descarga por defecto | ✗ Falso. No hay configuración que apunte a repositorios de terceros |
| ✗ Anima o instruye sobre cómo obtener contenido ilegal | ✗ Falso. La documentación se limita a la gestión de bibliotecas personales |
| ✗ Garantiza que el uso del software es legal en tu jurisdicción | ✗ Falso. La legalidad depende del uso concreto que tú le des |

---

## 4. Estado legal por componente

| Componente | Estado | Notas |
|---|---|---|
| **Núcleo (orquestador, API, UI)** | ✅ Herramienta neutra | Análogo a Sonarr/Radarr; gestiona bibliotecas, no distribuye contenido [web:166] |
| **Enricher de metadatos (Comic Vine, AniList, Tebeosfera)** | ⚠️ Uso bajo responsabilidad del usuario | Los metadatos se cachean localmente; no se redistribuyen. Respeta `robots.txt` y rate limits conservadores |
| **Scraper de foros (IPB genérico)** | ⚠️ Plugin opcional, deshabilitado por defecto | El usuario aporta la URL del foro; el proyecto no incluye ni recomienda foros concretos |
| **Integración con clientes (Transmission, aMule, Prowlarr)** | ✅ Herramienta neutra | Los clientes son software legítimo; su configuración es responsabilidad del usuario |
| **Caché de portadas (CDN externos)** | ⚠️ Uso local, no redistribución | Las portadas se descargan una vez y se sirven desde disco; no se hotlinkean ni redistribuyen |
| **Documentación y ejemplos** | ✅ Sin referencias a fuentes infractoras | No hay capturas, URLs ni flujos que muestren descarga de contenido con copyright |

---

## 5. Responsabilidades del usuario

Al usar ZascArr, el usuario acepta que:

1. Es **responsable exclusivo** de verificar que posee derecho a usar el contenido que gestiona.
2. Debe **respetar los términos de uso** de las fuentes de metadatos que configure (Tebeosfera, Whakoom, Comic Vine, etc.).
3. Entiende que **compartir contenido protegido** en redes P2P/eD2K puede constituir infracción civil, aunque no sea delito penal [web:179].
4. Acepta que el autor del software **no ofrece garantías** de ningún tipo, conforme a los apartados 15-16 de la licencia GPL-3.0.

---

## 6. Licencia del código (GPL-3.0)

El código fuente de ZascArr se distribuye bajo la licencia **GNU General Public License v3.0** (GPL-3.0) [web:157].

Cláusulas relevantes para este aviso:
- **Sección 15 (Ausencia de garantía):** el programa se distribuye "SIN NINGUNA GARANTÍA", ni siquiera de comerciabilidad o idoneidad para un propósito particular.
- **Sección 16 (Limitación de responsabilidad):** en ningún caso los autores o titulares de derechos serán responsables por daños derivados del uso o imposibilidad de uso del programa.

Estas cláusulas **no excluyen responsabilidades que la ley no permita excluir**, pero se establecen el marco contractual entre el autor y el usuario.

---

## 7. Contenido de terceros y atribución

Algunas fuentes de metadatos usadas por ZascArr tienen licencias propias:

| Fuente | Licencia / Términos | Obligaciones |
|---|---|---|
| **Gran Catálogo de la Historieta (Tebeosfera)** | Uso personal; base de datos protegida por derecho *sui generis* [web:167] | No redistribuir extractos; respetar `robots.txt`; uso local del usuario |
| **Whakoom** | CC-BY-SA para contenido textual; portadas  editoriales [web:133] | Atribución requerida si se redistribuye; portadas no incluidas |
| **Comic Vine** | Términos de uso propios; API con rate limits | Uso conforme a sus términos; no redistribución masiva |
| **AniList** | API pública con términos de uso | Uso conforme a sus términos |
| **Grand Comics Database (GCD)** | CC BY-SA 4.0; API REST pública en `/api/`, anónima, con límite por hora no especificado | Atribución + enlace de vuelta a la ficha de GCD (cumplido: enlace directo en cada resultado de `/ui/descubrir`); sin redistribución masiva, solo búsqueda puntual bajo demanda del coleccionista |

**ZascArr no redistribuye** contenido de estas fuentes. Todo metadato o portada se cachea localmente para el uso privado del usuario final.

---

## 8. Contacto y notificaciones

Si eres titular de derechos y consideras que este proyecto infringe tu propiedad intelectual, por favor contacta antes de emprender acciones legales:

- **Correo:** [tu-email@ejemplo.com]
- **Asunto:** Notificación de propiedad intelectual — ZascArr

El autor está dispuesto a retirar funcionalidades específicas que vulneren derechos de terceros, siempre que la notificación sea fundada y conforme a la ley aplicable.

---

## 9. Jurisdicción aplicable

Este aviso legal se rige por la legislación de **España** y la normativa de la **Unión Europea** en materia de propiedad intelectual y protección de bases de datos.

Cualquier controversia se someterá a los juzgados y tribunales de **[tu ciudad, España]**, salvo que la ley aplicable disponga otra cosa.

---

## 10. Actualizaciones de este documento

Este aviso legal puede actualizarse para reflejar cambios en la legislación o en el ámbito del proyecto. La versión vigente es la publicada en el repositorio oficial en el momento de cada descarga o uso del software.

**Última actualización:** 22 de septiembre de 2026

---

## Referencias legales citadas

- [Art. 31.2 LPI (copia privada)](https://www.boe.es/buscar/doc.php?id=BOE-A-1996-8930) [web:168]
- [Directiva 96/9/CE (bases de datos)](https://eur-lex.europa.eu/legal-content/ES/ALL/?uri=celex:31996L0009) [web:167][web:170]
- [Doctrina Fiscalía: descargas sin ánimo de lucro no son delito](https://computerhoy.20minutos.es/noticias/internet/descargas-animo-lucro-no-son-delito-segun-fiscalia-38663) [web:179]
- [Circular Fiscalía sobre comunicación pública en P2P](https://www.boe.es/buscar/abrir_fiscalia.php?id=FIS-C-2006-00001.pdf) [web:173]
- [Análisis doctrinal: reproducción ilícita en P2P](https://dialnet.unirioja.es/descarga/articulo/4898254.pdf) [web:175]
- [Licencia GPL-3.0 (Sonarr/Radarr/Kavita)](https://github.com/Radarr/Radarr) [web:157]