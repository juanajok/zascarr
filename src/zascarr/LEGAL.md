# Aviso Legal — ZascArr

> **Importante:** Este documento no constituye asesoramiento jurídico. El autor del software no es abogado. Si tienes dudas sobre el uso que vas a dar a esta herramienta, consulta con un profesional del derecho de propiedad intelectual en tu jurisdicción.

---

## 1. Propósito del software

ZascArr es una herramienta de **gestión de bibliotecas personales de cómics y tebeos**. Su ámbito de uso legítimo es organizar, enriquecer con metadatos y secuenciar contenido que el usuario posee o tiene derecho a utilizar (ej. escaneos propios de obras de dominio público, adquisiciones digitales legales, o material bajo licencias abiertas).

El software **no distribuye, aloja ni facilita el acceso** a contenido protegido por derechos de autor. No incluye indexadores, fuentes de descarga ni enlaces a repositorios de terceros. Cualquier flujo de descarga que el usuario configure es responsabilidad exclusiva del usuario.

---

## 2. Marco legal aplicable (España / Unión Europea)

### 2.1 Copia privada (art. 31.2 LPI)

El artículo 31.2 del Texto Refundido de la Ley de Propiedad Intelectual establece el límite de copia privada, pero exige que la reproducción se realice **"a partir de una fuente lícita y sin vulnerar las condiciones de acceso"**.

Esto significa que:

- Descargar contenido protegido desde una fuente no autorizada (ej. redes P2P sin permiso del titular) **no está cubierto** por la excepción de copia privada según la redacción vigente.
- La doctrina académica califica estas descargas como "reproducción ilícita" desde el punto de vista civil.

### 2.2 Compartir en redes P2P / eD2K

Aunque **no es delito penal** descargar o compartir contenido sin ánimo de lucro (doctrina reiterada de la Fiscalía General del Estado), puede constituir una **infracción civil** por "comunicación pública no autorizada".

En la práctica:

- El usuario no enfrenta riesgo penal si no hay ánimo de lucro.
- El usuario puede ser demandado civilmente por los titulares de derechos.
- **ZascArr no controla ni audita** las fuentes que el usuario configure; esa elección es responsabilidad exclusiva del usuario.

### 2.3 Derecho *sui generis* sobre bases de datos (Directiva 96/9/CE)

La Directiva 96/9/CE, transpuesta a la LPI española (arts. 133-137), protege las bases de datos fruto de una inversión sustancial.

Implicaciones para ZascArr:

