# Fuentes de dominio público y plan de fixtures (1895–1930)

> **Aviso:** este documento **no es asesoramiento jurídico**. Ordena fuentes, fechas y
> comprobaciones para que el PO y quien revise puedan decidir con evidencia. Los puntos
> marcados **«requiere revisión»** necesitan abogado o, como mínimo, una segunda lectura
> con la ley delante. Nada de lo que aquí se propone se ha aprobado todavía.

- **Fecha:** 2026-11-16 (Europe/Madrid).
- **Punto de partida:** `origin/main` = `499e165d98ac35792756a51d8c023918b679482a`
  (merge de #889). Worktree `.squad/wt-pd`, rama `docs/fixtures-dominio-publico`.
- **Rol:** SCOUT/legal.
- **Petición del PO:** fixtures y demos para probar importación/paquetes y capturas con
  personajes de dominio público (Yellow Kid 1895, Krazy Kat 1913, Little Nemo 1905), sin
  meter escaneos con derechos dudosos en el repo.
- **Ámbito:** EE. UU., España/UE y marca registrada; fuentes de scans; plan de fixtures;
  etiquetado de demos; checklist y riesgos.
- **Fecha de acceso a todas las fuentes citadas:** 2026-11-16.
- **Caducidad:** 2027-01-15, o antes si cambia la ley, el año de dominio público o el
  contrato de las fuentes. La regla de EE. UU. cambia cada 1 de enero.

**Convención de resultados:** **PASS** = comprobado en vivo con la URL citada y el dato
coincide; **FAIL** = se intentó y el resultado no sirve; **NOT RUN** = no se ha podido o
no se ha querido comprobar (registro, navegador, términos tras un WAF) y **por tanto no
sostiene ninguna decisión**.

---

## 1. Resumen de decisiones propuestas

| # | Decisión propuesta | Estado |
|---|---|---|
| D1 | Fixtures **sintéticos generados** (Pillow), no escaneos, para tests y capturas. | Propuesta |
| D2 | Conjunto inicial: **Yellow Kid (1895)**, **Little Nemo (1905)** y **Krazy Kat (1913)**, 2 páginas sintéticas cada uno. | Propuesta |
| D3 | **Krazy Kat** queda condicionado a una comprobación de marca (Hearst/King Features). Sustituto si falla: **Dream of the Rarebit Fiend (1904)**. | Requiere revisión |
| D4 | Escaneos reales: **solo enlace**, nunca binario en el repo. Excepción futura: 1 página, ≤1,5 MB, con procedencia, hash y `ATRIBUCION.md`. | Propuesta |
| D5 | Biblioteca de ejemplo **etiquetada** (`(ejemplo)` en el título, `LEEME.txt`, nota en ComicInfo y pie en las capturas). | Propuesta |
| D6 | Excluir **Popeye** (marca de Hearst y versiones posteriores), **Katzenjammer Kids** y **Mutt and Jeff** (aún protegidos en España). | Propuesta |

---

## 2. Marco temporal en EE. UU.

### 2.1 La regla, en corto

La regla operativa es la de la tabla de Cornell, actualizada a 1 de enero de 2026: **toda
obra publicada en EE. UU. antes de 1931 está en dominio público** («Before 1931 — None — In
the public domain due to copyright expiration»,
[Copyright Term and the Public Domain](https://guides.library.cornell.edu/copyright/publicdomain)).
Cornell recoge casos especiales (obras extranjeras, la doctrina *Twin Books* en el 9.º
circuito); no afectan a este corpus, publicado en EE. UU. y en inglés. Para las obras que
todavía dependen del cómputo (publicadas entre 1931 y 1977), el plazo es de **95 años desde
la publicación** cuando hubo renovación o cuando son de 1964 en adelante; y todos los plazos
corren hasta el **31 de diciembre** del año en que vencen (17 U.S.C. §305). El Copyright
Office explica que, para obras publicadas antes de 1978, el plazo depende de la fecha y de
las formalidades, y remite al capítulo 3
([FAQ de duración](https://www.copyright.gov/help/faq/faq-duration.html)).

De ahí, para nuestras fechas:

- Publicada en **1930** → vence el **31-12-2025** → **dominio público el 01-01-2026**.
- Publicada en **1931** → vence el **31-12-2026** → dominio público el **01-01-2027**.

Duke lo formula así: «On January 1, 2026, thousands of copyrighted works from 1930 enter
the US public domain» ([Public Domain Day 2026](https://cspd.law.duke.edu/publicdomainday/2026)).

> **Matiz que sí importa:** la regla de «≤1930» vale para **obras publicadas**. Un dibujo
> inédito, o una página sin fecha de publicación acreditada, no entra por esta puerta.
> Tampoco entra una **edición moderna** (maquetación, restauración, color) de una obra de
> 1905: el texto/imagen original puede ser de dominio público y la edición no.

### 2.2 Estado de las obras del encargo

| Obra / personaje | Primera publicación | Autor | ¿≤1930? | Estado EE. UU. (2026-11-16) | Evidencia |
|---|---|---|---|---|---|
| The Yellow Kid (*Hogan's Alley*) | 1895 (primera plana en color, 05-05-1895) | Richard F. Outcault | Sí | **Dominio público** | Cornell «before 1931»; [Wikipedia](https://en.wikipedia.org/wiki/The_Yellow_Kid) |
| Little Nemo in Slumberland | 1905-10-15 | Winsor McCay | Sí | **Dominio público** | Cornell; [Wikipedia](https://en.wikipedia.org/wiki/Little_Nemo) |
| Krazy Kat | 1913-10-28 | George Herriman | Sí | **Dominio público** | Cornell; [Wikipedia](https://en.wikipedia.org/wiki/Krazy_Kat) |
| Dream of the Rarebit Fiend | 1904-09-10 | Winsor McCay | Sí | **Dominio público** | Cornell; Wikidata `Q973014` |
| The Katzenjammer Kids | 1897-12-12 | Rudolph Dirks | Sí | **Dominio público** | Cornell; Wikidata `Q1315973` |
| Mutt and Jeff | 1907 | Bud Fisher | Sí | **Dominio público** | Cornell; Wikidata `Q1955932` |
| Popeye (*Thimble Theatre*) | 1929 | E. C. Segar | Sí | **Dominio público solo la versión de 1929** | [Duke 2025](https://cspd.law.duke.edu/publicdomainday/2025) |

**Cuidado con las fechas de «primera aparición»:** el personaje puede ser anterior a la
tira. Krazy Kat aparece como secundario en *The Dingbat Family* (1910) y el Yellow Kid
tiene un prototipo de 1894 en *Truth*. Para el análisis de copyright manda la **fecha de
publicación de la obra concreta** que se vaya a usar, no la del personaje.

**URAA:** no afecta a este corpus. La restauración de derechos de la Uruguay Round
Agreements Act afecta a obras extranjeras publicadas entre 1931 y 1977 que habían caído
en el dominio público en EE. UU. por incumplir formalidades; nuestras obras son
estadounidenses y anteriores a 1931. Se deja anotado para que nadie lo aplique por
analogía a una obra de 1935.

---

## 3. Marco temporal en España / UE

### 3.1 La regla, en corto

- **Art. 26 TRLPI:** los derechos de explotación duran **la vida del autor y 70 años**
  después de su muerte o declaración de fallecimiento.
- **Art. 30 TRLPI:** los plazos se computan **desde el 1 de enero del año siguiente** al
  de la muerte.
- **Disposición transitoria cuarta TRLPI:** para autores **fallecidos antes del 7 de
  diciembre de 1987**, la duración es la de la **Ley de 10 de enero de 1879**, que fijó
  **80 años** tras la muerte (art. 6 de la ley de 1879).

Textos comprobados en el BOE consolidado (consulta vía API de legislación consolidada):
[TRLPI, BOE-A-1996-8930](https://www.boe.es/buscar/act.php?id=BOE-A-1996-8930).
La DT4 remite literalmente a la ley de 1879; el plazo de 80 años de esa ley y su lectura
corriente están recogidos en la síntesis de
[«Derecho de autor en España»](https://es.wikipedia.org/wiki/Derecho_de_autor_en_Espa%C3%B1a)
(fuente secundaria: **PASS con reserva**, no se ha consultado el texto de 1879 en el BOE).

> **Consecuencia práctica:** el plazo español es **más largo** que el estadounidense para
> estos autores. Que una obra sea de dominio público en EE. UU. **no** la hace libre en
> España. Como el repo y el producto viven en España, se aplica el criterio más estricto:
> **solo entran obras de dominio público en ambos sistemas**.

### 3.2 Estado por autor

| Autor | Fallecimiento | 70 años (art. 26) | 80 años (DT4) | Estado España (2026-11-16) | Dominio público desde |
|---|---|---|---|---|---|
| Richard F. Outcault | 1928-09-25 | fin 1998 | fin 2008 | **Dominio público** | 2009-01-01 |
| Winsor McCay | 1934-07-26 | fin 2004 | fin 2014 | **Dominio público** | 2015-01-01 |
| George Herriman | 1944-04-25 | fin 2014 | fin 2024 | **Dominio público** | 2025-01-01 |
| E. C. Segar | 1938-10-13 | fin 2008 | fin 2018 | **Dominio público** (tiras de Segar) | 2019-01-01 |
| Bud Fisher | 1954-09-07 | fin 2024 | fin 2034 | **Protegido** | 2035-01-01 |
| Rudolph Dirks | 1968-04-20 | fin 2038 | fin 2048 | **Protegido** | 2049-01-01 |

Fechas de fallecimiento: Wikidata (`Q737068`, `Q207960`, `Q453440`, `Q452745`,
`Q1000471`, `Q68586`). **PASS como fuente secundaria**; para un ítem que vaya a entrar
en el repo, la fecha se contrasta además con la fuente del scan.

**Lo que esto implica para las alternativas del encargo:**

| Candidata | EE. UU. | España/UE | Veredicto |
|---|---|---|---|
| **Dream of the Rarebit Fiend** (1904, McCay) | DP | DP (2015) | **Apta**; sin personaje fijo, buena para páginas de relleno |
| **The Katzenjammer Kids** (1897, Dirks) | DP | **No** (2049) | Solo EE. UU.; **no apta** para repo/demos en España |
| **Mutt and Jeff** (1907, Fisher) | DP | **No** (2035) | Solo EE. UU.; **no apta** |
| **Popeye** (1929, Segar) | DP (versión 1929) | DP (tiras de Segar) | **No recomendada**: marca de Hearst y versiones posteriores protegidas |

---

## 4. Marca registrada: personaje ≠ copyright de una obra

El copyright de una tira de 1913 y la marca de un personaje son derechos **distintos**,
con titulares, plazos y alcances distintos. Duke lo explica con claridad:

> «Copyrights cover creative works and prevent people from copying and adapting them
> without permission […]. Trademarks cover words, logos, images, and other signifiers that
> serve as brands identifying the source of a product. […] You can use a character's name
> or image in a new creative work so long as consumers are not likely to be misled into
> thinking that your work is produced or sponsored by the trademark holder.»
> — [Public Domain Day 2025](https://cspd.law.duke.edu/publicdomainday/2025)

Y el caso concreto que nos afecta:

> «Hearst Holdings owns the trademark rights to the word "Popeye" for products such as
> cartoon strips, "costumed figures" for musical plays and theatrical shows, amusement
> parks, advertising services, and clothing.»
> — [Public Domain Day 2025](https://cspd.law.duke.edu/publicdomainday/2025)

Para 2026, la propia Duke recuerda que «trademark rights still cover the character names
and designs when they are used on merchandise as brand signifiers»
([Public Domain Day 2026](https://cspd.law.duke.edu/publicdomainday/2026)).

### 4.1 Lectura para ZascArr

- **Uso interno de test y documentación:** usar el nombre para *referirse* a la obra
  («inspirado en *The Yellow Kid*, 1895») es uso descriptivo/nominativo. Riesgo bajo si
  hay atribución y no se sugiere patrocinio.
- **Uso como marca del producto:** poner «ZascArr Yellow Kid Edition», un logo, o usar el
  personaje en la portada del repo/tienda **no** es lo mismo. Ahí la marca sí muerde.
- **Popeye:** queda **fuera** del plan. Aunque las tiras de 1929 sean de dominio público,
  la marca de Hearst sigue viva y las versiones posteriores (incluida la fuerza de las
  espinacas, 1931) tienen su propio análisis.
- **Krazy Kat:** sindicada por **King Features** (Hearst). No se ha verificado un registro
  de marca concreto. **Requiere revisión** antes de usar el nombre fuera del test; si no
  hay certeza, se sustituye por *Dream of the Rarebit Fiend*.
- **Yellow Kid y Little Nemo:** no se ha verificado registro de marca. Se usan solo como
  referencia descriptiva en fixtures y capturas; **requiere revisión** si algún día se
  usan en marketing.

Herramientas de comprobación (no ejecutadas en esta pasada): [TSDR/USPTO](https://tsdr.uspto.gov/)
y [EUIPO](https://euipo.europa.eu/). Anotar número, titular, clases y estado en la ficha
del ítem si se decide usar el nombre en superficie pública.

---

## 5. Fuentes de scans y reutilización

Ninguna fuente es un sello de calidad: **la licencia se verifica ítem a ítem**. Un sitio
puede ser impecable y contener un scan de una edición moderna; un ítem puede tener
`licenseurl` de dominio público y ser, en realidad, la digitalización de un libro de 2017.

| Fuente | Licencia / términos | Cómo se verifica el ítem | Formatos y resolución | ¿Redistribuir? | Estado |
|---|---|---|---|---|---|
| **Internet Archive** | Aviso de la casa: no garantiza el estado de copyright de los ítems y el uso es «at your own risk» ([Rights](https://help.archive.org/help/rights/)); la página de términos devolvió vacío | API de metadatos: `licenseurl`, `rights`, `collection`, `possible-copyright-status`, `date`. `inlibrary` = préstamo, no redistribuir | PDF, JP2 ZIP, ZIP de imágenes, JPEG; ejemplos de 70 MB a 321 MB | Solo si `licenseurl` es PD Mark/CC0 **y** publicación ≤1930 **y** no es edición moderna; si no, **enlace** | **PASS** (API) / **FAIL** (`/about/terms.php` devolvió vacío) |
| **Wikimedia Commons** | Solo licencias libres; `PD-US-expired` exige además que la obra esté en DP en el país de origen ([Commons:Licensing](https://commons.wikimedia.org/wiki/Commons:Licensing)) | Página del fichero (wikitexto) + API `imageinfo` con `extmetadata`; comprobar que hay plantilla `PD-old-70`/`PD-old-80`, no solo `PD-US` | JPEG/PNG; resolución muy variable (842×72 en un caso, 1740×2376 en otro) | Sí, con aviso de licencia y atribución; conservar el historial | **PASS** |
| **Library of Congress / Chronicling America** | Declaración de derechos por ítem («no known restrictions» es lo habitual, no universal) | Ficha del ítem y su campo de derechos; API JSON de `loc.gov` | JP2/PDF, alta resolución | Solo tras leer la declaración del ítem; si no, enlace | **NOT RUN**: `loc.gov` y `chroniclingamerica.loc.gov` devolvieron **403** (Cloudflare) desde esta red |
| **Comic Book Plus** | Archivo voluntario de cómics que se presentan como de dominio público; **términos no accesibles** | Página del ítem: fecha, editorial, páginas. No muestra licencia por ítem | Lectura online; el listado da nº de páginas | **Enlace**, salvo verificación manual con licencia explícita | **PASS** (listado) / **NOT RUN** (términos: 403/406) |
| **Digital Comic Museum** | Archivo de dominio público con registro gratuito; **no verificado** | Ficha del ítem (requiere cuenta) | No verificado | **Enlace**; no copiar | **NOT RUN**: **403** (Cloudflare) en todas las rutas |
| **Comic Strip Library** | Sin licencia visible; es una SPA que no sirve contenido sin JS | No hay ficha de licencia; muchas fichas de Commons la citan como *fuente* | No verificado | **Enlace**; no copiar | **NOT RUN** (solo se obtuvo el título de la página) |

### 5.1 Ejemplos reales que ilustran el método

**Internet Archive — Little Nemo, tres estados distintos (y un cuarto sin licencia):**

| Ítem | Qué enseña | Datos |
|---|---|---|
| `LittleNemo1905-1914ByWinsorMccay` | Declara **PD Mark 1.0** | `licenseurl: http://creativecommons.org/publicdomain/mark/1.0/`; PDF 70,7 MB, ZIP 295 MB, JP2 ZIP 321 MB → **demasiado grande para el repo aunque sea PD** |
| `littlenemoinslum0000wins` | Está en **préstamo** (`inlibrary`), sin licencia | No redistribuible; es el caso típico de «accesible gratis ≠ dominio público» |
| `winsor-mc-cay-the-complete-little-nemo-1905-1909-c-2c-taschen-2017-empire-gca` | **Edición moderna** (Taschen, 2017) escaneada | Aunque el cómic de 1905 sea DP, la edición/maquetación de 2017 no lo es; **excluir** |
| `TheYellowKid189703` | Sin licencia declarada | Sin `licenseurl` ni `rights`; JPEG de 95 KB → **enlace** |

Comprobación reproducible:

```bash
curl -sS "https://archive.org/metadata/LittleNemo1905-1914ByWinsorMccay" \
  | python3 -c "import sys,json; m=json.load(sys.stdin)['metadata']; \
print({k:m.get(k) for k in ('title','date','licenseurl','rights','collection')})"
```

**Wikimedia Commons — la etiqueta no siempre está completa:**

| Fichero | Licencia declarada | Resolución | Observación |
|---|---|---|---|
| `File:Krazy Kat, October 28, 1913.png` | `{{PD-US-expired}}` + `{{PD-old-70}}` | 842×72 | Es un **recorte**, no una página; inservible para una demo |
| `File:Little Nemo in Slumberland (1905-10-22).jpeg` | Solo `{{PD-US}}` | 1740×2376 | La descripción dice «26 July 1908» y el campo `date` dice 1905-10-22: **metadatos incoherentes**; para España falta la etiqueta `PD-old` |
| `File:Yellow Kid 1896-3-15.jpg` | Solo `{{PD-US}}` | 1152×811 | Misma advertencia: `PD-US` no resuelve el plazo español |

Moraleja: en Commons hay que mirar **las plantillas del wikitexto**, no solo el resumen
«Public domain» que pinta la interfaz.

### 5.2 Regla de oro sobre escaneos

Un escaneo **no** es la obra: es una reproducción. En EE. UU. la doctrina dominante
(*Bridgeman v. Corel*, S.D.N.Y. 1999 — **requiere revisión**, no es jurisprudencia
vinculante en todos los circuitos) sostiene que la fotografía fiel de una obra plana en
dominio público no genera copyright nuevo; en España, en cambio, las **meras fotografías**
tienen protección de **25 años** (art. 128 TRLPI); y la edición de una obra no protegida
puede tener otros **25 años** si se individualiza por su composición tipográfica o
presentación (arts. 129.2 y 130.2 TRLPI). Es
decir: un scan reciente de una página de 1905 puede estar protegido en España por la mera
fotografía aunque la página no lo esté. Por eso el plan por defecto es **no meter scans**
y, si se mete alguno, que venga con licencia explícita de reutilización (Commons, PD Mark)
y no de un particular que solo lo subió.

---

## 6. Plan de fixtures propuesto

### 6.1 (a) Fixtures sintéticos generados (opción recomendada)

**Qué son:** páginas dibujadas por código con Pillow, con texto propio y una composición
genérica (rejilla de viñetas), **sin calcar ni copiar** ninguna página original. La
atribución es de inspiración, no de reproducción.

**Por qué:**

- Deterministas y pequeños (decenas de KB), sin red.
- Sin derechos de terceros: solo el código del generador, que es GPL-3.0 como el repo.
- Permiten probar lo que de verdad nos importa: CBZ, ZIP de paquetes, extracción de
  portada, ComicInfo, nombres de fichero, duplicados y capturas.

**Especificación propuesta:**

| Aspecto | Valor |
|---|---|
| Generador | `scripts/generar_fixtures_dp.py` (Pillow, ya es dependencia; sin red) |
| Salida | Los tests generan en `tmp_path`; el árbol versionado (opcional, solo si hace falta un snapshot) vive en `tests/fixtures/dominio-publico/`; para demos, `demo/zascarr-biblioteca-ejemplo/` (ignorada por git) |
| Página | 900×1350 px, PNG, paleta plana de 8 colores, marco grueso, rejilla 3×4 |
| Página 1 | Cabecera «PÁGINA DE EJEMPLO — NO ES UN ESCANEO»; título «inspirado en *The Yellow Kid* (1895)»; número de página |
| Página 2 | Cuatro viñetas con formas simples y bocadillos con texto de relleno |
| Pie | «CC0-1.0 · generado 2026-11-16 · ZascArr» |
| Tipografía | DejaVu Sans (libre) si está en la imagen; si no, la fuente por defecto de Pillow con tamaño explícito; **ninguna** fuente de cómic ni comercial |
| Metadatos | `ComicInfo.xml` con `Series`, `Number`, `Year`, `PageCount`, `Notes` = «Fixture sintético; no es un escaneo» |
| Tamaño | PNG ≤ 60 KB; CBZ ≤ 150 KB; ZIP de 3 CBZ ≤ 500 KB |

**Determinismo:** fijar texto, colores y orden; **no** fijar hashes de píxel entre
versiones de Pillow. Los tests comprueban estructura (2 páginas, 900×1350, ComicInfo
legible, portada extraíble), no el byte exacto de la imagen.

**Nombres de fichero propuestos (ASCII, minúsculas, guiones).** Este árbol es el del snapshot opcional; en el caso normal, los tests lo generan en `tmp_path` con los mismos nombres:

```
tests/fixtures/dominio-publico/
  LEEME.md
  yellow-kid-1895/
    yk-1895-p1.png
    yk-1895-p2.png
    yellow-kid-1895-ejemplo.cbz
  little-nemo-1905/
    ln-1905-p1.png
    ln-1905-p2.png
    little-nemo-1905-ejemplo.cbz
  krazy-kat-1913/
    kk-1913-p1.png
    kk-1913-p2.png
    krazy-kat-1913-ejemplo.cbz
  paquete-ejemplo-3-cbz.zip   # contiene los tres .cbz
```

**Qué prueban estos fixtures:**

1. Importación de un `.cbz` suelto y de un `.zip` con tres `.cbz`.
2. Extracción de portada (página 1) y de metadatos `ComicInfo.xml`.
3. Detección de duplicado por hash (dos copias del mismo `.cbz`).
4. Nombres con año y sufijo `(ejemplo)` sin romper el parser.
5. Capturas de la biblioteca de ejemplo con datos 100 % sintéticos.

### 6.2 (b) Si se usan scans de dominio público

Solo si el PO lo pide expresamente y hay una revisión que lo firme. Límites:

| Campo | Límite / regla |
|---|---|
| Número de páginas | 1 por personaje (máximo 2 por todo el repo) |
| Tamaño | ≤ 1,5 MB por imagen; lado largo ≤ 1600 px; JPEG calidad 82 |
| Edición | Solo la página original; **prohibida** una edición moderna, restaurada o coloreada |
| Procedencia | URL exacta, fecha de descarga, autor, fecha de publicación, país, licencia |
| Hash | SHA-256 en `SHA256SUMS` y en la ficha del ítem |
| Atribución | `ATRIBUCION.md` con tabla: obra, autor, fuente, licencia, URL, fecha, hash |
| Aprobación | Dos pares de ojos: SCOUT/legal + maintainer; sin procedencia, licencia y hash completos, no entra |
| Ubicación | `tests/fixtures/dominio-publico/escaneos/`, nunca en `docs/` ni en la raíz |

### 6.3 (c) Lo que **no** se mete en el repo

- Escaneos sin licencia explícita, aunque el sitio diga «public domain» en la portada.
- Obras publicadas en **1931 o después**.
- **Ediciones modernas** de obras antiguas (Taschen 2017 y similares).
- Personajes con marca viva usados como signo distintivo (**Popeye**).
- Escaneos de **Digital Comic Museum**, **Comic Book Plus** o **Comic Strip Library** sin
  términos verificados y licencia por ítem.
- Versiones coloreadas, reescaladas o restauradas con criterio moderno (pueden añadir
  material protegible).
- Capturas con datos reales de una instalación (rutas, biblioteca, nombres de usuario).

---

## 7. Demos y capturas

**Objetivo:** que nadie confunda la biblioteca de ejemplo con datos reales.

| Elemento | Regla |
|---|---|
| Carpeta | `demo/zascarr-biblioteca-ejemplo/` (sin acentos ni em dashes) |
| Título de serie | `Yellow Kid (1895) (ejemplo)` — el sufijo va en el título, no solo en la carpeta |
| `ComicInfo.xml` | `Notes`: «Datos de ejemplo de ZascArr. Páginas sintéticas inspiradas en obras de dominio público. No son escaneos.» |
| `LEEME.md` en la raíz | Qué es, qué no es, fecha, commit del generador, licencia CC0-1.0 de las páginas |
| Capturas | Pie obligatorio: «Biblioteca de ejemplo con páginas sintéticas inspiradas en obras de dominio público (1895–1913). No son escaneos ni ediciones originales. Generado el 2026-11-16 (<commit>).» |
| Atribución | «Inspirado en *The Yellow Kid* (R. F. Outcault, 1895), *Little Nemo in Slumberland* (Winsor McCay, 1905) y *Krazy Kat* (George Herriman, 1913), obras en dominio público.» |
| Licencia del material | Páginas sintéticas: **CC0-1.0** (para poder reutilizar capturas sin fricción). Generador: GPL-3.0, como el resto del repo. |
| Marca | Sin logos, sin «official», sin sugerir patrocinio de herederos ni de Hearst/King Features |
| Datos reales | Prohibido mezclar la biblioteca de ejemplo con una biblioteca real en la misma captura |

**Sobre la licencia del material:** el repo es GPL-3.0, pero eso no convierte automáticamente
las imágenes en GPL. Se declara CC0-1.0 para las páginas sintéticas y se deja escrito en
`LEEME.md`; si algún día se usa un scan, su licencia (PD/CC0) se declara aparte y **no** se
mezcla con la del código.

---

## 8. Checklist de verificación por ítem

Se rellena **antes** de que un fichero entre en el repo o en una demo publicada. Si falta
un campo, el ítem no entra.

| # | Campo | Cómo se obtiene | Criterio PASS |
|---|---|---|---|
| 1 | Obra y personaje | Ficha de la fuente + bibliografía | Coincide con la obra que se quiere probar |
| 2 | Primera publicación | Pie de la página, cabecera del diario, ficha de la fuente | Fecha acreditada y **≤ 1930** |
| 3 | País de primera publicación | Fuente | EE. UU. (para este corpus) |
| 4 | Autor | Firma en la página / ficha | Coincide con la atribución |
| 5 | Fallecimiento del autor | Wikidata + fuente biográfica | **≤ 1945** (regla española de 80 años) |
| 6 | Fuente | URL del ítem | Es una de las fuentes de la §5 |
| 7 | Licencia declarada | `licenseurl`/plantilla de Commons/ficha | PD Mark, CC0 o etiqueta PD-old; **no** «desconocida» |
| 8 | Edición | Ficha | Es la página original, no una edición moderna |
| 9 | Resolución y formato | API / fichero | ≥ 1000 px de lado largo; JPEG/PNG |
| 10 | Fecha de descarga | Reloj | ISO-8601, misma sesión que el hash |
| 11 | SHA-256 | `sha256sum` | Coincide con el fichero que se sube |
| 12 | Revisor | Persona | Nombre y fecha en `ATRIBUCION.md` |
| 13 | Uso | Este doc | Test/documentación, nunca marca del producto |
| 14 | Decisión | — | **PASS / FAIL / NOT RUN** con motivo |

---

## 9. Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| **Marca** (Popeye, posiblemente Krazy Kat) | Media | Alto (cese y desistimiento, retirada de capturas) | Excluir Popeye; comprobar TSDR/EUIPO antes de usar nombres en superficie pública; uso descriptivo y disclaimer |
| **Jurisdicción**: DP en EE. UU. pero no en España | Alta si se elige mal | Alto | Solo obras DP en ambos; tabla §3.2; excluir Katzenjammer y Mutt and Jeff |
| **Scan de tercero** con derechos propios (mera fotografía, 25 años en España) | Media | Medio | Preferir sintéticos; si hay scan, licencia explícita (Commons/PD Mark), no subida particular |
| **Edición moderna** escaneada (Taschen 2017) | Media | Alto | Verificar edición, no solo la fecha de la obra; en España la edición puede tener 25 años propios (arts. 129.2 y 130.2 TRLPI) |
| **Metadatos falsos o incoherentes** del uploader | Media | Medio | Contraste con la página/fecha; no fiarse de `licenseurl` aislado |
| **`editio princeps`** de obra inédita (arts. 129.1 y 130.1 TRLPI, 25 años) | Baja | Medio | No usar páginas inéditas; solo publicadas |
| **Confusión demo/datos reales** | Media | Medio | Sufijo `(ejemplo)`, `LEEME.txt`, nota en ComicInfo, pie en capturas |
| **Licencia del repo vs. licencia de la imagen** | Baja | Medio | Declarar CC0-1.0 para las páginas; no asumir GPL para imágenes |
| **Cambio de año de dominio público** | Cierta cada 1 de enero | Bajo | Revisar este doc en enero; la regla `≤1930` pasa a `≤1931` en 2027 |
| **Fuente caída o cambiada** | Media | Bajo | Guardar URL + fecha + hash; el fixture sintético no depende de la fuente |

---

## 10. Recomendación operativa

**Conjunto inicial (3 personajes, 2 páginas sintéticas cada uno):**

| Personaje | Obra | Autor (†) | Por qué entra | Estado |
|---|---|---|---|---|
| **Yellow Kid** | *Hogan's Alley*, 1895 | Outcault (1928) | DP en EE. UU. y España; icono visual fácil de dibujar en genérico | PASS |
| **Little Nemo** | *Little Nemo in Slumberland*, 1905 | McCay (1934) | DP en ambos; buena excusa para probar páginas verticales y color | PASS |
| **Krazy Kat** | *Krazy Kat*, 1913 | Herriman (1944) | DP en ambos desde 2025; tercera serie para el paquete | **Requiere revisión de marca** |

**Sustituto si Krazy Kat no pasa la revisión:** *Dream of the Rarebit Fiend* (1904,
McCay), DP en ambos y sin personaje con marca conocida.

**Entregables concretos:**

- 3 series × 2 páginas PNG (≤ 60 KB cada una) = 6 imágenes.
- 3 `.cbz` (2 páginas + `ComicInfo.xml`) ≈ 150 KB cada uno.
- 1 `.zip` con los 3 `.cbz` para probar el importador de paquetes.
- 1 `LEEME.md` + 1 `ATRIBUCION.md` (aunque las páginas sean CC0, la atribución de la
  inspiración se mantiene por cortesía y para el registro).
- 1 script generador y 1 test que lo ejercite.
- 3–5 capturas con pie y sin datos reales.

**Regla dura:** **no se descarga contenido con copyright vigente**. Si una fuente no
permite verificar la licencia en el momento, se enlaza y se sigue; no se copia «por si
acaso».

**Coste:** ~1 PR de código (script + fixtures + tests) y ~1 PR de documentación/demos.
Ninguno toca el modelo de datos ni la UI.

---

## 11. Plan de siguiente paso

| Paso | Quién | Salida | Puerta |
|---|---|---|---|
| 1. Revisión de este doc y de D1–D6 | PO + revisión legal | Comentarios en el PR | Sin decisión, no se implementa |
| 2. Comprobar marca de Krazy Kat (TSDR/EUIPO) y, si falla, cambiar a Rarebit Fiend | SCOUT/legal | Nota de 1 página con nº de registro y estado | D3 cerrada |
| 3. Implementar `scripts/generar_fixtures_dp.py` + fixtures + tests | Dev | PR pequeño, sin binarios pesados | Tests verdes y `git status` limpio |
| 4. `LEEME.md` y `ATRIBUCION.md` en la carpeta de fixtures | Dev + SCOUT/legal | Textos revisados | Checklist §8 completo |
| 5. Biblioteca de ejemplo y capturas | Dev + QA | 3–5 capturas con pie | Sin datos reales y con etiqueta `(ejemplo)` |
| 6. Revisión anual | SCOUT/legal | Actualización de §2 y §3 | Enero de 2027: la regla pasa a `≤1931` |

**Criterio de cierre:** los fixtures se generan sin red, los tests pasan, las capturas
llevan pie y atribución, y ninguna imagen del repo tiene una licencia dudosa.

---

## 12. Fuentes consultadas (fecha de acceso: 2026-11-16)

| Fuente | URL | Qué se usó | Resultado |
|---|---|---|---|
| Duke CSPD, Public Domain Day 2026 | https://cspd.law.duke.edu/publicdomainday/2026 | Obras de 1930 → DP el 01-01-2026; personajes vs. marca | PASS |
| Duke CSPD, Public Domain Day 2025 | https://cspd.law.duke.edu/publicdomainday/2025 | Popeye 1929; Hearst Holdings y la marca «Popeye»; uso nominativo | PASS |
| Cornell, Copyright Term and the Public Domain | https://guides.library.cornell.edu/copyright/publicdomain | «Before 1931 → public domain» (actualizado 01-01-2026) | PASS |
| U.S. Code §305 | https://www.law.cornell.edu/uscode/text/17/305 | Los plazos corren hasta el 31 de diciembre | PASS |
| U.S. Copyright Office, FAQ de duración | https://www.copyright.gov/help/faq/faq-duration.html | Vida + 70; para las publicadas antes de 1978 remite al capítulo 3 | PASS |
| TRLPI (BOE consolidado) | https://www.boe.es/buscar/act.php?id=BOE-A-1996-8930 | Art. 26 (70 años), art. 30 (cómputo), DT4 (80 años) | PASS |
| BOE, API de legislación consolidada | https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/BOE-A-1996-8930/texto | Texto literal de los artículos | PASS |
| «Derecho de autor en España» (Wikipedia) | https://es.wikipedia.org/wiki/Derecho_de_autor_en_Espa%C3%B1a | Ley de 1879, art. 6: 80 años (fuente secundaria) | PASS con reserva |
| Wikimedia Commons, Licensing | https://commons.wikimedia.org/wiki/Commons:Licensing | Solo licencias libres; DP en EE. UU. y en origen | PASS |
| Commons, `Template:PD-US-expired` | https://commons.wikimedia.org/wiki/Template:PD-US-expired | «Published before January 1, 1931»; aviso de país de origen | PASS |
| Commons, API `imageinfo` | `https://commons.wikimedia.org/w/api.php?action=query&prop=imageinfo&iiprop=extmetadata` | Licencia y resolución por fichero | PASS |
| Internet Archive, Rights | https://help.archive.org/help/rights/ | IA no garantiza el estado de copyright; uso a riesgo del usuario | PASS |
| Internet Archive, API de metadatos | `https://archive.org/metadata/<id>` | `licenseurl`, `collection`, formatos y tamaños | PASS |
| Internet Archive, Terms of Use | https://archive.org/about/terms.php | — | **FAIL** (respuesta vacía; se usó la página de Rights) |
| Library of Congress, Chronicling America | https://www.loc.gov/collections/chronicling-america/about-this-collection/rights-and-access/ | — | **NOT RUN** (403 Cloudflare) |
| Comic Book Plus | https://comicbookplus.com/ | Listado de cómics; sin licencia por ítem | PASS (listado) / **NOT RUN** (términos 403/406) |
| Digital Comic Museum | https://digitalcomicmuseum.com/ | — | **NOT RUN** (403 Cloudflare) |
| Comic Strip Library | https://comicstriplibrary.org/ | Solo el título de la SPA; sin términos | **NOT RUN** |
| Wikidata | `https://www.wikidata.org/wiki/Special:EntityData/<Q>.json` | Fechas de nacimiento/muerte y de inicio de las tiras | PASS (secundaria) |
| Wikipedia (EN) | https://en.wikipedia.org/wiki/The_Yellow_Kid · https://en.wikipedia.org/wiki/Krazy_Kat · https://en.wikipedia.org/wiki/Little_Nemo | Fechas de primera publicación y autores | PASS (secundaria) |
| USPTO, What is a trademark | https://www.uspto.gov/trademarks/basics/what-trademark | Distinción marca/copyright | **FAIL** (la definición no se pudo extraer; el dato se toma de Duke) / registro concreto **NOT RUN** |

---

## 13. Anexo: comprobaciones reproducibles

```bash
# 1) Estado de un ítem de Internet Archive (licencia, colección, formatos)
curl -sS "https://archive.org/metadata/<IDENTIFIER>" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); m=d['metadata']; \
print({k:m.get(k) for k in ('title','date','licenseurl','rights','collection','possible-copyright-status')}); \
[print(f['format'], f['name'], f.get('size')) for f in d.get('files',[]) if f.get('format') in ('Text PDF','JPEG','Single Page Processed JP2 ZIP','ZIP')]"

# 2) Licencia y tamaño de un fichero de Commons
curl -sS --get "https://commons.wikimedia.org/w/api.php" \
  --data-urlencode "action=query" \
  --data-urlencode "titles=File:<NOMBRE>" \
  --data-urlencode "prop=imageinfo" \
  --data-urlencode "iiprop=url|size|mime|extmetadata" \
  --data-urlencode "format=json"

# 3) Plantillas de licencia del wikitexto (lo que de verdad manda)
curl -sS --get "https://commons.wikimedia.org/w/api.php" \
  --data-urlencode "action=parse" \
  --data-urlencode "page=File:<NOMBRE>" \
  --data-urlencode "prop=wikitext" \
  --data-urlencode "format=json"

# 4) Hash del fichero que se va a subir
sha256sum <FICHERO>

# 5) Fecha de descarga + commit del generador (para LEEME y ATRIBUCION)
date -Iseconds
git -C . rev-parse --short HEAD
```

---

## 14. Resumen de 10 líneas

1. En EE. UU. las obras publicadas **≤1930** son de dominio público desde el **01-01-2026**
   (regla operativa de Cornell; el plazo de 95 años de la cohorte de 1930 vence el 31-12-2025,
   y los plazos corren hasta fin de año, 17 U.S.C. §305); todas las del encargo lo cumplen.
2. En España el plazo es **vida + 70** (art. 26 TRLPI) y **80** para autores fallecidos
   antes del 7-12-1987 (DT4): Outcault, McCay y Herriman están en DP; Dirks (2049) y
   Fisher (2035) **no**.
3. Por eso **Katzenjammer Kids** y **Mutt and Jeff** quedan fuera aunque en EE. UU. sean
   libres; la regla del repo es «DP en ambos».
4. **Popeye** queda fuera: la versión de 1929 es DP, pero «Popeye» es marca de **Hearst
   Holdings** y las versiones posteriores siguen protegidas.
5. **Krazy Kat** entra condicionado a una comprobación de marca (King Features/Hearst);
   si falla, se sustituye por **Dream of the Rarebit Fiend** (1904).
6. **Ninguna fuente es un sello de calidad:** se verifica ítem a ítem (`licenseurl`,
   plantillas `PD-old`, `collection`, edición) y lo no verificado se marca **NOT RUN**.
7. **No se meten scans en el repo:** un scan de 1905 puede tener 25 años de protección
   como mera fotografía en España (art. 128 TRLPI), y las ediciones modernas (Taschen
   2017) añaden capa propia.
8. Plan: **3 personajes × 2 páginas sintéticas** con Pillow, 3 `.cbz`, 1 `.zip` de
   paquete, `ComicInfo.xml`, `LEEME.md` y `ATRIBUCION.md`; todo ≤ 500 KB y sin red.
9. La demo se etiqueta `(ejemplo)` en el título, con nota en ComicInfo y pie de captura;
   las páginas sintéticas se declaran **CC0-1.0** y el generador GPL-3.0.
10. Siguiente paso: revisión del PO/legal de D1–D6, comprobación de marca de Krazy Kat y
    un PR pequeño de generador + fixtures + tests; revisión anual en enero.