- El código del proyecto es GPL-3.0 (licencia de software).
- Los **metadatos enriquecidos** que la aplicación descargue de las fuentes externas que el usuario active (ej. de Tebeosfera, Whakoom, Comic Vine) están sujetos a las licencias o términos de uso de esas fuentes.
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
| **Núcleo (orquestador, API, UI)** | ✅ Herramienta neutra | Análogo a Sonarr/Radarr; gestiona bibliotecas, no distribuye contenido |
| **Enricher de metadatos (Comic Vine, AniList, Tebeosfera, GCD, Metron, Open Library)** | ⚠️ Opcional, desactivado por defecto; uso bajo responsabilidad del usuario | **Opcional, desactivado por defecto.** Ninguna fuente de metadatos consulta servicios externos hasta que el usuario la activa en Ajustes. Las instalaciones anteriores conservan las fuentes que tuvieran activadas y muestran un aviso en Ajustes hasta que el usuario revise y guarde esa configuración. Los metadatos se cachean localmente; no se redistribuyen. Respeta `robots.txt` y rate limits conservadores |
| **Scraper de foros (IPB genérico)** | ⚠️ Plugin opcional, deshabilitado por defecto; **si la URL es `http://`, las credenciales viajan sin cifrar** | El usuario aporta la URL del foro; el proyecto no incluye ni recomienda foros concretos. El foro puede no ofrecer HTTPS: si usas `http://`, tu usuario y contraseña no van protegidos; no reutilices una contraseña que uses en otro sitio y, si puedes, usa un foro con HTTPS. Ajustes muestra este aviso junto a la tarjeta del foro ([aviso legal](/legal)). |
| **Comic Book Herald (feed RSS)** | ⚠️ Opcional, desactivado por defecto; solo el feed público | Se lee el RSS 2.0 público de WordPress (título, enlace, fecha y categorías); nunca se pide el HTML del artículo, imágenes ni se evade el WAF. Los datos no se redistribuyen: en «Sagas en orden» se muestra el título, la fecha y un enlace de atribución al artículo original (https://www.comicbookherald.com/). |
| **Integración con clientes (Transmission, aMule, Prowlarr)** | ✅ Herramienta neutra | Los clientes son software legítimo; su configuración es responsabilidad del usuario |
| **Caché de portadas (CDN externos)** | ⚠️ Uso local, no redistribución | Las portadas se descargan una vez y se sirven desde disco; no se hotlinkean ni redistribuyen |
| **Documentación y ejemplos** | ✅ Sin referencias a fuentes infractoras | No hay capturas, URLs ni flujos que muestren descarga de contenido con copyright |

---

## 5. Responsabilidades del usuario

Al usar ZascArr, el usuario acepta que:

1. Es **responsable exclusivo** de verificar que posee derecho a usar el contenido que gestiona.
2. Debe **respetar los términos de uso** de las fuentes de metadatos que el usuario active o configure (Tebeosfera, Whakoom, Comic Vine, etc.).
3. Entiende que **compartir contenido protegido** en redes P2P/eD2K puede constituir infracción civil, aunque no sea delito penal.
4. Acepta que el autor del software **no ofrece garantías** de ningún tipo, conforme a los apartados 15-16 de la licencia GPL-3.0.

---

## 6. Licencia del código (GPL-3.0)

El código fuente de ZascArr se distribuye bajo la licencia **GNU General Public License v3.0** (GPL-3.0).

Cláusulas relevantes para este aviso:

- **Sección 15 (Ausencia de garantía):** el programa se distribuye "SIN NINGUNA GARANTÍA", ni siquiera de comerciabilidad o idoneidad para un propósito particular.
- **Sección 16 (Limitación de responsabilidad):** en ningún caso los autores o titulares de derechos serán responsables por daños derivados del uso o imposibilidad de uso del programa.

Estas cláusulas **no excluyen responsabilidades que la ley no permita excluir**, pero se establecen el marco contractual entre el autor y el usuario.

---

## 7. Contenido de terceros y atribución

Algunas fuentes de metadatos usadas por ZascArr tienen licencias propias:

| Fuente | Licencia / Términos | Obligaciones |
|---|---|---|
| **Gran Catálogo de la Historieta (Tebeosfera)** | Uso personal; base de datos protegida por derecho *sui generis* | No redistribuir extractos; respetar `robots.txt`; uso local del usuario |
| **Whakoom** | CC-BY-SA para contenido textual; portadas  editoriales | Atribución requerida si se redistribuye; portadas no incluidas |
| **Comic Vine** | Términos de uso propios; API con rate limits | Uso conforme a sus términos; no redistribución masiva |
| **AniList** | API pública con términos de uso | Uso conforme a sus términos |
| **Grand Comics Database (GCD)** | CC BY-SA 4.0; API REST pública en `/api/`, anónima, con límite por hora no especificado | Atribución + enlace de vuelta a la ficha de GCD (cumplido: enlace directo en cada resultado de `/ui/descubrir`); sin redistribución masiva, solo búsqueda puntual bajo demanda del coleccionista |
| **Metron** | CC BY-SA 4.0; API con token propio y 20 peticiones/min | Atribución visible en la ficha (enlace a la ficha y a la licencia CC BY-SA 4.0). **Sin portadas**: no se descargan ni cachean. Solo se leen datos bibliográficos y la descripción para rellenar huecos por id; sin búsqueda por título ni redistribución de textos |
| **Open Library** | Datos de Internet Archive; licencia vigente en su web | Atribución visible en la ficha (enlace a la obra y a su página de licencias). Solo obras/tomos ya identificados por su id; sin portadas en el relleno ni redistribución de textos |
| **DC Database y Marvel Database (Fandom)** | Texto de la comunidad bajo CC-BY-SA 3.0; las portadas son *fair use* editorial (no cubiertas por esa licencia); se consumen solo por su API oficial `/api.php`, apagadas por defecto y con 1,5 s entre peticiones por wiki | Atribución visible en la UI: enlace al artículo original **y** a la licencia CC-BY-SA 3.0. Las portadas se cachean en el disco del usuario solo para identificar su colección (sin hotlinking ni redistribución) y **no** se etiquetan como CC-BY-SA. Sin redistribución de textos ni de fichas |
| **Comic Book Reading Orders** | Solo **referencias fácticas** de lectura (serie, número y orden); declara `Content-Signal: use=reference`; se lee su HTML público y su `sitemap.xml`, apagada por defecto y con 2,5 s entre peticiones | No se almacena ni redistribuye la prosa del autor ni se usa en IA: solo se guardan el título de la guía, el enlace a la guía y las referencias (serie/número/año/orden). Respetar `robots.txt`; atribución con enlace a la guía original en la vista de la saga. Uso personal del usuario |
| **Continuity Guide** | Solo **referencias fácticas** de lectura; se lee su HTML público y su `sitemap.xml` (nunca `?format=json`, que su `robots.txt` prohíbe), apagada por defecto y con 3,5 s entre peticiones | No se almacena ni redistribuye la prosa ni los títulos de arco entre comillas; solo la referencia y el enlace a la guía. Sin hotlinking ni descarga de sus imágenes. Atribución con enlace a la guía original. Uso personal del usuario |

**ZascArr no redistribuye** contenido de estas fuentes. Todo metadato o portada se cachea localmente para el uso privado del usuario final.

### 7.1 Sinopsis creativa, datos factuales y `comicinfo_propio` (decisión PO 2026-11-10)

ZascArr **no copia la sinopsis creativa de fuentes externas** al `ComicInfo.xml`. El etiquetador solo escribe `Summary` cuando la ficha local del número es de procedencia `manual` o `comicinfo_xml`, o cuando ZascArr ya escribió antes ese `Summary` (marcador `comicinfo_propio` en `File.metadata_`). Con Comic Vine, AniList, Tebeosfera, GCD o procedencia `None`, `Summary` queda «sin dato» y se **conserva el XML existente**. La procedencia que decide es la del número (`Issue.metadata_source`), no la del archivo (`File.metadata_source`).

El resto de campos del ComicInfo (año, editorial, créditos, género, páginas) son **datos factuales de la ficha local**. Si esa ficha los obtuvo de una fuente, se escribe el dato factual, no la sinopsis creativa; ZascArr no atribuye ni garantiza que el usuario pueda redistribuir esos datos. GCD es CC BY-SA 4.0: si se usa como fuente, la atribución/enlace corresponde a quien lo configure.

El marcador `comicinfo_propio` **no es una prueba de autoría jurídica**: solo indica que ZascArr escribió ese campo en una pasada anterior y puede actualizarlo sin tratar el valor actual como texto manual ajeno. Si la persona comparte el archivo, sigue siendo su decisión y su responsabilidad; ZascArr no controla los programas P2P ni la licitud de la compartición.

Esta decisión sustituye a la parte de CNV5-4 que iba a aplicar datos de fuentes al archivo. No se crea una base de datos pre-poblada ni se redistribuyen metadatos de terceros; la caché local del usuario no cambia.

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

- [Art. 31.2 LPI (copia privada)](https://www.boe.es/buscar/doc.php?id=BOE-A-1996-8930)
- [Directiva 96/9/CE (bases de datos)](https://eur-lex.europa.eu/legal-content/ES/ALL/?uri=celex:31996L0009)
- [Doctrina Fiscalía: descargas sin ánimo de lucro no son delito](https://computerhoy.20minutos.es/noticias/internet/descargas-animo-lucro-no-son-delito-segun-fiscalia-38663)
- [Circular Fiscalía sobre comunicación pública en P2P](https://www.boe.es/buscar/abrir_fiscalia.php?id=FIS-C-2006-00001.pdf)
- [Análisis doctrinal: reproducción ilícita en P2P](https://dialnet.unirioja.es/descarga/articulo/4898254.pdf)
- [Licencia GPL-3.0 (Sonarr/Radarr/Kavita)](https://github.com/Radarr/Radarr)